"""Phase 10 tests: Product Strategy, PRD, lifecycle stage progression, provenance, versioning, ownership, and DB constraints."""
import pytest
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app import ai
from app.lifecycle import STAGES, STAGE_DEPS, next_action, unmet_deps
from app.models import PrdDocument, StrategyDocument, uid
from app.prd import GeneratedPrd
from app.research import GeneratedResearch
from app.strategy import GeneratedStrategy
from fastapi.testclient import TestClient
from app.db import SessionLocal
from app.main import app

def auth(client, email: str = "founder@example.com") -> dict[str, str]:
    r = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    if r.status_code != 201:
        r = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return {}



def _research_payload() -> dict:
    return {
        "objectives": ["Understand how small agencies scope fixed-price projects"],
        "research_questions": ["What causes scope creep in agency retainers?"],
        "scope_in": ["Boutique digital agencies under 25 staff"],
        "scope_out": ["Enterprise ERP consulting"],
        "findings": [
            {
                "topic": "user_needs",
                "statement": "Agencies need a fast way to turn client intake notes into explicit scope boundaries.",
                "detail": "Informal email threads hide out-of-scope requests until delivery.",
                "evidence": "hypothesis",
            },
            {
                "topic": "opportunities",
                "statement": "Link approved deliverables directly to change-request workflows.",
                "detail": "Reduces disputes when clients ask for extra revisions.",
                "evidence": "ai_suggestion",
            },
        ],
        "unresolved_questions": ["Which project management tools require day-one export?"],
    }


def _strategy_payload(confirmed_ref: str | None = None) -> dict:
    ref1 = confirmed_ref or "idea-problem"
    return {
        "product_vision": "Help small agencies scope, price, and defend fixed-fee client engagements with zero ambiguity.",
        "value_proposition": "Turn messy client discovery notes into traceable scope boundaries and change-order guardrails.",
        "differentiation": " Focuses on scope provenance and client sign-off rather than generic task tracking.",
        "business_model": "Tiered monthly workspace subscription per active agency team.",
        "goals": [
            {
                "goal": "Reduce unbilled scope creep on fixed-fee agency projects",
                "rationale": "Directly addresses the core agency margin problem.",
                "supporting_refs": [ref1, "res-f-1"],
            }
        ],
        "target_users": [
            {
                "segment": "Boutique digital agency founders and account leads",
                "needs": "Clear scope baselines and rapid client sign-off before kickoff.",
                "supporting_refs": ["user-1", "res-f-1"],
            }
        ],
        "mvp_scope": [
            {
                "item": "Guided scope baseline builder with explicit in/out boundaries",
                "boundary": "in_mvp",
                "rationale": "Core workflow required to validate value proposition.",
                "supporting_refs": [ref1, "res-f-2"],
            },
            {
                "item": "Client-facing change request approval portal",
                "boundary": "post_mvp",
                "rationale": "Valuable expansion after agencies adopt internal scoping.",
                "supporting_refs": ["res-f-2"],
            },
            {
                "item": "Full accounting and payroll suite",
                "boundary": "out_of_scope",
                "rationale": "Handled by existing accounting software.",
                "supporting_refs": [],
            },
        ],
        "success_metrics": [
            {
                "metric": "Time from discovery call to signed scope baseline",
                "target_direction": "Decrease turnaround time across pilot agencies",
                "supporting_refs": [ref1],
            }
        ],
        "recommendations": [
            {
                "area": "mvp_scope",
                "title": "Prioritize traceable scope boundaries in MVP",
                "recommendation": "Launch with structured scope baselines linked to client intake notes before building billing.",
                "rationale": "Solves the primary pain point identified in research findings.",
                "status": "supported_by_research",
                "supporting_refs": ["res-f-1", "res-f-2"],
            },
            {
                "area": "business_model",
                "title": "Seat-independent agency workspace pricing",
                "recommendation": "Price by active client engagements rather than per-seat licenses.",
                "rationale": "Encourages whole-team adoption across project managers.",
                "status": "ai_suggestion",
                "supporting_refs": [ref1],
            },
        ],
        "risks": [
            {
                "risk": "Agencies may resist switching from spreadsheet templates",
                "mitigation": "Provide one-click import and clean PDF/link export for client sign-off.",
                "supporting_refs": ["res-f-1"],
            }
        ],
        "constraints": ["Must support fast browser-based review without client login"],
        "open_decisions": [
            {
                "question": "Should MVP include e-signature or simple checkbox acknowledgement?",
                "impact": "Affects legal weight vs implementation speed.",
            }
        ],
    }


