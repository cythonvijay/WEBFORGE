# WebForge Deployment Guide (Phase 15)

This guide documents the reproducible local startup, container build architecture, environment configuration, CI/CD pipeline, production deployment topology, and rollback procedures for WebForge.

---

## 1. Prerequisites

| Tool | Supported Version | Purpose |
| :--- | :--- | :--- |
| **Docker Engine & Compose** | Docker 24+ / Compose v2.20+ | Container builds, local PostgreSQL 16 service, and multi-service orchestration |
| **Python** | 3.11 – 3.12 (`3.12` pinned in Docker/CI) | FastAPI backend, Alembic migrations, `scripts.db_ops`, and pytest suites |
| **Node.js & npm** | Node.js 22 LTS (`node:22-alpine` in Docker/CI) | React 19 + TypeScript + Vite + Tailwind frontend build and Vitest suite |
| **PostgreSQL** | PostgreSQL 16 (`postgres:16-bookworm`) | Primary transactional and JSONB database |

---

## 2. Reproducible Local Development Startup

### Option A: Hybrid Local Workflow (PostgreSQL in Docker + Host Backend/Frontend)
1. Copy the placeholder environment file and set local secrets:
   ```bash
   cp .env.example .env
   # Edit .env: set POSTGRES_PASSWORD and generate JWT_SECRET:
   # python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. Start PostgreSQL 16 and wait for its `pg_isready` health check:
   ```bash
   make db
   # Equivalent: docker compose up -d --wait postgres
   ```
3. Apply and verify Alembic migrations (`0001` through `0007`):
   ```bash
   cd backend && python -m scripts.db_ops migrate
   ```
4. Run the FastAPI backend and Vite dev server:
   ```bash
   # Terminal 1 (Backend on http://127.0.0.1:8000)
   cd backend && uvicorn app.main:app --reload --port 8000

   # Terminal 2 (Frontend on http://localhost:5173, proxying /api -> :8000)
   cd frontend && npm ci && npm run dev
   ```

### Option B: Containerized Compose Workflow
- **Backend + Migrated PostgreSQL (`:8000`)**:
  ```bash
  make up
  # Equivalent: docker compose up --build backend
  ```
  `docker-compose.yml` starts `postgres`, waits for `service_healthy`, runs the one-shot `migrate` service (`python -m scripts.db_ops migrate`), waits for `service_completed_successfully`, and then starts `backend`.
- **Full Containerized Stack including Nginx Frontend (`:8080`)**:
  ```bash
  docker compose --profile fullstack up --build
  ```

---

## 3. Environment Configuration & Fail-Fast Rules

All configuration is loaded by `backend/app/config.py` (`Settings`) from environment variables (with `.env` fallback for local development).

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | Yes | `development` | One of `development`, `test`, `staging`, `production`. |
| `DATABASE_URL` | **Yes** | *(none)* | SQLAlchemy URL, e.g. `postgresql+psycopg://webforge:<pass>@postgres:5432/webforge`. |
| `JWT_SECRET` | **Yes** | `""` | HS256 signing secret. Must be `>= 32` chars and non-placeholder in `staging`/`production`. |
| `CORS_ORIGINS` | Yes | `http://localhost:5173` | Comma-separated allowed origins. Must be explicit `https://` origins in `production` (no `*`). |
| `COOKIE_SECURE` | Yes | `false` | Must be `true` in `production` so `access_token` and `refresh_token` require HTTPS. |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `LOG_JSON` | No | `false` | Emit single-line structured JSON logs with `request_id` when `true`. |
| `ENABLE_METRICS` | No | `true` | Maintain bounded in-memory request/status/error counters. |
| `DB_POOL_SIZE` | No | `5` | SQLAlchemy connection pool size (PostgreSQL). |
| `DB_MAX_OVERFLOW` | No | `10` | SQLAlchemy max overflow connections (PostgreSQL). |
| `DB_POOL_TIMEOUT` | No | `30` | Pool checkout timeout in seconds. |
| `DB_CONNECT_RETRIES` | No | `5` | Bounded connection retry count for `scripts.db_ops wait`/`migrate`. |
| `DB_CONNECT_RETRY_DELAY_SECONDS` | No | `1.0` | Delay in seconds between bounded DB connection retries. |
| `AI_PROVIDER` | No | `google` | AI provider identifier (`google`). |
| `GOOGLE_AI_API_KEY` | Optional | `""` | Server-side Gemini API key. Never exposed to the frontend build. |
| `GOOGLE_MODEL` | No | `gemini-3.8-flash` | Gemini model name. |
| `GOOGLE_TIMEOUT_SECONDS` | No | `60` | Upstream AI request timeout in seconds. |

