# WebForge Phase 17 — Documentation & Specification Export (`docs/EXPORT.md`)

## 1. Purpose & Scope Separation

Phase 17 implements the final planned engineering lifecycle stage (`documentation`) of WebForge. It provides a deterministic, provenance-verified system to inspect, validate, preview, generate, verify, and download a project's complete specification and documentation bundle.

### Project Documentation Export vs. Database Backup
WebForge strictly separates two distinct operational concepts:
- **Project Documentation & Specification Export (Phase 17 — `backend/app/documentation_export.py`, `backend/app/documentation_api.py`)**:
  - **Audience**: Product owners, engineers, designers, and stakeholders of a single WebForge project (`owned(project_id)`).
  - **Content**: Human-readable UTF-8 Markdown specification documents (`README.md`, `01-research.md` .. `12-traceability.md`), a machine-readable `MANIFEST.json` with per-file SHA-256 digests, a consolidated `.md` specification, and a validated `.json` specification.
  - **Security Boundary**: Never includes user password hashes, refresh tokens, JWT secrets, API keys, `.env` files, internal server paths, or other users' projects.
- **Platform Database Backup & Restore (Phase 15 — `backend/scripts/db_ops.py`, `scripts/backup_db.sh`, `scripts/restore_db.sh`)**:
  - **Audience**: Platform infrastructure operators with CLI/database access.
  - **Content**: Checksummed 15-table logical relational snapshots (`.wfbackup.json`) and native PostgreSQL `pg_dump` (`.pgdump`) archives for disaster recovery.

---

## 2. Export Bundle Structure & Supported Formats

Every persisted `DocumentationExport` record (`documentation_exports` table, Alembic migration `0009_phase17_documentation_exports`) can be downloaded in three honest, verified formats:

1. **Markdown Documentation Bundle (`.zip` — `format=zip`)**:
   - Deterministic ZIP archive (`ZipInfo` timestamps fixed to `2026-01-01 00:00:00`, permissions `0644`) containing:
     - `README.md` — Project overview, scope, 14-artifact provenance table, included documents, omitted sections, and known limitations.
     - `01-research.md` — User & Market Research report, evidence sources, citations, and preliminary/verified mode disclosures.
     - `02-strategy-and-prd.md` — Product Strategy, positioning, personas/goals, and Product Requirements Document (`FR-*`, `NFR-*`).
     - `03-ux-specification.md` — UX Personas, User Journeys, Information Architecture, Wireframes, and UX Review findings.
     - `04-design-system.md` — Design System tokens, typography, color/spacing scales, component specs, and design decisions.
     - `05-prototype.md` — Interactive Prototype screens, navigation flows, and interaction contracts.
     - `06-architecture.md` — Product Architecture, trust boundaries, domain entities (`ENT-*`), API endpoints (`API-*`), and ADRs (`ADR-*`).
     - `07-testing-and-security.md` — Phase 14 deterministic security & testing verification report (`CHK-*`) and evidence boundaries.
     - `08-infrastructure-and-deployment.md` — Phase 15 container, Compose, CI/CD, runtime observability, and recovery specification.
     - `09-seo.md` — Phase 16 SEO specification, route metadata, indexability rules, XML sitemap preview, and `robots.txt` preview.
     - `10-analytics.md` — Phase 16 Analytics event taxonomy (`EVT-*`), consent categories, PII governance, and conversion funnels.
     - `11-performance.md` — Phase 16 Core Web Vitals budgets, route asset budgets, API latency budgets, and recorded measurement evidence (`EVD-*`).
     - `12-traceability.md` — End-to-End Requirement Traceability Matrix (`PRD -> UX/Design -> Architecture -> SEO/Analytics/Performance`).
     - `MANIFEST.json` — Machine-readable provenance manifest recording `schema_version`, `export_mode`, `official_approved_bundle`, `snapshot_fingerprint`, per-artifact versions/hashes/staleness, per-file SHA-256 digests and byte sizes, validation findings, and known limitations.
2. **Consolidated Specification (`.md` — `format=markdown`)**:
   - Single UTF-8 Markdown file concatenating `README.md` and `01-research.md` .. `12-traceability.md` in canonical order with explicit `<!-- BEGIN FILE: ... -->` / `<!-- END FILE: ... -->` delimiters.
3. **Validated Project Specification (`.json` — `format=json`)**:
   - Clean, deterministic JSON representation (`webforge.project_specification_json.v1`) containing the manifest, project metadata, discovery state, approved/selected artifact payloads, and verification reports without ORM internals or secrets.
4. **Individual File Download (`GET /api/projects/{project_id}/documentation/exports/{export_id}/files/{filename}`)**:
   - Downloads any individual `.md` document or `MANIFEST.json` from a persisted export.

### Honest Format Policy
PDF export is intentionally not enabled in Phase 17 so WebForge never emits a fake `.pdf` file containing raw Markdown or HTML bytes. Unsupported `format` query parameters return `422 Unprocessable Entity` with a clear explanation.

---

## 3. Provenance, Official vs. Preview Mode & Pre-Export Validation