def _prd_payload() -> dict:
    return {
        "problem_statement": "Boutique agencies lose margin on fixed-fee projects because client intake notes are not translated into enforceable scope boundaries.",
        "target_users": ["Boutique digital agency founders", "Agency account and delivery leads"],
        "user_stories": [
            {
                "persona": "Agency founder",
                "action": "capture in-scope deliverables and explicit exclusions in a single baseline",
                "benefit": "clients understand exactly what is included before work starts",
                "priority": "must_have",
                "source_refs": ["sg-1", "su-1", "mvp-1"],
            },
            {
                "persona": "Account lead",
                "action": "flag out-of-scope client requests against the approved baseline",
                "benefit": "additional work is routed to a paid change request",
                "priority": "should_have",
                "source_refs": ["rec-1", "res-f-2"],
            },
        ],
        "functional_requirements": [
            {
                "title": "Scope Baseline Editor",
                "description": "Allow agency users to create, version, and publish structured project scope baselines with in-scope and out-of-scope lists.",
                "priority": "must_have",
                "mvp_boundary": "in_mvp",
                "user_story_indices": [1],
                "source_refs": ["sg-1", "mvp-1", "rec-1"],
                "acceptance_criteria": [
                    "User can add, edit, and reorder in-scope deliverables and explicit out-of-scope exclusions.",
                    "Publishing a baseline locks the version and generates a shareable read-only review view.",
                ],
                "edge_cases": [
                    "Attempting to publish a baseline with zero in-scope items returns a validation error."
                ],
                "dependencies": ["Project workspace authentication"],
            },
            {
                "title": "Scope Provenance Links",
                "description": "Link each scope deliverable to the discovery notes or client inputs that justified it.",
                "priority": "should_have",
                "mvp_boundary": "in_mvp",
                "user_story_indices": [1, 2],
                "source_refs": ["rec-1", "res-f-1"],
                "acceptance_criteria": [
                    "Each scope item displays its linked intake note or an unlinked warning badge.",
                ],
                "edge_cases": [
                    "Deleting a referenced note warns the user before unlinking dependent scope items."
                ],
                "dependencies": ["Scope Baseline Editor"],
            },
        ],
        "non_functional_requirements": [
            {
                "category": "security",
                "title": "Workspace Tenant Isolation",
                "description": "Ensure scope baselines and client notes are strictly isolated to the owning agency workspace.",
                "priority": "must_have",
                "mvp_boundary": "in_mvp",
                "source_refs": ["sr-1"],
                "acceptance_criteria": [
                    "Requests for another user's project scope baseline return HTTP 404.",
                ],
            }
        ],
        "mvp_boundaries": {
            "in_mvp": ["Scope Baseline Editor", "Scope Provenance Links"],
            "post_mvp": ["Client change-order billing portal"],
            "out_of_scope": ["Full accounting and payroll suite"],
        },
        "dependencies": ["Authentication service", "PostgreSQL persistence"],
        "risks": [
            {
                "risk": "Users write overly vague scope items",
                "mitigation": "Provide structured fields for deliverable acceptance criteria and exclusions.",
            }
        ],
        "open_questions": ["Do agencies need PDF export in MVP or is a web view sufficient?"],
    }


class StubPhase10Provider(ai.AIProvider):
    def __init__(self, research_data=None, strategy_data=None, prd_data=None, fail: Exception | None = None):
        self.research_data = research_data or _research_payload()
        self.strategy_data = strategy_data or _strategy_payload()
        self.prd_data = prd_data or _prd_payload()
        self.fail = fail
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        return '{}'

    async def generate_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        self.prompts.append(prompt)
        if self.fail:
            raise self.fail
        if schema is GeneratedResearch:
            return schema.model_validate(self.research_data)
        if schema is GeneratedStrategy:
            return schema.model_validate(self.strategy_data)
        if schema is GeneratedPrd:
            return schema.model_validate(self.prd_data)
        raise AssertionError(f"Unexpected schema {schema}")


