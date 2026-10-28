"""Phase 12 tests: Design System, Interactive Prototype, token/component/navigation validation,
wireframe reuse, copy-on-write, upstream UX invalidation, ownership, and `design` stage completion."""
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app import ai
from app.db import SessionLocal
from app.design import GeneratedDesignSystem, GeneratedPrototype
from app.main import app
from app.models import DesignArtifact
from tests.test_strategy_prd import auth
from tests.test_ux import StubPhase11Provider, _setup_project_with_approved_phase10


def _design_system_payload() -> dict:
    return {
        "foundations": {
            "color_tokens": [
                {
                    "token": "--color-primary",
                    "role": "Primary brand action",
                    "hex_value": "#1E40AF",
                    "usage": "Primary buttons, active links, and locked baseline indicators",
                    "contrast_note": "8.6:1 contrast against #FFFFFF surface (exceeds WCAG AAA)",
                },
                {
                    "token": "--color-surface",
                    "role": "Primary card and workspace surface",
                    "hex_value": "#FFFFFF",
                    "usage": "Cards, tables, and modal backgrounds",
                    "contrast_note": "Base light surface paired with #0F172A text",
                },
                {
                    "token": "--color-text-primary",
                    "role": "Primary body and heading text",
                    "hex_value": "#0F172A",
                    "usage": "All primary copy, table cells, and labels",
                    "contrast_note": "17.4:1 contrast against #FFFFFF surface",
                },
                {
                    "token": "--color-danger",
                    "role": "Error and out-of-scope alert accent",
                    "hex_value": "#B91C1C",
                    "usage": "Validation errors, unlinked warnings, and destructive actions",
                    "contrast_note": "6.4:1 contrast against #FFFFFF surface (exceeds WCAG AA)",
                },
            ],
            "typography_scale": [
                {
                    "token": "--font-heading-lg",
                    "role": "Workspace page heading (H1)",
                    "font_family": "Inter, system-ui, sans-serif",
                    "font_size": "1.25rem (20px)",
                    "line_height": "1.75rem (28px)",
                    "font_weight": "600",
                },
                {
                    "token": "--font-heading-md",
                    "role": "Section & card heading (H2/H3)",
                    "font_family": "Inter, system-ui, sans-serif",
                    "font_size": "1rem (16px)",
                    "line_height": "1.5rem (24px)",
                    "font_weight": "600",
                },
                {
                    "token": "--font-body",
                    "role": "Default interface and table copy",
                    "font_family": "Inter, system-ui, sans-serif",
                    "font_size": "0.875rem (14px)",
                    "line_height": "1.25rem (20px)",
                    "font_weight": "400",
                },
            ],
            "spacing_scale": [
                {"token": "--space-1", "value": "0.25rem (4px)", "usage": "Inline badge and icon gaps"},
                {"token": "--space-2", "value": "0.5rem (8px)", "usage": "Form field label spacing and compact stacks"},
                {"token": "--space-4", "value": "1rem (16px)", "usage": "Card padding and section spacing"},
            ],
            "grid_breakpoints": {
                "columns": 12,
                "gutter": "1rem (16px)",
                "max_width": "72rem (1152px)",
                "desktop": ">= 1024px: 12-column grid with persistent left navigation and split scope editor",
                "tablet": "640px - 1023px: 8-column grid with collapsible navigation drawer",
                "mobile": "< 640px: 4-column single-stack layout with sticky bottom action bar",
            },
            "surface_tokens": {
                "radii": ["rounded-md (6px) for inputs and buttons", "rounded-lg (8px) for cards and dialogs"],
                "borders": ["1px solid #E2E8F0 default card border", "2px solid #1E40AF focus ring"],
                "elevation_shadows": ["shadow-sm for cards", "shadow-lg for modal dialogs"],
            },
            "icon_guidelines": [
                "Always pair status icons (locked, unlinked warning) with visible text labels; never rely on color or icon alone."
            ],
            "accessibility_notes": [
                "Maintain >= 4.5:1 contrast for normal text and >= 3:1 for UI controls; visible 2px focus indicator on all interactive elements."
            ],
        },
        "components": [
            {
                "name": "Scope Action Button",
                "category": "buttons_links",
                "purpose": "Trigger primary scope baseline actions (Publish Baseline, Add Scope Item) and secondary navigation.",
                "variants": ["Primary solid", "Secondary bordered", "Danger ghost"],
                "states": ["default", "hover", "focus", "active", "disabled", "loading"],
                "design_tokens_used": ["--color-primary", "--color-surface", "--font-body", "--space-2"],
                "responsive_behavior": "Inline button group on desktop/tablet; full-width stacked actions on mobile.",
                "accessibility_notes": "Exposes aria-busy during loading and maintains 36px minimum hit target.",
                "wireframe_ids": ["WF-1", "WF-2"],
                "prd_requirement_ids": ["FR-1"],
            },
            {
                "name": "Deliverable & Exclusion Form Control",
                "category": "inputs_controls",
                "purpose": "Capture deliverable title, scope boundary (in_mvp / out_of_scope), and linked intake note reference.",
                "variants": ["Text input", "Boundary select", "Provenance ref selector"],
                "states": ["default", "focus", "error", "disabled"],
                "design_tokens_used": ["--color-surface", "--color-text-primary", "--color-danger", "--font-body", "--space-2"],
                "responsive_behavior": "Horizontal field row on desktop; vertical stack on tablet and mobile.",
                "accessibility_notes": "Every input has an explicit label and aria-describedby linking inline validation errors.",
                "wireframe_ids": ["WF-2"],
                "prd_requirement_ids": ["FR-1", "FR-2"],
            },
            {
                "name": "Provenance Traceability Table",
                "category": "tables_lists",
                "purpose": "Display scope deliverables alongside linked discovery intake notes or unlinked warning badges.",
                "variants": ["Full table", "Compact mobile card list"],
                "states": ["default", "loading", "empty", "error"],
                "design_tokens_used": ["--color-surface", "--color-text-primary", "--color-danger", "--font-body", "--space-4"],
                "responsive_behavior": "Data table on desktop/tablet; stacked cards on mobile.",
                "accessibility_notes": "Uses semantic table headers and descriptive text on unlinked badges.",
                "wireframe_ids": ["WF-3"],
                "prd_requirement_ids": ["FR-2", "NFR-1"],
            },
        ],
        "decisions": [
            {
                "title": "High-contrast status badges with explicit text labels",
                "chosen_value_or_rule": "Pair #1E40AF primary and #B91C1C danger tokens with explicit 'Locked' and 'Unlinked' text labels.",
                "rationale": "Supports account leads sharing screens on varying projectors and satisfies WCAG contrast requirements.",
                "supporting_refs": ["WF-2", "WF-3", "P-2", "FR-2"],
                "assumptions": ["Users frequently review baselines on laptops during live client calls"],
                "unresolved_questions": ["Should dark mode tokens be added post-MVP?"],
            }
        ],
    }


