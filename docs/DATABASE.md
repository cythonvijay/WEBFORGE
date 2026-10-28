# Database

PostgreSQL 16 is the runtime database. SQLite is supported only for the quick local test run. Schema is managed **only** by Alembic: the app never creates or alters tables at startup (an unmigrated database fails loudly).

Configuration: `DATABASE_URL` (required, no default). No host/port is hardcoded in Python.

## SQLite tests (fastest)
    cd backend && pip install -r requirements.txt && python -m pytest -q      # or: make test
PostgreSQL-only tests (`tests/test_postgres.py`) are skipped here. Even on SQLite the schema is built by running the real migrations.

## PostgreSQL development
    cp .env.example .env        # set POSTGRES_PASSWORD, JWT_SECRET; keep DATABASE_URL password in sync
    docker compose up -d --wait postgres      # or: make db
    export DATABASE_URL=postgresql+psycopg://webforge:<password>@127.0.0.1:5432/webforge
    cd backend && alembic upgrade head
Full suite against PostgreSQL (the test database is **wiped** — never point this at real data):
    createdb webforge_test   # once
    TEST_DATABASE_URL=postgresql+psycopg://webforge:<password>@127.0.0.1:5432/webforge_test python -m pytest -q

## Migrations
    alembic upgrade head          # apply all
    alembic current               # expected: 0003 (head)
    alembic history               # <base> -> 0001, initial schema
                                  0001 -> 0002, discovery sessions and questions
                                  0002 -> 0003 (head), research reports
    alembic downgrade <revision>  # e.g. `-1`; destructive, dev only, never part of startup
    alembic revision --autogenerate -m "describe change"   # then REVIEW the generated file
    alembic check                 # fails if models and migrations have drifted
Migrations are never run automatically by the app or by `docker compose up`.

## Docker workflow
    docker compose up -d --wait postgres
    docker compose run --rm backend alembic upgrade head
    docker compose up --build backend          # API on :8000, /api/ready checks the DB
Containers reach the database at host `postgres` (compose overrides `DATABASE_URL`). `make db-reset CONFIRM=yes` deletes the dev volume.

## Design notes
- `JSON().with_variant(JSONB, "postgresql")`: JSONB on PostgreSQL, JSON on SQLite. Same model code, verified lossless round trip.
- IDs are string UUIDs (portable). Timestamps are `timestamptz`; SQLite returns naive values, so comparisons go through `security.as_utc`.
- SQLite foreign keys are switched on per connection so cascades behave like PostgreSQL.
- `ON DELETE CASCADE` on all child tables; deleting a project removes its revisions and stages.

## Troubleshooting
- **PostgreSQL not ready / connection refused:** `docker compose ps` should show `healthy`; use `up --wait`. `/api/ready` returns 503 when the DB is unreachable.
- **Wrong DATABASE_URL / password authentication failed:** `POSTGRES_PASSWORD` only applies when the volume is first created; after changing it run `make db-reset CONFIRM=yes` or `ALTER ROLE`.
- **Port 5432 already in use:** set `POSTGRES_PORT=5433` in `.env` and use that port in your host `DATABASE_URL`.
- **`relation "users" does not exist` / HTTP 500 on register:** migrations not applied; run `alembic upgrade head`.
- **Backend container cannot resolve `postgres`:** you are using a `DATABASE_URL` with another host and bypassing compose's override, or running outside the compose network.
- **`DATABASE_URL` validation error at start:** the variable is required; export it or set it in `.env`.

## Discovery tables (migration 0002)
`discovery_sessions` (one per project, optimistic-lock `version`) and `discovery_questions` (unique `(session_id, fingerprint)` and `(session_id, position)`), both `ON DELETE CASCADE`. Details in docs/DISCOVERY.md. Verified on PostgreSQL: upgrade, `downgrade -1`, upgrade, `alembic check` (no drift).

