# Phase 13 — Product Architecture Specification

Phase 13 (`architecture` lifecycle stage, route `/projects/:projectId/architecture`) turns the approved upstream product specification into a validated, versioned technical architecture (`ArchitectureDocument`) that governs downstream implementation stages (`frontend`, `backend`, `database`, `api`).

## 1. Lifecycle Model & Upstream Prerequisite Gates

In `backend/app/lifecycle.py`, the 5 Engineering stages are modeled as separate lifecycle stages with explicit dependencies:
- `architecture` depends on `["product", "design"]`
- `frontend`, `backend`, and `database` depend on `["architecture"]`
- `api` depends on `["backend", "database"]`

Before generating, editing, submitting, or approving an `ArchitectureDocument`, `check_prerequisites(db, project_id)` verifies that all upstream artifacts are approved, current, and free of open drafts:
- **Phase 9**: `ResearchReport` (`research` stage `complete`)
- **Phase 10**: `StrategyDocument` and `PrdDocument` (`product` stage `complete`)
- **Phase 11**: `Personas`, `User Journeys`, `Information Architecture`, `Wireframes`, and `UX Review` (with zero unresolved critical findings; `ux` stage `complete`)
- **Phase 12**: `Design System` and `Interactive Prototype` (`design` stage `complete` and non-stale)

Any missing, stale, or open-draft prerequisite returns HTTP 409 with structured `missing` prerequisite details and `workspace_path` navigation links.

## 2. Schema, Reference Validation & Diagram Consistency (`backend/app/architecture.py`)

Each `ArchitectureContent` document validates:
- **A. System Overview (`SystemOverview`)**: `product_scope`, `system_boundaries`, `user_roles_and_trust_boundaries` (linked to `P-*`), `components` (`COMP-1..N` linked to `FR-*`/`NFR-*` and `WF-*`/`CMP-*`/`SCR-*`/`FLOW-*`/`IA-*`), and `external_integrations` (`INT-1..N` with `proposed_target` vs `verified_existing` status).
- **B. Application Architecture (`ApplicationArchitecture`)**: `frontend_boundaries` (`FE-1..N` linked to `COMP-*`, `SCR-*`, `CMP-*`, design tokens, and `FR-*`/`NFR-*`), `backend_modules` (`BE-1..N`), authentication/authorization, state/data fetching, error handling/logging, and environment separation.
- **C. Data Architecture (`DataArchitecture`)**: `entities` (`ENT-1..N` owned by `COMP-*` and backed by `FR-*`/`NFR-*` so no domain entity is invented outside approved PRD scope), `relationships` (`1:1`, `1:N`, `M:N`), `transaction_and_integrity_rules`, and `migration_strategy`.
- **D. API & Integration Architecture (`ApiArchitecture`)**: `endpoints` (`API-1..N` with HTTP method, `/` path, `component_id`, `entity_ids`, `auth_requirement`, contracts, `proposed_target` vs `verified_existing` status, `prototype_screen_ids`, and `prd_requirement_ids`).
- **E. Deployment & Operational Architecture (`DeploymentArchitecture`)**: `services_and_infrastructure` (`SVC-1..N` linked to `COMP-*` with `proposed_target` vs `verified_current` status), local dev, secrets, deployment boundaries, health checks, and backup/recovery.
- **F. Technical Decisions (`decisions`)**: `ADR-1..N` with status (`proposed | accepted | requires_review`), context, decision, alternatives/trade-offs, rationale, consequences/risks, `prd_requirement_ids`, and `source_refs`.
- **G. Validated Architecture Diagrams (`diagrams`)**: `DIAG-1..N` (`system_context`, `component`, `data_relationship`, `request_flow`, `deployment`) with structured `nodes`, `edges`, and Mermaid definitions. Every node `reference_id` must exist in the architecture inventory, `component` diagram edges must match `communicates_with`, and `data_relationship` diagram edges must match `data_architecture.relationships`.
- **H. Requirement Traceability Matrix (`traceability`)**: Deterministically computed via `compute_traceability(arch)` mapping every PRD requirement (`FR-*`, `NFR-*`) to `COMP-*`, `ENT-*`/`API-*`/`BE-*`/`INT-*`, `ADR-*`, and `SCR-*`/`CMP-*`/`WF-*`. Uncovered requirements or `requires_review` items block submission and approval (HTTP 422).

## 3. Versioning, Immutability, Approval & Upstream Invalidation

- Approved `ArchitectureDocument` rows are immutable; editing an approved version forks a new draft (`created_via="copy_of_approved"`, `parent_version=approved.version`) and demotes the `architecture` stage from `complete` to `in_progress`.
- Approving an `in_review` version records `architecture_spec` in `ProjectBrain` (`change_type="architecture_approved"`, protected by `PROTECTED_SECTIONS`) and marks the `architecture` lifecycle stage `complete`.
- `PUT /api/projects/{id}/stages/architecture` with `{"status": "complete"}` is guarded by `architecture_stage_completion_check(db, project_id)` so the stage cannot be marked complete manually without an approved, current, fully traced `ArchitectureDocument`.

## Phase 16 — SEO, Analytics & Performance Layer

- **Backend Module (`backend/app/optimization.py`, `backend/app/optimization_api.py`)**:
  - Consumes approved upstream Research (`0003`), Strategy & PRD (`0004`), UX Artifacts (`0005`), Design System & Prototype (`0006`), and Product Architecture (`0007`) to build `OptimizationBasisSummary` and validate cross-artifact references (`PRD -> UX/Prototype -> Architecture -> SEO/Analytics/Performance`).
  - Persists versioned `seo`, `analytics`, and `performance` specifications in `optimization_artifacts` (`0008`), updates `ProjectBrain.optimization_spec` on exact-hash approval, and invalidates `seo` and `analytics` lifecycle stages (`needs_review`) when upstream artifacts advance (`sync_optimization_stages`).
- **Scope Separation**:
  - Generated-product analytics (`AnalyticsContent`) is strictly separated from WebForge platform operational observability (`MetricsRegistry` in `backend/app/observability.py`, `scope="webforge_platform_operational_only"`).

## Phase 17 — Documentation & Specification Export Architecture
- **Domain & Validation Layer (`backend/app/documentation_export.py`)**: Collects read-only project snapshots across all 14 lifecycle artifacts, verifies canonical SHA-256 hashes and Project Brain pointers, evaluates cross-artifact staleness and PRD traceability, scans for secrets/internal paths, and renders deterministic Markdown bundles (`README.md`, `01-research.md` .. `12-traceability.md`), `MANIFEST.json`, consolidated Markdown, validated JSON specifications, and deterministic `.zip` archives.
- **Persistence & Lifecycle Integration (`backend/app/documentation_api.py`, `backend/app/models.py`)**: Persists immutable `DocumentationExport` records (`documentation_exports` table), updates `ProjectBrain.documentation_spec` on official export, enforces `documentation_stage_completion_check` on `PUT /api/projects/{id}/stages/documentation`, and cascades upstream edits via `sync_documentation_stage` (`complete -> needs_review`).
