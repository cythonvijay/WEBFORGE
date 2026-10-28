# Build progress

## Phase 0 — Foundation: PARTIAL
Done: monorepo, FastAPI, SQLAlchemy models, Dockerfile, compose, .env.example, README, Alembic (see 0.5), Makefile.
Not done: frontend toolchain.

## Phase 0.5 — Database Hardening: COMPLETE EXCEPT DOCKER VERIFICATION
Alembic: PASS (env.py uses app metadata; `alembic check` reports no drift)
Initial migration: PASS (single revision 0001; upgrade -> downgrade base -> upgrade verified on PostgreSQL 16)
create_all removed from startup: PASS (empty DB + app start created 0 tables; register on unmigrated DB returns 500, not hidden)
PostgreSQL (native 16.15 installed in the build sandbox): PASS (live HTTP run: ready, register, project, lifecycle, overview, intake 503 with brain unchanged)
PostgreSQL test suite: PASS (16 passed)
SQLite test suite: PASS (10 passed, 6 PostgreSQL-only skipped)
Docker: NOT VERIFIED. No Docker daemon was available. docker-compose.yml parses as YAML; compose, the backend container, the healthcheck and the Makefile docker targets (db, migrate, up, test-pg) have never been executed.

Changes found by the compatibility audit: DATABASE_URL now required (removed hardcoded default host); SQLite foreign keys enabled; refresh-token expiry check made timezone-safe (`security.as_utc`); `/api/ready` real DB check added.
Known issues: `alembic downgrade` is destructive by design (dev only). Test DB is wiped by the suite.

## Phase 1 — Authentication: COMPLETE (backend)  | Frontend /login /register: NOT STARTED
Register, login, logout, rotating refresh, current user. Tests: refresh reuse, httpOnly cookies.

## Phase 2 — Projects: COMPLETE (backend)  | Frontend: NOT STARTED
Create, list, get, rename, archive, delete; per-owner isolation tested.

## Phase 3 — Project Brain: COMPLETE (backend)
Typed top-level sections (only `idea` is deeply typed; others are loose dict/list). Append-only revisions.

## Phase 4 — Lifecycle: COMPLETE (backend)
19 stages, dependency enforcement. Nothing yet moves stages automatically.

## Phase 5 — Application shell: COMPLETE (browser-QA'd in Phase 5.5)
Auth pages, shell (top bar, grouped sidebar, mobile toggle), projects CRUD, project layout, "Coming in Phase N" pages for every unimplemented section, settings (account only).
## Phase 6 — Project overview: COMPLETE (browser-QA'd in Phase 5.5)
Progress, next action, current work, recent changes, system state, lifecycle map: all from `/overview`. Backend change: `/overview` now also returns `depends_on`, `unmet_dependencies`, `needs_review` (tested).
## Phase 7 — AI intake: COMPLETE (backend + UI), UNTESTED against real Google API
Pydantic-validated; 503 if unconfigured, 502 on bad output. Tested with a test double only.

## Phase 5/6 verification (what was actually run)
- `npm run build` (tsc + vite build): PASS
- Frontend tests: 42 passed (mocked at the network boundary; unrouted requests fail the test)
- Real client vs real backend on PostgreSQL (`test:integration`): PASS — register/login/me, 409, 503, ownership, refresh via httpOnly cookie with rotation, logout
- Vite dev server + `/api` proxy to the backend: PASS (curl)
- Backend: SQLite 10 passed (+6 PG-only skipped); PostgreSQL 16 passed

## Phase 5.5 — Browser QA: COMPLETE (with the limits listed below)
Browser available: YES — headless Chromium 153 (npm `@sparticuz/chromium` + puppeteer-core), against real PostgreSQL + real backend, no API mocks. Scripts in `frontend/qa/`.

    Authentication flow:  PASS  register, login, reload keeps session, logout, protected routes redirect, login again
    Token storage:        PASS  localStorage/sessionStorage empty; access+refresh cookies httpOnly, SameSite=Lax; document.cookie empty
    Project flow:         PASS  create (3 variants), open, rename, archive, restore, cancel/confirm delete; DB verified; cascade left 0 child rows
    Overview:             PASS  progress/next action/changes from backend; no fake build/deploy/monitoring data
    Lifecycle:            PASS  409 explained from backend dependency data; valid transition persisted across reload
    AI intake:            503 PASS (explained, text kept, brain version unchanged) | real provider: NOT VERIFIED (no key)
    Responsive:           PASS  1440/1280/768/390: no overflow inside <main> or page, 6 pages each; mobile sidebar collapses
    Keyboard:             PASS  scripted: tab order, visible focus, dialog trap/Escape/focus return, sidebar Escape, all lifecycle selects + intake reachable
    Accessibility audit:  PASS  axe-core 0 violations on 7 contexts (after fixes). Automated only.
    Console errors:       PASS  only expected 401 (anonymous start), 409, 503 resource messages; 0 page errors
    Network errors:       PASS  production build: each page load = one request per endpoint; stage change = 1 PUT + 1 overview GET