## Research table (migration 0003)
`research_reports`: one row per report version, `UNIQUE(project_id, version)`, optimistic-lock `row_version`, JSON `content`/`basis`, and two **partial unique indexes** (`uq_research_one_generating`: one generation in flight per project; `uq_research_one_open`: one draft/in_review version per project). Cascade-deleted with the project. Verified on PostgreSQL: upgrade, `downgrade -1`, upgrade, `alembic check` (no drift). Details in docs/RESEARCH.md.


## Phase 10 — Strategy and PRD Tables (`0004_strategy_and_prd`)

- `strategy_documents`: versioned Product Strategy documents per project (`UniqueConstraint("project_id", "version")`), optimistic locking (`row_version`), and partial unique indexes `uq_strategy_one_generating` (`status = 'generating'`) and `uq_strategy_one_open` (`status IN ('draft', 'in_review')`).
- `prd_documents`: versioned PRD documents per project (`UniqueConstraint("project_id", "version")`), optimistic locking (`row_version`), and partial unique indexes `uq_prd_one_generating` (`status = 'generating'`) and `uq_prd_one_open` (`status IN ('draft', 'in_review')`).
- `ProjectBrain` includes `strategy: StrategyBrain` and `prd: PrdBrain` pointer sections written exclusively on version approval (`strategy_approved`, `prd_approved`); `PROTECTED_SECTIONS = {"discovery", "research", "strategy", "prd"}`.


## Phase 11 — UX Artifacts Table (`0005_ux_artifacts`)

- `ux_artifacts`: project-scoped versioned UX documents across `artifact_type` in `('personas', 'journeys', 'ia', 'wireframes', 'ux_review')` (`UniqueConstraint("project_id", "artifact_type", "version")`), optimistic locking (`row_version`), and composite partial unique indexes `uq_ux_one_generating` (`(project_id, artifact_type) WHERE status = 'generating'`) and `uq_ux_one_open` (`(project_id, artifact_type) WHERE status IN ('draft', 'in_review')`).
- `ProjectBrain` includes `ux: UxBrain` (`personas`, `journeys`, `ia`, `wireframes`, `ux_review` `UxArtifactPointer` records) written exclusively on exact-hash version approval (`ux_personas_approved`, `ux_journeys_approved`, `ux_ia_approved`, `ux_wireframes_approved`, `ux_review_approved`); `PROTECTED_SECTIONS = {"discovery", "research", "strategy", "prd", "ux"}`.


## Phase 12 — Design Artifacts Table (`0006_design_artifacts`)

- `design_artifacts`: project-scoped versioned Design documents across `artifact_type` in `('design_system', 'prototype')` (`UniqueConstraint("project_id", "artifact_type", "version")`), optimistic locking (`row_version`), and composite partial unique indexes `uq_design_one_generating` (`(project_id, artifact_type) WHERE status = 'generating'`) and `uq_design_one_open` (`(project_id, artifact_type) WHERE status IN ('draft', 'in_review')`).
- `ProjectBrain` includes `design_spec: DesignBrain` (`design_system`, `prototype` `UxArtifactPointer` records) written exclusively on exact-hash version approval (`design_design_system_approved`, `design_prototype_approved`); `PROTECTED_SECTIONS = {"discovery", "research", "strategy", "prd", "ux", "design_spec"}`.


## Phase 13 — Architecture Documents Table (`0007_architecture_documents`)

- `architecture_documents`: project-scoped versioned Product Architecture specifications (`UniqueConstraint("project_id", "version")`), optimistic locking (`row_version`), and partial unique indexes `uq_arch_one_generating` (`(project_id) WHERE status = 'generating'`) and `uq_arch_one_open` (`(project_id) WHERE status IN ('draft', 'in_review')`).
- `ProjectBrain` includes `architecture_spec: ArchitectureBrain` pointer written exclusively on exact-hash version approval (`architecture_approved`); `PROTECTED_SECTIONS = {"discovery", "research", "strategy", "prd", "ux", "design_spec", "architecture_spec"}`.


## Phase 15 — Safe Database Operations, Readiness & Backup/Restore (`scripts.db_ops`)