def _setup_project_with_approved_research(client, monkeypatch, email="founder@example.com"):
    h = auth(client, email)
    pid = client.post("/api/projects", json={"name": "ScopeGuard", "description": "Agency scope protection"}, headers=h).json()["id"]
    client.put(
        f"/api/projects/{pid}/brain/idea",
        json={
            "value": {
                "raw": "A scope management platform for boutique digital agencies to prevent unbilled scope creep.",
                "product_name": "ScopeGuard",
                "product_type": "B2B SaaS",
                "problem": "Agencies lose profit when informal client requests expand fixed-fee scope.",
                "features": ["Scope baseline builder", "Change request log"],
                "assumptions": ["Agencies will log scope items before kickoff"],
                "open_questions": ["Which PM tools need integration?"],
            }
        },
        headers=h,
    )
    client.put(f"/api/projects/{pid}/brain/target_users", json={"value": ["Boutique agency founders"]}, headers=h)
    client.put(f"/api/projects/{pid}/brain/goals", json={"value": ["Protect agency project margins"]}, headers=h)

    stub = StubPhase10Provider()
    monkeypatch.setattr(ai, "get_provider", lambda: stub)

    gen = client.post(f"/api/projects/{pid}/research/generate", json={}, headers=h)
    assert gen.status_code == 200
    r_hash = gen.json()["current"]["content_hash"]
    sub = client.post(f"/api/projects/{pid}/research/reports/1/submit", json={"base_hash": r_hash}, headers=h)
    assert sub.status_code == 200
    app = client.post(
        f"/api/projects/{pid}/research/reports/1/approve",
        json={"content_hash": r_hash, "acknowledge_unverified": True, "note": "Approved preliminary research"},
        headers=h,
    )
    assert app.status_code == 200
    return h, pid, stub


def test_lifecycle_mapping_and_next_action_progression():
    assert len(STAGES) == 19
    assert STAGES[0] == "research"
    assert STAGES[1] == "product"
    assert STAGE_DEPS["product"] == ["research"]
    assert STAGE_DEPS["ux"] == ["product"]

    statuses = {s: "not_started" for s in STAGES}
    assert next_action(statuses) == "research"

    statuses["research"] = "complete"
    assert next_action(statuses) == "product"

    statuses["product"] = "in_progress"
    assert next_action(statuses) == "product"

    statuses["product"] = "needs_review"
    assert next_action(statuses) == "product"

    statuses["product"] = "complete"
    assert next_action(statuses) == "ux"
    assert unmet_deps("ux", statuses) == []


def test_strategy_preconditions_require_idea_and_approved_research(client, monkeypatch):
    h = auth(client)
    pid = client.post("/api/projects", json={"name": "EmptyProj"}, headers=h).json()["id"]
    stub = StubPhase10Provider()
    monkeypatch.setattr(ai, "get_provider", lambda: stub)

    st0 = client.get(f"/api/projects/{pid}/strategy", headers=h).json()
    assert st0["status"] == "not_started"
    assert st0["idea_ready"] is False
    assert st0["research_ready"] is False
    assert st0["can_generate"] is False
    assert st0["next_step"]["key"] == "describe_idea"

    r = client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h)
    assert r.status_code == 409
    assert "idea" in r.json()["detail"].lower()

    client.put(f"/api/projects/{pid}/brain/idea", json={"value": {"raw": "An agency scoping assistant for fixed-fee teams."}}, headers=h)
    st1 = client.get(f"/api/projects/{pid}/strategy", headers=h).json()
    assert st1["idea_ready"] is True
    assert st1["research_ready"] is False
    assert st1["next_step"]["key"] == "complete_research"

    r2 = client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h)
    assert r2.status_code == 409
    assert "research" in r2.json()["detail"].lower()


def test_strategy_generation_provenance_and_numeric_downgrade(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_research(client, monkeypatch)

    bad_strategy = _strategy_payload()
    bad_strategy["recommendations"].append(
        {
            "area": "market_context" if False else "differentiation",
            "title": "Capture 45% of the $12 billion agency market",
            "recommendation": "Target a 45% market share within 12 months across 10,000 agencies.",
            "rationale": "Large market opportunity.",
            "status": "ai_suggestion",
            "supporting_refs": ["res-f-1"],
        }
    )
    bad_strategy["recommendations"].append(
        {
            "area": "risks",
            "title": "Ungrounded claim pretending to be confirmed",
            "recommendation": "Require enterprise SSO on all free plans.",
            "rationale": "Guessed without any supporting input.",
            "status": "grounded_in_confirmed",
            "supporting_refs": [],
        }
    )
    monkeypatch.setattr(ai, "get_provider", lambda: StubPhase10Provider(strategy_data=bad_strategy))

    res = client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h)
    assert res.status_code == 200
    state = res.json()
    assert state["status"] == "draft"
    doc = state["current"]
    assert doc["version"] == 1

    recs = {r["title"]: r for r in doc["content"]["recommendations"]}
    num_rec = recs["Capture 45% of the $12 billion agency market"]
    assert num_rec["status"] == "unsupported"
    assert num_rec["needs_evidence"] is True
    assert "numeric" in (num_rec["note"] or "").lower()

    ungrounded = recs["Ungrounded claim pretending to be confirmed"]
    assert ungrounded["status"] == "unsupported"
    assert ungrounded["needs_evidence"] is True
    assert doc["unsupported_count"] == 2
    assert any(w["code"] == "unsupported" for w in doc["warnings"])


