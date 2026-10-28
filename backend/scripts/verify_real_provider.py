"""End-to-end verification of the REAL Google AI provider through WebForge: config, a live request, AI intake, and the
progressive-discovery workflow (questions, answer, Brain update + provenance, revisions, next round, review).

    cd backend && python scripts/verify_real_provider.py [--report report.json]

Requires GOOGLE_AI_API_KEY (and optionally GOOGLE_MODEL) in the environment or .env. Runs against a TEMPORARY SQLite database,
so your data is untouched. The only data that leaves your machine is the test idea and the prompts sent to Google. The key is
never printed. Exit: 0 all checks passed, 1 not configured, 2 a check failed or Google was unreachable.
"""
import argparse
import asyncio
import json
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1]
IDEA = "I want to build a website where people can find local photographers, compare their packages and prices, and book a session online."
PASSING = {"PASS", "REVIEW"}


class Report:
    def __init__(self, say=print):
        self.rows, self.say, self.notes = [], say, []

    def add(self, check: str, status: str, detail: str = ""):
        self.rows.append({"check": check, "status": status, "detail": detail})
        self.say(f"  [{status:^14}] {check}" + (f" - {detail}" if detail else ""))

    def skip_rest(self, checks: list[str], why: str):
        for c in checks:
            self.add(c, "SKIPPED", why)


ALL_CHECKS = ["Real AI intake", "Intake: Brain update + revision", "Real discovery question generation", "Answer persistence",
              "Brain section update + provenance", "Append-only revision", "Next round without repeats", "Review reflects stored data"]


def _answer_for(q: dict):
    t = q["qtype"]
    return {"free_text": "Independent photographers and small studios in my city.", "single_choice": (q["options"] or [{}])[0].get("id"),
            "multiple_choice": [o["id"] for o in q["options"][:1]], "confirmation": True}[t]


