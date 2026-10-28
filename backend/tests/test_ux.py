"""Phase 11 tests: Personas, User Journeys, Information Architecture, Wireframes, UX Review,
upstream staleness gates, IA tree cycle checks, copy-on-write, ownership, and `ux` stage completion."""
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app import ai
from app.db import SessionLocal
from app.main import app
from app.models import UxArtifact
from app.prd import GeneratedPrd
from app.research import GeneratedResearch
from app.strategy import GeneratedStrategy
from app.ux import (
    GeneratedIa,
    GeneratedJourneys,
    GeneratedPersonas,
    GeneratedUxReview,
    GeneratedWireframes,
)
from tests.test_strategy_prd import (
    StubPhase10Provider,
    _prd_payload,
    _research_payload,
    _strategy_payload,
    auth,
)


def _personas_payload() -> dict:
    return {
        "personas": [
            {
                "name": "Maya Lin — Agency Founder",
                "segment": "Boutique digital agency founders",
                "context": "Runs a 12-person agency managing fixed-fee web and brand engagements.",
                "goals": ["Eliminate unbilled scope creep before kickoff"],
                "tasks_behaviors": ["Reviews discovery call notes and drafts project scope baselines"],
                "needs_pain_points": ["Client email requests blur what was included in the fixed fee"],
                "frustrations_barriers": ["Spreadsheet scope sheets get out of sync quickly"],
                "accessibility_device_notes": [
                    "Reviews baselines on laptop and mobile between client calls; requires full keyboard navigation"
                ],
                "motivations": ["Protect agency delivery margins and client trust"],
                "user_story_ids": ["US-1"],
                "prd_requirement_ids": ["FR-1", "NFR-1"],
                "evidence_refs": ["res-f-1", "sg-1"],
                "unverified_assumptions": ["Founders will require clients to acknowledge exclusions before kickoff"],
                "evidence_status": "mixed",
            },
            {
                "name": "Devon Brooks — Account Lead",
                "segment": "Agency account and delivery leads",
                "context": "Coordinates day-to-day client communication and flags out-of-scope requests.",
                "goals": ["Route extra client requests into structured change orders"],
                "tasks_behaviors": ["Links client asks back to approved scope items"],
                "needs_pain_points": ["Needs fast provenance links to show why a request is out of scope"],
                "frustrations_barriers": ["Searching through old threads during live client calls"],
                "accessibility_device_notes": ["Uses high-contrast mode and keyboard shortcuts during screen shares"],
                "motivations": ["Avoid awkward scope arguments with clients"],
                "user_story_ids": ["US-1", "US-2"],
                "prd_requirement_ids": ["FR-2"],
                "evidence_refs": ["res-f-2", "rec-1"],
                "unverified_assumptions": [],
                "evidence_status": "mixed",
            },
        ]
    }