- **Supported PostgreSQL Version**: PostgreSQL 16 (`postgres:16-bookworm`).
- **Connection Pooling & Bounded Retries**: `backend/app/db.py` configures `pool_pre_ping=True`, `DB_POOL_SIZE` (default `5`), `DB_MAX_OVERFLOW` (default `10`), `DB_POOL_TIMEOUT` (default `30`), and bounded connection retries (`wait_for_database` using `DB_CONNECT_RETRIES` and `DB_CONNECT_RETRY_DELAY_SECONDS`).
- **Explicit Migration Execution (`python -m scripts.db_ops migrate`)**:
  - Application workers never run migrations concurrently on startup.
  - Migrations run as an explicit step (`make migrate` or the one-shot `migrate` service in `docker-compose.yml`), verifying that `alembic_version` reaches head (`0007`) and stopping deployment on failure without resetting volumes.
- **Readiness vs. Liveness**: `check_database_readiness()` powers `/api/ready` and `/api/health/ready`, distinguishing `database: "unavailable"` from `migrations: "unmigrated"` or `"out_of_sync"`.
- **Verified Logical Backups & Disposable Restore (`python -m scripts.db_ops backup|restore|verify-backup-restore`)**:
  - `./scripts/backup_db.sh` exports all 13 tables in topological foreign-key order with SHA-256 table digests (`.wfbackup.json`) plus a native `.pgdump` sidecar when `pg_dump` is available.
  - `./scripts/restore_db.sh` restores into a separate disposable database, refusing to overwrite the active `DATABASE_URL` unless `--allow-same-db` is passed, and verifies 100% row count and SHA-256 digest fidelity.

## Phase 16 — Optimization Artifacts Table (`0008_phase16_seo_analytics_performance`)

- `optimization_artifacts`: project-scoped versioned optimization specifications across `area` in `('seo', 'analytics', 'performance')` (`UniqueConstraint("project_id", "area", "version")`), optimistic locking (`row_version`), `content` (`JSON/JSONB`), `basis` (`JSON/JSONB`), `content_hash` (`String(64)`), and composite partial unique indexes `uq_optimization_one_generating` (`(project_id, area) WHERE status = 'generating'`) and `uq_optimization_one_open` (`(project_id, area) WHERE status IN ('draft', 'in_review')`).
- `ProjectBrain` includes `optimization_spec: OptimizationBrain` (`seo`, `analytics`, `performance` `UxArtifactPointer` records) written exclusively on exact-hash version approval (`optimization_seo_approved`, `optimization_analytics_approved`, `optimization_performance_approved`); `PROTECTED_SECTIONS = {"discovery", "research", "strategy", "prd", "ux", "design_spec", "architecture_spec", "optimization_spec"}`.
- `scripts/db_ops.py` exports and restores all 14 tables (including `optimization_artifacts`) in foreign-key topological order with SHA-256 verification.

## Phase 17 — `documentation_exports` Table (Migration `0009_phase17_documentation_exports`)
- **Table**: `documentation_exports` (`models.DocumentationExport`)
- **Columns**: `id` (PK), `project_id` (FK `projects.id` ON DELETE CASCADE), `version` (int), `export_mode` (`official` | `preview`), `status` (`completed` | `superseded` | `failed`), `source_snapshot` (JSON/JSONB), `manifest` (JSON/JSONB), `documents` (JSON/JSONB), `validation_summary` (JSON/JSONB), `manifest_sha256` (`String(64)`), `bundle_sha256` (`String(64)`), `created_by` (FK `users.id` ON DELETE SET NULL), `export_note` (`Text`), `brain_revision` (int), `row_version` (int), `created_at`, `updated_at`.
- **Constraints & Indexes**:
  - `uq_documentation_export_project_version`: `UNIQUE (project_id, version)`
  - `uq_documentation_official_current`: Partial unique index on `(project_id)` where `export_mode = 'official' AND status = 'completed'`, guaranteeing at most one active official export per project.
- **Backup & Restore Coverage**: Registered in `ORDERED_MODELS` in `backend/scripts/db_ops.py` (15 tables total). Note that Phase 17 project documentation exports are user-facing specification bundles and are completely separate from Phase 15 operator database backups (`.wfbackup.json` / `.pgdump`).
