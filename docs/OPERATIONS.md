# WebForge Operations, Observability & Recovery Runbook (Phase 15)

This runbook covers health and readiness probes, structured logging and correlation IDs, outage triage, database backup and restore verification, and credential rotation.

---

## 1. Health Checks & Readiness Probes

WebForge separates **process liveness** from **dependency/database readiness** so orchestrators do not restart healthy application processes during transient database maintenance.

| Endpoint | Probe Type | Success | Failure | What It Checks |
| :--- | :--- | :--- | :--- | :--- |
| `GET /api/health` | Liveness (minimal) | `200 {"status": "ok"}` | Unreachable | FastAPI process event loop responsiveness. |
| `GET /api/health/live` | Liveness + Metrics | `200 {"status": "ok", "check": "liveness", ...}` | Unreachable | Process liveness, environment name, and bounded in-memory request/error metrics. Zero DB queries. |
| `GET /api/ready` | Readiness (minimal) | `200 {"status": "ready"}` | `503 Service Unavailable` | Database connectivity (`SELECT 1`), Alembic head alignment (`0007`), and runtime config validity. |
| `GET /api/health/ready` | Readiness (detailed) | `200 {"status": "ready", "checks": {...}}` | `503 {"status": "not_ready", "checks": {...}}` | Reports per-subsystem status (`database`, `migrations`, `configuration`) without leaking connection strings or stack traces. |
| `GET /healthz` (Nginx) | Frontend Liveness | `200 {"status": "ok"}` | Unreachable | Frontend Nginx worker responsiveness on port `8080`. |

### Distinguishing Application Outage vs. Dependency Outage
1. **`/api/health/live` fails or times out**: The backend container/process is down, deadlocked, or unreachable. Inspect container status (`docker compose ps`, `docker compose logs backend`).
2. **`/api/health/live` returns `200`, but `/api/health/ready` returns `503`**:
   - If `checks.database == "unavailable"`: PostgreSQL is unreachable or rejecting connections. Check `docker compose ps postgres` and `docker compose logs postgres`.
   - If `checks.migrations == "unmigrated"` or `"out_of_sync"`: The database is reachable, but Alembic migrations have not been applied up to head (`0007`). Run `docker compose run --rm migrate` (or `cd backend && python -m scripts.db_ops migrate`).
   - If `checks.configuration == "invalid"`: A required runtime setting is invalid. Inspect startup logs.

---

## 2. Structured Logging, Correlation IDs & Secret Redaction

### Request Correlation (`X-Request-ID`)
- `ObservabilityMiddleware` (`backend/app/observability.py`) inspects incoming requests for a valid `X-Request-ID` header (`^[A-Za-z0-9._-]{1,64}$`). If absent or malformed, it generates a 16-character hex correlation ID.
- Every response includes the `X-Request-ID` header, and every log line emitted during that request includes `request_id`.
- When `LOG_JSON=true` (default in `docker-compose.prod.yml`), logs are emitted as single-line JSON objects:
  ```json
  {"timestamp":"2026-10-28T05:12:11.092000+00:00","level":"INFO","logger":"webforge","request_id":"req-custom-trace-001","environment":"production","message":"GET /api/health/live -> 200 (3.43ms)","method":"GET","path":"/api/health/live","status_code":200,"duration_ms":3.43}
  ```

### Automatic Sensitive-Value Redaction
`RedactingFilter` and `redact_sensitive_text()` scrub all log messages, arguments, and formatted exceptions before output:
- Database URLs (`postgresql+psycopg://user:secret@host/db` -> `postgresql+psycopg://user:[REDACTED]@host/db`)
- API keys (`AIza...` -> `[REDACTED_GOOGLE_API_KEY]`, `sk-...` -> `[REDACTED_API_KEY]`)
- JWTs (`eyJ...` -> `[REDACTED_JWT]`) and `Bearer` tokens
- Session cookies (`access_token`, `refresh_token`, `wf_access`, `wf_refresh`)
- Key-value fields matching `password`, `password_hash`, `jwt_secret`, `google_ai_api_key`, `authorization`, `cookie`, or `set-cookie`.

---

## 3. Database Backups, Verification & Restore Procedures