def _journeys_payload() -> dict:
    return {
        "journeys": [
            {
                "title": "Create and Publish Scope Baseline",
                "persona_id": "P-1",
                "scenario": "Maya turns discovery notes into a published scope baseline with explicit exclusions.",
                "desired_outcome": "Client reviews and acknowledges the locked scope baseline before project kickoff.",
                "entry_point": "Project workspace dashboard after discovery intake",
                "preconditions": ["Project workspace created", "Client intake notes recorded"],
                "stages": [
                    {
                        "stage_name": "Draft Scope Items & Exclusions",
                        "user_actions": ["Add in-scope deliverables and explicit out-of-scope exclusions"],
                        "thoughts_questions": ["Did I capture every exclusion that caused scope creep last quarter?"],
                        "touchpoints": ["Scope Baseline Editor"],
                        "pain_points": ["Manually linking each deliverable to intake notes can feel repetitive"],
                        "system_responses": ["Validates deliverable fields and links each item to intake notes"],
                        "failure_recovery_paths": [
                            "If user attempts to publish with zero in-scope deliverables, show inline error and focus first empty list"
                        ],
                    },
                    {
                        "stage_name": "Publish & Share Read-Only Baseline",
                        "user_actions": ["Lock baseline version and copy client review link"],
                        "thoughts_questions": ["Can the client view this without creating an account?"],
                        "touchpoints": ["Baseline Publish Modal"],
                        "pain_points": ["Worried about editing after sending link"],
                        "system_responses": ["Locks v1 snapshot and generates a read-only review view"],
                        "failure_recovery_paths": [
                            "If network drops during publish, preserve draft state and allow retry without duplicate version"
                        ],
                    },
                ],
                "accessibility_considerations": [
                    "Keyboard reordering for scope items and focus trap inside publish confirmation modal"
                ],
                "prd_requirement_ids": ["FR-1", "NFR-1"],
                "opportunities": ["Pre-suggest common agency exclusions from intake notes"],
                "unresolved_questions": ["Should published baselines support password protection?"],
            },
            {
                "title": "Trace Client Request to Scope Provenance",
                "persona_id": "P-2",
                "scenario": "Devon checks whether a client request is covered by the signed baseline and links provenance.",
                "desired_outcome": "Out-of-scope request is clearly identified with linked intake provenance.",
                "entry_point": "Published Scope Baseline view",
                "preconditions": ["Scope baseline v1 published"],
                "stages": [
                    {
                        "stage_name": "Inspect Provenance & Flag Exclusion",
                        "user_actions": ["Filter baseline items and open linked discovery note"],
                        "thoughts_questions": ["Which intake note justified this boundary?"],
                        "touchpoints": ["Scope Provenance Drawer"],
                        "pain_points": ["Unlinked items lack context"],
                        "system_responses": ["Displays linked intake note or unlinked warning badge"],
                        "failure_recovery_paths": [
                            "If a referenced intake note is deleted, warn user before unlinking dependent scope items"
                        ],
                    }
                ],
                "accessibility_considerations": ["Provenance badges expose full text to screen readers via aria-label"],
                "prd_requirement_ids": ["FR-2"],
                "opportunities": ["One-click draft change request from an exclusion item"],
                "unresolved_questions": [],
            },
        ]
    }


def _ia_payload() -> dict:
    return {
        "navigation_model": {
            "primary_nav": ["Projects Dashboard", "Scope Baselines", "Provenance & Notes"],
            "secondary_nav": ["Baseline History", "Client Review Preview"],
            "utility_nav": ["Workspace Settings", "Account"],
        },
        "nodes": [
            {
                "id": "IA-1",
                "name": "Projects Dashboard",
                "path": "/projects",
                "parent_id": None,
                "order": 1,
                "purpose": "List active agency engagements and baseline status.",
                "navigation_group": "primary",
                "content_groups": ["Active projects list", "Baseline status summary"],
                "key_actions": ["Create project", "Open scope baseline"],
                "access_role": "Agency member",
                "prd_requirement_ids": ["FR-1", "NFR-1"],
            },
            {
                "id": "IA-2",
                "name": "Scope Baseline Editor",
                "path": "/projects/:id/baseline",
                "parent_id": "IA-1",
                "order": 1,
                "purpose": "Author, reorder, and publish in-scope deliverables and explicit exclusions.",
                "navigation_group": "primary",
                "content_groups": ["In-scope deliverables", "Explicit exclusions", "Publish controls"],
                "key_actions": ["Add deliverable", "Add exclusion", "Publish baseline"],
                "access_role": "Agency member",
                "prd_requirement_ids": ["FR-1"],
            },
            {
                "id": "IA-3",
                "name": "Provenance & Intake Links",
                "path": "/projects/:id/provenance",
                "parent_id": "IA-2",
                "order": 1,
                "purpose": "Link scope items to client discovery notes and inspect unlinked warnings.",
                "navigation_group": "primary",
                "content_groups": ["Intake note catalog", "Linked scope items", "Unlinked warnings"],
                "key_actions": ["Attach intake note", "Filter unlinked items"],
                "access_role": "Agency member",
                "prd_requirement_ids": ["FR-2"],
            },
        ],
        "open_questions": ["Should client review preview live under a public /review/:token route?"],
        "assumptions": ["All agency team members share the same workspace role in MVP"],
    }


