# Research (Phase 9)

Scope: turn the Project Brain and Discovery answers into an **editable, versioned, evidence-labelled research report**, with explicit review and approval. It is *preliminary* research: **no web research is performed** (no search or retrieval exists in this phase). Competitor deep-dives, strategy and PRD are later phases.

## Workflow
`generate` -> **draft** -> (edit: add/edit findings, sources, follow-ups) -> `submit` -> **in_review** -> `approve` -> **approved**.
Status values: `generating | failed | draft | in_review | approved | superseded`.
- Generation builds a **deterministic brief** from the Brain (facts only, each tagged `user_confirmed` or `ai_suggested`, with an explicit *missing inputs* list), then asks the existing provider (`ai.get_provider().generate_structured`) for objectives, research questions, scope, findings and unresolved questions. Output is validated by Pydantic; anything invalid is rejected (502) and nothing is stored except a `failed` row. A retry **reuses** that row, so retries never create duplicate versions.
- Only one generation may be in flight and one editable (draft / in_review) version may exist per project: enforced by partial unique indexes plus a project row lock. Regenerating over an open version needs `supersede: true`; the old version stays in history as `superseded`. If generation fails, the old version is untouched.
- Editing a draft changes it in place. Editing an **in_review** report returns it to draft (it was never approved). Editing an **approved** report is copy-on-write: a **new draft version** is created (`created_via: copy_of_approved`, `parent_version`), the approved version is never modified, and the new version needs approval again.
- Every mutation carries the `base_hash` of the content the client saw; a mismatch is **409** (no lost updates). Approval carries the `content_hash` of the exact version: if the content changed, it is refused.

## Evidence integrity
| Classification | Meaning | Who can set it |
|---|---|---|
| `verified_source` | backed by a cited source the **user marked as examined** (with an access date) | user edits only; needs >= 1 citation to an examined source |
| `user_provided` | supplied by the user, not independently verified | user (default for findings the user adds) |
| `hypothesis` | plausible, unverified | AI or user |
| `ai_suggestion` | a model-generated proposal | AI or user |
| `unsupported` | a claim that needs evidence | AI or user; always flagged for follow-up |
Rules enforced server-side:
- **AI output** may only use `hypothesis`, `ai_suggestion`, `unsupported`; may not carry sources or citations (the schema forbids extra fields); may not contain URLs; and the factual topics (`user_needs`, `market_context`, `competitors_alternatives`, `technology_trends`) may not use `ai_suggestion`. Violations reject the whole response.
- **Numeric or statistical claims** in AI findings are visibly downgraded to `unsupported` with a note (never upgraded).
- No finding is ever machine-verified: WebForge does not fetch or check URLs. `examined` is the user's attestation; the UI says "Source examined by you". `examined_by: "webforge"` cannot be set by clients.
- Sources: `http(s)` only, no credentials, no localhost/private/reserved hosts, tracking parameters and fragments stripped, access date required when examined and not in the future. A citation carries the **specific claim** it supports and stays attached to its finding. A source cited by a finding cannot be deleted (409).
- A cited but unexamined source never upgrades a finding's label.

## Persistence (migration `0003`, table `research_reports`)
One row per version: `version` (unique per project), `status`, `mode` (`preliminary`), `content` (validated JSON: brief, findings, sources, unresolved questions, limitations), `content_hash`, `basis` (Brain version and discovery state used), `parent_version`, `created_via`, safe `error`, review/approval metadata (`submitted_at`, `approved_at/by`, `approval_note`, `acknowledged_unverified`), `brain_revision`, and an optimistic-lock `row_version`. Approved versions are immutable; history is never overwritten. Cascade-deleted with the project.