def _prototype_payload() -> dict:
    return {
        "screens": [
            {
                "id": "SCR-1",
                "wireframe_id": "WF-1",
                "ia_node_id": "IA-1",
                "title": "Projects Dashboard",
                "route_path": "/projects",
                "purpose": "Overview of active agency engagements and scope baseline lock status.",
                "component_ids": ["CMP-1"],
                "form_fields": [],
                "interactions": [
                    {
                        "id": "ix-1",
                        "trigger_label": "Open Scope Baseline Editor",
                        "trigger_kind": "primary_button",
                        "action_type": "navigate",
                        "target_screen_id": "SCR-2",
                        "dialog_title": None,
                        "dialog_body": None,
                        "resulting_state": "default",
                        "simulation_note": "Simulated navigation to SCR-2 (Scope Baseline Editor)",
                    }
                ],
                "mock_data_note": "Displays 2 deterministic sample agency projects (Acme Rebrand v1 Locked, Nova Portal Draft).",
                "journey_ids": ["J-1"],
                "prd_requirement_ids": ["FR-1", "NFR-1"],
            },
            {
                "id": "SCR-2",
                "wireframe_id": "WF-2",
                "ia_node_id": "IA-2",
                "title": "Scope Baseline Editor",
                "route_path": "/projects/:id/baseline",
                "purpose": "Author, validate, and publish in-scope deliverables and explicit exclusions.",
                "component_ids": ["CMP-1", "CMP-2"],
                "form_fields": [
                    {
                        "name": "deliverable_title",
                        "label": "Deliverable title",
                        "field_type": "text",
                        "required": True,
                        "placeholder": "e.g. Responsive marketing homepage (up to 5 sections)",
                        "default_mock_value": "Responsive marketing homepage",
                        "validation_rule": "Required (3 to 200 characters)",
                    },
                    {
                        "name": "boundary_type",
                        "label": "Scope boundary",
                        "field_type": "select",
                        "required": True,
                        "placeholder": "Select boundary",
                        "default_mock_value": "In MVP Scope",
                        "validation_rule": "Must be In MVP Scope or Explicit Exclusion",
                    },
                ],
                "interactions": [
                    {
                        "id": "ix-2",
                        "trigger_label": "Add Scope Item",
                        "trigger_kind": "form_submit",
                        "action_type": "submit_form",
                        "target_screen_id": None,
                        "dialog_title": None,
                        "dialog_body": None,
                        "resulting_state": "success",
                        "simulation_note": "Validates required deliverable fields locally and transitions preview to success state.",
                    },
                    {
                        "id": "ix-3",
                        "trigger_label": "Publish Baseline",
                        "trigger_kind": "primary_button",
                        "action_type": "open_dialog",
                        "target_screen_id": None,
                        "dialog_title": "Lock and Publish Baseline v1?",
                        "dialog_body": "Publishing locks this scope baseline version and generates a read-only client sign-off view.",
                        "resulting_state": "default",
                        "simulation_note": "Opens simulated pre-publish confirmation modal.",
                    },
                    {
                        "id": "ix-4",
                        "trigger_label": "Inspect Provenance Links",
                        "trigger_kind": "nav_link",
                        "action_type": "navigate",
                        "target_screen_id": "SCR-3",
                        "dialog_title": None,
                        "dialog_body": None,
                        "resulting_state": "default",
                        "simulation_note": "Navigates to SCR-3 (Provenance & Intake Links).",
                    },
                ],
                "mock_data_note": "Pre-populated with sample deliverables and exclusions in local browser state.",
                "journey_ids": ["J-1"],
                "prd_requirement_ids": ["FR-1"],
            },
            {
                "id": "SCR-3",
                "wireframe_id": "WF-3",
                "ia_node_id": "IA-3",
                "title": "Provenance & Intake Links",
                "route_path": "/projects/:id/provenance",
                "purpose": "Inspect discovery intake notes linked to each scope deliverable.",
                "component_ids": ["CMP-1", "CMP-3"],
                "form_fields": [],
                "interactions": [
                    {
                        "id": "ix-5",
                        "trigger_label": "Back to Projects Dashboard",
                        "trigger_kind": "secondary_button",
                        "action_type": "navigate",
                        "target_screen_id": "SCR-1",
                        "dialog_title": None,
                        "dialog_body": None,
                        "resulting_state": "default",
                        "simulation_note": "Returns to SCR-1 (Projects Dashboard).",
                    }
                ],
                "mock_data_note": "Shows sample traceability rows linking deliverables to client intake notes.",
                "journey_ids": ["J-2"],
                "prd_requirement_ids": ["FR-2"],
            },
        ],
        "flows": [
            {
                "id": "FLOW-1",
                "journey_id": "J-1",
                "title": "Create and Publish Scope Baseline",
                "start_screen_id": "SCR-1",
                "ordered_screen_ids": ["SCR-1", "SCR-2"],
                "happy_path_steps": [
                    "Select engagement on Projects Dashboard (SCR-1) and click Open Scope Baseline Editor",
                    "Validate deliverable form fields on Scope Baseline Editor (SCR-2) and open Publish Baseline confirmation dialog",
                ],
            },
            {
                "id": "FLOW-2",
                "journey_id": "J-2",
                "title": "Trace Client Request to Scope Provenance",
                "start_screen_id": "SCR-2",
                "ordered_screen_ids": ["SCR-2", "SCR-3", "SCR-1"],
                "happy_path_steps": [
                    "From Scope Baseline Editor (SCR-2), click Inspect Provenance Links",
                    "Verify linked discovery note on Provenance & Intake Links (SCR-3) and return to Dashboard (SCR-1)",
                ],
            },
        ],
    }