def _wireframes_payload() -> dict:
    return {
        "wireframes": [
            {
                "page_name": "Projects Dashboard",
                "purpose": "Overview of agency projects and their scope baseline lock status.",
                "ia_node_id": "IA-1",
                "target_viewport": "responsive",
                "regions": [
                    {
                        "region": "header",
                        "heading": "Top Workspace Bar",
                        "components": [
                            {
                                "id": "cmp-1",
                                "kind": "nav_bar",
                                "label": "Workspace Navigation",
                                "content_role": "Switch between Projects and Settings",
                                "elements": ["Workspace selector", "New Project button"],
                            }
                        ],
                    },
                    {
                        "region": "main",
                        "heading": "Project Baselines Grid",
                        "components": [
                            {
                                "id": "cmp-2",
                                "kind": "card_grid",
                                "label": "Engagement Cards",
                                "content_role": "Display each client project, baseline version, and lock badge",
                                "elements": ["Project title", "Baseline version badge", "Open Editor button"],
                            }
                        ],
                    },
                ],
                "primary_actions": ["Create Project", "Open Scope Baseline Editor"],
                "secondary_actions": ["Filter by baseline status"],
                "form_fields": [],
                "states": {
                    "loading": "Skeleton cards while project list loads",
                    "empty": "Empty state card prompting founder to create their first client scope baseline",
                    "error": "Retry banner if workspace projects cannot be fetched",
                    "success": "Updated project card badge after baseline publish",
                },
                "responsive_behavior": {
                    "desktop": "Three-column project card grid with persistent top bar",
                    "tablet": "Two-column project card grid",
                    "mobile": "Single-column stacked cards with full-width action buttons",
                },
                "accessibility_keyboard": ["Tab order moves through project cards and primary action buttons"],
                "persona_ids": ["P-1"],
                "journey_ids": ["J-1"],
                "prd_requirement_ids": ["FR-1", "NFR-1"],
            },
            {
                "page_name": "Scope Baseline Editor",
                "purpose": "Create, edit, and publish in-scope deliverables and out-of-scope exclusions.",
                "ia_node_id": "IA-2",
                "target_viewport": "responsive",
                "regions": [
                    {
                        "region": "main",
                        "heading": "Scope Deliverables & Exclusions",
                        "components": [
                            {
                                "id": "cmp-3",
                                "kind": "form",
                                "label": "Deliverable & Exclusion Editor",
                                "content_role": "Add and reorder in-scope items and explicit exclusions",
                                "elements": ["Deliverable title input", "Scope boundary toggle", "Provenance ref selector"],
                            },
                            {
                                "id": "cmp-4",
                                "kind": "action_bar",
                                "label": "Baseline Publish Bar",
                                "content_role": "Save draft or lock and publish version",
                                "elements": ["Save Draft button", "Publish Baseline button"],
                            },
                        ],
                    }
                ],
                "primary_actions": ["Publish Baseline", "Add Scope Item"],
                "secondary_actions": ["Preview Client View"],
                "form_fields": [
                    {
                        "name": "Deliverable title",
                        "field_type": "text",
                        "required": True,
                        "validation_rule": "3 to 200 characters; required before saving item",
                    },
                    {
                        "name": "Boundary type",
                        "field_type": "select",
                        "required": True,
                        "validation_rule": "Must be In Scope or Explicit Exclusion",
                    },
                ],
                "states": {
                    "loading": "Spinner on Publish button and disabled inputs while saving",
                    "empty": "Prompt to add at least one in-scope deliverable before publishing",
                    "error": "Inline validation alert if publishing with zero in-scope items",
                    "success": "Locked version banner with shareable read-only link",
                },
                "responsive_behavior": {
                    "desktop": "Two-column split between In-Scope Deliverables and Explicit Exclusions",
                    "tablet": "Stacked sections with sticky publish action bar",
                    "mobile": "Tabbed In-Scope / Exclusions view with bottom action bar",
                },
                "accessibility_keyboard": [
                    "Keyboard up/down buttons for reordering deliverables without drag-and-drop",
                    "Error summary receives focus when publish validation fails",
                ],
                "persona_ids": ["P-1", "P-2"],
                "journey_ids": ["J-1"],
                "prd_requirement_ids": ["FR-1"],
            },
            {
                "page_name": "Provenance & Intake Links",
                "purpose": "Inspect and attach discovery intake notes to scope deliverables.",
                "ia_node_id": "IA-3",
                "target_viewport": "responsive",
                "regions": [
                    {
                        "region": "main",
                        "heading": "Provenance Matrix",
                        "components": [
                            {
                                "id": "cmp-5",
                                "kind": "data_table",
                                "label": "Scope-to-Intake Traceability Table",
                                "content_role": "Show each scope item, linked intake note, or unlinked warning badge",
                                "elements": ["Scope item column", "Linked note badge", "Link/Unlink action"],
                            }
                        ],
                    }
                ],
                "primary_actions": ["Link Intake Note"],
                "secondary_actions": ["Filter Unlinked Only"],
                "form_fields": [],
                "states": {
                    "loading": "Table row placeholders while loading provenance links",
                    "empty": "Message prompting user to add intake notes or scope items first",
                    "error": "Warning modal when deleting a note that is still linked to scope items",
                    "success": "Verified provenance badge shown on linked row",
                },
                "responsive_behavior": {
                    "desktop": "Full traceability table with side-by-side note preview drawer",
                    "tablet": "Compact table with collapsible note details",
                    "mobile": "Card list per scope item with tap-to-open note sheet",
                },
                "accessibility_keyboard": ["Unlinked warning badges include descriptive aria-label text"],
                "persona_ids": ["P-2"],
                "journey_ids": ["J-2"],
                "prd_requirement_ids": ["FR-2"],
            },
        ]
    }


