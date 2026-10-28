# Frontend

React 19 + TypeScript + Vite + Tailwind CSS 4, React Router 6. No UI framework, no state library (a small `useAsync` hook covers data loading).

## Run
    cd frontend && npm install
    npm run dev          # http://localhost:5173, proxies /api to the backend (default http://127.0.0.1:8000)
    npm run build        # tsc --noEmit (type check, includes tests) + vite build
    npm test             # 87 unit/component tests, mocked at the network boundary
    WEBFORGE_API_URL=http://127.0.0.1:8000/api npm run test:integration   # real client vs a running backend

Environment (`frontend/.env.example`): `VITE_API_BASE_URL` (default `/api`, same origin) and `VITE_DEV_PROXY_TARGET` (used only by `vite.config.ts`). No backend URL appears in component code. Same-origin means the backend's httpOnly cookies work without CORS tweaks; for a cross-origin deployment set `VITE_API_BASE_URL` and the backend's `CORS_ORIGINS`/`COOKIE_SECURE`.

## Structure
    src/app/          router.tsx (route table), providers.tsx, App.tsx
    src/lib/          api.ts (client), useAsync.ts, utils.ts (labels, dates)
    src/types/        shapes of backend responses
    src/features/     research (FindingCard, Dialogs, Panels, labels, api) · discovery (QuestionList, ReviewPanel, callout, drafts, api) · auth (AuthProvider, guards) · projects (api, dialogs) · overview (panels, intake, idea review) · lifecycle (map)
    src/components/   ui (Button, Fields, Badge, ProgressBar, Alert, Dialog) · feedback (loading/error/empty) · layout (AppShell) · navigation (nav config, sidebar)
    src/pages/        Login, Register, Projects, ProjectLayout, ProjectOverview, Section (coming soon), Settings, NotFound

## Routes
`/login`, `/register` (redirect away when signed in) · `/projects` · `/settings` · `/projects/:id` → `/overview` · `/projects/:id/discovery` (progressive questions, see docs/DISCOVERY.md) · `/projects/:id/research` (docs/RESEARCH.md) · `/projects/:id/:section` renders the "Not implemented yet / Phase N" page for sections in `components/navigation/nav.ts`, 404 otherwise. Everything except login/register requires a session (`RequireAuth`).

## API client (`lib/api.ts`)
All requests go through `createApiClient`; components never call `fetch`. It sends `credentials: "include"`, normalizes errors into `ApiError { status, kind, message, detail }` (`detail` is the raw FastAPI detail, used for per-question 422 errors) (FastAPI `detail` strings/arrays become one sentence; 5xx internals are never shown; network failures get their own kind), and on a 401 from a non-`/auth/*` call performs one shared refresh then retries once. If refresh fails it notifies `AuthProvider`, which sends the user to login.

## Authentication
Cookies are httpOnly, so JavaScript never sees tokens and nothing is stored in localStorage. On startup `AuthProvider` calls `/auth/me`; on 401 it tries `/auth/refresh` once and asks again. Network failure shows a retry screen rather than logging the user out. Backend rotation means concurrent refreshes would trip reuse detection, hence the single shared refresh promise.

## Backend as source of truth
Progress, completed/in-progress/needs-review/blocked lists, next action and recent changes are rendered as returned by `GET /projects/:id/overview`. The lifecycle map groups stages into rows using the backend's `depends_on` (layout only) and explains blocking from `unmet_dependencies`. Status changes call `PUT .../stages/:stage`; the backend decides (409 → friendly message).

### API contract change made for this phase
`/overview` previously returned only `{stage, status}` per stage. Added: `stages[].depends_on`, `stages[].unmet_dependencies`, and a top-level `needs_review` list. Backward compatible; covered by `test_lifecycle_dependencies_and_overview`.

## Tests
- `lib/api.test.ts`: error normalization, refresh/retry, shared refresh, no refresh for `/auth/*`.
- `test/*.test.tsx`: routing, forms, project CRUD, overview data, stage conflicts, intake 503/502/validation/success, nav. `mockApi` stubs `fetch` by route and **fails the test on any unrouted request**.
- `test/backend.int.test.ts`: the real client against the real backend (cookie jar, refresh rotation, 409, 503, ownership). Skipped unless `WEBFORGE_API_URL` is set.

