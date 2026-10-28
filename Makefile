# Run `make help`. Reads .env automatically for compose; host commands need DATABASE_URL exported (see docs/DATABASE.md).
.PHONY: help test test-pg db up up-prod migrate check-db backup verify-backup down db-reset verify-phase14 verify-phase15 verify-phase16 verify-phase17
help:
	@echo "make test           SQLite test suite (no services needed)"
	@echo "make db             start PostgreSQL in Docker and wait until healthy"
	@echo "make migrate        apply Alembic migrations safely via scripts.db_ops"
	@echo "make check-db       verify database connectivity and Alembic head alignment"
	@echo "make test-pg        test suite against PostgreSQL (needs 'make db' first)"
	@echo "make up             start PostgreSQL + run migrations + start backend"
	@echo "make up-prod        start production Compose stack (postgres + migrate + backend + frontend Nginx)"
	@echo "make backup         create a checksummed logical backup in backups/"
	@echo "make verify-backup  verify backup & restore round-trip on disposable databases"
	@echo "make db-reset       DESTROY the dev database volume (requires CONFIRM=yes)"
	@echo "make verify-phase14 run Phase 14 security & verification suite"
	@echo "make verify-phase15 run Phase 15 infrastructure, DevOps & deployment verification suite"
	@echo "make verify-phase16 run Phase 16 SEO, analytics & performance verification suite"
	@echo "make verify-phase17 run Phase 17 documentation & specification export verification suite"

test:
	cd backend && python -m pytest -q

db:
	docker compose up -d --wait postgres

test-pg:
	docker compose exec -T postgres sh -c 'psql -U $$POSTGRES_USER -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='"'"'webforge_test'"'"'" | grep -q 1 || createdb -U $$POSTGRES_USER webforge_test'
	cd backend && TEST_DATABASE_URL=$$(echo $${DATABASE_URL} | sed 's#/[^/]*$$#/webforge_test#') python -m pytest -q

migrate: db
	docker compose run --rm migrate

check-db:
	cd backend && python -m scripts.db_ops check

up:
	docker compose up --build backend

up-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

backup:
	./scripts/backup_db.sh

verify-backup:
	cd backend && python -m scripts.db_ops verify-backup-restore

down:
	docker compose down

db-reset:
	@test "$(CONFIRM)" = "yes" || (echo "Refusing: this deletes all dev data. Re-run with CONFIRM=yes"; exit 1)
	docker compose down -v

verify-phase14:
	python3 backend/scripts/verify_phase14.py

verify-phase15:
	python3 backend/scripts/verify_phase15.py

verify-phase16:
	python3 backend/scripts/verify_phase16.py

verify-phase17:
	python3 backend/scripts/verify_phase17.py