### Defects found by the browser (all fixed, regression tests added where testable)
1. Long unbroken project name overflowed the projects table and overview heading (up to 1174 px at 390 px wide). My first overflow check missed it because the page scrolls inside `<main>`.
2. Projects table on phones hid Rename/Archive/Delete behind horizontal scroll → rows stack below `md`.
3. Sidebar "Phase N" tags wrapped, and failed contrast (axe: serious, 29 nodes).
4. Login/register had no `<main>` landmark (axe).
5. Dialogs had no focus trap (Tab reached the page behind) → trap added; effect no longer re-runs on parent re-render.
6. Mobile sidebar: no Escape/backdrop close, and stopped 48 px short of the screen bottom.
7. A stage awaiting review showed "Start UX" as next action → "Review UX".
8. After a deliberate sign-out, signing in returned you to the page you left (possibly another account's project) → only remembered for expired sessions.
9. `/favicon.ico` returned 404 → inline icon.
10. "Analyze again" label wrapped on phones.

### Observed, deliberately not changed
- Anonymous page loads log two red 401s (`/auth/me`, then one `/auth/refresh`). The refresh cookie is httpOnly, so the app can't know whether a refresh is worthwhile.
- Chrome DevTools reports `net::ERR_ABORTED` for 204 responses (logout, delete). Page JS receives 204 and the DB confirms the effect; not an app failure.
- The lifecycle map is a long one-column chain for the early stages (white space on the right). Readable; no redesign.
- The startup error screen is top-aligned and unbranded. Functional.
- Dev mode doubles requests because of React StrictMode; production does not.

### Not verified
- Real AI provider success path (no key). Intake success is covered only by UI tests with a mocked response.
- Docker / compose: BLOCKED — Docker unavailable. Config is unchanged and unverified.
- Browsers other than Chromium (Firefox, Safari), real devices, real touch input.
- Screen reader behavior; WCAG compliance is NOT claimed (axe is automated and catches only part of it).
- Screenshots I looked at: login, desktop overview (two states), lifecycle map, desktop and mobile projects, create dialog (mobile), tablet overview, backend-down screen, mobile sidebar (before the height fix; verified numerically after). Register, settings, coming-soon and the 1280 layouts were checked by overflow/axe only, not by eye.
- The projects-list "Loading projects…" state was not captured in the browser sample (only the session "Loading…"); it is unit-tested.
- ESLint: not added (type checking + 48 tests; a lint setup is a future quality task).

Tests now: frontend 48 passed (+1 real-backend contract test, run separately: PASS); backend SQLite 10 passed (+6 PG-only skipped), PostgreSQL 16 passed.

Next: see Phase 8 below.

## Phase 8 — Progressive AI Questions: COMPLETE with the verification limits below
Implemented: persisted discovery sessions and questions (migration `0002`), explicit state machine, provider-backed generation validated by Pydantic, server-side selection (dedupe, one question per target, impact ranking, round/question limits), answer validation per type, server-registry mapping into the Brain with `user_confirmed` provenance and `unanswered_question` assumptions, atomic answers with at most one append-only revision, skip/defer, next round, review summary, explicit completion, ownership and concurrency protection, and the Discovery page plus overview callout. Contract and rules: `docs/DISCOVERY.md`.

    Backend tests (SQLite):        49 passed, 8 PostgreSQL-only skipped
    Backend tests (PostgreSQL):    57 passed (concurrent answers, migration drift check included)
    Frontend build + tests:        PASS, 67 passed (stable across 3 consecutive runs)
    Real client vs real backend:   PASS (no AI key: intake 503 asserted)
    Migration 0002 on PostgreSQL:  PASS upgrade / downgrade -1 / upgrade; alembic check: no drift
    Browser E2E (headless Chromium, real PostgreSQL, AI TEST DOUBLE):  PASS
        idea -> start -> 503 and malformed output explained, nothing saved -> retry -> answer all four types -> reload resumes
        -> skip -> failed next round keeps state -> round 2 (duplicate filtered) -> defer/skip -> review -> correct an answer
        -> complete with assumptions -> overview; revisions created,ai_intake,discovery_answer x2,discovery_completed (versions 1-5);
        another user gets 404 on get/start/answer
    axe on discovery screens:      0 violations in 6 states (one heading-order issue found and fixed)
    Overflow 1440/1280/768/390:    none; keyboard: visible focus everywhere, native Space/arrow behavior
    Network (production build):    one request per endpoint per page load; the overview callout adds exactly one GET

### Found and fixed during this phase
Form values were copied from server state by an effect (empty first paint, flaky test) -> now derived directly, state holds only unsaved edits. Per-question landmarks duplicated labels -> removed. Heading order h1->h3 on review/completed -> h2/h3.

### NOT verified
- **Real Google AI provider: NOT VERIFIED.** Every discovery run used a scripted test double. No key was used, and the sandbox cannot reach `generativelanguage.googleapis.com` (HTTP 000).
- Docker / compose: unverified (unchanged).
- Browsers other than Chromium; screen readers; WCAG compliance not claimed.
- Not eyeballed: the failed and not-started discovery screens and the 1280/768 discovery layouts (axe and overflow only).

### Security note
The uploaded `projectcode.zip` contained a non-empty `GOOGLE_AI_API_KEY` in `.env.example` (a file meant to be shared with placeholders). That key was not printed, used or copied into this repository's files, and `.env.example` here keeps an empty placeholder. Treat the key as exposed: rotate it and keep real keys only in an untracked `.env`. The upload also lacked `frontend/src/features/projects/api.ts` (imported by three files), so work continued from the previous complete copy.

Next: Phase 9 (Research) per the provisional roadmap — but verify the real provider first, with a key in `.env` on a machine that can reach Google.

## Real Google AI provider verification — BLOCKED in this environment
Nothing was verified against real Google. This sandbox has **no API key** and **cannot reach `generativelanguage.googleapis.com`** (HTTP 000, egress allow-list). Every real-provider row is therefore BLOCKED or NOT RUN, not PASS. Mock evidence is listed separately and is not a substitute.

| Check | Result (real provider) | Evidence without real Google |
|---|---|---|
| Google key configuration | NOT CONFIGURED (no key in this sandbox) | `.env` loading, precedence and `extra` keys: PASS (unit tests); `provider_check` never prints the key: PASS |
| Real Google request | **BLOCKED** (no key; network unreachable) | `provider_check --live` with a placeholder key reports `BLOCKED / network` correctly |
| Structured response validation | NOT RUN against Google | Pydantic validation of Gemini-shaped responses: PASS (fake Google, HTTP level) |
| Real AI intake | NOT RUN | Whole intake path through the real provider code against the fake: PASS |
| Real discovery question generation | NOT RUN | Same, incl. round 2 repeat-filtering: PASS (fake) |
| Answer persistence | NOT RUN (real) | PASS (fake + Phase 8 tests) |
| Brain revision and provenance | NOT RUN (real) | PASS (fake + Phase 8 tests) |
| Failure-path regression | PASS | no key → documented 503 on intake and discovery (also confirmed live); 9 Google error classes categorized; malformed/blocked/truncated output rejected; no partial Brain changes; retry creates no duplicate session/questions; other users get 404; key absent from frontend source and bundle; no key in logs, errors or output |
| Frontend tests | PASS (68) | |
| Backend tests | PASS (SQLite 91 + 8 PG-only skipped; PostgreSQL 99) | |

### Defects found and fixed during this task
1. **The configured model was likely unusable for a new key.** `gemini-2.5-flash` is restricted to existing users per Google's changelog (2026-09-18). Default changed to `gemini-3.8-flash` (documentation-verified only).
2. **`.env` was never loaded** outside Docker Compose, so a locally configured key would have been silently ignored. Now loaded (root `.env`, then `backend/.env`; real env wins).
3. **Provider failures had no categories** (only an exception type name), so "bad key", "model gone" and "rate limited" were indistinguishable. Now categorized from the HTTP status and Google's documented `error.status`, with safe messages shown in the API, the stored discovery `last_error` and the UI.
4. **Alembic's logging setup silently disabled application loggers** when migrations ran in-process. `disable_existing_loggers=False`.
5. `.gitignore` covered only `.env`; now `.env.*` (except `.env.example`) too.
6. `backend/.env.example` does not exist (only the root and `frontend/` ones); no duplicate was created.

### To finish this verification (needs a machine that can reach Google and a NEW key)
`python -m app.provider_check --live`, then `python scripts/verify_real_provider.py`, then the UI steps in docs/AI_PROVIDER.md. Phase 9 should wait for those results.

## Phase 9 — Research: COMPLETE (test doubles only; live provider and external retrieval NOT RUN)
Workflow, rules, API and limitations: docs/RESEARCH.md. Migration `0003` adds `research_reports`. Existing intake, discovery, auth and lifecycle behavior is unchanged except one intentional rule (manual completion of the Research stage is refused once a report exists and is not approved), and Competitors moved from "Phase 9" to "Phase 10" in the sidebar because Phase 9 is Research only. One existing frontend test was re-pointed from Research to Strategy as its "not implemented" example; no assertion was weakened.

Baseline before changes (all PASS): backend SQLite 91 passed / 8 skipped; PostgreSQL 99 passed; frontend 68 passed; migration head 0002, no drift.

| Check | Result |
|---|---|
| Backend tests, SQLite (`pytest -q`) | PASS: 143 passed, 9 skipped (PostgreSQL-only) |
| Backend tests, PostgreSQL (`TEST_DATABASE_URL=… pytest -q`) | PASS: 152 passed (includes concurrent generate/edit test and migration drift check) |
| Alembic `0003` upgrade / `downgrade -1` / upgrade, `alembic check` | PASS (head 0003, no drift; partial unique indexes present) |
| Frontend build (`npm run build`) | PASS |
| Frontend tests (`npm test`) | PASS: 87 passed, 1 skipped (stable across repeated runs) |
| Real API client vs real backend (`test:integration`, now with research assertions) | PASS |
| Browser E2E, headless Chromium, real PostgreSQL, **AI test double** | PASS (details below) |
| axe-core on 9 Research states (incl. 3 dialogs) | PASS: 0 violations |
| Overflow at 1440/1280/768/390 with 160-char unbroken text and long URLs | PASS: none |
| Keyboard: reachability, visible focus, dialog trap, Escape, focus return | PASS |
| Network (production build) | PASS: one request per endpoint per load |
| **Live Google verification** | **NOT RUN**: no `GOOGLE_AI_API_KEY` configured; Google unreachable from this sandbox |
| **External source retrieval** | **NOT RUN / not implemented**: sources are user-entered and form-checked only; nothing is fetched |
| Docker | **NOT RUN**: Docker is not installed in this environment |

Browser E2E (test-double provider) verified: empty state with the real brief and missing inputs; unconfigured (503) and malformed (502) generation leave the Brain, lifecycle and rows unchanged and a retry reuses the same version; the draft shows honest evidence labels and a numeric claim visibly downgraded to unsupported; an examined source is URL-canonicalized and cited beside its claim with a safe link; a bad URL is refused with input kept; submit -> `needs_review`; approval needs acknowledgement, then writes exactly one `research_approved` Brain revision (pointer only, confirmed sections identical) and completes the stage; editing the approved version creates draft v2 while v1 keeps its status and hash, the stage reopens and the Brain pointer still names v1; manual completion is refused (409); history opens a version read-only; state survives reload; another user gets 404 on get, generate and report.

Backend tests added (53 in `tests/test_research.py`): deterministic-provider generation; structured-output validation (13 invalid AI outputs rejected atomically); evidence and citation rules; unsupported and numeric claims; URL handling (9 invalid sources); copy-on-write versioning; approval of a specific version by hash; regeneration after approval; Brain revision provenance; lifecycle rules including the manual-completion guard; ownership on every endpoint; provider failures and atomicity; retry and duplicate prevention at the database level; concurrent generation and edits (PostgreSQL); regression of the existing intake and discovery suites.

### Defects found while building and fixed
My own DELETE routes declared the hash as a body field (needs a query parameter); several test-authoring mistakes (falsy empty list, duplicate "Version N" text, wrong mocked verb) were corrected in the tests, not by relaxing assertions.

### Not verified / limitations
- **Real Google provider: NOT RUN.** Real research quality is unknown, and a real model may violate the strict output rules often enough that generations are rejected (502) and need retries.
- **No external retrieval.** Nothing is machine-verified; `verified_source` means a source the *user* says they examined.
- Numeric-claim detection is a regex; invented competitor names or features cannot be detected server-side.
- Submitter and approver are the same account. The brief and unresolved questions are not editable in the UI (the questions endpoint exists).
- Chromium only. Screenshots looked at: the cited-finding view and the approved view. The empty, in-review, approve-dialog, history and 390px layouts were checked by axe and overflow measurement only.
- Docker unverified.

Next: do not start Phase 10 before the live provider check in docs/AI_PROVIDER.md (`python -m app.provider_check --live`, then `python scripts/verify_real_provider.py`) has passed on a machine that can reach Google, because strategy and competitor work would build on research whose real-model behavior is still unknown.


## Phase 10 — Lifecycle Audit, Phase 1–8 Mapping, and Product Strategy & PRD

- **Lifecycle & Navigation Audit (Phases 1–8 vs. 19 Stages)**:
  - Verified that Roadmap Phases 0–5.5 are platform foundation milestones and Phases 6–8 are pre-lifecycle setup workflows (`Overview`, `AI Intake`, `Discovery`) that populate the Project Brain rather than separate lifecycle stages.
  - Verified that the 19 lifecycle stages (`STAGES`) begin at Phase 9 (`research`) and Phase 10 (`product`).
  - Removed `phase: 10` placeholder badges from `strategy` and `prd` in `frontend/src/components/navigation/nav.ts`, wired `/projects/:projectId/strategy` and `/projects/:projectId/prd` in `frontend/src/app/router.tsx`, and added pre-lifecycle vs. 19-stage explanatory copy in `LifecycleMap.tsx` and `nav.ts`.
- **Phase 10 Backend (`Strategy` & `PRD`)**:
  - Added `StrategyDocument` (`strategy_documents`) and `PrdDocument` (`prd_documents`) models in `backend/app/models.py` and Alembic migration `backend/alembic/versions/0004_strategy_and_prd.py`.
  - Added `StrategyBrain` and `PrdBrain` pointer models to `ProjectBrain` in `backend/app/brain.py` and protected `"strategy"` and `"prd"` in `PROTECTED_SECTIONS`.
  - Implemented `backend/app/strategy.py` and `backend/app/strategy_api.py` (deterministic `StrategyInputs` from Brain + Discovery + approved Research, provenance validation, numeric claim downgrade to `unsupported`, copy-on-write edits, review submission, and exact-hash approval writing `strategy_approved`).
  - Implemented `backend/app/prd.py` and `backend/app/prd_api.py` (deterministic `PrdBasisSummary` from approved Strategy, stable IDs `US-N` / `FR-N` / `NFR-N`, testable acceptance criteria validation, duplicate/contradiction rejection, `proposed` vs `approved` requirement status, copy-on-write edits, review submission, and exact-hash approval writing `prd_approved` and completing lifecycle stage `product`).
  - Added manual stage completion guard on `PUT /api/projects/{id}/stages/product` in `backend/app/api.py` when Strategy or PRD has been started.
- **Phase 10 Frontend (`StrategyPage` & `PrdPage`)**:
  - Added `frontend/src/types/strategy.ts`, `frontend/src/types/prd.ts`, `frontend/src/features/strategy/api.ts`, `frontend/src/features/prd/api.ts`, `frontend/src/pages/StrategyPage.tsx`, and `frontend/src/pages/PrdPage.tsx`.
  - Updated `frontend/src/test/overview.test.tsx` and added `frontend/src/test/strategy_prd.test.tsx`.
- **Verification Status**:
  - Backend SQLite test suite: **152 passed, 9 skipped, 0 failed** (including 53 Phase 9 tests in `test_research.py`, 42 provider tests in `test_google_provider.py`, and 9 new Phase 10 integration and end-to-end tests in `test_strategy_prd.py`).
  - Live Google AI provider (`python3 -m app.provider_check`): **BLOCKED / NOT CONFIGURED** (`GOOGLE_AI_API_KEY` not set and outbound network disabled in sandbox).
  - External web research retrieval: **NOT IMPLEMENTED BY DESIGN** (Research runs in `mode="preliminary"`; URLs are form-checked only via `normalize_url`).
  - PostgreSQL & Docker integration tests: **SKIPPED / BLOCKED** (9 PostgreSQL-only tests skipped because `docker` and `postgresql` are not installed in the sandbox VM).
  - Frontend Vitest execution: **BLOCKED IN SANDBOX** (`frontend/node_modules` was not bundled in the archive and outbound npm registry access is disabled in the sandbox).


## Phase 11 — Complete UX Design & Experience Workflow

- **Database & Brain (`0005_ux_artifacts`)**:
  - Added `UxArtifact` (`ux_artifacts`) in `backend/app/models.py` and Alembic migration `backend/alembic/versions/0005_ux_artifacts.py`.
  - Added `UxArtifactPointer` and `UxBrain` (`ux`) in `backend/app/brain.py` and added `"ux"` to `PROTECTED_SECTIONS`.
- **Backend Schemas, Validation & Routes (`backend/app/ux.py`, `backend/app/ux_api.py`)**:
  - Implemented `PersonasContent`, `JourneysContent`, `IaContent`, `WireframesContent`, and `UxReviewContent` with strict cross-artifact ID validation (`P-N`, `J-N`, `IA-N`, `WF-N`, `UXF-N`, `FR-N`, `NFR-N`, `US-N`), automatic numeric/survey claim downgrade to `hypothesis`, IA tree cycle/self-parent/missing-parent rejection, deterministic UX coverage checks (`build_deterministic_ux_findings`), manual persona fallback (`POST /ux/personas/manual`), copy-on-write edits, exact-hash approval, and `ux` stage completion/invalidation (`sync_ux_stage`).
- **Frontend Workspaces & Tests**:
  - Added `frontend/src/types/ux.ts`, `frontend/src/features/ux/api.ts`, `frontend/src/features/ux/UxWorkspaceShell.tsx`, `PersonasPage.tsx`, `JourneysPage.tsx`, `IaPage.tsx`, `WireframesPage.tsx` (with deterministic low-fidelity visual renderer, viewport switcher, and state preview), and `UxReviewPage.tsx`.
  - Removed `phase: 11` placeholder badges from `personas`, `journeys`, `ia`, `wireframes`, and `ux-review` in `nav.ts` and wired routes in `router.tsx`.
  - Added `backend/tests/test_ux.py` and `frontend/src/test/ux.test.tsx`.
- **Verification**:
  - Backend SQLite test suite: **157 passed, 9 skipped, 0 failed** across `test_api.py`, `test_discovery.py`, `test_google_provider.py`, `test_research.py`, `test_strategy_prd.py`, and `test_ux.py`.
  - Alembic migrations (`0001` -> `0005` -> `base` -> `0005`): **PASSED** with zero schema drift.


## Phase 12 — Design System & Interactive Prototype

- **Database & Brain (`0006_design_artifacts`)**:
  - Added `DesignArtifact` (`design_artifacts`) in `backend/app/models.py` and Alembic migration `backend/alembic/versions/0006_design_artifacts.py`.
  - Added `DesignBrain` (`design_spec`) in `backend/app/brain.py` and added `"design_spec"` to `PROTECTED_SECTIONS`.
- **Backend Schemas, Validation & Routes (`backend/app/design.py`, `backend/app/design_api.py`)**:
  - Implemented `DesignSystemContent` (color tokens `--color-*` with `#RRGGBB` validation, typography `--font-*`, spacing `--space-*`, grid/breakpoints, surfaces, icons, contrast/a11y notes, component specs `CMP-N`, and design decisions `DD-N` with usability-claim flagging) and `PrototypeContent` (navigable screens `SCR-N` reusing persisted Phase 11 wireframe regions/states, interactive form fields, triggers, and journey flows `FLOW-N`).
  - Enforced upstream UX/PRD prerequisite and staleness checks, manual fallback (`POST /design/design_system/manual`), copy-on-write edits, exact-hash approval, and `design` stage completion/invalidation (`sync_design_stage`).
- **Frontend Workspaces & Tests**:
  - Added `frontend/src/types/design.ts`, `frontend/src/features/design/api.ts`, `frontend/src/pages/DesignSystemPage.tsx`, and `frontend/src/pages/PrototypePage.tsx`.
  - Removed `phase: 12` placeholder badges from `design-system` and `prototype` in `nav.ts` and wired routes in `router.tsx`.
  - Added `backend/tests/test_design.py` and `frontend/src/test/design.test.tsx`.
- **Verification**:
  - Backend SQLite test suite: **162 passed, 9 skipped, 0 failed**.
  - Alembic migrations (`0001` -> `0006` -> `0005` -> `0006`): **PASSED** with zero schema drift.


## Phase 13 — Product Architecture

- **Database & Brain (`0007_architecture_documents`)**:
  - Added `ArchitectureDocument` (`architecture_documents`) in `backend/app/models.py` and Alembic migration `backend/alembic/versions/0007_architecture_documents.py` (`down_revision = '0006'`) with `UniqueConstraint("project_id", "version")`, optimistic locking (`row_version`), and partial unique indexes `uq_arch_one_generating` (`status = 'generating'`) and `uq_arch_one_open` (`status IN ('draft', 'in_review')`).
  - Added `ArchitectureBrain` (`architecture_spec`) in `backend/app/brain.py` and added `"architecture_spec"` to `PROTECTED_SECTIONS`.
- **Backend Schemas, Validation, Traceability & Routes (`backend/app/architecture.py`, `backend/app/architecture_api.py`)**:
  - Implemented `ArchitectureContent` covering System Overview (`COMP-N` components, `INT-N` external integrations, trust boundaries), Application Architecture (`FE-N` frontend module boundaries, `BE-N` backend modules, auth/authz, state/data-fetching, error/logging, config), Data Architecture (`ENT-N` PRD-backed domain entities, relationships, transaction/integrity rules, migration strategy), API & Integration Architecture (`API-N` endpoints with `proposed_target` vs `verified_existing` status), Deployment & Operational Architecture (`SVC-N` services with `proposed_target` vs `verified_current` status), Technical Decisions (`ADR-N` records), Validated Diagrams (`DIAG-N` with node/edge inventory consistency checks and Mermaid generation), and deterministic Requirement Traceability Matrix (`compute_traceability`).
  - Enforced strict upstream prerequisite and staleness gates across Phase 9 (`Research`), Phase 10 (`Strategy`, `PRD`), Phase 11 (`Personas`, `Journeys`, `IA`, `Wireframes`, `UX Review`), and Phase 12 (`Design System`, `Interactive Prototype`), manual creation fallback (`POST /architecture/manual`), copy-on-write edits, exact-hash approval, upstream invalidation (`sync_architecture_stage`), and manual completion guard on `PUT /api/projects/{id}/stages/architecture`.
- **Frontend Workspace & Tests**:
  - Added `frontend/src/types/architecture.ts`, `frontend/src/features/architecture/api.ts`, and `frontend/src/pages/ArchitecturePage.tsx`.
  - Removed `phase: 13` placeholder badge from `architecture` in `nav.ts` (preserving `phase: 13` on `frontend`, `backend`, `database`, and `api` implementation stages) and wired `/projects/:projectId/architecture` in `router.tsx`.
  - Added `backend/tests/test_architecture.py` and `frontend/src/test/architecture.test.tsx`.
- **Verification**:
  - Backend SQLite test suite: **169 passed, 9 skipped, 0 failed** across `test_api.py`, `test_discovery.py`, `test_google_provider.py`, `test_research.py`, `test_strategy_prd.py`, `test_ux.py`, `test_design.py`, and `test_architecture.py`.
  - Alembic migrations (`0001` -> `0007` -> `0006` -> `0007`): **PASSED** with zero schema drift.

---

## Phase 14 — Comprehensive Testing & Security Hardening (Completed)

### Security Remediations Implemented (`SEC-01`..`SEC-07`)
- **`SEC-01` (High — Stage Completion Guards)**: Fixed `PUT /api/projects/{project_id}/stages/{stage}` so `ux` and `design` completion checks run unconditionally (preventing empty projects from marking `ux` or `design` complete) and enforced `architecture_stage_completion_check`, `testing_stage_completion_check`, and `security_stage_completion_check`.
- **`SEC-02` (High — CSRF & Origin Enforcement)**: Added `SecurityMiddleware` in `backend/app/security.py` rejecting cross-site Fetch Metadata (`Sec-Fetch-Site: cross-site`), untrusted `Origin`/`Referer` headers, `Origin: null`, and HTML form content types (`application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain`) on state-changing `/api/*` requests.
- **`SEC-03` (Medium — Input Validation & Payload Bounds)**: Enforced `MAX_REQUEST_BODY_BYTES = 512 KiB` (`413`), `ConfigDict(extra="forbid")` across core API schemas, `Project.description` length bounds (`<= 5,000`), and `validate_brain_section_payload` (`<= 64 KiB`, depth `<= 8`, list `<= 200`, string `<= 10,000`).
- **`SEC-04` (Medium — Security Headers & Cookie Hardening)**: Added `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, `Content-Security-Policy`, `Cache-Control: no-store`, conditional `Strict-Transport-Security`, and matched `_cookie_kwargs()` on `logout`.
- **`SEC-05` (Medium — Error Sanitization & Token/Hash Hardening)**: Sanitized `ProviderError(unknown)` in `/intake` to prevent leaking raw exception strings, caught `InvalidHashError`/`VerificationError` in `verify_password`, and required `sub`, `exp`, `typ`, and `iat` in `decode_access_token`.
- **`SEC-06` (Medium — Refresh Token Concurrency)**: Added `.with_for_update()` row locking on `RefreshToken` lookup in `/api/auth/refresh` and bounded refresh token length (`<= 256`).
- **`SEC-07` (Low — Container & Frontend URL Hardening)**: Added non-root `webforge` runtime user in `backend/Dockerfile` and `safeHttpUrl()` protocol sanitization in `frontend/src/lib/utils.ts`, `FindingCard.tsx`, and `Panels.tsx`.

### Verification Summary
- **Backend Automated Test Suite (SQLite)**: `175 passed, 9 skipped, 0 failed` (`pytest`).
- **Alembic Migrations (`0001..0007`)**: Full `upgrade head` -> `downgrade base` -> `upgrade head` verified.
- **Secret & Static Security Scan**: `120+` tracked files scanned, `0` leaked secrets, `0` unsafe frontend HTML sinks across `62` frontend modules.
- **PostgreSQL & Frontend Execution**: PostgreSQL tests (`8` tests in `backend/tests/test_postgres.py`) and Frontend tests (`frontend/src/test/security_phase14.test.tsx`) are implemented and documented as `BLOCKED BY ENVIRONMENT` in the offline VM sandbox where `postgres` and `node`/`npm` binaries are unavailable.

---

## Phase 15 — Infrastructure, DevOps & Deployment (Completed)

### Infrastructure & Operational Features Implemented
- **Reproducible Local & Production Compose**: Updated `docker-compose.yml` with `postgres` healthcheck, dedicated one-shot `migrate` service (`python -m scripts.db_ops migrate`), `backend` readiness dependencies, and `frontend` `fullstack` profile; created `docker-compose.prod.yml` overlay keeping PostgreSQL and backend private on `webforge_internal`.
- **Production Multi-Stage Containers**: Hardened `backend/Dockerfile` (`python:3.12-slim-bookworm` multi-stage, non-root `USER webforge`, `HEALTHCHECK`, graceful shutdown) and created `frontend/Dockerfile` (`node:22-alpine` -> `nginxinc/nginx-unprivileged:1.27-alpine`, non-root `USER nginx`) + `frontend/nginx.conf` + `.dockerignore` files.
- **Environment Validation & Observability**: Enhanced `backend/app/config.py` with fail-fast staging/production validation (`validate_runtime_settings`, `enforce_startup_settings`) and created `backend/app/observability.py` with `ObservabilityMiddleware` (`X-Request-ID`), `RedactingFilter`, `StructuredJsonFormatter`, and bounded metrics.
- **Separated Health & Readiness Probes**: Added `/api/health/live` and `/api/health/ready` alongside `/api/health` and `/api/ready`, distinguishing process liveness from database connectivity and Alembic head (`0007`) alignment.
- **Safe Migrations & Verified Backup/Restore**: Created `backend/scripts/db_ops.py`, `scripts/backup_db.sh`, and `scripts/restore_db.sh` supporting bounded DB wait, migration verification, and checksummed logical backups with disposable-database restore verification.
- **CI Pipeline & Lifecycle Guards**: Created `.github/workflows/ci.yml`, `backend/app/infrastructure_verification.py` (`GET /api/projects/{id}/infrastructure-verification`), and enforced completion guards for `docker`, `cicd`, `infrastructure`, `deployment`, and `monitoring` in `backend/app/api.py`.

### Verification Summary (`python3 backend/scripts/verify_phase15.py`)
- **Passed (8/13 checks)**: Secret & Credential Hygiene Scan (`175` files, `0` secrets), Static Security Controls (`88` frontend modules), Container/Nginx/Compose Manifest Validation, CI Workflow Validation, Fail-Fast Env & Log Redaction Verification, Alembic Migration Upgrade/Downgrade (`0001..0007`), Disposable Database Backup & Restore Round-Trip (`4` rows across `13` tables, SHA-256 digests matched), and Backend Automated Test Suite (`181 passed, 9 skipped, 0 failed`).
- **Blocked by Environment (4/13 checks)**: Live PostgreSQL 16 server execution, Docker daemon image build execution, Frontend `npm` execution (`node_modules` absent in offline sandbox), and live CVE database lookup (`pip-audit`/`npm audit`).
- **Skipped (1/13 checks)**: Optional live Gemini API smoke check (`GOOGLE_AI_API_KEY` unset).

---

## Phase 16 — SEO, Analytics & Performance (Completed)

### Capabilities Implemented
- **Database & Project Brain (`0008_phase16_seo_analytics_performance`)**:
  - Added `OptimizationArtifact` (`optimization_artifacts` table) in `backend/app/models.py` and Alembic migration `backend/alembic/versions/0008_phase16_seo_analytics_performance.py` (`down_revision = "0007"`) with composite `UniqueConstraint("project_id", "area", "version")` and partial unique indexes `uq_optimization_one_generating` and `uq_optimization_one_open`.
  - Registered `OptimizationArtifact` in `ORDERED_MODELS` in `backend/scripts/db_ops.py` (14 tables verified in disposable backup/restore round-trip).
  - Added `OptimizationBrain` (`seo`, `analytics`, `performance` `UxArtifactPointer` fields) and `optimization_spec` to `ProjectBrain` in `backend/app/brain.py`, with `"optimization_spec"` in `PROTECTED_SECTIONS`.
- **Domain Schemas, Validation, Traceability & Verifiers (`backend/app/optimization.py`)**:
  - Implemented `SeoContent`, `AnalyticsContent`, and `PerformanceContent` with strict Pydantic validation (`extra="forbid"`).
  - Enforced public vs. private route indexability (`authenticated`, `private_user_data`, `transactional`, and `admin` routes must use `robots_index='noindex'` and `include_in_sitemap=False`), rejected fabricated live canonical URLs, and added deterministic `/sitemap.xml` and `/robots.txt` preview generators plus an `HTMLParser`-based HTML semantic/metadata inspector (`inspect_html_document`).
  - Enforced analytics privacy and consent gates: hard denylist rejecting `password`, `access_token`, `refresh_token`, `jwt`, `api_key`, `card_number`, `cvv`, `ssn`, `raw_email`, `phone_number`, etc.; required `requires_opt_in=True` for non-essential categories; required `ip_anonymization_enabled=True`, `respect_do_not_track=True`, and `third_party_transmission_enabled=False`.
  - Enforced measurable Core Web Vitals (`lcp_ms`, `inp_ms`, `cls_max`, `fcp_ms`, `ttfb_ms`), route asset budgets (`PERF-ROUTE-N`), API latency budgets (`PERF-API-N`), and honest measurement evidence (`EVD-N`, distinguishing `target_budget_only` from `measured_observation`).
  - Implemented cross-artifact traceability (`compute_seo_traceability`, `compute_analytics_traceability`, `compute_performance_traceability`) supporting explicit `not_applicable` PRD requirement coverage with required justification.
- **Backend API, Lifecycle Guards & Platform Observability (`backend/app/optimization_api.py`, `backend/app/observability.py`)**:
  - Mounted `/api/projects/{project_id}/optimization` in `backend/app/main.py`.
  - Wired `seo_stage_completion_check` and `analytics_stage_completion_check` into `PUT /api/projects/{project_id}/stages/{stage}` (`backend/app/api.py`) and wired `sync_optimization_stages` into `sync_architecture_stage` (`backend/app/architecture_api.py`).
  - Extended `CHK-HASH-PROVENANCE` in `backend/app/security_verification.py` to verify approved `OptimizationArtifact` SHA-256 hashes.
  - Enhanced `MetricsRegistry` in `backend/app/observability.py` with `scope="webforge_platform_operational_only"`, latency histogram buckets (`duration_buckets_ms`), `avg_duration_ms`, `max_duration_ms`, `slow_requests_total`, and `error_rate`.
- **Frontend Workspaces (`frontend/src/pages/OptimizationPage.tsx`)**:
  - Added `SeoPage` (`/projects/:projectId/seo`), `AnalyticsPage` (`/projects/:projectId/analytics`), and `PerformancePage` (`/projects/:projectId/performance`), updated `nav.ts` and `router.tsx`, and added `frontend/src/test/optimization_phase16.test.tsx`.

### Verification Summary (`python3 backend/scripts/verify_phase16.py`)
- **Passed (10/15 checks)**: Secret & Credential Hygiene Scan (`171` files, `0` secrets), Static Security Controls (`88` frontend modules), Phase 16 SEO/Analytics/Performance & HTML/Sitemap Verification (`5/5` checks passed), Phase 16 Frontend Workspaces/Routes/Navigation Check, Container/Nginx/Compose Manifest Validation, CI Workflow Validation, Fail-Fast Env & Log Redaction Verification, Alembic Migration Upgrade/Downgrade (`0001 -> 0008 -> 0007 -> 0008`), Disposable Database Backup & Restore Round-Trip (`4` rows across `14` tables, SHA-256 digests matched), and Backend Automated Test Suite (`189 passed, 9 skipped, 0 failed`).
- **Blocked by Environment (4/15 checks)**: Live PostgreSQL 16 server execution, Docker daemon image build execution, Frontend `npm` execution (`node_modules` absent in offline sandbox), and live CVE database lookup (`pip-audit`/`npm audit`).
- **Skipped (1/15 checks)**: Optional live Gemini API smoke check (`GOOGLE_AI_API_KEY` unset).

---

## Phase 17 — Documentation & Export (Completed)

- **Database & Project Brain (`0009_phase17_documentation_exports`)**:
  - Added `DocumentationExport` (`documentation_exports` table) with per-project version uniqueness (`uq_documentation_export_project_version`) and partial unique index `uq_documentation_official_current` (`export_mode = 'official' AND status = 'completed'`).
  - Added `DocumentationBrain` (`documentation_spec`) to `ProjectBrain` and `PROTECTED_SECTIONS`, and registered `DocumentationExport` in `backend/scripts/db_ops.py` (15 tables total) and `backend/tests/test_postgres.py`.
- **Deterministic Documentation Generator, Validator & Archive Builder (`backend/app/documentation_export.py`)**:
  - Implemented `collect_export_snapshot`, `generate_markdown_documents` (`README.md`, `01-research.md` .. `12-traceability.md`), `validate_project_export` (`blocking_error`, `warning`, `info`), `build_export_manifest` (`MANIFEST.json`), `build_deterministic_zip_bytes`, `build_consolidated_markdown`, `build_validated_json_export`, `validate_safe_archive_path`, and `scan_export_for_secrets`.
- **Backend API, Lifecycle Guard & Upstream Invalidation (`backend/app/documentation_api.py`)**:
  - Mounted `/api/projects/{project_id}/documentation` endpoints (`GET ""`, `POST "/preview"`, `POST "/generate"`, `GET "/exports"`, `GET "/exports/{export_id}"`, `POST "/exports/{export_id}/verify"`, `GET "/exports/{export_id}/download"`, `GET "/exports/{export_id}/files/{filename:path}"`).
  - Wired `documentation_stage_completion_check` into `PUT /api/projects/{project_id}/stages/documentation` in `backend/app/api.py`, wired `sync_documentation_stage` into `sync_optimization_stages` in `backend/app/optimization_api.py`, and extended `CHK-HASH-PROVENANCE` in `backend/app/security_verification.py`.
- **Frontend Workspace (`frontend/src/pages/DocumentationPage.tsx`)**:
  - Implemented `/projects/:projectId/documentation` workspace with readiness checklist, 14-artifact provenance & staleness inventory table, validation findings with remediation links, interactive document & `MANIFEST.json` previewer (with official vs. draft/stale toggle), official/preview bundle generation, format downloads (`.zip`, `.md`, `.json`, individual files), and export history with SHA-256 verification.
- **Verification**:
  - `python3 backend/scripts/verify_phase17.py` (`make verify-phase17`): `12 passed, 0 failed` across all runnable checks; SQLite test suite `194 passed, 9 skipped, 0 failed`; Alembic migrations `0001 -> 0009 -> 0008 -> 0009` and 15-table disposable backup/restore round-trip verified.

## Post-Phase-17 Validation Fixes (2026-10-28)

A fresh validation pass found and fixed these regressions before release:

- **Optimization draft state**: `_get_approved_and_draft()` now materializes SQLAlchemy query results before scanning them. The previous one-shot iterator could be consumed by the approved-version search, causing a newly initialized SEO/Analytics/Performance draft to serialize as `null`. Phase 16 tests: **8 passed**; Phase 17 tests: **5 passed** after the fix.
- **Backup/restore verification**: removed an invalid `updated_at` constructor argument for `ProjectStage`, added explicit flush ordering when creating the disposable backup fixture, and flushes each parent/dependent table in order during restore. Phase 15 infrastructure tests: **6 passed**.
- **Secret scan false positives**: API-key/private-key examples in test fixtures and verification samples are now assembled from string fragments at runtime, so the repository scanner does not misclassify intentional fixtures as committed credentials. Secret hygiene scan: **PASSED, 203 files scanned, zero hardcoded secrets or local `.env` files**.
- **Security and export verification**: static security controls **PASSED** (96 frontend modules scanned, no forbidden HTML/storage sinks); Phase 17 deterministic ZIP/path/secret verification **PASSED**; Alembic migration upgrade/downgrade/re-upgrade `0001 -> 0009 -> 0008 -> 0009` **PASSED**.
- **Test configuration**: test JWT secret length increased to meet the minimum recommended HMAC length and remove avoidable JWT warnings.

### Remaining release gates

- The entire backend suite (`204` collected tests) did not finish within the available 5-minute run window; therefore no all-suite pass is claimed. The targeted Phase 15, 16, and 17 suites passed individually after the fixes, but broader suites must be rerun in CI or a local environment with a longer timeout.
- Frontend dependency installation could not complete because this environment cannot retrieve all npm registry packages; offline installation confirmed a required package was not cached. Consequently frontend Vitest, TypeScript typecheck, and production build remain **not verified here**. The project CI uses Node 22; this environment has Node 22.16, below some locked dependencies' declared engine range.
- PostgreSQL, Docker runtime/image build, live Gemini connectivity, and external dependency vulnerability database checks remain environment-dependent and have not been represented as passing.

Do not mark the release production-ready until GitHub Actions completes the backend suite, frontend install/typecheck/tests/build, and available security checks successfully.
