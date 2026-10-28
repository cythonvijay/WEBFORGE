"""Safe provider diagnostics. Reports configuration *state* (booleans and names), never the credential or any part of it.

    python -m app.provider_check                 # configuration only (no network)
    python -m app.provider_check --live          # + one minimal real request through the configured provider
    python -m app.provider_check --live --models # + on a model error, list models this key can use (names only)
Exit codes: 0 ok, 1 configuration missing, 2 live request failed or blocked.
"""
import asyncio
import os
import sys
import time

import httpx
from pydantic import BaseModel

RECOMMENDED = ("gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.5-flash")  # per Google's model docs, 2026-10


class _Ping(BaseModel):
    ok: bool
    word: str


def config_report() -> dict:
    from .ai import PROVIDERS
    from .config import _ENV_FILES, settings

    return {
        "provider": settings.ai_provider,
        "provider_known": settings.ai_provider in PROVIDERS,
        "provider_implemented": settings.ai_provider == "google",
        "api_key_configured": bool(settings.google_ai_api_key),
        "model": settings.google_model,
        "model_configured": bool(settings.google_model),
        "env_files_present": [str(p) for p in _ENV_FILES if p.exists()],
    }


async def live_request() -> dict:
    """One minimal structured request through the real configured provider. No retries."""
    from . import ai

    t0 = time.monotonic()
    try:
        out = await ai.get_provider().generate_structured('Return JSON with "ok": true and "word": "pong".', _Ping)
    except ai.ProviderNotConfigured:
        return {"status": "NOT CONFIGURED", "category": "not_configured"}
    except ai.ProviderError as e:
        return {"status": "BLOCKED" if e.category == "network" else "FAIL", "category": e.category, "message": ai.user_message(e),
                "seconds": round(time.monotonic() - t0, 2)}
    return {"status": "PASS", "validated": out.ok is True, "seconds": round(time.monotonic() - t0, 2)}


async def list_models(transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Names of models the key may call with generateContent. Only model names are returned."""
    from . import ai
    from .config import settings

    if not settings.google_ai_api_key:
        return {"status": "NOT CONFIGURED"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.google_timeout_seconds, connect=10), transport=transport) as c:
            r = await c.get(f"{ai.GOOGLE_API_BASE}/models", params={"pageSize": 200}, headers={"x-goog-api-key": settings.google_ai_api_key})
    except httpx.TimeoutException:
        return {"status": "FAIL", "category": "timeout"}
    except httpx.HTTPError:
        return {"status": "BLOCKED", "category": "network"}
    try:
        data = r.json()
    except ValueError:
        data = None
    if r.status_code != 200:
        return {"status": "FAIL", "category": ai.classify_http_error(r.status_code, data)}
    names = sorted(m["name"].removeprefix("models/") for m in (data or {}).get("models", [])
                   if isinstance(m, dict) and "generateContent" in m.get("supportedGenerationMethods", []) and str(m.get("name", "")).startswith("models/gemini"))
    return {"status": "PASS", "usable_recommended": [n for n in RECOMMENDED if n in names], "other_gemini_models": [n for n in names if n not in RECOMMENDED][:20]}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    os.environ.setdefault("DATABASE_URL", "sqlite://")  # diagnostics never touch the database
    rep = config_report()
    print("Configuration")
    for k, v in rep.items():
        print(f"  {k}: {v}")
    if not (rep["provider_known"] and rep["provider_implemented"] and rep["api_key_configured"] and rep["model_configured"]):
        why = [m for ok, m in ((rep["provider_implemented"], "AI_PROVIDER must be 'google' (the only implemented provider)"),
                               (rep["api_key_configured"], "GOOGLE_AI_API_KEY is not configured (set it in .env or the environment)"),
                               (rep["model_configured"], "GOOGLE_MODEL is empty")) if not ok]
        print("Configuration incomplete:", "; ".join(why))
        return 1
    if "--live" not in argv:
        return 0
    res = asyncio.run(live_request())
    print("\nLive request:", {k: v for k, v in res.items()})
    if res["status"] == "PASS":
        return 0
    if res.get("category") == "model_not_found" or "--models" in argv:
        print("\nModels this key can use:", asyncio.run(list_models()))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
