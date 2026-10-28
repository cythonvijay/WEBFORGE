"""Phase 13 tests: Product Architecture artifact, upstream Phase 9-12 prerequisite & staleness gates,
cross-artifact reference validation, diagram-to-inventory consistency, PRD requirement traceability,
copy-on-write immutability, manual stage completion guard, upstream invalidation, and DB constraints."""
import copy
import pytest
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app import ai
from app.architecture import GeneratedArchitecture
from app.db import SessionLocal
from app.models import ArchitectureDocument
from tests.test_design import StubPhase12Provider, _setup_project_with_approved_phase11
from tests.test_strategy_prd import auth


def _architecture_payload() -> dict:
    return {
        "system_overview": {
            "product_scope": (
                "ScopeLock web application enabling freelance agencies to capture client discovery notes, "
                "author versioned scope baselines with explicit exclusions, and share read-only sign-off links."
            ),
            "system_boundaries": [
                "Authenticated agency workspace browser client communicating over HTTPS JSON REST APIs.",
                "Transactional relational database storing agency projects, discovery notes, and immutable scope baselines.",
                "Outbound transactional email notification adapter for client baseline sign-off alerts.",
            ],
            "user_roles_and_trust_boundaries": [
                {
                    "role": "Agency Principal / Lead PM",
                    "persona_ids": ["P-1"],
                    "trust_zone": "authenticated_user",
                    "allowed_capabilities": [
                        "Create projects and capture client discovery notes",
                        "Draft, validate, and lock versioned scope baselines",
                    ],
                },
                {
                    "role": "Delivery Operations Manager",
                    "persona_ids": ["P-2"],
                    "trust_zone": "authenticated_user",
                    "allowed_capabilities": [
                        "Audit deliverable-to-intake provenance links",
                        "Export approved scope baselines and review change requests",
                    ],
                },
            ],
            "components": [
                {
                    "id": "COMP-1",
                    "name": "Scope Workspace Web Client",
                    "layer": "frontend",
                    "purpose": "Single-page React application rendering the Projects Dashboard, Scope Baseline Editor, and Provenance views.",
                    "responsibilities": [
                        "Render responsive dashboard, baseline editor, and provenance inspection screens",
                        "Perform client-side field validation before submitting baseline drafts",
                    ],
                    "communicates_with": ["COMP-2"],
                    "prd_requirement_ids": ["FR-1", "FR-2", "NFR-1"],
                    "design_refs": ["WF-1", "WF-2", "WF-3", "CMP-1", "CMP-2", "CMP-3", "SCR-1", "SCR-2", "SCR-3"],
                },
                {
                    "id": "COMP-2",
                    "name": "Scope Baseline & Provenance API Service",
                    "layer": "backend",
                    "purpose": "FastAPI application enforcing authentication, project ownership, deliverable provenance validation, and baseline locking.",
                    "responsibilities": [
                        "Authenticate agency users and enforce project-level authorization boundaries",
                        "Validate that every scope deliverable links to a verified discovery note and explicit exclusion rule",
                        "Lock published scope baselines as immutable versions and trigger sign-off notifications",
                    ],
                    "communicates_with": ["COMP-3", "INT-1"],
                    "prd_requirement_ids": ["FR-1", "FR-2", "NFR-1"],
                    "design_refs": ["SCR-1", "SCR-2", "SCR-3", "FLOW-1", "FLOW-2"],
                },
                {
                    "id": "COMP-3",
                    "name": "Relational Scope Store",
                    "layer": "data",
                    "purpose": "PostgreSQL relational persistence layer storing projects, intake notes, deliverables, and locked baseline snapshots.",
                    "responsibilities": [
                        "Enforce foreign-key integrity and optimistic row-version concurrency on scope baselines",
                        "Persist immutable published baseline revisions and audit timestamps",
                    ],
                    "communicates_with": [],
                    "prd_requirement_ids": ["FR-1", "FR-2"],
                    "design_refs": ["WF-2", "WF-3"],
                },
            ],
            "external_integrations": [
                {
                    "id": "INT-1",
                    "name": "Transactional Email Notification Adapter",
                    "purpose": "Send baseline publication and client sign-off notification emails when a baseline version is locked.",
                    "protocol_or_contract": "HTTPS REST webhook payload with idempotency key and 5-second timeout",
                    "failure_mode_and_fallback": "Queue notification retry on transient 5xx/timeout without rolling back the locked baseline transaction.",
                    "implementation_status": "proposed_target",
                    "prd_requirement_ids": ["FR-1"],
                }
            ],
        },
        "application_architecture": {
            "frontend_boundaries": [
                {
                    "id": "FE-1",
                    "module_name": "ProjectsDashboardModule",
                    "route_or_feature_scope": "/projects — Agency project list, baseline status overview, and entry into scope editor",
                    "component_id": "COMP-1",
                    "prototype_screen_ids": ["SCR-1"],
                    "design_component_ids": ["CMP-1", "CMP-3"],
                    "design_tokens_used": ["--color-primary", "--color-surface", "--font-heading-lg", "--space-4"],
                    "prd_requirement_ids": ["FR-1", "NFR-1"],
                },
                {
                    "id": "FE-2",
                    "module_name": "ScopeBaselineEditorModule",
                    "route_or_feature_scope": "/projects/:id/scope and /projects/:id/provenance — Deliverable editor, exclusions, and provenance inspector",
                    "component_id": "COMP-1",
                    "prototype_screen_ids": ["SCR-2", "SCR-3"],
                    "design_component_ids": ["CMP-1", "CMP-2", "CMP-3"],
                    "design_tokens_used": ["--color-primary", "--color-danger", "--font-body", "--space-2"],
                    "prd_requirement_ids": ["FR-1", "FR-2", "NFR-1"],
                },
            ],
            "backend_modules": [
                {
                    "id": "BE-1",
                    "module_name": "ScopeBaselineService",
                    "service_responsibility": "Manage draft scope baselines, enforce exclusion and acceptance criteria rules, and publish immutable baseline versions.",
                    "component_id": "COMP-2",
                    "prd_requirement_ids": ["FR-1", "NFR-1"],
                },
                {
                    "id": "BE-2",
                    "module_name": "ProvenanceTraceService",
                    "service_responsibility": "Link scope deliverables to discovery intake notes and compute unlinked-deliverable warnings.",
                    "component_id": "COMP-2",
                    "prd_requirement_ids": ["FR-2"],
                },
            ],
            "authentication_and_authorization": (
                "HttpOnly SameSite=Lax JWT access and rotating refresh cookies; every project route verifies project ownership before reading or mutating scope data."
            ),
            "state_management_and_data_fetching": (
                "Typed REST client with explicit loading, error, and optimistic content-hash conflict detection on baseline edits."
            ),
            "error_handling_and_logging": (
                "Structured JSON error responses (401, 403, 404, 409, 422, 502, 503) with correlation IDs and zero secret leakage."
            ),
            "configuration_and_env_separation": (
                "12-factor environment variables validated via Pydantic Settings separating local SQLite/PostgreSQL dev, staging, and production secrets."
            ),
        },
        "data_architecture": {
            "entities": [
                {
                    "id": "ENT-1",
                    "name": "ScopeBaseline",
                    "description": "Versioned scope baseline container for an agency engagement with draft and locked states.",
                    "owning_component_id": "COMP-3",
                    "key_fields": ["id (UUID)", "project_id (FK)", "version (int)", "status (draft|locked)", "content_hash (sha256)"],
                    "access_boundary": "Read/write restricted to authenticated owning agency user via ScopeBaselineService.",
                    "retention_and_lifecycle": "Retained for the life of the parent project; locked versions are immutable.",
                    "sensitive_data_handling": "Contains commercial scope terms; encrypted in transit and scoped by project_id.",
                    "status": "approved_scope",
                    "prd_requirement_ids": ["FR-1"],
                },
                {
                    "id": "ENT-2",
                    "name": "ScopeDeliverableItem",
                    "description": "Individual deliverable item within a scope baseline with explicit exclusions and intake provenance link.",
                    "owning_component_id": "COMP-3",
                    "key_fields": ["id (UUID)", "baseline_id (FK)", "title (varchar)", "exclusions (jsonb)", "intake_note_ref (varchar)"],
                    "access_boundary": "Accessed exclusively through parent ScopeBaseline ownership checks.",
                    "retention_and_lifecycle": "Copied on write when a new baseline draft version is forked from a locked baseline.",
                    "sensitive_data_handling": "Client discovery quotes sanitized and stored without raw credentials or PII.",
                    "status": "proposed",
                    "prd_requirement_ids": ["FR-1", "FR-2"],
                },
            ],
            "relationships": [
                {
                    "source_entity_id": "ENT-1",
                    "target_entity_id": "ENT-2",
                    "cardinality": "1:N",
                    "description": "Each ScopeBaseline version owns one or more ScopeDeliverableItem records.",
                }
            ],
            "transaction_and_integrity_rules": [
                "Publishing a ScopeBaseline executes in a single ACID transaction that verifies all deliverables have non-empty exclusions and provenance links.",
                "Concurrent edits check content_hash and SQLAlchemy row_version to prevent lost updates.",
            ],
            "migration_strategy": (
                "Sequential forward-only Alembic migrations with explicit upgrade() and downgrade() steps verified against SQLite and PostgreSQL."
            ),
        },
        "api_architecture": {
            "endpoints": [
                {
                    "id": "API-1",
                    "method": "GET",
                    "path": "/api/projects/{project_id}/baselines",
                    "summary": "Retrieve the current scope baseline, version history, and provenance coverage summary.",
                    "component_id": "COMP-2",
                    "entity_ids": ["ENT-1", "ENT-2"],
                    "auth_requirement": "authenticated",
                    "request_contract": "Path parameter project_id (UUID); authenticated session cookie.",
                    "response_contract": "200 OK with current ScopeBaseline, deliverable items, and provenance warnings.",
                    "validation_and_error_handling": "Returns 401 if unauthenticated, 404 if project is not owned by caller.",
                    "pagination_and_filtering": "Version history ordered descending by version; deliverable list filtered by status.",
                    "implementation_status": "proposed_target",
                    "prototype_screen_ids": ["SCR-1", "SCR-2"],
                    "prd_requirement_ids": ["FR-1", "NFR-1"],
                },
                {
                    "id": "API-2",
                    "method": "POST",
                    "path": "/api/projects/{project_id}/baselines/{version}/deliverables",
                    "summary": "Add or update a scope deliverable item linked to a discovery intake note.",
                    "component_id": "COMP-2",
                    "entity_ids": ["ENT-1", "ENT-2"],
                    "auth_requirement": "authenticated",
                    "request_contract": "JSON body with base_hash, title, acceptance_criteria, exclusions, and intake_note_ref.",
                    "response_contract": "200 OK with updated ScopeBaseline draft (or new copy-on-write version) and new content_hash.",
                    "validation_and_error_handling": "Returns 409 on base_hash mismatch, 422 if exclusions or intake_note_ref are missing.",
                    "pagination_and_filtering": "Not applicable for single-resource mutation.",
                    "implementation_status": "proposed_target",
                    "prototype_screen_ids": ["SCR-2", "SCR-3"],
                    "prd_requirement_ids": ["FR-1", "FR-2"],
                },
            ],
            "request_response_conventions": "JSON request/response bodies with ISO-8601 UTC timestamps and SHA-256 content_hash concurrency tokens.",
            "validation_and_error_conventions": "Pydantic v2 strict schema validation returning 422 field errors and 409 state conflict messages.",
            "integration_contracts_and_failure_behavior": "Outbound email notifications use bounded timeouts and non-blocking retry queues.",
        },
        "deployment_architecture": {
            "local_development_environment": "Vite React TypeScript frontend dev server and Uvicorn FastAPI backend with SQLite/PostgreSQL.",
            "services_and_infrastructure": [
                {
                    "id": "SVC-1",
                    "name": "Web & API Application Runtime",
                    "environment": "all",
                    "responsibility": "Serve compiled React SPA assets and FastAPI REST endpoints.",
                    "component_ids": ["COMP-1", "COMP-2"],
                    "implementation_status": "proposed_target",
                },
                {
                    "id": "SVC-2",
                    "name": "Managed PostgreSQL Database",
                    "environment": "production",
                    "responsibility": "Primary ACID relational data store for projects, baselines, and deliverables.",
                    "component_ids": ["COMP-3"],
                    "implementation_status": "proposed_target",
                },
            ],
            "configuration_and_secret_management": "Environment variables injected at runtime; secrets never committed to Git or exposed to browser bundles.",
            "deployment_boundaries": "Stateless API containers behind TLS reverse proxy; database isolated in private network subnet.",
            "health_checks_and_observability": "Liveness (/api/health) and database readiness (/api/ready) probes with structured request logging.",
            "backup_recovery_and_failure": "Daily automated database snapshots and point-in-time recovery before running schema migrations.",
        },
        "decisions": [
            {
                "id": "ADR-1",
                "title": "Copy-on-Write Immutability for Locked Scope Baselines",
                "status": "proposed",
                "context_and_problem": "Agencies need an tamper-evident record of what the client approved while still being able to draft scope revisions.",
                "decision": "Store each ScopeBaseline as a versioned row where locked versions are immutable and edits fork a new draft version.",
                "alternatives_and_tradeoffs": [
                    "In-place mutation with audit log table — simpler queries but risks accidental overwrite of signed-off baseline terms."
                ],
                "rationale": "Guarantees historical sign-off integrity and matches WebForge artifact versioning semantics.",
                "consequences_and_risks": [
                    "Requires copy-on-write cloning of deliverable items when editing an approved baseline."
                ],
                "prd_requirement_ids": ["FR-1", "FR-2"],
                "source_refs": ["FR-1", "FR-2", "WF-2", "CMP-3", "SCR-2", "COMP-2", "ENT-1"],
            }
        ],
        "diagrams": [
            {
                "id": "DIAG-1",
                "diagram_type": "component",
                "title": "ScopeLock Component & Integration Topology",
                "summary": "Shows request flow from the React workspace client through the FastAPI service to the relational store and email adapter.",
                "nodes": [
                    {"id": "N1", "label": "Scope Workspace Client", "reference_id": "COMP-1"},
                    {"id": "N2", "label": "Scope Baseline API", "reference_id": "COMP-2"},
                    {"id": "N3", "label": "Relational Scope Store", "reference_id": "COMP-3"},
                    {"id": "N4", "label": "Email Notification Adapter", "reference_id": "INT-1"},
                ],
                "edges": [
                    {"from_node": "N1", "to_node": "N2", "label": "HTTPS JSON REST"},
                    {"from_node": "N2", "to_node": "N3", "label": "SQLAlchemy ACID Txn"},
                    {"from_node": "N2", "to_node": "N4", "label": "Sign-off Webhook"},
                ],
                "mermaid": (
                    "flowchart LR\n"
                    '    N1["Scope Workspace Client (COMP-1)"]\n'
                    '    N2["Scope Baseline API (COMP-2)"]\n'
                    '    N3["Relational Scope Store (COMP-3)"]\n'
                    '    N4["Email Notification Adapter (INT-1)"]\n'
                    '    N1 -->|"HTTPS JSON REST"| N2\n'
                    '    N2 -->|"SQLAlchemy ACID Txn"| N3\n'
                    '    N2 -->|"Sign-off Webhook"| N4'
                ),
            },
            {
                "id": "DIAG-2",
                "diagram_type": "data_relationship",
                "title": "ScopeBaseline & Deliverable Entity Relationship Diagram",
                "summary": "Illustrates 1:N ownership between versioned ScopeBaseline records and ScopeDeliverableItem rows.",
                "nodes": [
                    {"id": "E1", "label": "ScopeBaseline", "reference_id": "ENT-1"},
                    {"id": "E2", "label": "ScopeDeliverableItem", "reference_id": "ENT-2"},
                ],
                "edges": [
                    {"from_node": "E1", "to_node": "E2", "label": "1:N owns deliverables"},
                ],
                "mermaid": (
                    "flowchart LR\n"
                    '    E1["ScopeBaseline (ENT-1)"]\n'
                    '    E2["ScopeDeliverableItem (ENT-2)"]\n'
                    '    E1 -->|"1:N owns deliverables"| E2'
                ),
            },
        ],
    }