def test_strategy_url_in_ai_output_fails_closed(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_research(client, monkeypatch)
    url_strategy = _strategy_payload()
    url_strategy["product_vision"] = "See https://example.com/report for details on our product vision."
    monkeypatch.setattr(ai, "get_provider", lambda: StubPhase10Provider(strategy_data=url_strategy))

    res = client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h)
    assert res.status_code == 502
    st = client.get(f"/api/projects/{pid}/strategy", headers=h).json()
    assert st["status"] == "failed"
    assert st["current"] is None


def test_strategy_edits_versioning_approval_and_brain_provenance(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_research(client, monkeypatch)
    brain_before = client.get(f"/api/projects/{pid}/brain", headers=h).json()

    gen = client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h).json()
    v1_hash = gen["current"]["content_hash"]

    # Invalid supporting_refs rejected
    bad_rec = client.post(
        f"/api/projects/{pid}/strategy/versions/1/recommendations",
        json={
            "base_hash": v1_hash,
            "area": "vision",
            "title": "Bad ref recommendation",
            "recommendation": "Use a nonexistent input reference.",
            "rationale": "Testing validation.",
            "status": "ai_suggestion",
            "supporting_refs": ["nonexistent-ref"],
        },
        headers=h,
    )
    assert bad_rec.status_code == 422

    # Valid edit updates content_hash
    patched = client.patch(
        f"/api/projects/{pid}/strategy/versions/1/overview",
        json={"base_hash": v1_hash, "product_vision": "Updated vision: eliminate fixed-fee agency scope disputes."},
        headers=h,
    )
    assert patched.status_code == 200
    new_hash = patched.json()["document"]["content_hash"]
    assert new_hash != v1_hash

    # Stale hash rejected
    stale = client.patch(
        f"/api/projects/{pid}/strategy/versions/1/overview",
        json={"base_hash": v1_hash, "product_vision": "Should fail with 409."},
        headers=h,
    )
    assert stale.status_code == 409

    # Submit for review
    sub = client.post(f"/api/projects/{pid}/strategy/versions/1/submit", json={"base_hash": new_hash}, headers=h)
    assert sub.status_code == 200
    assert sub.json()["status"] == "in_review"
    assert sub.json()["lifecycle"]["status"] == "needs_review"

    # Approval requires acknowledging unverified recommendations
    no_ack = client.post(
        f"/api/projects/{pid}/strategy/versions/1/approve",
        json={"content_hash": new_hash, "acknowledge_unverified": False},
        headers=h,
    )
    assert no_ack.status_code == 409

    # Approve v1
    app = client.post(
        f"/api/projects/{pid}/strategy/versions/1/approve",
        json={"content_hash": new_hash, "acknowledge_unverified": True, "note": "Strategy v1 approved"},
        headers=h,
    )
    assert app.status_code == 200
    app_state = app.json()
    assert app_state["status"] == "approved"
    assert app_state["approved_version"] == 1
    # Product stage is in_progress (not complete!) because PRD is not approved yet
    assert app_state["lifecycle"]["status"] == "in_progress"

    brain_after = client.get(f"/api/projects/{pid}/brain", headers=h).json()
    assert brain_after["brain"]["idea"] == brain_before["brain"]["idea"]
    assert brain_after["brain"]["discovery"] == brain_before["brain"]["discovery"]
    assert brain_after["brain"]["strategy"]["approved_version"] == 1
    assert brain_after["brain"]["strategy"]["content_hash"] == new_hash

    # Protected section cannot be overwritten via generic brain endpoint
    forbid = client.put(f"/api/projects/{pid}/brain/strategy", json={"value": {"approved_version": 99}}, headers=h)
    assert forbid.status_code == 403

    # Editing approved v1 creates v2 via copy-on-write and leaves v1 immutable
    cow = client.post(
        f"/api/projects/{pid}/strategy/versions/1/recommendations",
        json={
            "base_hash": new_hash,
            "area": "goals",
            "title": "Add pilot agency onboarding goal",
            "recommendation": "Onboard five pilot agencies with white-glove template setup.",
            "rationale": "Reduces initial template switching friction.",
            "status": "supported_by_research",
            "supporting_refs": ["res-f-1"],
        },
        headers=h,
    )
    assert cow.status_code == 200
    assert cow.json()["document"]["version"] == 2
    assert cow.json()["document"]["status"] == "draft"
    assert cow.json()["document"]["created_via"] == "copy_of_approved"
    assert cow.json()["document"]["parent_version"] == 1

    v1_still = client.get(f"/api/projects/{pid}/strategy/versions/1", headers=h).json()
    assert v1_still["status"] == "approved"
    assert v1_still["content_hash"] == new_hash