def _ux_review_payload(critical: bool = False) -> dict:
    findings = [
        {
            "severity": "critical" if critical else "medium",
            "category": "error_recovery",
            "affected_artifact": "wireframes",
            "affected_item_id": "WF-2",
            "title": "Clarify confirmation step before locking a published baseline",
            "reasoning": "Publishing a scope baseline locks the version; users need an explicit confirmation summary showing unlinked items before lock.",
            "prd_requirement_ids": ["FR-1", "FR-2"],
            "recommended_action": "Include a pre-publish checklist modal summarizing unlinked scope items.",
            "status": "open",
        }
    ]
    return {
        "summary": "Personas, journeys, IA, and wireframes cover all must-have PRD requirements (FR-1, FR-2, NFR-1) with clear keyboard accessibility and state definitions.",
        "findings": findings,
    }


class StubPhase11Provider(StubPhase10Provider):
    def __init__(self, personas_data=None, journeys_data=None, ia_data=None, wireframes_data=None, review_data=None, fail: Exception | None = None):
        super().__init__(fail=fail)
        self.personas_data = personas_data or _personas_payload()
        self.journeys_data = journeys_data or _journeys_payload()
        self.ia_data = ia_data or _ia_payload()
        self.wireframes_data = wireframes_data or _wireframes_payload()
        self.review_data = review_data or _ux_review_payload()

    async def generate_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        self.prompts.append(prompt)
        if self.fail:
            raise self.fail
        if schema is GeneratedPersonas:
            return schema.model_validate(self.personas_data)
        if schema is GeneratedJourneys:
            return schema.model_validate(self.journeys_data)
        if schema is GeneratedIa:
            return schema.model_validate(self.ia_data)
        if schema is GeneratedWireframes:
            return schema.model_validate(self.wireframes_data)
        if schema is GeneratedUxReview:
            return schema.model_validate(self.review_data)
        return await super().generate_structured(prompt, schema)


def _setup_project_with_approved_phase10(client, monkeypatch, email="ux-founder@example.com"):
    h = auth(client, email)
    pid = client.post("/api/projects", json={"name": "ScopeGuard UX", "description": "Phase 11 verification"}, headers=h).json()["id"]
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

    stub = StubPhase11Provider()
    monkeypatch.setattr(ai, "get_provider", lambda: stub)

    # Approve Research v1
    r_gen = client.post(f"/api/projects/{pid}/research/generate", json={}, headers=h).json()
    r_hash = r_gen["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/research/reports/1/submit", json={"base_hash": r_hash}, headers=h)
    client.post(f"/api/projects/{pid}/research/reports/1/approve", json={"content_hash": r_hash, "acknowledge_unverified": True}, headers=h)

    # Approve Strategy v1
    s_gen = client.post(f"/api/projects/{pid}/strategy/generate", json={}, headers=h).json()
    s_hash = s_gen["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/strategy/versions/1/submit", json={"base_hash": s_hash}, headers=h)
    client.post(f"/api/projects/{pid}/strategy/versions/1/approve", json={"content_hash": s_hash, "acknowledge_unverified": True}, headers=h)

    # Approve PRD v1
    p_gen = client.post(f"/api/projects/{pid}/prd/generate", json={}, headers=h).json()
    p_hash = p_gen["current"]["content_hash"]
    p_req = client.post(
        f"/api/projects/{pid}/prd/versions/1/requirements/status",
        json={"base_hash": p_hash, "requirement_ids": ["FR-1", "FR-2", "NFR-1"], "status": "approved"},
        headers=h,
    ).json()
    p_hash2 = p_req["document"]["content_hash"]
    client.post(f"/api/projects/{pid}/prd/versions/1/submit", json={"base_hash": p_hash2}, headers=h)
    client.post(f"/api/projects/{pid}/prd/versions/1/approve", json={"content_hash": p_hash2, "acknowledge_unverified": False}, headers=h)

    return h, pid, stub