class StubPhase13Provider(StubPhase12Provider):
    def __init__(self, architecture_data=None, fail: Exception | None = None):
        super().__init__(fail=fail)
        self.architecture_data = copy.deepcopy(architecture_data or _architecture_payload())

    async def generate_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel:
        self.prompts.append(prompt)
        if self.fail:
            raise self.fail
        if schema is GeneratedArchitecture:
            return schema.model_validate(self.architecture_data)
        return await super().generate_structured(prompt, schema)


def _setup_project_with_approved_phase12(client, monkeypatch, email="arch-founder@example.com"):
    h, pid, _ = _setup_project_with_approved_phase11(client, monkeypatch, email=email)
    stub = StubPhase13Provider()
    monkeypatch.setattr(ai, "get_provider", lambda: stub)

    for dtype in ("design_system", "prototype"):
        gen = client.post(f"/api/projects/{pid}/design/{dtype}/generate", json={}, headers=h).json()
        hsh = gen["current"]["content_hash"]
        client.post(f"/api/projects/{pid}/design/{dtype}/versions/1/submit", json={"base_hash": hsh}, headers=h)
        app_res = client.post(
            f"/api/projects/{pid}/design/{dtype}/versions/1/approve",
            json={"content_hash": hsh, "acknowledge_unverified": True},
            headers=h,
        )
        assert app_res.status_code == 200

    ov = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    assert ov["next_action"] == "architecture"
    return h, pid, stub