def test_prd_workflow_validation_approval_and_product_stage_completion(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_research(client, monkeypatch)

    # PRD cannot be generated before Strategy is approved
    pre = client.post(f"/api/projects/{pid}/prd/generate", json={}, headers=h)
    assert pre.status_code == 409

    # Generate and approve Strategy v1
    s_gen = client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h).json()
    s_hash = s_gen["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/strategy/versions/1/submit", json={"base_hash": s_hash}, headers=h)
    client.post(
        f"/api/projects/{pid}/strategy/versions/1/approve",
        json={"content_hash": s_hash, "acknowledge_unverified": True},
        headers=h,
    )

    # Generate PRD v1
    p_gen = client.post(f"/api/projects/{pid}/prd/generate", json={}, headers=h)
    assert p_gen.status_code == 200
    p_state = p_gen.json()
    assert p_state["status"] == "draft"
    doc = p_state["current"]
    assert doc["version"] == 1
    assert doc["content"]["functional_requirements"][0]["id"] == "FR-1"
    assert doc["content"]["functional_requirements"][0]["status"] == "proposed"
    assert doc["content"]["non_functional_requirements"][0]["id"] == "NFR-1"
    p_hash = doc["content_hash"]

    # Reject vague acceptance criteria
    vague = client.post(
        f"/api/projects/{pid}/prd/versions/1/functional-requirements",
        json={
            "base_hash": p_hash,
            "title": "Fast Export",
            "description": "Export scope baseline to PDF quickly.",
            "priority": "should_have",
            "mvp_boundary": "in_mvp",
            "acceptance_criteria": ["Works well"],
        },
        headers=h,
    )
    assert vague.status_code == 422

    # Reject contradictory priority + mvp_boundary (must_have + out_of_scope)
    contra = client.post(
        f"/api/projects/{pid}/prd/versions/1/functional-requirements",
        json={
            "base_hash": p_hash,
            "title": "Contradictory Requirement",
            "description": "This requirement claims to be must_have but out_of_scope.",
            "priority": "must_have",
            "mvp_boundary": "out_of_scope",
            "acceptance_criteria": ["System returns an explicit validation error when invoked."],
        },
        headers=h,
    )
    assert contra.status_code == 422

    # Reject duplicate requirement title
    dup = client.post(
        f"/api/projects/{pid}/prd/versions/1/functional-requirements",
        json={
            "base_hash": p_hash,
            "title": "Scope Baseline Editor",
            "description": "Duplicate title of FR-1 should be rejected.",
            "priority": "should_have",
            "mvp_boundary": "in_mvp",
            "acceptance_criteria": ["User can edit the scope baseline with full version history."],
        },
        headers=h,
    )
    assert dup.status_code == 422

    # Manual completion of product stage is blocked while PRD is unapproved
    manual_block = client.put(f"/api/projects/{pid}/stages/product", json={"status": "complete"}, headers=h)
    assert manual_block.status_code == 409

    # Approve individual requirements (FR-1, FR-2, NFR-1)
    req_status = client.post(
        f"/api/projects/{pid}/prd/versions/1/requirements/status",
        json={"base_hash": p_hash, "requirement_ids": ["FR-1", "FR-2", "NFR-1"], "status": "approved"},
        headers=h,
    )
    assert req_status.status_code == 200
    p_hash2 = req_status.json()["document"]["content_hash"]
    assert req_status.json()["document"]["proposed_count"] == 0

    # Submit PRD v1 for review
    sub = client.post(f"/api/projects/{pid}/prd/versions/1/submit", json={"base_hash": p_hash2}, headers=h)
    assert sub.status_code == 200
    assert sub.json()["status"] == "in_review"
    assert sub.json()["lifecycle"]["status"] == "needs_review"

    # Approve PRD v1 -> since all requirements are approved and linked, acknowledge_unverified=False succeeds!
    app = client.post(
        f"/api/projects/{pid}/prd/versions/1/approve",
        json={"content_hash": p_hash2, "acknowledge_unverified": False, "note": "PRD v1 approved"},
        headers=h,
    )
    assert app.status_code == 200
    app_state = app.json()
    assert app_state["status"] == "approved"
    assert app_state["lifecycle"]["status"] == "complete"

    # Overview now shows 2 of 19 stages complete (research + product) and next_action == "ux"
    ov = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    assert set(ov["completed"]) == {"research", "product"}
    assert ov["progress"] == round(100 * 2 / 19)
    assert ov["next_action"] == "ux"

    # Brain has prd pointer and protected section guard works
    brain = client.get(f"/api/projects/{pid}/brain", headers=h).json()
    assert brain["brain"]["prd"]["approved_version"] == 1
    assert brain["brain"]["prd"]["strategy_version"] == 1
    assert brain["brain"]["prd"]["approved_requirement_count"] == 3
    assert client.put(f"/api/projects/{pid}/brain/prd", json={"value": {}}, headers=h).status_code == 403

    # Editing approved PRD creates v2 (copy-on-write) and reopens product stage to in_progress
    cow = client.post(
        f"/api/projects/{pid}/prd/versions/1/functional-requirements",
        json={
            "base_hash": p_hash2,
            "title": "Client Sign-Off Snapshot",
            "description": "Record client acknowledgement timestamp and content hash on published scope baselines.",
            "priority": "must_have",
            "mvp_boundary": "in_mvp",
            "source_refs": ["sg-1"],
            "acceptance_criteria": [
                "Client acknowledgement stores timestamp, signer name, and baseline content hash."
            ],
        },
        headers=h,
    )
    assert cow.status_code == 200
    assert cow.json()["document"]["version"] == 2
    assert cow.json()["document"]["status"] == "draft"
    assert cow.json()["state"]["lifecycle"]["status"] == "in_progress"

    ov2 = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    assert ov2["next_action"] == "product"