def test_ux_upstream_prerequisite_gates_and_workspace_links(client, monkeypatch):
    h = auth(client, "gates@example.com")
    pid = client.post("/api/projects", json={"name": "GateProj"}, headers=h).json()["id"]
    monkeypatch.setattr(ai, "get_provider", lambda: StubPhase11Provider())

    # Before Research, Strategy, PRD are approved: Personas reports missing prerequisites with workspace links
    st = client.get(f"/api/projects/{pid}/ux/personas", headers=h).json()
    assert st["prerequisites"]["ready"] is False
    assert st["can_generate"] is False
    missing_artifacts = [m["artifact"] for m in st["prerequisites"]["missing"]]
    assert "research" in missing_artifacts and "strategy" in missing_artifacts and "prd" in missing_artifacts
    assert st["prerequisites"]["missing"][0]["workspace_path"] == f"/projects/{pid}/research"

    assert client.post(f"/api/projects/{pid}/ux/personas/generate", json={}, headers=h).status_code == 409
    assert client.post(f"/api/projects/{pid}/ux/journeys/generate", json={}, headers=h).status_code == 409
    assert client.post(f"/api/projects/{pid}/ux/ia/generate", json={}, headers=h).status_code == 409
    assert client.post(f"/api/projects/{pid}/ux/wireframes/generate", json={}, headers=h).status_code == 409
    assert client.post(f"/api/projects/{pid}/ux/ux_review/generate", json={}, headers=h).status_code == 409