def run_checks(client, say=print) -> Report:
    """`client` is a Starlette TestClient for the WebForge app; the provider is whatever `ai.get_provider()` returns."""
    from app import discovery as dz
    from app.provider_check import config_report, live_request

    rep = Report(say)
    cfg = config_report()
    ok_cfg = cfg["provider_implemented"] and cfg["api_key_configured"] and cfg["model_configured"]
    rep.add("Google key configuration", "PASS" if ok_cfg else "NOT CONFIGURED", f"provider={cfg['provider']} model={cfg['model']} key_configured={cfg['api_key_configured']}")
    if not ok_cfg:
        rep.add("Real Google request", "SKIPPED", "no key configured")
        rep.skip_rest(["Structured response validation"] + ALL_CHECKS, "no key configured")
        return rep
    live = asyncio.run(live_request())
    rep.add("Real Google request", live["status"], live.get("message") or f"{live.get('seconds')}s")
    if live["status"] == "PASS":
        rep.add("Structured response validation", "PASS" if live.get("validated") else "FAIL", "minimal schema validated by Pydantic")
    else:
        rep.add("Structured response validation", "SKIPPED", "no response to validate")
    if live["status"] != "PASS":
        rep.skip_rest(ALL_CHECKS, f"live request {live['status']} ({live.get('category')})")
        return rep

    pw = secrets.token_urlsafe(12)
    assert client.post("/api/auth/register", json={"email": f"verify-{secrets.token_hex(4)}@example.com", "password": pw}).status_code == 201
    pid = client.post("/api/projects", json={"name": "Provider verification"}).json()["id"]
    D = lambda p="": f"/api/projects/{pid}/discovery{p}"  # noqa: E731
    revs = lambda: client.get(f"/api/projects/{pid}/revisions").json()  # noqa: E731
    brain = lambda: client.get(f"/api/projects/{pid}/brain").json()  # noqa: E731

    # ---- intake ----
    r = client.post(f"/api/projects/{pid}/intake", json={"idea": IDEA})
    if r.status_code != 200:
        rep.add("Real AI intake", "FAIL", f"HTTP {r.status_code}: {r.json().get('detail')}")
        rep.skip_rest(ALL_CHECKS[1:], "intake failed")
        return rep
    res = r.json()["result"]
    rep.add("Real AI intake", "PASS" if res["product_name"] and res["problem"] and res["target_users"] else "FAIL",
            f"product='{res['product_name'][:40]}' type='{res['product_type'][:30]}' users={len(res['target_users'])} features={len(res['features'])}")
    b, rv = brain(), revs()
    good = (b["brain"]["idea"]["raw"] == IDEA and b["brain"]["idea"]["product_name"] == res["product_name"] and rv[0]["change_type"] == "ai_intake"
            and set(rv[0]["patch"]) == {"idea", "target_users", "goals"} and [x["version"] for x in rv] == list(range(rv[0]["version"], 0, -1)))
    rep.add("Intake: Brain update + revision", "PASS" if good else "FAIL", f"brain v{b['version']}, latest change_type={rv[0]['change_type']}")

    # ---- discovery round 1 ----
    r = client.post(D())
    if r.status_code != 200 or r.json()["status"] != "awaiting_answers":
        rep.add("Real discovery question generation", "FAIL", f"HTTP {r.status_code} {r.json().get('detail') or r.json().get('status')}")
        rep.skip_rest(ALL_CHECKS[3:], "question generation failed")
        return rep
    st = r.json()
    qs = st["questions"]
    words = {w for w in re.findall(r"[a-z]{5,}", IDEA.lower())}
    relevant = sum(any(w in (q["prompt"] + q["rationale"]).lower() for w in words) for q in qs)
    shape_ok = 1 <= len(qs) <= 5 and all(q["prompt"] and q["rationale"] and q["target"] and q["status"] == "open" for q in qs)
    rep.add("Real discovery question generation", "PASS" if shape_ok and relevant else ("REVIEW" if shape_ok else "FAIL"),
            f"{len(qs)} questions, {relevant} mention terms from the idea (read them below; relevance is a human judgement)")
    for q in qs:
        say(f"        - ({q['target']}, {q['qtype']}{', required' if q['required'] else ''}) {q['prompt'][:110]}")
    # ---- answer one ----
    before = revs()
    q0 = qs[0]
    val = _answer_for(q0)
    a = client.post(D("/answers"), json={"answers": [{"question_id": q0["id"], "value": val}]})
    st2 = a.json() if a.status_code == 200 else {}
    saved = next((q for q in st2.get("questions", []) if q["id"] == q0["id"]), None)
    rep.add("Answer persistence", "PASS" if saved and saved["status"] == "answered" and client.get(D()).json()["counts"]["answered"] == 1 else "FAIL", f"HTTP {a.status_code}")
    b2, after = brain(), revs()
    fact = next((f for f in b2["brain"]["discovery"]["confirmed"] if f["question_id"] == q0["id"]), None)
    qobj = SimpleNamespace(**q0)
    shown = dz.display_answer(qobj, dz.validate_answer(qobj, val)[0])
    t = dz.TARGETS[q0["target"]]
    section_ok = True
    if t["kind"] == "text":
        section_ok = b2["brain"][t["section"]][t["field"]] == shown
    elif t["kind"] == "value":
        section_ok = b2["brain"][t["section"]].get(t["field"]) == shown
    elif t["kind"] == "list":
        section_ok = bool(b2["brain"][t["section"]])
    rep.add("Brain section update + provenance", "PASS" if fact and fact["source"] == "user_confirmed" and fact["answer"] == shown and section_ok else "FAIL",
            f"target={q0['target']} -> {t['section'] or 'confirmed fact only'}; source={fact and fact['source']}")
    rep.add("Append-only revision", "PASS" if after[0]["change_type"] == "discovery_answer" and after[0]["version"] == before[0]["version"] + 1 and after[1:] == before else "FAIL",
            f"v{before[0]['version']} -> v{after[0]['version']}, earlier revisions unchanged")
    # ---- next round ----
    for q in qs[1:]:
        client.post(D(f"/questions/{q['id']}/{'defer' if q['required'] else 'skip'}"))
    n = client.post(D("/next-round"))
    if n.status_code != 200:
        rep.add("Next round without repeats", "FAIL", f"HTTP {n.status_code}: {n.json().get('detail')}")
        rep.skip_rest(ALL_CHECKS[7:], "next round failed")
        return rep
    st3 = n.json()
    old = {q["id"] for q in qs}
    new = [q for q in st3["questions"] if q["id"] not in old]
    old_prompts = {dz.fingerprint(q["prompt"]) for q in qs}
    old_targets = {q["target"] for q in qs if q["target"] != "other"}
    repeats = [q for q in new if dz.fingerprint(q["prompt"]) in old_prompts or (q["target"] != "other" and q["target"] in old_targets)]
    rep.add("Next round without repeats", "PASS" if not repeats and (new or st3["status"] == "ready_for_review") else "FAIL",
            f"round {st3['round']}, {len(new)} new question(s), status={st3['status']}")
    for q in new:
        say(f"        - ({q['target']}, {q['qtype']}) {q['prompt'][:110]}")
    # ---- review ----
    rv2 = client.post(D("/review"))
    summ = rv2.json().get("summary") if rv2.status_code == 200 else None
    stored = brain()["brain"]["discovery"]["confirmed"]
    same = summ is not None and [(f["question_id"], f["answer"]) for f in summ["confirmed"]] == [(f["question_id"], f["answer"]) for f in stored]
    rep.add("Review reflects stored data", "PASS" if same and summ["proposed"] is not None else "FAIL", f"{len(stored)} confirmed fact(s) match the Brain")
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", help="write the results table as JSON (contains no credentials)")
    args = ap.parse_args(argv)
    tmp = tempfile.mkdtemp(prefix="webforge-verify-")
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/verify.db"  # temporary database; overrides any .env value
    os.environ["JWT_SECRET"] = secrets.token_urlsafe(32)
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient

    command.upgrade(Config("alembic.ini"), "head")
    from app.main import app

    print("WebForge real-provider verification (temporary database; key never printed)\n")
    with TestClient(app) as client:
        rep = run_checks(client)
    bad = [r for r in rep.rows if r["status"] not in PASSING | {"SKIPPED"}]
    print("\nResult:", "ALL CHECKS PASSED" if not bad and not any(r["status"] == "SKIPPED" for r in rep.rows) else "INCOMPLETE OR FAILED")
    if args.report:
        Path(args.report).write_text(json.dumps(rep.rows, indent=2))
    if any(r["status"] == "NOT CONFIGURED" for r in rep.rows):
        return 1
    return 0 if not bad and not any(r["status"] == "SKIPPED" for r in rep.rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