def test_ownership_isolation_and_failure_atomicity(client, monkeypatch):
    h1, pid, _ = _setup_project_with_approved_research(client, monkeypatch, email="owner1@example.com")
    other = TestClient(app)
    h2 = auth(other, "intruder@example.com")

    # Generate Strategy v1 as owner
    s_gen = client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h1)
    assert s_gen.status_code == 200

    # Other user gets 404 across Strategy and PRD endpoints
    assert other.get(f"/api/projects/{pid}/strategy", headers=h2).status_code == 404
    assert other.post(f"/api/projects/{pid}/strategy/generate", json={"supersede": True}, headers=h2).status_code == 404
    assert other.get(f"/api/projects/{pid}/prd", headers=h2).status_code == 404
    assert other.post(f"/api/projects/{pid}/prd/generate", json={}, headers=h2).status_code == 404

    # Provider failure during regeneration leaves existing approved Strategy and Brain untouched
    s_hash = s_gen.json()["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/strategy/versions/1/submit", json={"base_hash": s_hash}, headers=h1)
    client.post(f"/api/projects/{pid}/strategy/versions/1/approve", json={"content_hash": s_hash, "acknowledge_unverified": True}, headers=h1)
    brain_v = client.get(f"/api/projects/{pid}/brain", headers=h1).json()["version"]

    monkeypatch.setattr(ai, "get_provider", lambda: StubPhase10Provider(fail=ai.ProviderError("Request timed out", category="timeout")))
    fail_res = client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h1)
    assert fail_res.status_code == 502
    assert client.get(f"/api/projects/{pid}/brain", headers=h1).json()["version"] == brain_v

    # Retry reuses the failed version 2 row rather than creating version 3
    monkeypatch.setattr(ai, "get_provider", lambda: StubPhase10Provider())
    retry_res = client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h1)
    assert retry_res.status_code == 200
    assert retry_res.json()["current"]["version"] == 2