### Source Artifact Inventory (14 Required Artifacts)
`collect_export_snapshot()` inspects all 14 lifecycle artifacts across Phases 9–16:
`research`, `strategy`, `prd`, `personas`, `journeys`, `ia`, `wireframes`, `ux_review`, `design_system`, `prototype`, `architecture`, `seo`, `analytics`, `performance`.

For each artifact, WebForge recomputes its canonical SHA-256 content hash (`research.content_hash` for Phases 9–13 and `optimization.compute_optimization_hash` for Phase 16), checks whether an unapproved draft (`draft` / `in_review`) is open, and evaluates upstream basis staleness.

### Pre-Export Validation Findings (`validate_project_export`)
Findings are classified into three severities:
- **`blocking_error`** (blocks `mode="official"` export and `documentation` stage completion):
  - `MISSING_REQUIRED_ARTIFACT` — Required artifact has no persisted version.
  - `UNAPPROVED_SOURCE_ARTIFACT` — Selected version is not `approved`.
  - `OPEN_DRAFT_EXISTS` — An unapproved draft (`vN`) is open alongside an older approved version.
  - `STALE_SOURCE_ARTIFACT` — Artifact basis version/hash does not match the latest approved upstream artifact.
  - `ARTIFACT_HASH_MISMATCH` — Stored `content_hash` does not match recomputed SHA-256 digest (tamper detection).
  - `BRAIN_PROVENANCE_MISMATCH` — `ProjectBrain` pointer hash diverges from the approved artifact row.
  - `INCOMPLETE_REQUIREMENT_TRACEABILITY` / `*_TRACEABILITY_ERROR` — Uncovered PRD requirements or broken cross-artifact references.
  - `UNRESOLVED_CRITICAL_UX_FINDING` — Open critical findings in UX Review.
  - `SECURITY_VERIFICATION_INCOMPLETE` — Any failing deterministic check in Phase 14 security verification.
  - `SECRET_DETECTED_IN_EXPORT` — Secret scanner matched a credential, private key, DB password, or internal server path (blocks both `official` and `preview` exports).
- **`warning`** / **`info`**:
  - `PRELIMINARY_RESEARCH_MODE` — Discloses that research was synthesized in preliminary mode without live web crawling.
  - `PERFORMANCE_TARGET_BUDGET_ONLY` — Discloses that performance figures are engineering target budgets (`target_budget_only`) rather than live production benchmark observations.

### Official vs. Preview Exports
- **Official Export (`mode="official"`, `include_drafts_or_stale=False`)**:
  - Requires all 14 source artifacts to be approved, current, and free of open drafts, with `0` `blocking_error` findings.
  - Supersedes any prior `official` export, writes an immutable `DocumentationExport` record, commits a `documentation_exported` revision to `ProjectBrain.documentation_spec`, and marks the `documentation` lifecycle stage `complete`.
- **Preview Export (`mode="preview"`)**:
  - Can include draft or stale artifacts (`include_drafts_or_stale=True`) to inspect work-in-progress documentation.
  - Every generated Markdown file and `MANIFEST.json` carries an explicit `PREVIEW / NON-OFFICIAL EXPORT` banner (`official_approved_bundle: false`).
  - Preview exports and file downloads never mark the `documentation` lifecycle stage `complete`.

---

## 4. Security Controls & Lifecycle Invalidation

1. **Authentication & Ownership Isolation**:
   - All `/api/projects/{project_id}/documentation*` endpoints require authentication (`401` if unauthenticated) and verify project ownership via `owned(project_id)` (`404` for non-owners to prevent project/export ID enumeration).
2. **Archive Path & Extension Safety (`validate_safe_archive_path`)**:
   - Rejects empty names, leading slashes, backslashes, drive prefixes (`:`), path traversal (`..`), hidden dotfiles (`.env`, `.git`), control characters, duplicate entry paths, and any extension outside `.md` and `.json`.
3. **Secret & Internal Path Scanning (`scan_export_for_secrets`)**:
   - Scans all generated Markdown documents and `MANIFEST.json` for Google AI keys (`AIza...`), OpenAI/secret keys (`sk-...`), GitHub PATs (`ghp_...`), AWS keys (`AKIA...`), PEM private keys, database URLs with passwords, `JWT_SECRET` assignments, Argon2 password hashes, and internal server paths (`/working_dir/...`).
4. **Safe Download Response Headers**:
   - All download endpoints set `Content-Disposition: attachment; filename="..."`, `X-Content-Type-Options: nosniff`, and `Cache-Control: no-store`.
5. **Lifecycle Completion Guard & Automatic Upstream Invalidation**:
   - `PUT /api/projects/{project_id}/stages/documentation` (`status="complete"`) runs `documentation_stage_completion_check(db, project_id)` and rejects manual completion (`409`) unless a current, hash-verified official export exists with 0 blocking errors.
   - Any upstream artifact edit, regeneration, or approval cascades through `sync_optimization_stages -> sync_documentation_stage`, automatically transitioning `documentation` from `complete` to `needs_review` and marking the previous official export stale against current sources (`matches_current_sources: false`).