## Browser QA (Phase 5.5)
Scripts in `frontend/qa/` (see its README) drive real headless Chromium against the real stack: auth/session/cookies, project flow, lifecycle, intake 503, four viewports, keyboard/focus/dialogs, axe, network counts. Results and the defects it found are in `docs/BUILD_PROGRESS.md`. Layout notes that came from it: long names use `overflow-wrap:anywhere`; the projects table stacks into rows below `md`; the page scrolls inside `<main>` (measure overflow there, not on `documentElement`); dialogs trap focus and restore it to the trigger; the mobile sidebar closes on Escape or backdrop click.

## Not done / limits
No ESLint config (type checking only; lint is a future task). Only Chromium was tested; no screen-reader pass; WCAG compliance is not claimed. Section phase numbers (9–17) in `nav.ts` are provisional.


## Phase 10 — Product Strategy and PRD Workspaces

- `/projects/:projectId/strategy` (`StrategyPage.tsx`): displays `StrategyInputs` provenance (`user_confirmed`, `ai_suggestion`, `unresolved_assumption`, `research_finding`, `missing_inputs`), positioning & business model overview, traceable recommendations (`grounded_in_confirmed`, `supported_by_research`, `ai_suggestion`, `hypothesis`, `unsupported`), goals, target users, MVP scope boundaries, metrics, risks, open decisions, immutable version history, and exact-hash review/approval.
- `/projects/:projectId/prd` (`PrdPage.tsx`): displays Strategy basis summary, problem statement, target users, user stories (`US-N`), functional (`FR-N`) and non-functional (`NFR-N`) requirements with priority/MVP-boundary/approval-status badges (`proposed` vs `approved`), testable acceptance criteria, edge cases, source strategy references, individual/bulk requirement approval, immutable version history, and exact-hash review/approval completing the `product` lifecycle stage.
- Navigation (`nav.ts`): `strategy` and `prd` are live routes under the `Product` group (`stage: "product"`); `competitors` retains `phase: 10` until competitive intelligence is built. `LifecycleMap.tsx` explains how pre-lifecycle setup (Phases 1–8) relates to the 19 engineering lifecycle stages (Phases 9–17).


## Phase 11 — UX Design & Experience Workspaces

- `/projects/:projectId/personas` (`PersonasPage.tsx`): research- and PRD-grounded user personas (`P-N`), evidence status badges (`evidence_backed`, `mixed`, `hypothesis`), accessibility/device considerations, manual creation fallback when AI is unconfigured, copy-on-write edits, and exact-hash approval.
- `/projects/:projectId/journeys` (`JourneysPage.tsx`): stage-by-stage user journey timelines (`J-N`) linked to approved `P-N` personas and PRD requirements, labeling user thoughts as hypotheses and displaying explicit failure/recovery paths and accessibility notes.
- `/projects/:projectId/ia` (`IaPage.tsx`): hierarchical sitemap and navigation model (`IA-N`) with parent-child tree visualization, accessible parent re-assignment, cycle/self-parent rejection, and PRD requirement traceability.
- `/projects/:projectId/wireframes` (`WireframesPage.tsx`): structured low-fidelity wireframe specifications (`WF-N`) driving a deterministic visual wireframe renderer with interactive Viewport Switcher (`Desktop`, `Tablet`, `Mobile`) and UI State Preview (`Default`, `Loading`, `Empty`, `Error`, `Success`).
- `/projects/:projectId/ux-review` (`UxReviewPage.tsx`): combined deterministic cross-artifact consistency/coverage findings (`origin="deterministic"`) and AI review suggestions (`origin="ai"`), resolution/accepted-risk workflow requiring a `resolution_note`, and approval completing the `ux` lifecycle stage.


## Phase 12 — Design System & Interactive Prototype Workspaces

- `/projects/:projectId/design-system` (`DesignSystemPage.tsx`): renders color token swatches with contrast notes, typography scale specimens, spacing and grid/breakpoint foundations, reusable component specifications (`CMP-N`) with variants/states/tokens/wireframe/PRD traceability, and design decisions (`DD-N`) with proposed/reviewed/approved status toggles, copy-on-write edits, and exact-hash approval.
- `/projects/:projectId/prototype` (`PrototypePage.tsx`): interactive prototype player reusing persisted Phase 11 wireframe layouts and Phase 12 Design System tokens across screens (`SCR-N`) and journey happy-path flows (`FLOW-N`), with interactive screen navigation, simulated form validation, modal dialogs, viewport switching (`Desktop`, `Tablet`, `Mobile`), UI state previews (`Default`, `Loading`, `Empty`, `Error`, `Success`), screen index & relationship map, and exact-hash approval completing the `design` lifecycle stage.