def test_architecture_prerequisite_gates_require_approved_phase12(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase11(client, monkeypatch, email="arch-gates@example.com")
    monkeypatch.setattr(ai, "get_provider", lambda: StubPhase13Provider())

    # Before Phase 12 Design System & Prototype are approved, Architecture reports missing prerequisites
    st = client.get(f"/api/projects/{pid}/architecture", headers=h).json()
    assert st["prerequisites"]["ready"] is False
    assert st["can_generate"] is False
    missing_keys = [m["artifact"] for m in st["prerequisites"]["missing"]]
    assert "design_system" in missing_keys and "prototype" in missing_keys
    assert st["prerequisites"]["missing"][0]["workspace_path"] == f"/projects/{pid}/design-system"

    gen_blocked = client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h)
    assert gen_blocked.status_code == 409

    # Approve Design System only -> Prototype is still missing
    ds_gen = client.post(f"/api/projects/{pid}/design/design_system/generate", json={}, headers=h).json()
    ds_hash = ds_gen["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/design/design_system/versions/1/submit", json={"base_hash": ds_hash}, headers=h)
    client.post(
        f"/api/projects/{pid}/design/design_system/versions/1/approve",
        json={"content_hash": ds_hash, "acknowledge_unverified": True},
        headers=h,
    )
    st2 = client.get(f"/api/projects/{pid}/architecture", headers=h).json()
    assert st2["prerequisites"]["ready"] is False
    assert [m["artifact"] for m in st2["prerequisites"]["missing"]] == ["prototype"]
    assert st2["prerequisites"]["missing"][0]["workspace_path"] == f"/projects/{pid}/prototype"
    assert client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h).status_code == 409