def test_personas_generation_numeric_downgrade_manual_fallback_and_approval(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase10(client, monkeypatch, email="personas@example.com")

    # Test numeric/survey claim downgrade in AI persona output
    bad_p = _personas_payload()
    bad_p["personas"][0]["context"] = "In our survey of 500 interviewed respondents, 82% reported losing $50,000 annually."
    bad_p["personas"][0]["evidence_status"] = "evidence_backed"
    monkeypatch.setattr(ai, "get_provider", lambda: StubPhase11Provider(personas_data=bad_p))

    res = client.post(f"/api/projects/{pid}/ux/personas/generate", json={}, headers=h)
    assert res.status_code == 200
    doc = res.json()["current"]
    p1 = doc["content"]["personas"][0]
    assert p1["evidence_status"] == "hypothesis"
    assert p1["needs_evidence"] is True
    assert "numeric" in (p1["note"] or "").lower() or "confirmed" in (p1["note"] or "").lower()

    # Reject unknown PRD requirement ID on persona edit
    p_hash = doc["content_hash"]
    bad_edit = client.patch(
        f"/api/projects/{pid}/ux/personas/versions/1/items/P-1",
        json={"base_hash": p_hash, "prd_requirement_ids": ["FR-999"]},
        headers=h,
    )
    assert bad_edit.status_code == 422

    # Valid edit updates hash
    ok_edit = client.patch(
        f"/api/projects/{pid}/ux/personas/versions/1/items/P-1",
        json={"base_hash": p_hash, "context": "Runs a 12-person agency managing fixed-fee web engagements."},
        headers=h,
    )
    assert ok_edit.status_code == 200
    p_hash2 = ok_edit.json()["document"]["content_hash"]

    # Submit and approve (requires acknowledge_unverified=True because P-1 has unverified assumptions)
    client.post(f"/api/projects/{pid}/ux/personas/versions/1/submit", json={"base_hash": p_hash2}, headers=h)
    assert client.post(
        f"/api/projects/{pid}/ux/personas/versions/1/approve",
        json={"content_hash": p_hash2, "acknowledge_unverified": False},
        headers=h,
    ).status_code == 409

    app_res = client.post(
        f"/api/projects/{pid}/ux/personas/versions/1/approve",
        json={"content_hash": p_hash2, "acknowledge_unverified": True, "note": "Personas v1 approved"},
        headers=h,
    )
    assert app_res.status_code == 200
    assert app_res.json()["status"] == "approved"
    # UX stage is still in_progress because Journeys, IA, Wireframes, and UX Review are not approved yet
    assert app_res.json()["lifecycle"]["status"] == "in_progress"
    assert app_res.json()["lifecycle"]["ux_complete"] is False


def test_manual_personas_creation_when_ai_provider_unavailable(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase10(client, monkeypatch, email="manual-ux@example.com")

    class Unconfigured(ai.AIProvider):
        async def generate(self, prompt: str) -> str:
            raise ai.ProviderNotConfigured("No API key")

    monkeypatch.setattr(ai, "get_provider", lambda: Unconfigured())
    assert client.post(f"/api/projects/{pid}/ux/personas/generate", json={}, headers=h).status_code == 503

    # Manual creation succeeds without AI provider
    man = client.post(
        f"/api/projects/{pid}/ux/personas/manual",
        json={
            "name": "Alex Rivera — Studio Lead",
            "segment": "Small design studios",
            "context": "Manages client proposals and scope boundaries manually.",
            "goals": ["Keep fixed-fee projects within scope"],
            "tasks_behaviors": ["Writes scope deliverables and exclusions"],
            "needs_pain_points": ["Clients request extra revisions without change orders"],
            "accessibility_device_notes": ["Uses keyboard navigation and high-contrast display"],
            "prd_requirement_ids": ["FR-1"],
            "evidence_refs": ["res-f-1"],
            "evidence_status": "hypothesis",
        },
        headers=h,
    )
    assert man.status_code == 200
    assert man.json()["status"] == "draft"
    assert man.json()["current"]["created_via"] == "manual"
    assert man.json()["current"]["content"]["personas"][0]["id"] == "P-1"


def test_full_phase_11_workflow_ia_tree_validation_wireframes_review_and_invalidation(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase10(client, monkeypatch, email="full-ux@example.com")
    monkeypatch.setattr(ai, "get_provider", lambda: StubPhase11Provider(review_data=_ux_review_payload(critical=True)))

    # Journeys cannot generate before Personas is approved
    assert client.post(f"/api/projects/{pid}/ux/journeys/generate", json={}, headers=h).status_code == 409

    # 1. Generate and approve Personas v1
    p_gen = client.post(f"/api/projects/{pid}/ux/personas/generate", json={}, headers=h).json()
    p_hash = p_gen["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/ux/personas/versions/1/submit", json={"base_hash": p_hash}, headers=h)
    client.post(f"/api/projects/{pid}/ux/personas/versions/1/approve", json={"content_hash": p_hash, "acknowledge_unverified": True}, headers=h)

    # 2. Generate and validate User Journeys v1
    j_gen = client.post(f"/api/projects/{pid}/ux/journeys/generate", json={}, headers=h)
    assert j_gen.status_code == 200
    j_hash = j_gen.json()["current"]["content_hash"]

    # Reject unknown persona_id on journey edit
    assert client.patch(
        f"/api/projects/{pid}/ux/journeys/versions/1/items/J-1",
        json={"base_hash": j_hash, "persona_id": "P-99"},
        headers=h,
    ).status_code == 422

    client.post(f"/api/projects/{pid}/ux/journeys/versions/1/submit", json={"base_hash": j_hash}, headers=h)
    client.post(f"/api/projects/{pid}/ux/journeys/versions/1/approve", json={"content_hash": j_hash, "acknowledge_unverified": True}, headers=h)

    # 3. Generate and validate Information Architecture v1 (including tree integrity & cycle checks)
    ia_gen = client.post(f"/api/projects/{pid}/ux/ia/generate", json={}, headers=h)
    assert ia_gen.status_code == 200
    ia_hash = ia_gen.json()["current"]["content_hash"]

    # Reject self-parent
    assert client.patch(
        f"/api/projects/{pid}/ux/ia/versions/1/nodes/IA-1",
        json={"base_hash": ia_hash, "parent_id": "IA-1"},
        headers=h,
    ).status_code == 422

    # Reject nonexistent parent_id
    assert client.patch(
        f"/api/projects/{pid}/ux/ia/versions/1/nodes/IA-1",
        json={"base_hash": ia_hash, "parent_id": "IA-999"},
        headers=h,
    ).status_code == 422

    # Reject cycle: IA-1 -> IA-3 (since IA-3 -> IA-2 -> IA-1)
    cycle_res = client.patch(
        f"/api/projects/{pid}/ux/ia/versions/1/nodes/IA-1",
        json={"base_hash": ia_hash, "parent_id": "IA-3"},
        headers=h,
    )
    assert cycle_res.status_code == 422
    assert any("cycle" in e["msg"].lower() for e in cycle_res.json()["detail"])

    # Reject deleting IA-1 while IA-2 still has parent_id="IA-1"
    assert client.delete(f"/api/projects/{pid}/ux/ia/versions/1/nodes/IA-1?base_hash={ia_hash}", headers=h).status_code == 409

    # Valid node move: re-parent IA-3 directly under IA-1
    move_res = client.patch(
        f"/api/projects/{pid}/ux/ia/versions/1/nodes/IA-3",
        json={"base_hash": ia_hash, "parent_id": "IA-1", "order": 2},
        headers=h,
    )
    assert move_res.status_code == 200
    ia_hash2 = move_res.json()["document"]["content_hash"]

    client.post(f"/api/projects/{pid}/ux/ia/versions/1/submit", json={"base_hash": ia_hash2}, headers=h)
    client.post(f"/api/projects/{pid}/ux/ia/versions/1/approve", json={"content_hash": ia_hash2, "acknowledge_unverified": True}, headers=h)

    # 4. Generate and validate Wireframes v1
    wf_gen = client.post(f"/api/projects/{pid}/ux/wireframes/generate", json={}, headers=h)
    assert wf_gen.status_code == 200
    wf_hash = wf_gen.json()["current"]["content_hash"]

    # Reject nonexistent IA node reference on wireframe
    assert client.patch(
        f"/api/projects/{pid}/ux/wireframes/versions/1/items/WF-1",
        json={"base_hash": wf_hash, "ia_node_id": "IA-999"},
        headers=h,
    ).status_code == 422

    client.post(f"/api/projects/{pid}/ux/wireframes/versions/1/submit", json={"base_hash": wf_hash}, headers=h)
    client.post(f"/api/projects/{pid}/ux/wireframes/versions/1/approve", json={"content_hash": wf_hash, "acknowledge_unverified": False}, headers=h)

    # UX stage is STILL not complete because UX Review is not approved yet
    assert client.get(f"/api/projects/{pid}/overview", headers=h).json()["next_action"] == "ux"
    assert client.put(f"/api/projects/{pid}/stages/ux", json={"status": "complete"}, headers=h).status_code == 409

    # 5. Generate UX Review v1 (contains deterministic findings + 1 critical AI finding)
    rev_gen = client.post(f"/api/projects/{pid}/ux/ux_review/generate", json={}, headers=h)
    assert rev_gen.status_code == 200
    rev_doc = rev_gen.json()["current"]
    assert rev_doc["critical_open_count"] == 1
    assert any(f["origin"] == "deterministic" for f in rev_doc["content"]["findings"])
    assert any(f["origin"] == "ai" for f in rev_doc["content"]["findings"])
    rev_hash = rev_doc["content_hash"]

    client.post(f"/api/projects/{pid}/ux/ux_review/versions/1/submit", json={"base_hash": rev_hash}, headers=h)

    # Approving UX Review is blocked (409) while the critical finding is open
    assert client.post(
        f"/api/projects/{pid}/ux/ux_review/versions/1/approve",
        json={"content_hash": rev_hash, "acknowledge_unverified": True},
        headers=h,
    ).status_code == 409

    # Accepting or resolving a finding without a resolution_note is rejected (422)
    crit_id = next(f["id"] for f in rev_doc["content"]["findings"] if f["severity"] == "critical")
    assert client.patch(
        f"/api/projects/{pid}/ux/ux_review/versions/1/findings/{crit_id}",
        json={"base_hash": rev_hash, "status": "accepted"},
        headers=h,
    ).status_code == 422

    # Resolve/accept the critical finding with an explicit resolution_note
    resolved = client.patch(
        f"/api/projects/{pid}/ux/ux_review/versions/1/findings/{crit_id}",
        json={
            "base_hash": rev_hash,
            "status": "accepted",
            "resolution_note": "Accepted for MVP: publish bar already shows unlinked item count inline.",
        },
        headers=h,
    )
    assert resolved.status_code == 200
    rev_hash2 = resolved.json()["document"]["content_hash"]
    assert resolved.json()["document"]["critical_open_count"] == 0

    # Re-submit and approve UX Review v1 -> completes the `ux` lifecycle stage!
    client.post(f"/api/projects/{pid}/ux/ux_review/versions/1/submit", json={"base_hash": rev_hash2}, headers=h)
    rev_app = client.post(
        f"/api/projects/{pid}/ux/ux_review/versions/1/approve",
        json={"content_hash": rev_hash2, "acknowledge_unverified": True, "note": "UX Review v1 approved"},
        headers=h,
    )
    assert rev_app.status_code == 200
    assert rev_app.json()["lifecycle"]["status"] == "complete"
    assert rev_app.json()["lifecycle"]["ux_complete"] is True

    # Overview now shows 3 of 19 stages complete (research, product, ux -> 16%) and next_action == "design"
    ov = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    assert set(ov["completed"]) == {"research", "product", "ux"}
    assert ov["progress"] == round(100 * 3 / 19)
    assert ov["next_action"] == "design"

    # Brain `ux` section is populated and protected from direct overwrite
    brain = client.get(f"/api/projects/{pid}/brain", headers=h).json()["brain"]
    for t in ("personas", "journeys", "ia", "wireframes", "ux_review"):
        assert brain["ux"][t]["approved_version"] == 1
    assert client.put(f"/api/projects/{pid}/brain/ux", json={"value": {}}, headers=h).status_code == 403

    # Copy-on-write edit on approved Wireframes v1 creates v2 draft, marks UX Review stale, and reopens `ux` stage to in_progress
    cow = client.patch(
        f"/api/projects/{pid}/ux/wireframes/versions/1/items/WF-1",
        json={"base_hash": wf_hash, "purpose": "Updated dashboard purpose with quick baseline filter."},
        headers=h,
    )
    assert cow.status_code == 200
    assert cow.json()["document"]["version"] == 2
    assert cow.json()["document"]["status"] == "draft"
    assert cow.json()["document"]["created_via"] == "copy_of_approved"
    assert cow.json()["state"]["lifecycle"]["status"] == "in_progress"
    assert client.get(f"/api/projects/{pid}/ux/wireframes/versions/1", headers=h).json()["status"] == "approved"

    rev_stale = client.get(f"/api/projects/{pid}/ux/ux_review", headers=h).json()
    assert rev_stale["is_stale"] is True
    assert client.get(f"/api/projects/{pid}/overview", headers=h).json()["next_action"] == "ux"


def test_ux_ownership_isolation_and_db_partial_unique_indexes(client, monkeypatch):
    h1, pid, _ = _setup_project_with_approved_phase10(client, monkeypatch, email="ux-owner@example.com")
    other = TestClient(app)
    h2 = auth(other, "ux-intruder@example.com")

    assert client.post(f"/api/projects/{pid}/ux/personas/generate", json={}, headers=h1).status_code == 200
    assert other.get(f"/api/projects/{pid}/ux", headers=h2).status_code == 404
    assert other.get(f"/api/projects/{pid}/ux/personas", headers=h2).status_code == 404
    assert other.post(f"/api/projects/{pid}/ux/personas/generate", json={}, headers=h2).status_code == 404

    with SessionLocal() as db_session:
        u1 = UxArtifact(project_id=pid, artifact_type="journeys", version=1, status="generating", basis={}, created_by="u1", row_version=1)
        u2 = UxArtifact(project_id=pid, artifact_type="journeys", version=2, status="generating", basis={}, created_by="u1", row_version=1)
        db_session.add_all([u1, u2])
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
