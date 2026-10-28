# Roadmap

    Phase 0      Foundation          COMPLETE
    Phase 0.5    Database Hardening  COMPLETE*
    Phase 1      Authentication      COMPLETE
    Phase 2      Projects            COMPLETE
    Phase 3      Project Brain       COMPLETE
    Phase 4      Lifecycle           COMPLETE
    Phase 5      Application Shell   COMPLETE
    Phase 5.5    Browser QA          COMPLETE (headless Chromium only; see BUILD_PROGRESS)
    Phase 6      Project Overview    COMPLETE
    Phase 7      AI Intake           COMPLETE (real provider call never exercised)
    Phase 8      Progressive AI      COMPLETE** (test double + browser w/ test double; real provider NOT VERIFIED)
    Phase 9      Research            COMPLETE** (test doubles only; real provider and external retrieval NOT RUN)
    Phase 10     Strategy / PRD      COMPLETE** (Strategy & PRD workspaces complete; Competitors remains provisional)
    Phase 11     UX Workflow         COMPLETE** (Personas, Journeys, IA, Wireframes, UX Review complete)
    Phase 12     Design & Prototype  COMPLETE** (Design System & Interactive Prototype complete)
    Phase 13     Architecture        COMPLETE** (Product Architecture workspace complete; Frontend, Backend, Database, API implementation stages next)
    Phase 14     Testing & Security  COMPLETE** (Security hardening SEC-01..07, stage completion guards, repeatable verification suite)
    Phase 15     Infra & Deployment  COMPLETE*  (Docker/Compose, non-root multi-stage builds, observability, db_ops backup/restore, CI)
    Phase 16     SEO, Analytics, Perf COMPLETE** (Persistent versioned SEO, Analytics & Performance specs, HTML/sitemap/privacy/budget verification)
    Phase 17     Documentation        COMPLETE** (Deterministic Markdown/ZIP/JSON specification export, manifest & SHA-256 verification, final stage guard)

\* Docker verification pending because Docker was unavailable.
\*\* Real Google AI path never exercised: no usable key, and the sandbox cannot reach Google.