def test_architecture_generation_reference_and_diagram_validation(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase12(client, monkeypatch, email="arch-val@example.com")

    res = client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h)
    assert res.status_code == 200
    state = res.json()
    doc = state["current"]
    assert doc["version"] == 1
    assert doc["status"] == "draft"
    assert doc["basis"]["prd_version"] == 1
    assert doc["basis"]["design_system_version"] == 1
    assert doc["basis"]["prototype_version"] == 1
    assert doc["completeness"]["complete_traceability"] is True
    assert doc["completeness"]["traced_requirements"] == 3
    base_hash = doc["content_hash"]

    # 1. Reject external URL in overview scope
    bad_url = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/overview",
        json={"base_hash": base_hash, "product_scope": "See https://example.com/architecture for details."},
        headers=h,
    )
    assert bad_url.status_code == 422

    # 2. Reject unsupported certification / load-test claim
    bad_claim = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/overview",
        json={
            "base_hash": base_hash,
            "product_scope": "This architecture is SOC 2 certified and load-tested to 100k RPS.",
        },
        headers=h,
    )
    assert bad_claim.status_code == 422

    # 3. Reject component referencing unknown PRD requirement
    bad_comp_req = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/components/COMP-1",
        json={"base_hash": base_hash, "prd_requirement_ids": ["FR-999"]},
        headers=h,
    )
    assert bad_comp_req.status_code == 422

    # 4. Reject component referencing unknown UX/Design artifact
    bad_comp_design = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/components/COMP-1",
        json={"base_hash": base_hash, "design_refs": ["SCR-999"]},
        headers=h,
    )
    assert bad_comp_design.status_code == 422

    # 5. Reject domain entity unsupported by PRD requirements
    bad_ent = client.post(
        f"/api/projects/{pid}/architecture/versions/1/entities",
        json={
            "base_hash": base_hash,
            "name": "InventedBlockchainLedger",
            "description": "Unapproved entity not in PRD",
            "owning_component_id": "COMP-3",
            "key_fields": ["id", "block_hash"],
            "access_boundary": "Internal",
            "retention_and_lifecycle": "Permanent",
            "sensitive_data_handling": "None",
            "status": "proposed",
            "prd_requirement_ids": ["FR-999"],
        },
        headers=h,
    )
    assert bad_ent.status_code == 422

    # 6. Reject API endpoint referencing unknown entity
    bad_ep = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/endpoints/API-1",
        json={"base_hash": base_hash, "entity_ids": ["ENT-999"]},
        headers=h,
    )
    assert bad_ep.status_code == 422

    # 7. Reject diagram node referencing nonexistent component/entity
    bad_diag_node = client.post(
        f"/api/projects/{pid}/architecture/versions/1/diagrams",
        json={
            "base_hash": base_hash,
            "diagram_type": "component",
            "title": "Invalid Node Diagram",
            "summary": "References unknown component COMP-99",
            "nodes": [
                {"id": "A", "label": "Client", "reference_id": "COMP-1"},
                {"id": "B", "label": "Ghost", "reference_id": "COMP-99"},
            ],
            "edges": [{"from_node": "A", "to_node": "B", "label": "Calls"}],
        },
        headers=h,
    )
    assert bad_diag_node.status_code == 422

    # 8. Reject component diagram edge that contradicts written component communication inventory (COMP-1 does not directly call COMP-3)
    bad_diag_edge = client.post(
        f"/api/projects/{pid}/architecture/versions/1/diagrams",
        json={
            "base_hash": base_hash,
            "diagram_type": "component",
            "title": "Contradictory Component Diagram",
            "summary": "Connects COMP-1 directly to COMP-3 bypassing COMP-2",
            "nodes": [
                {"id": "A", "label": "Client", "reference_id": "COMP-1"},
                {"id": "C", "label": "DB", "reference_id": "COMP-3"},
            ],
            "edges": [{"from_node": "A", "to_node": "C", "label": "Direct SQL from browser"}],
        },
        headers=h,
    )
    assert bad_diag_edge.status_code == 422