class StubPhase12Provider(StubPhase11Provider):
    def __init__(self, design_system_data=None, prototype_data=None, fail: Exception | None = None):
        super().__init__(fail=fail)
        self.design_system_data = design_system_data or _design_system_payload()
        self.prototype_data = prototype_data or _prototype_payload()

    async def generate_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        self.prompts.append(prompt)
        if self.fail:
            raise self.fail
        if schema is GeneratedDesignSystem:
            return schema.model_validate(self.design_system_data)
        if schema is GeneratedPrototype:
            return schema.model_validate(self.prototype_data)
        return await super().generate_structured(prompt, schema)


def _setup_project_with_approved_phase11(client, monkeypatch, email="design-founder@example.com"):
    h, pid, _ = _setup_project_with_approved_phase10(client, monkeypatch, email=email)
    stub = StubPhase12Provider()
    monkeypatch.setattr(ai, "get_provider", lambda: stub)

    for atype in ("personas", "journeys", "ia", "wireframes", "ux_review"):
        gen = client.post(f"/api/projects/{pid}/ux/{atype}/generate", json={}, headers=h).json()
        hsh = gen["current"]["content_hash"]
        client.post(f"/api/projects/{pid}/ux/{atype}/versions/1/submit", json={"base_hash": hsh}, headers=h)
        app_res = client.post(
            f"/api/projects/{pid}/ux/{atype}/versions/1/approve",
            json={"content_hash": hsh, "acknowledge_unverified": True},
            headers=h,
        )
        assert app_res.status_code == 200

    assert client.get(f"/api/projects/{pid}/overview", headers=h).json()["next_action"] == "design"
    return h, pid, stub