### Fail-Fast Startup Enforcement
During FastAPI lifespan startup (`enforce_startup_settings` in `backend/app/config.py`), the backend immediately aborts startup if:
- `ENVIRONMENT` or `LOG_LEVEL` is invalid, or `DATABASE_URL` is empty.
- In `staging` or `production`:
  - `JWT_SECRET` is shorter than 32 characters or matches a known weak/default value (`change-me`, `secret`, `test-secret`, etc.).
  - `DATABASE_URL` does not use PostgreSQL (`postgresql://` or `postgresql+psycopg://`) or uses a weak password (`change-me`, `postgres`, `password`, etc.).
  - `CORS_ORIGINS` is empty, contains `*`, or (in `production`) uses `http://` or `localhost`.
  - In `production`, `COOKIE_SECURE` is `false`.
  - `GOOGLE_AI_API_KEY` is set to a placeholder string (`change-me`, `your-api-key`, `placeholder`).

---

## 4. Production Container Architecture

### Backend Image (`backend/Dockerfile`)
- **Multi-stage build**: Stage 1 (`python:3.12-slim-bookworm` `builder`) installs pinned Python dependencies into `/install` with `PIP_NO_CACHE_DIR=1`. Stage 2 (`runtime`) copies only `/install`, `alembic.ini`, `alembic/`, `app/`, and `scripts/`.
- **Non-root execution**: Runs as system user `webforge` (`UID 10001`, `GID 10001`).
- **Signal handling & workers**: Uses exec-form `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--timeout-graceful-shutdown", "30"]` so `SIGTERM` triggers clean connection draining.
- **No concurrent worker auto-migrations**: Application workers never run `alembic upgrade head` on boot; migrations run exclusively via the dedicated `migrate` job (`python -m scripts.db_ops migrate`).

### Frontend Image (`frontend/Dockerfile` & `frontend/nginx.conf`)
- **Multi-stage build**: Stage 1 (`node:22-alpine` `builder`) runs `npm ci` and `npm run build` (`tsc --noEmit && vite build`). No server-side secrets (`GOOGLE_AI_API_KEY`, `JWT_SECRET`, `DATABASE_URL`) are passed into the build.
- **Unprivileged runtime**: Stage 2 (`nginxinc/nginx-unprivileged:1.27-alpine`) runs as non-root `USER nginx` on port `8080`.
- **Routing & Caching (`frontend/nginx.conf`)**:
  - `/api/` is reverse-proxied to `http://backend:8000/api/` with `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Request-ID` headers, and is never intercepted by the SPA router.
  - `/assets/` (Vite content-hashed bundles) sets `Cache-Control: public, max-age=31536000, immutable`.
  - `/index.html` and SPA routes (`try_files $uri $uri/ /index.html;`) set `Cache-Control: no-cache, no-store, must-revalidate` so browser clients never serve a stale application shell after deployment.

---

### Vercel Frontend + Separately Hosted FastAPI Backend

The frontend defaults to `VITE_API_BASE_URL=/api`. `VITE_DEV_PROXY_TARGET` is only for the local Vite development server; it does not configure a production proxy.

If the Vite frontend is deployed to Vercel while FastAPI is hosted separately (for example, on Render):

1. Set the Vercel project root to `frontend`, the build command to `npm run build`, and the output directory to `dist`.
2. Keep `VITE_API_BASE_URL=/api` so browser requests stay on the frontend origin and retain the app's HTTP-only cookie session behavior.
3. Add a `vercel.json` in the Vercel project root with an API rewrite **before** the SPA fallback. Replace the example hostname with the real deployed backend origin; do not deploy the placeholder hostname:

   ```json
   {
     "$schema": "https://openapi.vercel.sh/vercel.json",
     "rewrites": [
       {
         "source": "/api/:path*",
         "destination": "https://YOUR-BACKEND-HOST.example/api/:path*"
       },
       {
         "source": "/(.*)",
         "destination": "/index.html"
       }
     ]
   }
   ```

4. Configure the backend with `ENVIRONMENT=production`, `DATABASE_URL=postgresql+psycopg://...`, a generated `JWT_SECRET` of at least 32 characters, `COOKIE_SECURE=true`, and `CORS_ORIGINS` containing the exact production frontend origin(s). Set `GOOGLE_AI_API_KEY` only if live Gemini generation is required.
5. Redeploy after changing Vercel environment variables, since `VITE_*` variables are embedded at build time. Never put database credentials, JWT secrets, or the Google AI API key in any `VITE_*` variable.