def test_architecture_traceability_gaps_and_requires_review_block_submission(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase12(client, monkeypatch, email="arch-trace@example.com")
    gen = client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h).json()
    h1 = gen["current"]["content_hash"]

    # Remove FR-2 from COMP-1, COMP-2, COMP-3 so FR-2 has no component coverage
    r1 = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/components/COMP-1",
        json={"base_hash": h1, "prd_requirement_ids": ["FR-1", "NFR-1"]},
        headers=h,
    ).json()
    h2 = r1["document"]["content_hash"]
    r2 = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/components/COMP-2",
        json={"base_hash": h2, "prd_requirement_ids": ["FR-1", "NFR-1"]},
        headers=h,
    ).json()
    h3 = r2["document"]["content_hash"]
    r3 = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/components/COMP-3",
        json={"base_hash": h3, "prd_requirement_ids": ["FR-1"]},
        headers=h,
    ).json()
    h4 = r3["document"]["content_hash"]

    assert r3["document"]["completeness"]["complete_traceability"] is False
    assert "FR-2" in r3["document"]["completeness"]["uncovered_requirements"]
    assert r3["state"]["can_submit"] is False

    # Submitting with uncovered FR-2 is rejected with 422
    sub_blocked = client.post(
        f"/api/projects/{pid}/architecture/versions/1/submit",
        json={"base_hash": h4},
        headers=h,
    )
    assert sub_blocked.status_code == 422
    assert "FR-2" in str(sub_blocked.json()["detail"])

    # Restore FR-2 on COMP-2, but mark ADR-1 as requires_review -> still blocks submit
    r4 = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/components/COMP-2",
        json={"base_hash": h4, "prd_requirement_ids": ["FR-1", "FR-2", "NFR-1"]},
        headers=h,
    ).json()
    h5 = r4["document"]["content_hash"]
    r5 = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/decisions/ADR-1",
        json={"base_hash": h5, "status": "requires_review"},
        headers=h,
    ).json()
    h6 = r5["document"]["content_hash"]
    assert client.post(
        f"/api/projects/{pid}/architecture/versions/1/submit",
        json={"base_hash": h6},
        headers=h,
    ).status_code == 422

    # Accept ADR-1 -> submission succeeds
    r6 = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/decisions/ADR-1",
        json={"base_hash": h6, "status": "accepted"},
        headers=h,
    ).json()
    h7 = r6["document"]["content_hash"]
    sub_ok = client.post(
        f"/api/projects/{pid}/architecture/versions/1/submit",
        json={"base_hash": h7},
        headers=h,
    )
    assert sub_ok.status_code == 200
    assert sub_ok.json()["status"] == "in_review"