def test_design_prerequisite_gates_require_approved_ux(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase10(client, monkeypatch, email="design-gates@example.com")
    monkeypatch.setattr(ai, "get_provider", lambda: StubPhase12Provider())

    # Before Phase 11 UX is complete, Design System reports missing UX artifacts with workspace links
    st = client.get(f"/api/projects/{pid}/design/design_system", headers=h).json()
    assert st["prerequisites"]["ready"] is False
    assert st["can_generate"] is False
    missing = [m["artifact"] for m in st["prerequisites"]["missing"]]
    assert "personas" in missing and "wireframes" in missing and "ux_review" in missing
    assert st["prerequisites"]["missing"][0]["workspace_path"] == f"/projects/{pid}/personas"

    assert client.post(f"/api/projects/{pid}/design/design_system/generate", json={}, headers=h).status_code == 409
    assert client.post(f"/api/projects/{pid}/design/prototype/generate", json={}, headers=h).status_code == 409


def test_design_system_generation_validation_usability_claim_flag_and_manual_fallback(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase11(client, monkeypatch, email="ds-test@example.com")

    # Test usability-claim flagging in AI design decisions
    ds_payload = _design_system_payload()
    ds_payload["decisions"][0]["rationale"] = "This color pairing was usability-tested and A/B tested with 200 users."
    monkeypatch.setattr(ai, "get_provider", lambda: StubPhase12Provider(design_system_data=ds_payload))

    res = client.post(f"/api/projects/{pid}/design/design_system/generate", json={}, headers=h)
    assert res.status_code == 200
    doc = res.json()["current"]
    dec = doc["content"]["decisions"][0]
    assert dec["status"] == "proposed"
    assert "usability" in (dec["note"] or "").lower()
    assert any("unverified usability" in a.lower() for a in dec["assumptions"])

    ds_hash = doc["content_hash"]

    # Reject invalid hex color token
    bad_color = client.patch(
        f"/api/projects/{pid}/design/design_system/versions/1/foundations",
        json={
            "base_hash": ds_hash,
            "color_tokens": [
                {"token": "--color-primary", "role": "Primary", "hex_value": "not-a-hex", "usage": "Buttons", "contrast_note": "4.5:1"}
            ],
        },
        headers=h,
    )
    assert bad_color.status_code == 422

    # Reject component referencing nonexistent design token
    bad_tok = client.patch(
        f"/api/projects/{pid}/design/design_system/versions/1/components/CMP-1",
        json={"base_hash": ds_hash, "design_tokens_used": ["--color-nonexistent"]},
        headers=h,
    )
    assert bad_tok.status_code == 422

    # Reject component referencing nonexistent wireframe ID
    bad_wf = client.patch(
        f"/api/projects/{pid}/design/design_system/versions/1/components/CMP-1",
        json={"base_hash": ds_hash, "wireframe_ids": ["WF-999"]},
        headers=h,
    )
    assert bad_wf.status_code == 422

    # Approve decision DD-1 and clear assumptions so unverified_count becomes 0
    ok_dec = client.patch(
        f"/api/projects/{pid}/design/design_system/versions/1/decisions/DD-1",
        json={"base_hash": ds_hash, "status": "approved", "assumptions": [], "unresolved_questions": []},
        headers=h,
    )
    assert ok_dec.status_code == 200
    ds_hash2 = ok_dec.json()["document"]["content_hash"]
    assert ok_dec.json()["document"]["unverified_count"] == 0

    client.post(f"/api/projects/{pid}/design/design_system/versions/1/submit", json={"base_hash": ds_hash2}, headers=h)
    app_ds = client.post(
        f"/api/projects/{pid}/design/design_system/versions/1/approve",
        json={"content_hash": ds_hash2, "acknowledge_unverified": False, "note": "Design System v1 approved"},
        headers=h,
    )
    assert app_ds.status_code == 200
    assert app_ds.json()["status"] == "approved"
    # Design stage remains in_progress until Prototype is also approved
    assert app_ds.json()["lifecycle"]["status"] == "in_progress"
    assert app_ds.json()["lifecycle"]["design_complete"] is False


def test_prototype_generation_wireframe_reuse_navigation_validation_and_stage_completion(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase11(client, monkeypatch, email="proto-test@example.com")

    # Prototype cannot generate before Design System is approved
    assert client.post(f"/api/projects/{pid}/design/prototype/generate", json={}, headers=h).status_code == 409

    # Generate and approve Design System v1
    ds_gen = client.post(f"/api/projects/{pid}/design/design_system/generate", json={}, headers=h).json()
    ds_hash = ds_gen["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/design/design_system/versions/1/submit", json={"base_hash": ds_hash}, headers=h)
    client.post(
        f"/api/projects/{pid}/design/design_system/versions/1/approve",
        json={"content_hash": ds_hash, "acknowledge_unverified": True},
        headers=h,
    )

    # Generate Interactive Prototype v1
    pr_gen = client.post(f"/api/projects/{pid}/design/prototype/generate", json={}, headers=h)
    assert pr_gen.status_code == 200
    pr_doc = pr_gen.json()["current"]
    assert len(pr_doc["content"]["screens"]) == 3
    assert len(pr_doc["content"]["flows"]) == 2
    # Verify wireframe regions & states were reused from Phase 11 wireframes
    scr2 = next(s for s in pr_doc["content"]["screens"] if s["id"] == "SCR-2")
    assert scr2["wireframe_id"] == "WF-2"
    assert scr2["regions"][0]["heading"] == "Scope Deliverables & Exclusions"
    assert "zero in-scope items" in scr2["states"]["error"]
    pr_hash = pr_doc["content_hash"]

    # Reject interaction navigating to nonexistent target_screen_id
    bad_nav = client.patch(
        f"/api/projects/{pid}/design/prototype/versions/1/screens/SCR-1",
        json={
            "base_hash": pr_hash,
            "interactions": [
                {
                    "id": "ix-1",
                    "trigger_label": "Broken Link",
                    "trigger_kind": "primary_button",
                    "action_type": "navigate",
                    "target_screen_id": "SCR-999",
                    "simulation_note": "Invalid target screen",
                }
            ],
        },
        headers=h,
    )
    assert bad_nav.status_code == 422

    # Reject flow where ordered_screen_ids does not start with start_screen_id
    bad_flow = client.patch(
        f"/api/projects/{pid}/design/prototype/versions/1/flows/FLOW-1",
        json={"base_hash": pr_hash, "start_screen_id": "SCR-1", "ordered_screen_ids": ["SCR-2", "SCR-1"]},
        headers=h,
    )
    assert bad_flow.status_code == 422

    # Manual completion of design stage is blocked while Prototype is unapproved
    assert client.put(f"/api/projects/{pid}/stages/design", json={"status": "complete"}, headers=h).status_code == 409

    # Submit and approve Prototype v1 -> completes `design` lifecycle stage!
    client.post(f"/api/projects/{pid}/design/prototype/versions/1/submit", json={"base_hash": pr_hash}, headers=h)
    pr_app = client.post(
        f"/api/projects/{pid}/design/prototype/versions/1/approve",
        json={"content_hash": pr_hash, "acknowledge_unverified": False, "note": "Prototype v1 approved"},
        headers=h,
    )
    assert pr_app.status_code == 200
    assert pr_app.json()["lifecycle"]["status"] == "complete"
    assert pr_app.json()["lifecycle"]["design_complete"] is True

    # Overview now shows 4 of 19 stages complete (research, product, ux, design -> 21%) and next_action == "architecture"
    ov = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    assert set(ov["completed"]) == {"research", "product", "ux", "design"}
    assert ov["progress"] == round(100 * 4 / 19)
    assert ov["next_action"] == "architecture"
    arch_stage = next(s for s in ov["stages"] if s["stage"] == "architecture")
    assert arch_stage["unmet_dependencies"] == []

    # Brain `design_spec` pointers are recorded and protected from direct overwrite
    brain = client.get(f"/api/projects/{pid}/brain", headers=h).json()["brain"]
    assert brain["design_spec"]["design_system"]["approved_version"] == 1
    assert brain["design_spec"]["prototype"]["approved_version"] == 1
    assert client.put(f"/api/projects/{pid}/brain/design_spec", json={"value": {}}, headers=h).status_code == 403

    # Copy-on-write edit on approved Design System v1 creates v2 draft, marks Prototype stale, and reopens `design` stage
    cow = client.patch(
        f"/api/projects/{pid}/design/design_system/versions/1/components/CMP-1",
        json={"base_hash": ds_hash, "purpose": "Updated button purpose with keyboard shortcut badge support."},
        headers=h,
    )
    assert cow.status_code == 200
    assert cow.json()["document"]["version"] == 2
    assert cow.json()["document"]["status"] == "draft"
    assert cow.json()["document"]["created_via"] == "copy_of_approved"
    assert cow.json()["state"]["lifecycle"]["status"] == "in_progress"

    pr_stale = client.get(f"/api/projects/{pid}/design/prototype", headers=h).json()
    assert pr_stale["is_stale"] is True
    assert client.get(f"/api/projects/{pid}/overview", headers=h).json()["next_action"] == "design"


def test_upstream_ux_change_invalidates_design_readiness(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase11(client, monkeypatch, email="inval@example.com")

    # Approve Design System v1 and Prototype v1
    ds_gen = client.post(f"/api/projects/{pid}/design/design_system/generate", json={}, headers=h).json()
    ds_hash = ds_gen["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/design/design_system/versions/1/submit", json={"base_hash": ds_hash}, headers=h)
    client.post(f"/api/projects/{pid}/design/design_system/versions/1/approve", json={"content_hash": ds_hash, "acknowledge_unverified": True}, headers=h)

    pr_gen = client.post(f"/api/projects/{pid}/design/prototype/generate", json={}, headers=h).json()
    pr_hash = pr_gen["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/design/prototype/versions/1/submit", json={"base_hash": pr_hash}, headers=h)
    client.post(f"/api/projects/{pid}/design/prototype/versions/1/approve", json={"content_hash": pr_hash, "acknowledge_unverified": False}, headers=h)
    assert client.get(f"/api/projects/{pid}/overview", headers=h).json()["next_action"] == "architecture"

    # Now edit upstream Phase 11 Wireframes v1 (creates Wireframes v2 draft) -> reopens both `ux` and `design` stages!
    wf_hash = client.get(f"/api/projects/{pid}/ux/wireframes", headers=h).json()["current"]["content_hash"]
    client.patch(
        f"/api/projects/{pid}/ux/wireframes/versions/1/items/WF-1",
        json={"base_hash": wf_hash, "purpose": "Revised dashboard wireframe purpose."},
        headers=h,
    )
    ov = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    assert "ux" not in ov["completed"]
    assert "design" not in ov["completed"]
    assert ov["next_action"] == "ux"
    assert client.get(f"/api/projects/{pid}/design/design_system", headers=h).json()["is_stale"] is True
    assert client.get(f"/api/projects/{pid}/design/prototype", headers=h).json()["is_stale"] is True


def test_design_ownership_isolation_and_db_partial_unique_indexes(client, monkeypatch):
    h1, pid, _ = _setup_project_with_approved_phase11(client, monkeypatch, email="ds-owner@example.com")
    other = TestClient(app)
    h2 = auth(other, "ds-intruder@example.com")

    assert client.post(f"/api/projects/{pid}/design/design_system/generate", json={}, headers=h1).status_code == 200
    assert other.get(f"/api/projects/{pid}/design", headers=h2).status_code == 404
    assert other.get(f"/api/projects/{pid}/design/design_system", headers=h2).status_code == 404
    assert other.post(f"/api/projects/{pid}/design/design_system/generate", json={}, headers=h2).status_code == 404
    assert other.get(f"/api/projects/{pid}/design/prototype", headers=h2).status_code == 404

    with SessionLocal() as db_session:
        d1 = DesignArtifact(project_id=pid, artifact_type="prototype", version=1, status="generating", basis={}, created_by="u1", row_version=1)
        d2 = DesignArtifact(project_id=pid, artifact_type="prototype", version=2, status="generating", basis={}, created_by="u1", row_version=1)
        db_session.add_all([d1, d2])
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
