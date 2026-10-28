"""Progressive AI questions. The provider here is a scripted TEST DOUBLE: these tests prove WebForge's behavior,
not that the real Google provider works (that path is unverified)."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import ai
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import BrainRevision, DiscoveryQuestion, DiscoverySession
from conftest import IS_PG

C = {"email": "a@example.com", "password": "password123"}
IDEA = "A marketplace where customers find local photographers and book them online."


class Scripted(ai.AIProvider):
    def __init__(self, *outputs):
        self.outputs, self.prompts = list(outputs), []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        out = self.outputs.pop(0)  # an exhausted script fails the test: no hidden extra provider calls
        if isinstance(out, Exception):
            raise out
        return out if isinstance(out, str) else json.dumps(out)


def Q(prompt, target, qtype="free_text", options=None, required=False, priority=3, **kw):
    return {"prompt": prompt, "rationale": "This changes what the first release must contain.", "target": target, "qtype": qtype,
            "options": [{"id": i, "label": l} for i, l in (options or [])], "required": required, "priority": priority, **kw}


def round1():
    return {"questions": [
        Q("Who will use the product first?", "target_users", required=True, priority=1),
        Q("Which feature must the first release include?", "mvp_scope", "single_choice", [("booking", "Online booking"), ("payments", "Payments"), ("reviews", "Reviews")], True, 2),
        Q("Which systems must it connect to?", "integrations", "multiple_choice", [("stripe", "Stripe"), ("calendar", "Calendar"), ("email", "Email")], False, 3),
        Q("Will you store customers' personal data?", "security_privacy", "confirmation", priority=3),
        Q("How will the product make money?", "business_model", priority=4),
    ]}


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


def project(c, idea=IDEA):
    pid = c.post("/api/projects", json={"name": "Snapbook"}).json()["id"]
    c.put(f"/api/projects/{pid}/brain/idea", json={"value": {"raw": idea, "product_name": "Snapbook", "product_type": "marketplace", "problem": "Hard to compare photographers",
                                                           "features": ["Package comparison"], "assumptions": ["Customers book online"], "open_questions": []}})
    c.put(f"/api/projects/{pid}/brain/target_users", json={"value": ["Shop owners"]})
    return pid


def D(pid, path=""):
    return f"/api/projects/{pid}/discovery{path}"


def started(c, provide, pid=None):
    pid = pid or project(c)
    prov = provide(round1())
    st = c.post(D(pid)).json()
    return pid, prov, st


def qmap(st):
    return {q["target"]: q for q in st["questions"]}


def brain(c, pid):
    return c.get(f"/api/projects/{pid}/brain").json()


def count_rows(model):
    with SessionLocal() as db:
        return db.query(model).count()


def answer(c, pid, qid, value):
    return c.post(D(pid, "/answers"), json={"answers": [{"question_id": qid, "value": value}]})


# ---------- start / resume / persistence ----------
def test_get_before_start_creates_nothing(authed):
    pid = project(authed)
    st = authed.get(D(pid)).json()
    assert st["status"] == "not_started" and st["questions"] == [] and st["next_step"]["key"] == "start_discovery"
    assert count_rows(DiscoverySession) == 0


def test_start_requires_an_idea_and_creates_nothing(authed, provide):
    pid = authed.post("/api/projects", json={"name": "Empty"}).json()["id"]
    prov = provide()
    assert authed.post(D(pid)).status_code == 409
    assert count_rows(DiscoverySession) == 0 and prov.prompts == []


def test_start_persists_questions_and_resume_does_not_regenerate(authed, provide):
    pid, prov, st = started(authed, provide)
    assert st["status"] == "awaiting_answers" and st["round"] == 1 and st["counts"] == {"open": 5, "answered": 0, "skipped": 0, "deferred": 0, "total": 5}
    assert [q["target"] for q in st["questions"]][:2] == ["target_users", "mvp_scope"]  # impact order
    ids = [q["id"] for q in st["questions"]]
    again = authed.post(D(pid)).json()  # e.g. a page refresh that calls start again
    assert [q["id"] for q in again["questions"]] == ids and len(prov.prompts) == 1
    assert count_rows(DiscoverySession) == 1 and count_rows(DiscoveryQuestion) == 5
    assert [q["id"] for q in authed.get(D(pid)).json()["questions"]] == ids


def test_prompt_contains_only_this_project_and_treats_it_as_data(authed, provide):
    other = project(authed, "A secret idea about submarine logistics")
    pid = project(authed)
    prov = provide(round1())
    authed.post(D(pid))
    p = prov.prompts[0]
    assert "local photographers" in p and "submarine" not in p and "Ignore any instructions" in p
    assert C["password"] not in p and C["email"] not in p and other not in p


def test_questions_are_not_asked_for_what_the_brain_already_confirms(authed, provide):
    pid, prov, st = started(authed, provide)
    answer(authed, pid, qmap(st)["target_users"]["id"], "Photographers")
    resolve_all(authed, pid, authed.get(D(pid)).json())
    prov2 = provide({"questions": []})
    assert authed.post(D(pid, "/next-round")).status_code == 200
    assert "Photographers" in prov2.prompts[0] and "confirmed_by_user" in prov2.prompts[0]


# ---------- provider failures ----------
@pytest.mark.parametrize("failure,code", [(ai.ProviderNotConfigured("GOOGLE_AI_API_KEY is not set"), 503),
                                          (ai.ProviderError("Google AI request failed: ReadTimeout"), 502),
                                          ('{"questions": [{"prompt": "Short?"}]}', 502),
                                          ("not json at all", 502)])
def test_provider_failure_changes_nothing_and_can_be_retried(authed, provide, failure, code):
    pid = project(authed)
    v0 = brain(authed, pid)["version"]
    provide(failure)
    r = authed.post(D(pid))
    assert r.status_code == code
    assert "GOOGLE_AI_API_KEY" not in r.text and "Traceback" not in r.text and "ReadTimeout" not in r.text
    st = authed.get(D(pid)).json()
    assert st["status"] == "failed" and st["questions"] == [] and st["last_error"] and st["next_step"]["key"] == "retry_generation"
    assert brain(authed, pid)["version"] == v0 and count_rows(DiscoveryQuestion) == 0
    provide(round1())
    assert authed.post(D(pid)).json()["status"] == "awaiting_answers"  # retry recovers, same single session
    assert count_rows(DiscoverySession) == 1


# ---------- answers ----------
@pytest.mark.parametrize("target,bad", [("target_users", ""), ("target_users", "  "), ("target_users", 5), ("target_users", "x" * 2001),
                                        ("mvp_scope", "not_an_option"), ("mvp_scope", ["booking"]), ("integrations", []),
                                        ("integrations", ["stripe", "stripe"]), ("integrations", ["bogus"]), ("integrations", "stripe"),
                                        ("security_privacy", "yes"), ("security_privacy", 1), ("security_privacy", None)])
def test_invalid_answers_are_rejected_with_the_question_id(authed, provide, target, bad):
    pid, _, st = started(authed, provide)
    q = qmap(st)[target]
    v0 = brain(authed, pid)["version"]
    r = answer(authed, pid, q["id"], bad)
    assert r.status_code == 422 and r.json()["detail"][0]["loc"][-1] == q["id"]
    after = authed.get(D(pid)).json()
    assert qmap(after)[target]["status"] == "open" and brain(authed, pid)["version"] == v0


def test_valid_answers_update_the_brain_once_with_provenance(authed, provide):
    pid, _, st = started(authed, provide)
    qs = qmap(st)
    before = brain(authed, pid)
    r = authed.post(D(pid, "/answers"), json={"answers": [
        {"question_id": qs["target_users"]["id"], "value": "Photographers; Studios"},
        {"question_id": qs["mvp_scope"]["id"], "value": "booking"},
        {"question_id": qs["integrations"]["id"], "value": ["email", "stripe"]},
        {"question_id": qs["security_privacy"]["id"], "value": True}]})
    assert r.status_code == 200 and r.json()["counts"]["answered"] == 4 and r.json()["counts"]["open"] == 1
    after = brain(authed, pid)
    assert after["version"] == before["version"] + 1  # one revision for the whole batch
    b = after["brain"]
    assert b["target_users"] == ["Photographers", "Studios"]
    assert b["product_strategy"]["mvp_scope"] == "Online booking"
    assert b["architecture"]["integrations"] == ["Stripe", "Email"]
    assert b["security"]["privacy_requirements"] is True
    facts = b["discovery"]["confirmed"]
    assert len(facts) == 4 and {f["source"] for f in facts} == {"user_confirmed"} and facts[0]["question"] == "Who will use the product first?"
    assert b["idea"]["features"] == ["Package comparison"]  # AI-suggested content is untouched by answers
    revs = authed.get(f"/api/projects/{pid}/revisions").json()
    assert revs[0]["change_type"] == "discovery_answer" and set(revs[0]["patch"]) == {"target_users", "product_strategy", "architecture", "security", "discovery"}
    assert revs[1]["version"] == before["version"]
    with SessionLocal() as db:  # append-only: the earlier snapshot still shows the old value
        old = db.query(BrainRevision).filter_by(project_id=pid, version=before["version"]).one()
        assert old.snapshot["target_users"] == ["Shop owners"] and old.snapshot.get("discovery", {}).get("confirmed", []) == []


def test_a_batch_with_one_invalid_answer_applies_nothing(authed, provide):
    pid, _, st = started(authed, provide)
    qs = qmap(st)
    v0 = brain(authed, pid)["version"]
    r = authed.post(D(pid, "/answers"), json={"answers": [{"question_id": qs["target_users"]["id"], "value": "Photographers"},
                                                          {"question_id": qs["mvp_scope"]["id"], "value": "nope"}]})
    assert r.status_code == 422
    after = authed.get(D(pid)).json()
    assert after["counts"]["answered"] == 0 and brain(authed, pid)["version"] == v0


def test_resubmitting_is_idempotent_and_corrections_replace_the_fact(authed, provide):
    pid, _, st = started(authed, provide)
    qid = qmap(st)["target_users"]["id"]
    answer(authed, pid, qid, "Photographers")
    v1 = brain(authed, pid)["version"]
    answer(authed, pid, qid, "  Photographers ")
    assert brain(authed, pid)["version"] == v1  # same answer: no new revision
    answer(authed, pid, qid, "Wedding photographers")
    b = brain(authed, pid)
    assert b["version"] == v1 + 1 and b["brain"]["target_users"] == ["Wedding photographers"]
    assert [f["answer"] for f in b["brain"]["discovery"]["confirmed"]] == ["Wedding photographers"]


def test_works_on_brains_created_before_the_discovery_section_existed(authed, provide):
    pid = project(authed)
    with SessionLocal() as db:
        rev = db.query(BrainRevision).filter_by(project_id=pid).order_by(BrainRevision.version.desc()).first()
        snap = dict(rev.snapshot); snap.pop("discovery"); rev.snapshot = snap; db.commit()
    provide(round1())
    st = authed.post(D(pid)).json()
    assert answer(authed, pid, qmap(st)["target_users"]["id"], "Photographers").status_code == 200


def test_clients_cannot_write_the_discovery_section_directly(authed):
    pid = project(authed)
    forged = {"confirmed": [{"question_id": "x", "target": "other", "question": "q", "answer": "a", "source": "user_confirmed", "recorded_at": "now"}], "assumptions": []}
    assert authed.put(f"/api/projects/{pid}/brain/discovery", json={"value": forged}).status_code == 403


# ---------- ownership / tampering ----------
def test_question_id_tampering_and_cross_session_ids_are_rejected(authed, provide):
    pid, _, st = started(authed, provide)
    v0 = brain(authed, pid)["version"]
    assert answer(authed, pid, "00000000-0000-0000-0000-000000000000", "x").status_code == 404
    other_pid = project(authed)
    provide(round1())
    other = authed.post(D(other_pid)).json()
    foreign = other["questions"][0]["id"]
    assert answer(authed, pid, foreign, "Photographers").status_code == 404
    assert authed.post(D(pid, f"/questions/{foreign}/skip")).status_code == 404
    assert brain(authed, pid)["version"] == v0 and authed.get(D(other_pid)).json()["counts"]["answered"] == 0
    mixed = authed.post(D(pid, "/answers"), json={"answers": [{"question_id": st["questions"][0]["id"], "value": "ok"}, {"question_id": foreign, "value": "x"}]})
    assert mixed.status_code == 404 and authed.get(D(pid)).json()["counts"]["answered"] == 0  # nothing partially applied


def test_other_users_cannot_touch_a_projects_discovery(authed, provide):
    pid, _, st = started(authed, provide)
    qid = st["questions"][0]["id"]
    authed.post("/api/auth/logout")
    authed.post("/api/auth/register", json={"email": "b@example.com", "password": "password123"})
    calls = [("get", D(pid), None), ("post", D(pid), {}), ("post", D(pid, "/answers"), {"answers": [{"question_id": qid, "value": "x"}]}),
             ("post", D(pid, f"/questions/{qid}/skip"), {}), ("post", D(pid, f"/questions/{qid}/defer"), {}),
             ("post", D(pid, "/next-round"), {}), ("post", D(pid, "/review"), {}), ("post", D(pid, "/complete"), {})]
    for method, url, body in calls:
        r = getattr(authed, method)(url) if body is None else getattr(authed, method)(url, json=body)
        assert r.status_code == 404, (method, url)
    authed.post("/api/auth/logout")
    assert authed.get(D(pid)).status_code == 401


# ---------- skip / defer ----------
def test_skip_and_defer_rules(authed, provide):
    pid, _, st = started(authed, provide)
    qs = qmap(st)
    v0 = brain(authed, pid)["version"]
    assert authed.post(D(pid, f"/questions/{qs['business_model']['id']}/skip")).json()["counts"]["skipped"] == 1
    assert authed.post(D(pid, f"/questions/{qs['target_users']['id']}/skip")).status_code == 409  # required
    assert authed.post(D(pid, f"/questions/{qs['target_users']['id']}/defer")).json()["counts"]["deferred"] == 1
    assert authed.post(D(pid, f"/questions/{qs['target_users']['id']}/defer")).status_code == 200  # idempotent
    assert brain(authed, pid)["version"] == v0  # skipping/deferring never touches the Brain
    after = answer(authed, pid, qs["target_users"]["id"], "Photographers").json()
    assert after["counts"]["deferred"] == 0 and after["counts"]["answered"] == 1
    assert authed.post(D(pid, f"/questions/{qs['target_users']['id']}/defer")).status_code == 409  # already answered
    assert qs["target_users"]["id"] not in after["outstanding_questions"] and qs["business_model"]["id"] not in after["outstanding_questions"]


# ---------- next rounds ----------
def resolve_all(c, pid, st):
    for q in st["questions"]:
        c.post(D(pid, f"/questions/{q['id']}/{'defer' if q['required'] else 'skip'}"))


def test_next_round_needs_all_questions_resolved_and_filters_duplicates(authed, provide):
    pid, prov, st = started(authed, provide)
    qs = qmap(st)
    assert authed.post(D(pid, "/next-round")).status_code == 409 and st["can_generate_next_round"] is False
    answer(authed, pid, qs["target_users"]["id"], "Photographers")
    resolve_all(authed, pid, authed.get(D(pid)).json())
    provide({"questions": [
        Q("Who will use the product first?", "target_users"),                       # exact duplicate
        Q("Which kind of customers matter most?", "target_users", priority=1),      # target already confirmed
        Q("What must a customer be able to do in one visit?", "core_workflows", priority=2),
        Q("Anything about accessibility we should know?", "other", priority=5)]})
    st2 = authed.post(D(pid, "/next-round")).json()
    assert st2["round"] == 2 and st2["status"] == "awaiting_answers"
    new = [q for q in st2["questions"] if q["round"] == 2]
    assert [q["target"] for q in new] == ["core_workflows", "other"]
    assert len({q["id"] for q in st2["questions"]}) == 7 and [q["id"] for q in st2["questions"]][:5] == [q["id"] for q in st["questions"]]


def test_round_limit_is_enforced_and_explained(authed, provide, monkeypatch):
    monkeypatch.setattr(settings, "discovery_max_rounds", 1)
    pid, _, st = started(authed, provide)
    resolve_all(authed, pid, st)
    st = authed.get(D(pid)).json()
    assert st["can_generate_next_round"] is False
    r = authed.post(D(pid, "/next-round"))
    assert r.status_code == 409 and "documented assumptions" in r.json()["detail"]


def test_a_round_with_nothing_useful_moves_to_review(authed, provide):
    pid, _, st = started(authed, provide)
    resolve_all(authed, pid, st)
    provide({"questions": []})
    assert authed.post(D(pid, "/next-round")).json()["status"] == "ready_for_review"


def test_failed_next_round_keeps_everything(authed, provide):
    pid, _, st = started(authed, provide)
    answer(authed, pid, qmap(st)["target_users"]["id"], "Photographers")
    resolve_all(authed, pid, authed.get(D(pid)).json())
    before, v0 = authed.get(D(pid)).json(), brain(authed, pid)["version"]
    provide(ai.ProviderError("Google AI request failed: ReadTimeout"))
    assert authed.post(D(pid, "/next-round")).status_code == 502
    after = authed.get(D(pid)).json()
    assert after["status"] == "awaiting_answers" and after["last_error"] and after["questions"] == before["questions"]
    assert brain(authed, pid)["version"] == v0
    provide({"questions": []})
    assert authed.post(D(pid, "/next-round")).status_code == 200  # retry works


def test_concurrent_generation_is_blocked_and_abandoned_generation_recovers(authed, provide):
    pid, _, st = started(authed, provide)
    resolve_all(authed, pid, st)
    with SessionLocal() as db:
        s = db.query(DiscoverySession).one(); s.status = "generating"; db.commit()
    prov = provide()
    for r in (authed.post(D(pid, "/next-round")), authed.post(D(pid, "/answers"), json={"answers": [{"question_id": st["questions"][0]["id"], "value": "x"}]})):
        assert r.status_code == 409
    assert prov.prompts == []
    assert authed.post(D(pid)).json()["status"] == "generating"  # start resumes instead of duplicating work
    with SessionLocal() as db:
        s = db.query(DiscoverySession).one(); s.updated_at = datetime.now(timezone.utc) - timedelta(seconds=settings.discovery_generation_timeout_seconds + 5); db.commit()
    provide({"questions": []})
    assert authed.post(D(pid, "/next-round")).json()["status"] == "ready_for_review"


# ---------- review / completion ----------
def test_review_summary_separates_confirmed_proposed_assumptions_and_open_items(authed, provide):
    pid, _, st = started(authed, provide)
    qs = qmap(st)
    answer(authed, pid, qs["target_users"]["id"], "Photographers")
    authed.post(D(pid, f"/questions/{qs['mvp_scope']['id']}/defer"))
    authed.post(D(pid, f"/questions/{qs['business_model']['id']}/skip"))
    s = authed.post(D(pid, "/review")).json()
    assert s["status"] == "ready_for_review" and s["can_complete"] and not s["can_review"]
    sm = s["summary"]
    assert [f["answer"] for f in sm["confirmed"]] == ["Photographers"]
    proposed = {p["label"]: p["items"] for p in sm["proposed"]}
    assert "Target users" not in proposed  # confirmed by the user, so no longer merely proposed
    assert proposed["Features"] == ["Package comparison"] and proposed["Problem"] == ["Hard to compare photographers"]
    assert {"id": "idea:0", "text": "Customers book online", "source": "ai_suggested", "status": "unverified"} in sm["assumptions"]
    assert {q["question"] for q in sm["unanswered"]} == {qs["integrations"]["prompt"], qs["security_privacy"]["prompt"]}
    assert [q["id"] for q in sm["deferred"]] == [qs["mvp_scope"]["id"]] and [q["id"] for q in sm["skipped"]] == [qs["business_model"]["id"]]
    assert authed.post(D(pid, "/review")).status_code == 200  # idempotent
    fixed = answer(authed, pid, qs["integrations"]["id"], ["stripe"])  # corrections are allowed during review
    assert fixed.status_code == 200 and fixed.json()["status"] == "ready_for_review"


def test_completion_is_explicit_and_documents_unresolved_questions_as_assumptions(authed, provide):
    pid, _, st = started(authed, provide)
    assert authed.post(D(pid, "/complete"), json={}).status_code == 409  # review first
    answer(authed, pid, qmap(st)["target_users"]["id"], "Photographers")
    authed.post(D(pid, "/review"))
    blocked = authed.post(D(pid, "/complete"), json={})
    assert blocked.status_code == 409 and "documented assumptions" in blocked.json()["detail"]
    assert authed.get(D(pid)).json()["status"] == "ready_for_review"
    v0 = brain(authed, pid)["version"]
    done = authed.post(D(pid, "/complete"), json={"accept_assumptions": True}).json()
    assert done["status"] == "completed" and done["next_step"]["key"] == "return_to_overview" and "not available yet" in done["next_step"]["note"]
    b = brain(authed, pid)
    unresolved = [a for a in b["brain"]["discovery"]["assumptions"] if a["source"] == "unanswered_question"]
    assert b["version"] == v0 + 1 and len(unresolved) == 4 and {a["status"] for a in unresolved} == {"unverified"}
    assert authed.get(f"/api/projects/{pid}/revisions").json()[0]["change_type"] == "discovery_completed"
    again = authed.post(D(pid, "/complete"), json={"accept_assumptions": True})  # idempotent: no duplicate assumptions
    assert again.status_code == 200 and brain(authed, pid)["version"] == v0 + 1
    qid = st["questions"][0]["id"]
    for r in (answer(authed, pid, qid, "x"), authed.post(D(pid, f"/questions/{qid}/skip")), authed.post(D(pid, "/next-round")), authed.post(D(pid, "/review"))):
        assert r.status_code == 409  # completed is terminal


def test_completing_with_everything_resolved_adds_no_assumptions(authed, provide):
    pid, _, st = started(authed, provide)
    for q in st["questions"]:
        v = {"free_text": "text", "single_choice": q["options"][0]["id"] if q["options"] else None,
             "multiple_choice": [q["options"][0]["id"]] if q["options"] else None, "confirmation": False}[q["qtype"]]
        assert answer(authed, pid, q["id"], v).status_code == 200
    authed.post(D(pid, "/review"))
    v0 = brain(authed, pid)["version"]
    assert authed.post(D(pid, "/complete"), json={}).json()["status"] == "completed"
    assert brain(authed, pid)["version"] == v0


def test_deleting_a_project_removes_its_discovery_data(authed, provide):
    pid, _, _ = started(authed, provide)
    assert count_rows(DiscoveryQuestion) == 5
    authed.delete(f"/api/projects/{pid}")
    assert count_rows(DiscoverySession) == 0 and count_rows(DiscoveryQuestion) == 0


@pytest.mark.skipif(not IS_PG, reason="row locking is PostgreSQL behavior")
def test_concurrent_answers_never_lose_updates(authed, provide):
    pid, _, st = started(authed, provide)
    qs = qmap(st)
    jar = dict(authed.cookies)

    def submit(target, value):
        with TestClient(app, cookies=jar) as c:
            return c.post(D(pid, "/answers"), json={"answers": [{"question_id": qs[target]["id"], "value": value}]}).status_code
    with ThreadPoolExecutor(2) as ex:
        codes = list(ex.map(lambda a: submit(*a), [("target_users", "Photographers"), ("business_model", "Commission")]))
    assert set(codes) <= {200, 409}
    facts = brain(authed, pid)["brain"]["discovery"]["confirmed"]
    assert len(facts) == codes.count(200) >= 1  # every acknowledged answer is stored; none silently overwritten
    versions = sorted(r["version"] for r in authed.get(f"/api/projects/{pid}/revisions").json())
    assert versions == list(range(1, len(versions) + 1))