def test_architecture_approval_copy_on_write_immutability_and_manual_stage_guard(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase12(client, monkeypatch, email="arch-cow@example.com")

    # Cannot mark architecture stage complete manually before an approved ArchitectureDocument exists
    manual_complete = client.put(
        f"/api/projects/{pid}/stages/architecture",
        json={"status": "complete"},
        headers=h,
    )
    assert manual_complete.status_code == 409
    assert "Product Architecture has not been approved yet" in manual_complete.json()["detail"]

    # Generate and submit v1
    gen = client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h).json()
    h1 = gen["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/architecture/versions/1/submit", json={"base_hash": h1}, headers=h)
    assert client.get(f"/api/projects/{pid}/overview", headers=h).json()["needs_review"] == ["architecture"]

    # Approving without acknowledging proposed items (ADR-1 and ENT-2 are 'proposed') returns 409
    app_no_ack = client.post(
        f"/api/projects/{pid}/architecture/versions/1/approve",
        json={"content_hash": h1, "acknowledge_unverified": False},
        headers=h,
    )
    assert app_no_ack.status_code == 409

    # Approve with acknowledge_unverified=True
    app_ok = client.post(
        f"/api/projects/{pid}/architecture/versions/1/approve",
        json={"content_hash": h1, "acknowledge_unverified": True, "note": "Approved Phase 13 architecture"},
        headers=h,
    )
    assert app_ok.status_code == 200
    st = app_ok.json()
    assert st["status"] == "approved"
    assert st["approved_version"] == 1
    assert st["lifecycle"]["status"] == "complete"
    assert st["lifecycle"]["architecture_complete"] is True

    # Project Brain records architecture_spec pointer and protects it from direct PUT
    brain = client.get(f"/api/projects/{pid}/brain", headers=h).json()["brain"]
    assert brain["architecture_spec"]["approved_version"] == 1
    assert brain["architecture_spec"]["content_hash"] == h1
    assert client.put(
        f"/api/projects/{pid}/brain/architecture_spec",
        json={"value": {}},
        headers=h,
    ).status_code == 403

    # Overview next_action advances to frontend
    ov = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    assert "architecture" in ov["completed"]
    assert ov["next_action"] == "frontend"

    # Editing approved v1 creates copy-on-write draft v2 while keeping v1 immutable
    edit_res = client.patch(
        f"/api/projects/{pid}/architecture/versions/1/components/COMP-1",
        json={"base_hash": h1, "purpose": "Updated React SPA workspace client with offline draft indicator."},
        headers=h,
    )
    assert edit_res.status_code == 200
    v2 = edit_res.json()["document"]
    assert v2["version"] == 2
    assert v2["status"] == "draft"
    assert v2["created_via"] == "copy_of_approved"
    assert v2["parent_version"] == 1

    # v1 is untouched
    v1_after = client.get(f"/api/projects/{pid}/architecture/versions/1", headers=h).json()
    assert v1_after["status"] == "approved"
    assert v1_after["content_hash"] == h1
    assert "offline draft indicator" not in v1_after["content"]["system_overview"]["components"][0]["purpose"]

    # Architecture stage demoted to in_progress while v2 draft is open, and cannot be forced complete manually
    assert edit_res.json()["state"]["lifecycle"]["status"] == "in_progress"
    assert client.put(
        f"/api/projects/{pid}/stages/architecture",
        json={"status": "complete"},
        headers=h,
    ).status_code == 409