Provisional later phases (the numbers shown as "Phase N" in the app's sidebar):

    Phase 9   Research, Competitors        Phase 14  Testing, Security
    Phase 10  Strategy, PRD                Phase 15  Docker, CI/CD, Jenkins, Infrastructure, Kubernetes, Deployments, Monitoring
    Phase 11  Personas, Journeys, IA,      Phase 16  SEO, Analytics, Performance
              Wireframes, UX Review        Phase 17  Documentation, Export
    Phase 12  Design System, Prototype     
    Phase 13  Architecture, Frontend, Backend, Database, API generation


## Roadmap Phases vs. 19 Engineering Lifecycle Stages

- **Phases 0–5.5** are platform-level foundation milestones (Repository layout, Auth, Projects CRUD, append-only Project Brain, 19-stage Lifecycle dependency engine, and Application Shell). They are not per-project lifecycle stages.
- **Phases 6–8** are pre-lifecycle project setup and clarification workflows (`Overview` + `AI Intake` in Phases 6–7, and `Discovery` Q&A in Phase 8). They populate the Project Brain (`idea`, `target_users`, `goals`, `discovery.confirmed`, `discovery.assumptions`) and do not increment the 19-stage lifecycle counter.
- **Phases 9–17** implement the 19 engineering lifecycle stages (`research`, `product`, `ux`, `design`, `architecture`, `frontend`, `backend`, `database`, `api`, `testing`, `security`, `docker`, `cicd`, `infrastructure`, `deployment`, `monitoring`, `seo`, `analytics`, `documentation`).

## Phase 14 — Comprehensive Testing & Security Hardening (Implemented)
- Completed comprehensive security audit (`SEC-01`..`SEC-07`) documented in `docs/SECURITY.md`.
- Hardened authentication, refresh-token row locking (`with_for_update`), logout cookie clearing, CSRF/Origin/Fetch-Metadata defense (`SecurityMiddleware`), HTTP security headers, and `512 KiB` request body size caps.
- Enforced strict Pydantic `extra="forbid"` and payload size/depth limits on Project Brain sections and AI Intake results, plus sanitized AI provider error handling.
- Implemented deterministic Phase 14 security & testing verification (`GET /api/projects/{id}/security-verification`) and enforced real completion guards for `ux`, `design`, `architecture`, `testing`, and `security` stages on `PUT /api/projects/{id}/stages/{stage}`.
- Added repeatable verification runner (`backend/scripts/verify_phase14.py` / `make verify-phase14`) and expanded automated backend (`175 passed` on SQLite + PostgreSQL concurrency suite) and frontend security tests.

## Phase 15 — Infrastructure, DevOps & Deployment (Implemented)
- Implemented reproducible local and production Docker Compose configurations (`docker-compose.yml`, `docker-compose.prod.yml`) with health checks, one-shot `migrate` service, persistent `pgdata` volume, and internal bridge networking.
- Implemented multi-stage non-root Dockerfiles for backend (`backend/Dockerfile`) and frontend (`frontend/Dockerfile` + `frontend/nginx.conf` with `/api/` reverse proxy, immutable asset caching, `no-cache` SPA shell, and SPA fallback), plus `.dockerignore` files.
- Added fail-fast runtime environment validation (`backend/app/config.py`), structured JSON/text logging with `X-Request-ID` correlation and secret redaction (`backend/app/observability.py`), and separated liveness (`/api/health/live`) and readiness (`/api/health/ready`) probes.
- Added safe database operations and checksummed backup/restore CLI (`backend/scripts/db_ops.py`, `scripts/backup_db.sh`, `scripts/restore_db.sh`) verified against disposable databases.
- Added GitHub Actions CI pipeline (`.github/workflows/ci.yml`), Phase 15 lifecycle completion guards (`backend/app/infrastructure_verification.py`), automated test suite (`backend/tests/test_infrastructure_phase15.py`), repeatable verification runner (`backend/scripts/verify_phase15.py`), and `docs/DEPLOYMENT.md` + `docs/OPERATIONS.md`.

## Phase 16 — SEO, Analytics & Performance (Implemented)
- Added `OptimizationArtifact` (`optimization_artifacts`, migration `0008_phase16_seo_analytics_performance`) and `OptimizationBrain` (`optimization_spec` in `ProjectBrain` with `seo`, `analytics`, and `performance` pointers).
- Implemented validated domain schemas (`SeoContent`, `AnalyticsContent`, `PerformanceContent`) with cross-artifact traceability (`PRD -> UX/Prototype -> Architecture -> Optimization`), public vs. private route indexability enforcement, analytics sensitive-field denylist and opt-in consent gates, Core Web Vitals/route/API performance budgets, and honest measurement evidence (`target_budget_only` vs `measured_observation`).
- Implemented `/api/projects/{project_id}/optimization` endpoints (`GET /`, `GET /{area}`, `POST /{area}/initialize`, `POST /{area}/generate`, `PUT/PATCH`, `submit`, `approve`, `verify-html`, `verify-product`, and `performance/versions/{v}/evidence`) plus `seo` and `analytics` stage completion guards and upstream invalidation (`sync_optimization_stages`).
- Connected frontend workspaces `/projects/:projectId/seo` (`SeoPage`), `/projects/:projectId/analytics` (`AnalyticsPage`), and `/projects/:projectId/performance` (`PerformancePage`).
- Separated WebForge platform operational observability (`backend/app/observability.py` latency histogram, slow request counter, error rate) from generated-product analytics.
- Added automated backend (`backend/tests/test_optimization_phase16.py`) and frontend (`frontend/src/test/optimization_phase16.test.tsx`) tests, repeatable verification runner (`backend/scripts/verify_phase16.py` / `make verify-phase16`), and `docs/SEO.md`, `docs/ANALYTICS.md`, and `docs/PERFORMANCE.md`.

## Phase 17 — Documentation & Export (Implemented — Final Planned Phase)
- Added `DocumentationExport` (`documentation_exports`, migration `0009_phase17_documentation_exports`) and `DocumentationBrain` (`documentation_spec` in `ProjectBrain`).
- Implemented deterministic documentation bundle generation (`README.md`, `01-research.md` .. `12-traceability.md`, `MANIFEST.json`), consolidated Markdown (`.md`), validated specification JSON (`.json`), and deterministic `.zip` packaging (`backend/app/documentation_export.py`).
- Implemented pre-export validation across all 14 project artifacts (verifying approval state, open drafts, upstream staleness, SHA-256 content hashes, Project Brain pointer alignment, PRD requirement traceability, UX/security readiness, archive path safety, and secret scanning).
- Implemented `/api/projects/{project_id}/documentation` endpoints (`GET /`, `POST /preview`, `POST /generate`, `GET /exports`, `GET /exports/{id}`, `POST /exports/{id}/verify`, `GET /exports/{id}/download`, `GET /exports/{id}/files/{filename}`), plus `documentation` stage completion guard (`documentation_stage_completion_check`) and upstream invalidation (`sync_documentation_stage`).
- Connected frontend workspace `/projects/:projectId/documentation` (`DocumentationPage.tsx`) and removed placeholder `phase: 17` from `nav.ts`.
- Added automated backend (`backend/tests/test_documentation_phase17.py`) and frontend (`frontend/src/test/documentation_phase17.test.tsx`) tests, repeatable verification runner (`backend/scripts/verify_phase17.py` / `make verify-phase17`), and `docs/EXPORT.md`.
