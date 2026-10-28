"""The real GoogleAIProvider against a fake Google (see fake_google.py): request shape, parsing, categorized errors, secrecy."""
import importlib.util
import json
import logging
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel
from fastapi.testclient import TestClient

from app import ai, provider_check
from app.config import Settings, settings
from app.main import app
from fake_google import FakeGoogle, envelope, error_body

KEY = "test-key-NOT-REAL-9f8e7d6c5b4a"
MODEL = "gemini-test-model"
ROOT = Path(__file__).resolve().parents[2]


class Ping(BaseModel):
    ok: bool
    word: str


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setattr(settings, "google_ai_api_key", KEY)
    monkeypatch.setattr(settings, "google_model", MODEL)
    monkeypatch.setattr(settings, "ai_provider", "google")
    g = FakeGoogle(KEY, MODEL)
    monkeypatch.setattr(ai, "get_provider", lambda: ai.GoogleAIProvider(transport=g.transport))
    return g


def run(coro):
    import asyncio
    return asyncio.run(coro)


def provider(g):
    return ai.GoogleAIProvider(transport=g.transport)


# ---------- request shape ----------
def test_request_matches_the_documented_generate_content_call(google):
    out = run(provider(google).generate("hello"))
    assert out == "ok"  # the fake's generic answer; what matters below is the request that was sent
    req = google.requests[0]
    assert req.method == "POST" and req.url.host == "generativelanguage.googleapis.com"
    assert req.url.path == f"/v1beta/models/{MODEL}:generateContent"
    assert req.headers["x-goog-api-key"] == KEY and req.headers["content-type"] == "application/json"
    body = json.loads(req.content)
    assert body["contents"][0]["parts"][0]["text"] == "hello" and body["generationConfig"]["responseMimeType"] == "application/json"
    assert KEY not in str(req.url) and KEY not in req.content.decode()  # the key only travels in the header


def test_structured_output_is_validated_by_pydantic(google):
    assert run(provider(google).generate_structured('Return JSON with "ok": true and "word": "pong".', Ping)) == Ping(ok=True, word="pong")
    google.override = lambda r: httpx.Response(200, json=envelope('{"ok": "not-a-bool"}'))
    with pytest.raises(ai.ProviderError) as e:
        run(provider(google).generate_structured("x", Ping))
    assert e.value.category == "malformed" and "error(s)" in str(e.value) and "not-a-bool" not in str(e.value)  # never echoes model output


# ---------- error categories (statuses from Google's troubleshooting page) ----------
@pytest.mark.parametrize("code,status,message,category", [
    (400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.", "auth"),
    (400, "INVALID_ARGUMENT", "Request contains an invalid argument.", "bad_request"),
    (400, "FAILED_PRECONDITION", "Gemini API free tier is not available in your country.", "precondition"),
    (403, "PERMISSION_DENIED", "Your API key doesn't have the required permissions.", "auth"),
    (404, "NOT_FOUND", "models/gemini-2.5-flash is no longer available.", "model_not_found"),
    (429, "RESOURCE_EXHAUSTED", "You've exceeded the rate limit.", "quota"),
    (500, "INTERNAL", "An unexpected error occurred.", "upstream"),
    (503, "UNAVAILABLE", "The service may be temporarily overloaded.", "upstream"),
    (504, "DEADLINE_EXCEEDED", "Deadline expired.", "timeout"),
])
def test_google_errors_are_categorized_without_echoing_the_response(google, code, status, message, category):
    google.override = lambda r: httpx.Response(code, json=error_body(code, status, message))
    with pytest.raises(ai.ProviderError) as e:
        run(provider(google).generate("x"))
    assert e.value.category == category
    assert message not in str(e.value) and KEY not in str(e.value) and KEY not in repr(e.value)
    assert len(google.requests) == 1  # no retries


def test_network_and_timeout_failures(google):
    def boom(exc):
        def h(request): raise exc
        return h
    google.override = boom(httpx.ConnectError("dns", request=None))
    with pytest.raises(ai.ProviderError) as e:
        run(provider(google).generate("x"))
    assert e.value.category == "network"
    google.override = boom(httpx.ReadTimeout("slow", request=None))
    with pytest.raises(ai.ProviderError) as e:
        run(provider(google).generate("x"))
    assert e.value.category == "timeout" and len(google.requests) == 2


@pytest.mark.parametrize("resp,category", [
    (httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}), "blocked"),
    (httpx.Response(200, json={"candidates": []}), "malformed"),
    (httpx.Response(200, json={"candidates": [{"finishReason": "SAFETY"}]}), "blocked"),
    (httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": []}}]}), "malformed"),
    (httpx.Response(200, text="<html>not json</html>"), "malformed"),
    (httpx.Response(200, json=["unexpected"]), "malformed"),
])
def test_unusable_200_responses(google, resp, category):
    google.override = lambda r: resp
    with pytest.raises(ai.ProviderError) as e:
        run(provider(google).generate("x"))
    assert e.value.category == category