def test_architecture_upstream_invalidation_and_earlier_stage_isolation(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase12(client, monkeypatch, email="arch-stale@example.com")

    gen = client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h).json()
    h1 = gen["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/architecture/versions/1/submit", json={"base_hash": h1}, headers=h)
    client.post(
        f"/api/projects/{pid}/architecture/versions/1/approve",
        json={"content_hash": h1, "acknowledge_unverified": True},
        headers=h,
    )
    assert client.get(f"/api/projects/{pid}/architecture", headers=h).json()["lifecycle"]["status"] == "complete"

    # Edit upstream Design System (creates copy-on-write draft v2 on design_system)
    ds_cur = client.get(f"/api/projects/{pid}/design/design_system", headers=h).json()["current"]
    ds_patch = client.patch(
        f"/api/projects/{pid}/design/design_system/versions/1/components/CMP-1",
        json={"base_hash": ds_cur["content_hash"], "purpose": "Updated button purpose in Design System v2"},
        headers=h,
    )
    assert ds_patch.status_code == 200

    # Architecture is now flagged stale and architecture stage demotes from complete to in_progress
    arch_st = client.get(f"/api/projects/{pid}/architecture", headers=h).json()
    assert arch_st["is_stale"] is True
    assert any("Design System" in r for r in arch_st["stale_reasons"])
    assert arch_st["lifecycle"]["status"] == "in_progress"
    assert arch_st["lifecycle"]["architecture_complete"] is False

    # Earlier stages (research, product, ux) remain complete
    ov = client.get(f"/api/projects/{pid}/overview", headers=h).json()
    for earlier in ("research", "product", "ux"):
        assert earlier in ov["completed"]