## Phase 13 — Product Architecture Workspace

- `/projects/:projectId/architecture` (`ArchitecturePage.tsx`): renders System Overview & Component/Integration Inventory (`COMP-N`, `INT-N`), Application Architecture (`FE-N`, `BE-N`), Data Architecture (`ENT-N`, relationships, integrity/migration rules), API & Integration Architecture (`API-N`), Deployment & Operational Architecture (`SVC-N`), Technical Decision Records (`ADR-N`), Structured Diagram Viewer (`DIAG-N` with validated nodes, directed edges, and Mermaid definitions), and the end-to-end Requirement Traceability Matrix (`PRD requirement -> Component -> Data/API/Backend boundary -> Approved Design/Prototype ref`), with inline copy-on-write editing, prerequisite/staleness alerts, version history, and exact-hash review/approval completing the `architecture` lifecycle stage.

## Phase 16 — SEO, Analytics & Performance Workspaces

- `/projects/:projectId/seo` (`SeoPage` in `OptimizationPage.tsx`): displays SEO Strategy & Crawl Policy, Page Metadata & Indexability table (`SEO-PAGE-N`) with public vs. non-public (`noindex`) badges and canonical paths, generated `/sitemap.xml` and `/robots.txt` previews, Technical & Semantic SEO Checklist (`SEO-CHK-N`), interactive HTML Semantic & Metadata Inspector (`verify-html`), PRD Requirement Traceability (`covered` / `not_applicable`), version history, copy-on-write editing, and exact-hash approval completing the `seo` lifecycle stage.
- `/projects/:projectId/analytics` (`AnalyticsPage` in `OptimizationPage.tsx`): displays Measurement Objective, KPIs & Funnels, Consent & Privacy Governance (`denied_until_opt_in`, `requires_opt_in`, PII redaction rules, prohibited sensitive fields denylist, `third_party_transmission_enabled=false`), Event Taxonomy & Property Schema (`EVT-N`), Reporting & Funnel Views (`VIEW-N`), PRD Requirement Traceability, copy-on-write editing, and exact-hash approval completing the `analytics` lifecycle stage.
- `/projects/:projectId/performance` (`PerformancePage` in `OptimizationPage.tsx`): displays Core Web Vitals Budgets (`LCP`, `INP`, `CLS`, `FCP`, `TTFB`) with honest `target_budget_only` vs. `measured_observation` posture badge, Route Asset & Bundle Budgets (`PERF-ROUTE-N`), Backend API Latency & Payload Budgets (`PERF-API-N`), Recorded Measurement Evidence (`EVD-N`) with interactive observation recording, and exact-hash approval.
- Navigation (`nav.ts`): `seo`, `analytics`, and `performance` are live routes under the `Optimization` group (no `phase: 16` placeholder badges).

## Phase 17 — Documentation & Export Workspace (`/projects/:projectId/documentation`)
- **Types & API Client**: `frontend/src/types/documentation.ts` and `frontend/src/features/documentation/api.ts`.
- **Workspace Component (`frontend/src/pages/DocumentationPage.tsx`)**:
  - Displays `documentation` stage status badge, completion checklist, and blocking reasons.
  - Renders the 14-artifact Provenance, Approval & Staleness Inventory table with version badges, `CURRENT` vs `STALE` indicators, SHA-256 hash verification status, and direct links to each artifact's workspace.
  - Displays Pre-Export Validation Findings grouped by severity (`blocking_error`, `warning`, `info`) with remediation links.
  - Provides an interactive Bundle Document & `MANIFEST.json` Inspector with file tabs (`README.md`, `01-research.md` .. `12-traceability.md`, `MANIFEST.json`) and a toggle to preview draft/stale artifacts (`NON-OFFICIAL`).
  - Provides Official Export generation (`mode="official"`), Preview bundle saving (`mode="preview"`), format downloads (`.zip`, `.md`, `.json`, and individual files), and persisted Export History with `Verify SHA-256` integrity checking.