def test_multi_part_answers_are_joined_and_thought_parts_ignored(google):
    parts = [{"text": "internal reasoning", "thought": True}, {"text": '{"ok": tr'}, {"text": 'ue, "word": "pong"}'}]
    google.override = lambda r: httpx.Response(200, json={"candidates": [{"content": {"parts": parts}, "finishReason": "STOP"}]})
    assert run(provider(google).generate_structured("x", Ping)) == Ping(ok=True, word="pong")


def test_truncated_json_is_rejected_not_repaired(google):
    google.override = lambda r: httpx.Response(200, json=envelope('{"ok": true, "wo', finish="MAX_TOKENS"))
    with pytest.raises(ai.ProviderError) as e:
        run(provider(google).generate_structured("x", Ping))
    assert e.value.category == "malformed"


# ---------- configuration ----------
def test_missing_key_and_bad_model_never_reach_the_network(google, monkeypatch):
    monkeypatch.setattr(settings, "google_ai_api_key", "")
    with pytest.raises(ai.ProviderNotConfigured):
        run(provider(google).generate("x"))
    monkeypatch.setattr(settings, "google_ai_api_key", KEY)
    for bad in ("", "../admin", "a/b", "x y", "m?key=1"):
        monkeypatch.setattr(settings, "google_model", bad)
        with pytest.raises(ai.ProviderNotConfigured):
            run(provider(google).generate("x"))
    assert google.requests == []