def test_architecture_concurrency_isolation_provider_failures_and_manual_fallback(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase12(client, monkeypatch, email="arch-err@example.com")

    # 1. ProviderNotConfigured -> 503 and stores failed status without corrupting state
    class Unconfigured(ai.AIProvider):
        async def generate(self, prompt: str) -> str:
            raise ai.ProviderNotConfigured("missing key")

    monkeypatch.setattr(ai, "get_provider", lambda: Unconfigured())
    r503 = client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h)
    assert r503.status_code == 503
    assert client.get(f"/api/projects/{pid}/architecture", headers=h).json()["status"] == "failed"

    # 2. ProviderError (timeout) -> 502
    monkeypatch.setattr(ai, "get_provider", lambda: StubPhase13Provider(fail=ai.ProviderError("timeout", "timed out")))
    r502 = client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h)
    assert r502.status_code == 502

    # 3. Manual fallback creation succeeds when AI provider is unconfigured
    manual_res = client.post(
        f"/api/projects/{pid}/architecture/manual",
        json=_architecture_payload(),
        headers=h,
    )
    assert manual_res.status_code == 200
    doc = manual_res.json()["current"]
    assert doc["created_via"] == "manual"
    assert doc["status"] == "draft"
    h_doc = doc["content_hash"]

    # 4. Stale base_hash on edit returns 409
    stale_edit = client.patch(
        f"/api/projects/{pid}/architecture/versions/{doc['version']}/overview",
        json={"base_hash": "0" * 64, "product_scope": "Concurrent conflicting edit text here."},
        headers=h,
    )
    assert stale_edit.status_code == 409

    # 5. Cross-user isolation returns 404
    h_other = auth(client, "other-arch-user@example.com")
    assert client.get(f"/api/projects/{pid}/architecture", headers=h_other).status_code == 404
    assert client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h_other).status_code == 404


def test_architecture_db_partial_unique_indexes(client, monkeypatch):
    _, pid, _ = _setup_project_with_approved_phase12(client, monkeypatch, email="arch-db-idx@example.com")
    with SessionLocal() as db:
        db.add(ArchitectureDocument(project_id=pid, version=1, status="draft", basis={}))
        db.commit()
        db.add(ArchitectureDocument(project_id=pid, version=2, status="in_review", basis={}))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