### Creating a Backup
Run the backup wrapper from the repository root (or call `scripts.db_ops` directly):
```bash
make backup
# or:
./scripts/backup_db.sh backups/pre_release.wfbackup.json
```
- **What it produces**:
  1. A portable, deterministic logical backup manifest (`.wfbackup.json`) containing the current `alembic_revisions` (`["0007"]`), per-table row counts, per-table canonical **SHA-256 checksums**, and serialized rows in topological foreign-key order across all 13 WebForge tables.
  2. When connected to PostgreSQL with `pg_dump` installed, it also creates a native custom-format PostgreSQL dump sidecar (`.pgdump` via `pg_dump --format=custom --no-owner --no-acl`).
- **Zero credential leakage**: Database passwords are never printed to stdout or logs.

### Restoring and Verifying a Backup into a Disposable Database
Never restore an untested backup directly over your active production database. Always restore into a separate disposable database first:
```bash
# 1. Create a disposable database on PostgreSQL (or point at a disposable SQLite file)
docker compose exec -T postgres createdb -U webforge webforge_restore_verify

# 2. Restore and verify SHA-256 table checksums
./scripts/restore_db.sh backups/pre_release.wfbackup.json   "postgresql+psycopg://webforge:<password>@127.0.0.1:5432/webforge_restore_verify"
```
Safety guards enforced by `restore_logical_backup` (`backend/scripts/db_ops.py`):
- **Active DB protection**: Refuses (`PermissionError`) to overwrite the active `DATABASE_URL` unless `--allow-same-db` is explicitly passed.
- **Schema compatibility check**: Verifies the backup's `alembic_revisions` match the application's expected Alembic head (`0007`) before inserting data.
- **Cryptographic integrity check**: Recomputes SHA-256 digests across every restored table and fails if any table's row count or digest diverges from the backup manifest.

### Automated Backup/Restore Round-Trip Self-Test
Verify backup and restore tooling at any time using two disposable databases:
```bash
make verify-backup
# Equivalent: cd backend && python -m scripts.db_ops verify-backup-restore
```

### Backup Retention Recommendations
- **Pre-deployment / Pre-migration snapshots**: Retain for at least **30 days**.
- **Daily automated backups**: Retain daily snapshots for **14 days**, weekly snapshots for **8 weeks**, and monthly snapshots for **12 months** in encrypted, access-controlled object storage.
- **Restore drills**: Run `python -m scripts.db_ops verify-backup-restore` in CI on every push and perform a full staging restore drill monthly.

---

## 4. Credential Rotation Runbook

1. **Rotating `JWT_SECRET`**:
   - Generate a new `>= 32`-character random secret: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
   - Update `JWT_SECRET` in the secret manager / `.env` and restart `backend`.
   - If rotating due to suspected compromise, also revoke all refresh tokens:
     `UPDATE refresh_tokens SET revoked = true WHERE revoked = false;`.
2. **Rotating `POSTGRES_PASSWORD`**:
   - Update the role password in PostgreSQL: `ALTER ROLE webforge WITH PASSWORD '<new-strong-password>';`.
   - Update `POSTGRES_PASSWORD` and `DATABASE_URL` in `.env` / secret manager and restart `backend`.
3. **Rotating `GOOGLE_AI_API_KEY`**:
   - Provision a new key in Google AI Studio / Google Cloud Console, update `GOOGLE_AI_API_KEY` on the backend, restart `backend`, and revoke the old key.

---

## 5. Known Verification Limitations in Sandbox Environment

Run `make verify-phase15` (`python3 backend/scripts/verify_phase15.py`) to inspect the exact execution status of every operational check. In the offline verification sandbox:
- **Docker Daemon (`docker` CLI)**: Not installed in the sandbox (`BLOCKED BY ENVIRONMENT`). Dockerfile, `.dockerignore`, Nginx, and Compose configurations are verified via static AST/YAML analysis and tested in CI (`container-build-verify`).
- **Live PostgreSQL Server (`postgres` daemon)**: Not running in the sandbox (`BLOCKED BY ENVIRONMENT`). PostgreSQL integration and concurrency tests (`backend/tests/test_postgres.py`) are configured in CI (`backend-postgres-integration`).
- **Frontend Node Dependencies (`frontend/node_modules`)**: Not installed in the offline sandbox (`BLOCKED BY ENVIRONMENT`). Executed in CI (`frontend-verify`) and locally via `cd frontend && npm ci && npm run typecheck && npm test && npm run build`.
- **Vulnerability Databases (`pip-audit` / `npm audit`)**: Offline sandbox lacks outbound CVE database access (`BLOCKED BY ENVIRONMENT`). Configured in CI (`dependency-audit`).