def test_dotenv_is_loaded_ignores_unrelated_keys_and_real_env_wins(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text(f"GOOGLE_AI_API_KEY={KEY}\nGOOGLE_MODEL=gemini-3.5-flash-lite\nPOSTGRES_PASSWORD=whatever\nVITE_X=1\n")
    monkeypatch.delenv("GOOGLE_AI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_MODEL", raising=False)
    s = Settings(_env_file=f, database_url="sqlite://")
    assert s.google_ai_api_key == KEY and s.google_model == "gemini-3.5-flash-lite"  # extra keys did not raise
    monkeypatch.setenv("GOOGLE_AI_API_KEY", "from-real-environment")
    assert Settings(_env_file=f, database_url="sqlite://").google_ai_api_key == "from-real-environment"


def test_default_model_is_not_the_one_google_closed_to_new_keys():
    assert Settings(_env_file=None, database_url="sqlite://").google_model in ("gemini-3.8-flash", "gemini-3.5-flash-lite")


def test_config_report_and_cli_never_reveal_the_key(google, capsys):
    rep = provider_check.config_report()
    assert rep["api_key_configured"] is True and KEY not in json.dumps(rep) and "9f8e7d6c" not in json.dumps(rep)
    assert provider_check.main([]) == 0
    out = capsys.readouterr().out
    assert "api_key_configured: True" in out and KEY not in out and "9f8e" not in out


def test_cli_stops_before_any_request_when_unconfigured(google, monkeypatch, capsys):
    monkeypatch.setattr(settings, "google_ai_api_key", "")
    assert provider_check.main(["--live"]) == 1
    assert google.requests == [] and "GOOGLE_AI_API_KEY is not configured" in capsys.readouterr().out


def test_live_request_reports_pass_blocked_and_failures(google):
    assert run(provider_check.live_request())["status"] == "PASS"
    google.override = lambda r: (_ for _ in ()).throw(httpx.ConnectError("x", request=None))
    assert run(provider_check.live_request()) | {} == run(provider_check.live_request()) | {} and run(provider_check.live_request())["status"] == "BLOCKED"
    google.override = lambda r: httpx.Response(404, json=error_body(404, "NOT_FOUND"))
    res = run(provider_check.live_request())
    assert res["status"] == "FAIL" and res["category"] == "model_not_found"


def test_model_listing_returns_only_usable_recommended_names(google, monkeypatch):
    models = {"models": [{"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
                         {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                         {"name": "models/gemini-embedding", "supportedGenerationMethods": ["embedContent"]},
                         {"name": "models/text-bison", "supportedGenerationMethods": ["generateContent"]}]}
    t = httpx.MockTransport(lambda r: httpx.Response(200, json=models) if r.headers["x-goog-api-key"] == KEY else httpx.Response(403, json=error_body(403, "PERMISSION_DENIED")))
    res = run(provider_check.list_models(transport=t))
    assert res == {"status": "PASS", "usable_recommended": ["gemini-3.8-flash"], "other_gemini_models": ["gemini-2.5-flash"]}


# ---------- logging / API surface ----------
def test_nothing_secret_is_logged_or_returned(google, caplog):
    caplog.set_level(logging.DEBUG)
    google.override = lambda r: httpx.Response(403, json=error_body(403, "PERMISSION_DENIED", f"bad key {KEY}"))
    with pytest.raises(ai.ProviderError):
        run(provider(google).generate("a private idea about X"))
    assert KEY not in caplog.text and "private idea" not in caplog.text and "category=auth" in caplog.text


@pytest.fixture
def authed(client):
    assert client.post("/api/auth/register", json={"email": "p@example.com", "password": "password123"}).status_code == 201
    return client


@pytest.mark.parametrize("category", sorted(ai.USER_MESSAGES))
def test_api_errors_carry_only_the_safe_category_message(authed, monkeypatch, category):
    class Boom(ai.AIProvider):
        async def generate(self, prompt): raise ai.ProviderError(f"detail {KEY}", category)
    monkeypatch.setattr(ai, "get_provider", lambda: Boom())
    pid = authed.post("/api/projects", json={"name": "P"}).json()["id"]
    r = authed.post(f"/api/projects/{pid}/intake", json={"idea": "A marketplace for photographers"})
    assert r.status_code == 502 and r.json()["detail"] == ai.USER_MESSAGES[category] and KEY not in r.text and "Traceback" not in r.text
    authed.put(f"/api/projects/{pid}/brain/idea", json={"value": {"raw": "idea text here", "product_name": "", "product_type": "", "problem": "", "features": [], "assumptions": [], "open_questions": []}})
    r = authed.post(f"/api/projects/{pid}/discovery")
    assert r.status_code == 502 and ai.USER_MESSAGES[category] in r.json()["detail"] and KEY not in r.text
    assert authed.get(f"/api/projects/{pid}/discovery").json()["last_error"] == ai.USER_MESSAGES[category]


# ---------- repository hygiene ----------
def test_env_examples_hold_placeholders_only_and_secrets_are_gitignored():
    for path in (ROOT / ".env.example", ROOT / "frontend" / ".env.example"):
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                if any(w in k for w in ("KEY", "SECRET")):
                    assert v.strip() == "", f"{path.name}: {k} must be empty"
                if "PASSWORD" in k:
                    assert v.strip() in ("", "change-me"), f"{path.name}: {k} must be a placeholder"
    ignore = (ROOT / ".gitignore").read_text().split()
    assert ".env" in ignore and ".env.*" in ignore and "!.env.example" in ignore


def test_the_key_is_unknown_to_the_frontend():
    for f in [p for p in (ROOT / "frontend" / "src").rglob("*.ts*") if "test" not in p.parts] + [ROOT / "frontend" / "vite.config.ts", ROOT / "frontend" / ".env.example"]:
        txt = f.read_text()
        assert "GOOGLE_AI" not in txt and "x-goog-api-key" not in txt and "generativelanguage" not in txt, f
    dist = ROOT / "frontend" / "dist"
    for f in (dist.rglob("*.js") if dist.exists() else []):
        assert "GOOGLE_AI" not in f.read_text() and "x-goog-api-key" not in f.read_text(), f


# ---------- the verification script, driven end to end by the fake Google ----------
def test_verification_script_runs_the_whole_workflow_through_the_real_provider_code(google, client):
    spec = importlib.util.spec_from_file_location("verify_real_provider", ROOT / "backend" / "scripts" / "verify_real_provider.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    lines = []
    with TestClient(app) as c:
        rep = mod.run_checks(c, say=lines.append)
    statuses = {r["check"]: r["status"] for r in rep.rows}
    assert all(s in ("PASS", "REVIEW") for s in statuses.values()), statuses
    assert len(statuses) == 11
    assert all(r.headers["x-goog-api-key"] == KEY for r in google.requests)
    assert len(google.requests) == 4  # ping, intake, discovery round 1, round 2
    assert KEY not in "\n".join(lines)


def test_verification_script_reports_blocked_google_without_pretending(google, client):
    spec = importlib.util.spec_from_file_location("verify_real_provider", ROOT / "backend" / "scripts" / "verify_real_provider.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    google.override = lambda r: (_ for _ in ()).throw(httpx.ConnectError("x", request=None))
    with TestClient(app) as c:
        rep = mod.run_checks(c, say=lambda s: None)
    st = {r["check"]: r["status"] for r in rep.rows}
    assert st["Real Google request"] == "BLOCKED" and st["Real AI intake"] == "SKIPPED" and st["Review reflects stored data"] == "SKIPPED"
    assert not any(s == "PASS" for k, s in st.items() if k not in ("Google key configuration",))