Do not point `VITE_API_BASE_URL` directly at a separate backend origin without changing the authentication/CSRF design: the app uses cookie sessions and blocks cross-site state-changing requests. Verify the proxy through the frontend origin using `/api/health/live`, then verify backend readiness and migration head using `/api/ready`.

---

## 5. Recommended Production Deployment Target & Cost Assumptions

### Recommended Target Topology
WebForge is designed for portable container deployment on a single Linux VM / Docker host or managed container platform (e.g., AWS ECS Fargate + RDS PostgreSQL 16, Google Cloud Run + Cloud SQL PostgreSQL 16, or a hardened Docker Compose host behind Caddy / Cloudflare / AWS ALB):
1. **TLS Boundary**: An external reverse proxy or load balancer terminates HTTPS (TLS 1.2/1.3) and forwards traffic to `frontend:8080` (`127.0.0.1:8080` in `docker-compose.prod.yml`).
2. **Frontend / Edge Tier (`frontend`)**: Serves static SPA bundles and proxies `/api/*` over the private internal bridge network (`webforge_internal`) to `backend:8000`.
3. **Application Tier (`backend`)**: Stateless FastAPI containers (`ENVIRONMENT=production`, `COOKIE_SECURE=true`, `LOG_JSON=true`).
4. **Data Tier (`postgres`)**: PostgreSQL 16 bound strictly to `webforge_internal` (`expose: ["5432"]`, zero public host ports) with persistent volume storage (`pgdata`) or managed private-VPC RDS/Cloud SQL.

### Production Launch Commands (Docker Compose Overlay)
```bash
# 1. Create pre-deployment backup (if upgrading an existing environment)
./scripts/backup_db.sh

# 2. Build and run one-shot migration + production services
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 3. Verify liveness and readiness
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/api/health/ready
```

### Cost & Provisioning Disclaimer
- No paid cloud infrastructure or external services are provisioned automatically by this repository.
- Running WebForge locally via Docker Compose or SQLite incurs **$0** infrastructure cost.
- Optional live Google Gemini API calls (`GOOGLE_AI_API_KEY`) incur standard per-token usage charges only when explicitly configured by the operator.

---

## 6. Continuous Integration Pipeline (`.github/workflows/ci.yml`)

The GitHub Actions workflow runs on `push` and `pull_request` to `main` with `permissions: contents: read`:
1. **`security-and-hygiene`**: Secret regex scan across all tracked files and static security assertions (`SecurityMiddleware`, non-root Dockerfiles, zero unsafe DOM sinks).
2. **`backend-sqlite-and-ops`**: Installs pinned `backend/requirements.txt`, verifies Alembic `upgrade head -> downgrade base -> upgrade head` (`0001..0009`), runs disposable backup/restore verification (`python -m scripts.db_ops verify-backup-restore`), and runs the full SQLite pytest suite.
3. **`backend-postgres-integration`**: Spins up an isolated `postgres:16-bookworm` service container, runs `python -m scripts.db_ops migrate`, and executes the full pytest suite including `tests/test_postgres.py` against PostgreSQL 16.
4. **`frontend-verify`**: Runs `npm ci`, `npm run typecheck`, `npm test`, `npm run build`, and scans `dist/` to ensure no server secrets leaked into client bundles.
5. **`dependency-audit`**: Runs `pip-audit -r backend/requirements.txt` and `npm audit --omit=dev --audit-level=high`.
6. **`container-build-verify`**: Validates `docker compose config` for both dev and prod Compose files, builds `backend/Dockerfile` and `frontend/Dockerfile`, and verifies both images run as non-root (`id -u != 0`).
7. **`optional-live-ai`**: Manual `workflow_dispatch`-only job (`inputs.run_live_ai == 'true'`); never runs on untrusted pull requests.

---

## 7. Rollback & Failed Deployment Recovery

1. **Migration Failure During Deployment**:
   - Because `backend` depends on `migrate: condition: service_completed_successfully`, a failed migration stops the new backend containers from starting while leaving existing data intact.
   - Inspect migration logs: `docker compose logs migrate`.
   - Each Alembic migration executes inside a transaction on PostgreSQL (`env.py`), rolling back failed DDL automatically.
2. **Application Rollback (No Schema Change)**:
   - Redeploy the previous known-good Git tag/commit image:
     ```bash
     git checkout <previous-tag>
     docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build backend frontend
     ```
3. **Database & Schema Rollback**:
   - If a schema migration must be reverted in a staging/recovery scenario, first create a backup (`./scripts/backup_db.sh`), restore the pre-deployment backup into a disposable database via `./scripts/restore_db.sh` to verify integrity, and switch over only after `python -m scripts.db_ops check` passes.