## Brain and lifecycle rules
- Generation and edits **never touch the Brain** and never advance the lifecycle.
- **Approval** is one transaction: report -> `approved`, stage `research` -> `complete`, and **one** Brain revision `research_approved` that writes only the `research` pointer (`approved_version`, `report_id`, `content_hash`, evidence counts, source count, whether unverified findings were acknowledged). Confirmed sections (idea, target users, goals, discovery) are never overwritten. The `research` section is protected from the generic Brain-edit endpoint (403). The report itself is not copied into the Brain: downstream phases read the approved version through the pointer.
- If the report contains any `hypothesis`, `ai_suggestion` or `unsupported` finding, approval requires `acknowledge_unverified: true` (409 otherwise); the pointer records that it was acknowledged. (`user_provided` findings are the user's own statements and do not require it.)
- Stage rules: submit -> `needs_review`; approve -> `complete`; creating a new draft from an approved version, or editing an in-review report, reopens the stage to `in_progress`. Once any report exists, `PUT /stages/research {status: complete}` is refused (409) unless the latest version is approved; projects that never used Research keep the old manual behavior.

## API (all under `/api/projects/{id}/research`, owner-only; others get 404)
| Method + path | Purpose |
|---|---|
| `GET` | state: status, current report, approved version, history, brief preview (when no report), lifecycle stage status, flags (`can_generate`, `needs_supersede`, `can_submit`, `can_approve`), limitations |
| `GET /reports/{version}` | one version (read-only history) |
| `POST /generate {supersede}` | start, retry or regenerate. 409 no idea / already generating / draft exists; 503 provider not configured; 502 unusable AI output |
| `POST /reports/{v}/findings` · `PATCH .../findings/{fid}` · `DELETE .../findings/{fid}?base_hash=` | add / edit (incl. evidence and citations) / delete findings |
| `POST /reports/{v}/follow-up` | mark findings for follow-up (unsupported ones cannot be cleared) |
| `POST /reports/{v}/sources` · `PATCH`/`DELETE .../sources/{sid}` | source records |
| `PUT /reports/{v}/questions` | replace unresolved questions (no UI yet) |
| `POST /reports/{v}/submit {base_hash}` | draft -> in_review (needs >= 1 finding; idempotent) |
| `POST /reports/{v}/approve {content_hash, acknowledge_unverified, note}` | approve that exact version (idempotent) |
Validation errors are `422` with `[{loc, msg}]`; stale hashes `409`; messages never include provider output, credentials or stack traces.

## Frontend
Route `/projects/:id/research` (sidebar "Research"): status badges (version, report status, backend-reported Research stage, approved version), a "no web research was performed" banner, the brief with confirmed/unconfirmed labels and missing inputs, findings grouped by topic with evidence labels, origin ("AI-generated", "Added by you", "Edited by you") and follow-up flags, citations with the source link beside the claim it supports, sources panel, unresolved questions, report history with read-only version view, and dialogs for finding/source edits, delete, regenerate and approval (acknowledgement checkbox when unverified findings exist). Loading, empty, validation, error and retry states are real; nothing is hard-coded. No lifecycle or approval rule is computed in React.

## Setup and tests
No new configuration is required (optional `RESEARCH_GENERATION_TIMEOUT_SECONDS`, default 180). Uses the existing provider setup (docs/AI_PROVIDER.md).
    cd backend && alembic upgrade head && pytest -q          # SQLite
    TEST_DATABASE_URL=postgresql+psycopg://... pytest -q     # PostgreSQL (incl. concurrency + migration drift)
    cd frontend && npm test && npm run build
Browser scripts: `frontend/qa/research_e2e.mjs`, `research_qa.mjs`, `research_kb.mjs` (they use the QA-only test double `qa_backend.py`).

## Known limitations
- **Real Google provider and real research quality: not verified.** All generation tests use scripted test doubles; a real model may break the strict rules often enough to be rejected (502) and need retries. No external source retrieval exists.
- Numeric-claim detection is a regex (misses written-out figures); invented competitor names/features cannot be detected server-side (prompt rules + `hypothesis`/`unsupported` labels only).
- A source's `examined` flag is the user's word; URLs are never opened or checked.
- Submitter and approver are the same account (no separate reviewer role).
- The brief and unresolved questions are not editable in the UI (the questions endpoint exists).
- One editable version at a time; concurrent editors get 409 and must reload.