def test_db_partial_unique_indexes_for_strategy_and_prd(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_research(client, monkeypatch)
    user_id = "u-test"
    with SessionLocal() as db_session:
        s1 = StrategyDocument(project_id=pid, version=1, status="draft", basis={}, created_by=user_id, row_version=1)
        s2 = StrategyDocument(project_id=pid, version=2, status="in_review", basis={}, created_by=user_id, row_version=1)
        db_session.add_all([s1, s2])
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

        p1 = PrdDocument(project_id=pid, version=1, status="generating", basis={}, created_by=user_id, row_version=1)
        p2 = PrdDocument(project_id=pid, version=2, status="generating", basis={}, created_by=user_id, row_version=1)
        db_session.add_all([p1, p2])
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


def test_complete_phase_9_and_10_end_to_end_workflow(client, monkeypatch):
    """Verifies the complete 10-step workflow from project creation & AI intake through Discovery, Research,
    Strategy, and PRD approval, stage progression, Brain provenance, and copy-on-write immutability."""
    from app.brain import IntakeResult
    from app.discovery import DiscoveryRound

    class FullWorkflowProvider(StubPhase10Provider):
        async def generate_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
            if schema is IntakeResult:
                return IntakeResult(
                    product_name="ScopeGuard",
                    product_type="B2B SaaS",
                    problem="Boutique agencies lose margin when informal client requests expand fixed-fee project scope.",
                    target_users=["Boutique digital agency founders"],
                    goals=["Reduce unbilled scope creep"],
                    features=["Scope baseline builder", "Change request log"],
                    assumptions=["Clients will review scope baselines in a browser"],
                    questions=["What billing model will you use?"],
                )
            if schema is DiscoveryRound:
                return DiscoveryRound.model_validate({
                    "questions": [
                        {
                            "prompt": "How will you charge agencies for ScopeGuard?",
                            "rationale": "Clarifies the business model before strategy and PRD.",
                            "target": "business_model",
                            "qtype": "free_text",
                            "options": [],
                            "required": True,
                            "priority": 1,
                        }
                    ]
                })
            return await super().generate_structured(prompt, schema)

    monkeypatch.setattr(ai, "get_provider", lambda: FullWorkflowProvider())
    h = auth(client, "e2e-founder@example.com")

    # 1. Project creation and AI intake
    proj = client.post("/api/projects", json={"name": "ScopeGuard E2E", "description": "End-to-end verification"}, headers=h).json()
    pid = proj["id"]
    ov0 = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    assert ov0["progress"] == 0
    assert ov0["completed"] == []
    assert ov0["next_action"] == "research"

    intake_res = client.post(
        f"/api/projects/{pid}/intake",
        json={"idea": "A B2B SaaS tool that helps boutique digital agencies turn client intake notes into enforceable scope baselines."},
        headers=h,
    )
    assert intake_res.status_code == 200
    assert intake_res.json()["version"] == 2
    assert client.get(f"/api/projects/{pid}/overview", headers=h).json()["progress"] == 0

    # 2. Discovery and Brain revision persistence
    disc_start = client.post(f"/api/projects/{pid}/discovery", headers=h)
    assert disc_start.status_code == 200
    qid = disc_start.json()["questions"][0]["id"]
    ans = client.post(
        f"/api/projects/{pid}/discovery/answers",
        json={"answers": [{"question_id": qid, "value": "Tiered monthly workspace subscription"}]},
        headers=h,
    )
    assert ans.status_code == 200
    rev_disc = client.post(f"/api/projects/{pid}/discovery/review", headers=h)
    assert rev_disc.status_code == 200
    comp_disc = client.post(f"/api/projects/{pid}/discovery/complete", json={"accept_assumptions": True}, headers=h)
    assert comp_disc.status_code == 200
    assert comp_disc.json()["status"] == "completed"
    # Discovery completion writes Brain revision v4 but does NOT complete any lifecycle stage
    brain_after_disc = client.get(f"/api/projects/{pid}/brain", headers=h).json()
    assert brain_after_disc["version"] >= 3
    assert len(brain_after_disc["brain"]["discovery"]["confirmed"]) == 1
    assert client.get(f"/api/projects/{pid}/overview", headers=h).json()["completed"] == []

    # 3. Research draft generation, evidence handling, editing, review, and approval
    r_gen = client.post(f"/api/projects/{pid}/research/generate", json={}, headers=h)
    assert r_gen.status_code == 200
    r_hash1 = r_gen.json()["current"]["content_hash"]
    # Add examined source and upgrade f-1 to verified_source
    add_src = client.post(
        f"/api/projects/{pid}/research/reports/1/sources",
        json={
            "base_hash": r_hash1,
            "title": "Agency Scope Benchmark Study",
            "url": "https://example.org/agency-benchmark",
            "publisher": "Agency Ops Institute",
            "accessed_on": "2026-04-01",
            "examined": True,
            "note": "Reviewed section 3 on scope disputes",
        },
        headers=h,
    )
    assert add_src.status_code == 200
    r_hash2 = add_src.json()["report"]["content_hash"]
    up_f1 = client.patch(
        f"/api/projects/{pid}/research/reports/1/findings/f-1",
        json={
            "base_hash": r_hash2,
            "evidence": "verified_source",
            "citations": [{"source_id": "src-1", "claim": "Informal client intake threads cause scope disputes"}],
        },
        headers=h,
    )
    assert up_f1.status_code == 200
    r_hash3 = up_f1.json()["report"]["content_hash"]
    client.post(f"/api/projects/{pid}/research/reports/1/submit", json={"base_hash": r_hash3}, headers=h)
    r_app = client.post(
        f"/api/projects/{pid}/research/reports/1/approve",
        json={"content_hash": r_hash3, "acknowledge_unverified": True, "note": "Research v1 verified"},
        headers=h,
    )
    assert r_app.status_code == 200
    ov1 = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    assert ov1["completed"] == ["research"]
    assert ov1["progress"] == round(100 * 1 / 19)
    assert ov1["next_action"] == "product"

    # 4 & 5. Strategy generation using approved Research v1, review, and approval
    s_gen = client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h)
    assert s_gen.status_code == 200
    s_doc = s_gen.json()["current"]
    assert s_doc["basis"]["research_version"] == 1
    assert any(x["ref_id"] == f"fact-{qid}" for x in s_doc["content"]["inputs"]["confirmed_facts"])
    s_hash = s_doc["content_hash"]
    client.post(f"/api/projects/{pid}/strategy/versions/1/submit", json={"base_hash": s_hash}, headers=h)
    s_app = client.post(
        f"/api/projects/{pid}/strategy/versions/1/approve",
        json={"content_hash": s_hash, "acknowledge_unverified": True, "note": "Strategy v1 approved"},
        headers=h,
    )
    assert s_app.status_code == 200
    assert s_app.json()["lifecycle"]["status"] == "in_progress"

    # 6 & 7. PRD generation using approved Strategy v1, requirement approval, and PRD approval
    p_gen = client.post(f"/api/projects/{pid}/prd/generate", json={}, headers=h)
    assert p_gen.status_code == 200
    p_doc = p_gen.json()["current"]
    assert p_doc["basis"]["strategy_version"] == 1
    assert p_doc["basis"]["research_version"] == 1
    p_hash = p_doc["content_hash"]
    req_ok = client.post(
        f"/api/projects/{pid}/prd/versions/1/requirements/status",
        json={"base_hash": p_hash, "requirement_ids": ["FR-1", "FR-2", "NFR-1"], "status": "approved"},
        headers=h,
    )
    assert req_ok.status_code == 200
    p_hash2 = req_ok.json()["document"]["content_hash"]
    client.post(f"/api/projects/{pid}/prd/versions/1/submit", json={"base_hash": p_hash2}, headers=h)
    p_app = client.post(
        f"/api/projects/{pid}/prd/versions/1/approve",
        json={"content_hash": p_hash2, "acknowledge_unverified": False, "note": "PRD v1 approved"},
        headers=h,
    )
    assert p_app.status_code == 200
    assert p_app.json()["lifecycle"]["status"] == "complete"

    # 8. Verify lifecycle progress (2/19 = 11%) and next_action == "ux" (Phase 11 unblocked)
    ov2 = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    assert set(ov2["completed"]) == {"research", "product"}
    assert ov2["progress"] == round(100 * 2 / 19)
    assert ov2["next_action"] == "ux"
    ux_stage = next(s for s in ov2["stages"] if s["stage"] == "ux")
    assert ux_stage["unmet_dependencies"] == []

    # 9. Verify stale Strategy guard: if Strategy v2 is created and approved, Product stage reopens until PRD is updated
    s_gen2 = client.post(f"/api/projects/{pid}/strategy/generate", json={"supersede": True}, headers=h).json()
    assert s_gen2["current"]["version"] == 2
    assert s_gen2["lifecycle"]["status"] == "in_progress"
    s2_hash = s_gen2["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/strategy/versions/2/submit", json={"base_hash": s2_hash}, headers=h)
    client.post(f"/api/projects/{pid}/strategy/versions/2/approve", json={"content_hash": s2_hash, "acknowledge_unverified": True}, headers=h)

    prd_stale = client.get(f"/api/projects/{pid}/prd", headers=h).json()
    assert prd_stale["lifecycle"]["status"] == "in_progress"
    assert prd_stale["next_step"]["key"] == "stale_strategy"
    assert any(w["code"] == "stale_strategy" for w in prd_stale["current"]["warnings"])
