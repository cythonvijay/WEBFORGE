# WebForge — From idea to production.

WebForge is a full-lifecycle AI Product Engineering Platform built with **FastAPI**, **SQLAlchemy 2**, **Alembic**, **PostgreSQL 16**, **React 19**, **TypeScript**, **Vite**, and **Tailwind CSS**.

It guides product teams from initial idea intake and progressive discovery through versioned, hash-approved **Research**, **Product Strategy**, **PRD**, **UX (Personas, Journeys, IA, Wireframes, UX Review)**, **Design System**, **Interactive Prototype**, **Product Architecture**, **Security Verification (Phase 14)**, **Infrastructure, DevOps & Deployment (Phase 15)**, **SEO, Analytics & Performance (Phase 16)**, and **Documentation & Specification Export (Phase 17)**.

---

## Quick Start (Local Development)

### 1. Configure Environment
```bash
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD and a strong JWT_SECRET:
# python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. Run with Docker Compose (PostgreSQL 16 + Safe Migrations + Backend)
```bash
make db         # Start PostgreSQL 16 and wait for pg_isready health check
make migrate    # Run `python -m scripts.db_ops migrate` (applies Alembic 0001..0009 and verifies head)
make up         # Start backend on http://127.0.0.1:8000
```
To run the full containerized stack including the unprivileged Nginx frontend on `http://127.0.0.1:8080`:
```bash
docker compose --profile fullstack up --build
```

### 3. Frontend Development Server
```bash
cd frontend && npm ci && npm run dev   # http://localhost:5173 (proxies /api -> http://127.0.0.1:8000)
```

---

## Verification, Testing & Database Operations

| Command | Description |
| :--- | :--- |
| `make test` | Run backend unit, API, security, and infrastructure tests on SQLite (`194 passed`) |
| `make test-pg` | Run full backend test suite including PostgreSQL concurrency tests against PostgreSQL 16 |
| `make check-db` | Verify database connectivity and confirm `alembic_version` matches head (`0009`) |
| `make backup` | Create a checksummed logical backup (`.wfbackup.json` + `.pgdump` sidecar on PG) in `backups/` |
| `make verify-backup` | Run automated backup & restore round-trip verification across disposable databases |
| `make verify-phase14` | Run repeatable Phase 14 Testing & Security verification runner |
| `make verify-phase15` | Run repeatable Phase 15 Infrastructure, DevOps & Deployment verification runner |
| `make verify-phase16` | Run repeatable Phase 16 SEO, Analytics & Performance verification runner |
| `make verify-phase17` | Run repeatable Phase 17 Documentation & Export verification runner |

---

## Health & Observability Endpoints

- `GET /api/health` & `GET /api/health/live` — Process liveness and bounded request/error metrics (zero DB dependency).
- `GET /api/ready` & `GET /api/health/ready` — Readiness probe verifying PostgreSQL connectivity, Alembic head revision (`0009`), and runtime configuration without leaking secrets.

---

## Documentation Index

- **Architecture**: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **Documentation & Export (Phase 17)**: [`docs/EXPORT.md`](docs/EXPORT.md)
- **SEO, Analytics & Performance (Phase 16)**: [`docs/SEO.md`](docs/SEO.md) | [`docs/ANALYTICS.md`](docs/ANALYTICS.md) | [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md)
- **Database & Migrations**: [`docs/DATABASE.md`](docs/DATABASE.md)
- **Deployment & CI/CD (Phase 15)**: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- **Operations, Health Checks & Backups (Phase 15)**: [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- **Security & Verification (Phases 14–15)**: [`docs/SECURITY.md`](docs/SECURITY.md)
- **Frontend & Design**: [`docs/FRONTEND.md`](docs/FRONTEND.md) | [`docs/DESIGN.md`](docs/DESIGN.md) | [`docs/UX.md`](docs/UX.md)
- **Discovery, Research & AI Provider**: [`docs/DISCOVERY.md`](docs/DISCOVERY.md) | [`docs/RESEARCH.md`](docs/RESEARCH.md) | [`docs/AI_PROVIDER.md`](docs/AI_PROVIDER.md)
- **Roadmap & Build Progress**: [`docs/ROADMAP.md`](docs/ROADMAP.md) | [`docs/BUILD_PROGRESS.md`](docs/BUILD_PROGRESS.md)
