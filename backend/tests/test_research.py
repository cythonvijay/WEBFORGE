"""Research (Phase 9). The provider is a scripted TEST DOUBLE: these tests prove WebForge's rules, not real research quality
and not the real Google provider. No web research exists in this phase, so no finding is ever machine-verified."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app import ai, research as rs
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import BrainRevision, ProjectStage, ResearchReport
from conftest import IS_PG

C = {"email": "a@example.com", "password": "password123"}
IDEA = "A marketplace where customers find local photographers and book them online."
OTHER_IDEA = "A secret idea about submarine logistics for harbor authorities."


class Scripted(ai.AIProvider):
    def __init__(self, *outputs):
        self.outputs, self.prompts = list(outputs), []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out if isinstance(out, str) else json.dumps(out)


def F(topic, statement, evidence="hypothesis", detail=None):
    return {"topic": topic, "statement": statement, "evidence": evidence, **({"detail": detail} if detail else {})}


def GEN(findings=None, **kw):
    return {"objectives": ["Understand how customers choose a photographer"], "research_questions": ["What makes customers trust a photographer online?", "How do customers compare packages today?"],
            "scope_in": ["Local portrait and event photography"], "scope_out": ["Stock photography"],
            "findings": findings if findings is not None else [F("user_needs", "Customers probably struggle to compare photographers on price and style."),
                                     F("risks", "Photographers may resist online booking fees.", "ai_suggestion"),
                                     F("competitors_alternatives", "Customers likely rely on social media and word of mouth today.", "unsupported")],
            "unresolved_questions": ["Which cities should launch first?"], **kw}


@pytest.fixture
def authed(client):
    assert client.post("/api/auth/register", json=C).status_code == 201
    return client


@pytest.fixture
def provide(monkeypatch):
    def _install(*outputs):
        prov = Scripted(*outputs)
        monkeypatch.setattr(ai, "get_provider", lambda: prov)
        return prov
    return _install


def project(c, idea=IDEA, users=("Shop owners",)):
    pid = c.post("/api/projects", json={"name": "Snapbook"}).json()["id"]
    if idea:
        c.put(f"/api/projects/{pid}/brain/idea", json={"value": {"raw": idea, "product_name": "Snapbook", "product_type": "marketplace", "problem": "Hard to compare photographers",
                                                               "features": ["Package comparison"], "assumptions": ["Customers book online"], "open_questions": ["Who pays the fee?"]}})
        c.put(f"/api/projects/{pid}/brain/target_users", json={"value": list(users)})
    return pid


def R(pid, path=""):
    return f"/api/projects/{pid}/research{path}"


def ready(c, provide, pid=None, gen=None):
    pid = pid or project(c)
    prov = provide(gen or GEN())
    r = c.post(R(pid, "/generate"), json={})
    assert r.status_code == 200, r.text
    return pid, prov, r.json()


def brain(c, pid):
    return c.get(f"/api/projects/{pid}/brain").json()


def stage(c, pid, name="research"):
    return next(s["status"] for s in c.get(f"/api/projects/{pid}/overview").json()["stages"] if s["stage"] == name)


def rows(model=ResearchReport):
    with SessionLocal() as db:
        return db.query(model).count()


def cur(state):
    return state["current"]


def edit(c, pid, version, kind, path, base, method="post", **body):
    return getattr(c, method)(R(pid, f"/reports/{version}{path}"), json={"base_hash": base, **body})


def submitted(c, provide):
    pid, _, st = ready(c, provide)
    r = c.post(R(pid, "/reports/1/submit"), json={"base_hash": cur(st)["content_hash"]})
    assert r.status_code == 200
    return pid, r.json()


def approve(c, pid, st, **kw):
    return c.post(R(pid, f"/reports/{cur(st)['version']}/approve"), json={"content_hash": cur(st)["content_hash"], "acknowledge_unverified": True, **kw})


# ---------- empty state / preconditions ----------
def test_empty_state_shows_a_real_brief_preview_and_creates_nothing(authed):
    pid = project(authed)
    st = authed.get(R(pid)).json()
    assert st["status"] == "not_started" and st["current"] is None and st["history"] == [] and st["next_step"]["key"] == "start_research"
    brief = st["brief_preview"]
    assert brief["product_summary"].startswith("Snapbook") and brief["problem"]["status"] == "ai_suggested"
    assert [u["status"] for u in brief["target_users"]] == ["ai_suggested"]  # intake-derived: not confirmed
    assert any("not been confirmed" in m for m in brief["missing_inputs"]) and any("Discovery is not completed" in m for m in brief["missing_inputs"])
    assert rows() == 0 and st["limitations"] and st["mode"] == "preliminary"


def test_generation_needs_an_idea_and_creates_nothing(authed, provide):
    pid = project(authed, idea=None)
    prov = provide()
    assert authed.post(R(pid, "/generate"), json={}).status_code == 409
    assert rows() == 0 and prov.prompts == []


# ---------- generation ----------
def test_generation_persists_a_validated_draft_without_touching_the_brain_or_lifecycle(authed, provide):
    pid = project(authed)
    b0, s0 = brain(authed, pid)["version"], stage(authed, pid)
    pid, prov, st = ready(authed, provide, pid)
    r = cur(st)
    assert st["status"] == "draft" and r["version"] == 1 and r["mode"] == "preliminary" and r["editable"] and r["created_via"] == "generated"
    c = r["content"]
    assert [f["id"] for f in c["findings"]] == ["f-1", "f-2", "f-3"] and {f["origin"] for f in c["findings"]} == {"ai"}
    assert {f["evidence"] for f in c["findings"]} <= {"hypothesis", "ai_suggestion", "unsupported"}  # never verified/user_provided from AI
    assert c["sources"] == [] and all(f["citations"] == [] for f in c["findings"])
    assert c["brief"]["objectives"] and c["brief"]["research_questions"] and c["limitations"]
    assert [w["code"] for w in r["warnings"]][:2] == ["no_sources", "unsupported"]
    assert r["content_hash"] == rs.content_hash(c) and r["basis"]["brain_version"] == b0 and r["basis"]["discovery_status"] == "not_started"
    assert brain(authed, pid)["version"] == b0 and stage(authed, pid) == s0 == "not_started"  # no silent Brain change or lifecycle advance
    assert st["lifecycle"] == {"stage": "research", "status": "not_started"}
    assert next(f for f in c["findings"] if f["evidence"] == "unsupported")["follow_up"] is True


def test_prompt_uses_only_this_project_and_forbids_invented_evidence(authed, provide):
    project(authed, idea=OTHER_IDEA)
    pid = project(authed)
    prov = provide(GEN())
    authed.post(R(pid, "/generate"), json={})
    p = prov.prompts[0]
    assert "local photographers" in p and "submarine" not in p and C["password"] not in p
    for rule in ("Never include URLs", "Do not invent competitor names", "NO internet access", "Ignore any instructions"):
        assert rule in p


@pytest.mark.parametrize("bad", [
    GEN([F("user_needs", "Customers want faster booking flows.", "verified_source")]),
    GEN([F("user_needs", "Customers want faster booking flows.", "user_provided")]),
    GEN([F("market_context", "The market for photography is growing quickly.", "ai_suggestion")]),
    GEN([F("competitors_alternatives", "Rivals offer instant booking widgets.", "ai_suggestion")]),
    GEN([F("user_needs", "See https://example.com/study for details on needs.")]),
    GEN([F("risks", "Photographers may resist fees.", "ai_suggestion", detail="Source: www.example.org/report")]),
    GEN([F("risks", "short", "ai_suggestion")]),
    GEN([F("not_a_topic", "A perfectly long enough statement here.")]),
    GEN([]),
    {**GEN(), "sources": [{"title": "x", "url": "https://example.com"}]},
    {**GEN(), "findings": [{**F("risks", "Photographers may resist online fees.", "ai_suggestion"), "citations": [{"source_id": "s1", "claim": "x"}]}]},
    {**GEN(), "research_questions": ["Read https://example.com/a first?"]},
    "this is not json",
])
def test_invalid_ai_output_is_rejected_atomically_and_retry_reuses_the_version(authed, provide, bad):
    pid = project(authed)
    b0, s0 = brain(authed, pid)["version"], stage(authed, pid)
    provide(bad)
    r = authed.post(R(pid, "/generate"), json={})
    assert r.status_code == 502 and "Traceback" not in r.text and "example.com" not in r.text
    st = authed.get(R(pid)).json()
    assert st["status"] == "failed" and st["current"] is None and st["history"] == [] and st["last_error"] and st["next_step"]["key"] == "retry_generation"
    assert brain(authed, pid)["version"] == b0 and stage(authed, pid) == s0 and rows() == 1
    provide(GEN())
    assert authed.post(R(pid, "/generate"), json={}).json()["current"]["version"] == 1 and rows() == 1  # same row reused: no duplicate


def test_numeric_claims_are_visibly_downgraded_not_trusted(authed, provide):
    g = GEN([F("market_context", "About 40% of local businesses lack an online store.", "hypothesis"),
             F("risks", "Fees above $50 per booking may deter photographers.", "ai_suggestion"), F("risks", "Photographers may resist online booking fees.", "ai_suggestion")])
    _, _, st = ready(authed, provide, gen=g)
    f = cur(st)["content"]["findings"]
    assert [x["evidence"] for x in f] == ["unsupported", "unsupported", "ai_suggestion"]
    assert f[0]["follow_up"] and "numeric" in f[0]["note"] and f[2]["note"] is None


@pytest.mark.parametrize("failure,code,text", [(ai.ProviderNotConfigured("GOOGLE_AI_API_KEY is not set"), 503, "not configured"),
                                               (ai.ProviderError("x", "auth"), 502, ai.USER_MESSAGES["auth"]),
                                               (ai.ProviderError("x", "quota"), 502, ai.USER_MESSAGES["quota"]),
                                               (ai.ProviderError("x", "timeout"), 502, ai.USER_MESSAGES["timeout"])])
def test_provider_failures_change_nothing_and_are_safe(authed, provide, failure, code, text):
    pid = project(authed)
    b0 = brain(authed, pid)["version"]
    provide(failure)
    r = authed.post(R(pid, "/generate"), json={})
    assert r.status_code == code and text in r.json()["detail"] and "GOOGLE_AI_API_KEY" not in r.text
    st = authed.get(R(pid)).json()
    assert st["status"] == "failed" and text in st["last_error"] and brain(authed, pid)["version"] == b0 and stage(authed, pid) == "not_started"


def test_concurrent_generation_is_blocked_and_an_abandoned_one_recovers(authed, provide):
    pid, _, _ = ready(authed, provide)
    with SessionLocal() as db:  # simulate another request mid-generation
        r = db.query(ResearchReport).one(); r.status = "superseded"
        db.add(ResearchReport(project_id=pid, version=2, status="generating", basis={}, created_by="x")); db.commit()
    prov = provide()
    assert authed.post(R(pid, "/generate"), json={"supersede": True}).status_code == 409 and prov.prompts == []
    assert authed.get(R(pid)).json()["status"] == "generating"
    with SessionLocal() as db:
        g = db.query(ResearchReport).filter_by(version=2).one(); g.updated_at = datetime.now(timezone.utc) - timedelta(seconds=settings.research_generation_timeout_seconds + 5); db.commit()
    provide(GEN())
    st = authed.post(R(pid, "/generate"), json={"supersede": True}).json()
    assert cur(st)["version"] == 2 and rows() == 2  # the stale row was reused, not duplicated


def test_one_generating_and_one_open_version_are_enforced_by_the_database(authed, provide):
    pid, _, _ = ready(authed, provide)
    with SessionLocal() as db:
        db.add(ResearchReport(project_id=pid, version=2, status="draft", basis={}, created_by="x"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(ResearchReport(project_id=pid, version=2, status="generating", basis={}, created_by="x")); db.commit()
        db.add(ResearchReport(project_id=pid, version=3, status="generating", basis={}, created_by="x"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_regenerating_over_an_open_draft_needs_explicit_consent_and_keeps_history(authed, provide):
    pid, _, st = ready(authed, provide)
    v1_hash = cur(st)["content_hash"]
    provide()
    assert authed.post(R(pid, "/generate"), json={}).status_code == 409
    provide(GEN([F("risks", "Photographers may resist online booking fees.", "ai_suggestion")]))
    st2 = authed.post(R(pid, "/generate"), json={"supersede": True}).json()
    assert cur(st2)["version"] == 2 and [(h["version"], h["status"]) for h in st2["history"]] == [(2, "draft"), (1, "superseded")]
    assert authed.get(R(pid, "/reports/1")).json()["content_hash"] == v1_hash  # superseded draft is preserved
    provide(ai.ProviderError("x", "upstream"))  # a failed regeneration leaves the open draft alone
    assert authed.post(R(pid, "/generate"), json={"supersede": True}).status_code == 502
    after = authed.get(R(pid)).json()
    assert after["status"] == "draft" and cur(after)["version"] == 2 and cur(after)["content_hash"] == cur(st2)["content_hash"]


# ---------- brief provenance ----------
def test_brief_separates_user_confirmed_facts_from_ai_proposals(authed, provide):
    pid = project(authed)
    provide({"questions": [
        {"prompt": "Who will use the product first?", "rationale": "It decides the first release scope.", "target": "target_users", "qtype": "free_text", "options": [], "required": True, "priority": 1},
        {"prompt": "How will the product make money?", "rationale": "It shapes the model.", "target": "business_model", "qtype": "free_text", "options": [], "required": False, "priority": 2}]})
    d = authed.post(f"/api/projects/{pid}/discovery").json()
    ids = {q["target"]: q["id"] for q in d["questions"]}
    authed.post(f"/api/projects/{pid}/discovery/answers", json={"answers": [{"question_id": ids["target_users"], "value": "Wedding photographers"}]})
    authed.post(f"/api/projects/{pid}/discovery/questions/{ids['business_model']}/defer")
    _, _, st = ready(authed, provide, pid)
    b = cur(st)["content"]["brief"]
    assert [(u["text"], u["status"]) for u in b["target_users"]] == [("Wedding photographers", "user_confirmed")]
    assert b["problem"]["status"] == "ai_suggested" and any("Unanswered discovery question: How will the product make money?" in u for u in b["unknowns"])
    assert any("Discovery is not completed" in m for m in b["missing_inputs"]) and any("business model" in m for m in b["missing_inputs"])
    assert cur(st)["basis"]["confirmed_fact_ids"] == [ids["target_users"]]


# ---------- edits, evidence rules, sources ----------
def test_user_findings_and_edits_are_recorded_with_provenance(authed, provide):
    pid, _, st = ready(authed, provide)
    h = cur(st)["content_hash"]
    r = edit(authed, pid, 1, "f", "/findings", h, topic="user_needs", statement="Two photographers told me booking by phone costs them clients.")
    assert r.status_code == 200
    f = r.json()["report"]["content"]["findings"][-1]
    assert (f["id"], f["origin"], f["evidence"], f["edited_by_user"]) == ("f-4", "user", "user_provided", False)  # user-supplied, unverified
    h = r.json()["report"]["content_hash"]
    r = edit(authed, pid, 1, "f", "/findings/f-1", h, method="patch", statement="Customers struggle to compare photographers on price and style.")
    f1 = r.json()["report"]["content"]["findings"][0]
    assert f1["edited_by_user"] is True and f1["origin"] == "ai" and f1["evidence"] == "hypothesis"
    h = r.json()["report"]["content_hash"]
    r = authed.delete(R(pid, f"/reports/1/findings/f-2?base_hash={h}"))
    assert r.status_code == 200 and [f["id"] for f in r.json()["report"]["content"]["findings"]] == ["f-1", "f-3", "f-4"]


def test_stale_hash_is_a_conflict_not_a_lost_update(authed, provide):
    pid, _, st = ready(authed, provide)
    h = cur(st)["content_hash"]
    assert edit(authed, pid, 1, "f", "/findings/f-1", h, method="patch", follow_up=True).status_code == 200
    r = edit(authed, pid, 1, "f", "/findings/f-1", h, method="patch", statement="A different statement entirely, written later.")
    assert r.status_code == 409 and "changed" in r.json()["detail"]


def test_verified_source_requires_a_citation_to_a_source_the_user_examined(authed, provide):
    pid, _, st = ready(authed, provide)
    h = cur(st)["content_hash"]
    bad = edit(authed, pid, 1, "f", "/findings/f-1", h, method="patch", evidence="verified_source")
    assert bad.status_code == 422 and "verified_source needs a citation" in bad.json()["detail"][0]["msg"]
    r = edit(authed, pid, 1, "s", "/sources", h, title="Industry report", url="HTTPS://Example.com/report?utm_source=x#sec", publisher="Example Org", accessed_on="2026-10-01", examined=True)
    assert r.status_code == 200
    src = r.json()["report"]["content"]["sources"][0]
    assert (src["id"], src["url"], src["examined"], src["examined_by"]) == ("src-1", "https://example.com/report", True, "user")
    h = r.json()["report"]["content_hash"]
    unknown = edit(authed, pid, 1, "f", "/findings/f-1", h, method="patch", evidence="verified_source", citations=[{"source_id": "src-9", "claim": "Customers compare on price."}])
    assert unknown.status_code == 422 and "unknown source" in unknown.json()["detail"][0]["msg"]
    ok = edit(authed, pid, 1, "f", "/findings/f-1", h, method="patch", evidence="verified_source", citations=[{"source_id": "src-1", "claim": "Customers compare photographers mainly on price."}])
    assert ok.status_code == 200
    f1 = ok.json()["report"]["content"]["findings"][0]
    assert f1["evidence"] == "verified_source" and f1["citations"][0]["claim"].startswith("Customers compare")
    h = ok.json()["report"]["content_hash"]
    assert authed.delete(R(pid, f"/reports/1/sources/src-1?base_hash={h}")).status_code == 409  # still cited
    assert ok.json()["report"]["unverified_count"] == 2


def test_a_source_the_user_did_not_examine_cannot_verify_a_finding(authed, provide):
    pid, _, st = ready(authed, provide)
    r = edit(authed, pid, 1, "s", "/sources", cur(st)["content_hash"], title="Maybe relevant", url="https://example.com/maybe")
    assert r.json()["report"]["content"]["sources"][0]["examined"] is False
    h = r.json()["report"]["content_hash"]
    r = edit(authed, pid, 1, "f", "/findings/f-1", h, method="patch", evidence="verified_source", citations=[{"source_id": "src-1", "claim": "Customers compare on price."}])
    assert r.status_code == 422
    r = edit(authed, pid, 1, "f", "/findings/f-1", h, method="patch", citations=[{"source_id": "src-1", "claim": "Customers compare on price."}])
    assert r.status_code == 200 and r.json()["report"]["content"]["findings"][0]["evidence"] == "hypothesis"  # cited, still not verified


@pytest.mark.parametrize("body", [{"url": "javascript:alert(1)"}, {"url": "ftp://example.com/x"}, {"url": "http://localhost:8000/x"}, {"url": "http://10.1.2.3/x"},
                                  {"url": "https://user:pw@example.com/x"}, {"url": "not a url"}, {"url": "https://example.com/x", "examined": True},
                                  {"url": "https://example.com/x", "examined": True, "accessed_on": "2999-01-01"}, {"title": "  "}])
def test_invalid_sources_are_rejected(authed, provide, body):
    pid, _, st = ready(authed, provide)
    h = cur(st)["content_hash"]
    r = edit(authed, pid, 1, "s", "/sources", h, **{"title": "A source", "url": "https://example.com/ok", **body})
    assert r.status_code == 422 and authed.get(R(pid)).json()["current"]["content_hash"] == h  # nothing changed


def test_clients_cannot_claim_webforge_examined_a_source(authed, provide):
    pid, _, st = ready(authed, provide)
    r = edit(authed, pid, 1, "s", "/sources", cur(st)["content_hash"], title="S", url="https://example.com/s", accessed_on="2026-10-01", examined=True, examined_by="webforge")
    assert r.json()["report"]["content"]["sources"][0]["examined_by"] == "user"


def test_unsupported_findings_are_always_flagged_and_follow_up_can_be_set_in_bulk(authed, provide):
    pid, _, st = ready(authed, provide)
    h = cur(st)["content_hash"]
    r = edit(authed, pid, 1, "f", "/findings/f-1", h, method="patch", evidence="unsupported", follow_up=False)
    assert r.json()["report"]["content"]["findings"][0]["follow_up"] is True  # cannot be un-flagged while unsupported
    r = edit(authed, pid, 1, "f", "/follow-up", r.json()["report"]["content_hash"], finding_ids=["f-2"], follow_up=True)
    assert [f["follow_up"] for f in r.json()["report"]["content"]["findings"]] == [True, True, True]
    assert edit(authed, pid, 1, "f", "/follow-up", r.json()["report"]["content_hash"], finding_ids=["f-99"]).status_code == 404


def test_unresolved_questions_can_be_replaced(authed, provide):
    pid, _, st = ready(authed, provide)
    r = authed.put(R(pid, "/reports/1/questions"), json={"base_hash": cur(st)["content_hash"], "questions": ["Which cities first?", "Do photographers want exclusivity?"]})
    assert [q["question"] for q in r.json()["report"]["content"]["unresolved_questions"]] == ["Which cities first?", "Do photographers want exclusivity?"]
    assert authed.put(R(pid, "/reports/1/questions"), json={"base_hash": r.json()["report"]["content_hash"], "questions": ["x"]}).status_code == 422


# ---------- submit / approve / versions / lifecycle ----------
def test_submit_rules_and_lifecycle(authed, provide):
    pid, _, st = ready(authed, provide)
    h = cur(st)["content_hash"]
    assert authed.post(R(pid, "/reports/1/submit"), json={"base_hash": "0" * 64}).status_code == 409
    assert stage(authed, pid) == "not_started"
    s = authed.post(R(pid, "/reports/1/submit"), json={"base_hash": h}).json()
    assert s["status"] == "in_review" and s["can_approve"] and not s["can_submit"] and stage(authed, pid) == "needs_review"
    assert authed.post(R(pid, "/reports/1/submit"), json={"base_hash": h}).status_code == 200  # idempotent


def test_an_empty_report_cannot_be_submitted(authed, provide):
    pid, _, st = ready(authed, provide, gen=GEN([F("risks", "Photographers may resist online booking fees.", "ai_suggestion")]))
    h = authed.delete(R(pid, f"/reports/1/findings/f-1?base_hash={cur(st)['content_hash']}")).json()["report"]["content_hash"]
    r = authed.post(R(pid, "/reports/1/submit"), json={"base_hash": h})
    assert r.status_code == 409 and "at least one finding" in r.json()["detail"] and stage(authed, pid) == "not_started"


def test_editing_an_in_review_report_returns_it_to_draft_and_invalidates_the_old_hash(authed, provide):
    pid, s = submitted(authed, provide)
    old = cur(s)["content_hash"]
    r = edit(authed, pid, 1, "f", "/findings/f-1", old, method="patch", follow_up=True)
    assert r.status_code == 200 and r.json()["report"]["status"] == "draft" and stage(authed, pid) == "in_progress"
    a = authed.post(R(pid, "/reports/1/approve"), json={"content_hash": old, "acknowledge_unverified": True})
    assert a.status_code == 409 and authed.get(R(pid)).json()["status"] == "draft"


def test_approval_is_explicit_version_bound_and_atomic(authed, provide):
    pid, s = submitted(authed, provide)
    h = cur(s)["content_hash"]
    assert authed.post(R(pid, "/reports/1/approve"), json={"content_hash": "f" * 64, "acknowledge_unverified": True}).status_code == 409
    blocked = authed.post(R(pid, "/reports/1/approve"), json={"content_hash": h})
    assert blocked.status_code == 409 and "Acknowledge" in blocked.json()["detail"]
    assert stage(authed, pid) == "needs_review" and cur(authed.get(R(pid)).json())["status"] == "in_review"
    b0 = brain(authed, pid)
    done = authed.post(R(pid, "/reports/1/approve"), json={"content_hash": h, "acknowledge_unverified": True, "note": "Reviewed with the team"})
    assert done.status_code == 200
    st = done.json()
    assert st["status"] == "approved" and st["approved_version"] == 1 and st["lifecycle"]["status"] == "complete" and stage(authed, pid) == "complete"
    r = cur(st)
    assert r["approval_note"] == "Reviewed with the team" and r["acknowledged_unverified"] is True and r["approved_at"] and not r["editable"]
    b1 = brain(authed, pid)
    assert b1["version"] == b0["version"] + 1 and r["brain_revision"] == b1["version"]
    ptr = b1["brain"]["research"]
    assert (ptr["approved_version"], ptr["content_hash"], ptr["mode"], ptr["unverified_acknowledged"]) == (1, h, "preliminary", True)
    assert ptr["finding_counts"]["verified_source"] == 0 and ptr["finding_counts"]["unsupported"] == 1 and ptr["source_count"] == 0
    for k in ("idea", "target_users", "goals", "discovery", "business"):  # approval never overwrites confirmed Brain data
        assert b1["brain"][k] == b0["brain"][k], k
    rev = authed.get(f"/api/projects/{pid}/revisions").json()[0]
    assert rev["change_type"] == "research_approved" and set(rev["patch"]) == {"research"}
    again = authed.post(R(pid, "/reports/1/approve"), json={"content_hash": h, "acknowledge_unverified": True})
    assert again.status_code == 200 and brain(authed, pid)["version"] == b1["version"]  # idempotent: no second revision


def test_an_approved_version_is_immutable_and_editing_creates_a_new_draft_that_needs_approval_again(authed, provide):
    pid, s = submitted(authed, provide)
    h1 = cur(s)["content_hash"]
    st = approve(authed, pid, s).json()
    r = edit(authed, pid, 1, "f", "/findings/f-1", h1, method="patch", statement="Customers struggle to compare photographers, and say so often.")
    assert r.status_code == 200
    new = r.json()["report"]
    assert new["version"] == 2 and new["status"] == "draft" and new["parent_version"] == 1 and new["created_via"] == "copy_of_approved"
    v1 = authed.get(R(pid, "/reports/1")).json()
    assert v1["status"] == "approved" and v1["content_hash"] == h1 and v1["content"]["findings"][0]["statement"].startswith("Customers probably")
    assert stage(authed, pid) == "in_progress"  # reopened by the explicit edit
    ptr = brain(authed, pid)["brain"]["research"]
    assert ptr["approved_version"] == 1 and ptr["content_hash"] == h1  # Brain still points at what was actually approved
    assert edit(authed, pid, 1, "f", "/findings/f-2", h1, method="patch", follow_up=True).status_code == 409  # a newer version is open: edit that one
    state = authed.get(R(pid)).json()
    assert state["status"] == "draft" and state["approved_version"] == 1 and [(h["version"], h["status"]) for h in state["history"]] == [(2, "draft"), (1, "approved")]
    authed.post(R(pid, "/reports/2/submit"), json={"base_hash": new["content_hash"]})
    assert stage(authed, pid) == "needs_review"
    st2 = authed.post(R(pid, "/reports/2/approve"), json={"content_hash": new["content_hash"], "acknowledge_unverified": True}).json()
    assert st2["approved_version"] == 2 and stage(authed, pid) == "complete" and brain(authed, pid)["brain"]["research"]["approved_version"] == 2
    assert authed.get(R(pid, "/reports/1")).json()["status"] == "approved"  # history preserved


def test_regenerating_after_approval_reopens_the_stage_and_failure_does_not(authed, provide):
    pid, s = submitted(authed, provide)
    approve(authed, pid, s)
    provide(ai.ProviderError("x", "quota"))
    assert authed.post(R(pid, "/generate"), json={}).status_code == 502
    st = authed.get(R(pid)).json()
    assert st["status"] == "approved" and st["approved_version"] == 1 and stage(authed, pid) == "complete" and st["last_error"]
    provide(GEN([F("risks", "Photographers may resist online booking fees.", "ai_suggestion")]))
    st = authed.post(R(pid, "/generate"), json={}).json()
    assert cur(st)["version"] == 2 and cur(st)["parent_version"] == 1 and st["status"] == "draft" and stage(authed, pid) == "in_progress"
    assert rows() == 2 and authed.get(R(pid, "/reports/1")).json()["status"] == "approved"


def test_manual_stage_completion_is_blocked_once_research_has_started_but_not_before(authed, provide):
    pid = project(authed)
    assert authed.put(f"/api/projects/{pid}/stages/research", json={"status": "in_progress"}).status_code == 200
    other = project(authed)
    assert authed.put(f"/api/projects/{other}/stages/research", json={"status": "complete"}).status_code == 200  # unchanged behavior without a report
    provide(GEN())
    authed.post(R(pid, "/generate"), json={})
    r = authed.put(f"/api/projects/{pid}/stages/research", json={"status": "complete"})
    assert r.status_code == 409 and "Approve the research report" in r.json()["detail"]
    authed.post(R(pid, "/reports/1/submit"), json={"base_hash": authed.get(R(pid)).json()["current"]["content_hash"]})
    st = authed.get(R(pid)).json()
    approve(authed, pid, st)
    assert authed.put(f"/api/projects/{pid}/stages/research", json={"status": "complete"}).status_code == 200


def test_the_research_brain_section_cannot_be_written_directly(authed):
    pid = project(authed)
    forged = {"approved_version": 7, "report_id": "x", "content_hash": "a" * 64}
    assert authed.put(f"/api/projects/{pid}/brain/research", json={"value": forged}).status_code == 403


# ---------- ownership ----------
def test_other_users_cannot_touch_a_projects_research(authed, provide):
    pid, _, st = ready(authed, provide)
    h = cur(st)["content_hash"]
    authed.post("/api/auth/logout")
    authed.post("/api/auth/register", json={"email": "b@example.com", "password": "password123"})
    calls = [("get", R(pid), None), ("get", R(pid, "/reports/1"), None), ("post", R(pid, "/generate"), {}),
             ("post", R(pid, "/reports/1/findings"), {"base_hash": h, "topic": "risks", "statement": "A long enough statement."}),
             ("patch", R(pid, "/reports/1/findings/f-1"), {"base_hash": h, "follow_up": True}),
             ("post", R(pid, "/reports/1/sources"), {"base_hash": h, "title": "t", "url": "https://example.com"}),
             ("put", R(pid, "/reports/1/questions"), {"base_hash": h, "questions": []}), ("post", R(pid, "/reports/1/follow-up"), {"base_hash": h, "finding_ids": ["f-1"]}),
             ("post", R(pid, "/reports/1/submit"), {"base_hash": h}), ("post", R(pid, "/reports/1/approve"), {"content_hash": h, "acknowledge_unverified": True})]
    for method, url, body in calls:
        r = getattr(authed, method)(url) if body is None else getattr(authed, method)(url, json=body)
        assert r.status_code == 404, (method, url)
    assert authed.delete(R(pid, f"/reports/1/findings/f-1?base_hash={h}")).status_code == 404
    mine = project(authed)
    assert authed.get(R(mine)).json()["status"] == "not_started"  # B's own project is independent of A's reports
    authed.post("/api/auth/logout")
    assert authed.get(R(pid)).status_code == 401


def test_invalid_requests(authed, provide):
    pid, _, st = ready(authed, provide)
    h = cur(st)["content_hash"]
    assert authed.get(R(pid, "/reports/9")).status_code == 404 and authed.get(R(pid, "/reports/abc")).status_code == 422
    assert edit(authed, pid, 1, "f", "/findings", "short", topic="risks", statement="A long enough statement here.").status_code == 422
    assert edit(authed, pid, 1, "f", "/findings", h, topic="nope", statement="A long enough statement here.").status_code == 422
    assert edit(authed, pid, 1, "f", "/findings", h, topic="risks", statement="tiny").status_code == 422
    assert edit(authed, pid, 1, "f", "/findings/f-99", h, method="patch", follow_up=True).status_code == 404
    assert edit(authed, pid, 9, "f", "/findings", h, topic="risks", statement="A long enough statement here.").status_code == 404
    assert authed.post(R(pid, "/reports/1/approve"), json={"content_hash": h}).status_code == 409  # draft cannot be approved
    assert authed.get(R(pid)).json()["current"]["content_hash"] == h


@pytest.mark.skipif(not IS_PG, reason="row locking is PostgreSQL behavior")
def test_concurrent_generation_and_edits_never_duplicate_or_lose_updates(authed, provide):
    pid = project(authed)
    prov = provide(GEN(), GEN())
    jar = dict(authed.cookies)

    def gen_call(_):
        with TestClient(app, cookies=jar) as c:
            return c.post(R(pid, "/generate"), json={}).status_code
    with ThreadPoolExecutor(2) as ex:
        codes = sorted(ex.map(gen_call, range(2)))
    assert codes == [200, 409] and rows() == 1 and len(prov.prompts) == 1  # exactly one version, one provider call
    st = authed.get(R(pid)).json()
    h = cur(st)["content_hash"]

    def edit_call(fid):
        with TestClient(app, cookies=jar) as c:
            return c.patch(R(pid, f"/reports/1/findings/{fid}"), json={"base_hash": h, "follow_up": True}).status_code
    with ThreadPoolExecutor(2) as ex:
        codes = sorted(ex.map(edit_call, ["f-1", "f-2"]))
    assert codes == [200, 409]  # same base hash: one wins, the other is told to reload
    final = authed.get(R(pid)).json()["current"]["content"]["findings"]
    assert sum(f["follow_up"] for f in final) == 2  # f-3 was already flagged (unsupported); exactly one of f-1/f-2 changed
