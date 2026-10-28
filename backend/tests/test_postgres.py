"""PostgreSQL-specific regression tests. Skipped unless TEST_DATABASE_URL points at PostgreSQL."""
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, engine
from app.models import BrainRevision
from conftest import IS_PG

pytestmark = pytest.mark.skipif(not IS_PG, reason="requires PostgreSQL")
C = {"email": "pg@example.com", "password": "password123"}


@pytest.fixture
def authed(client):
    client.post("/api/auth/register", json=C)
    return client


def test_schema_comes_from_migration_head():
    with engine.connect() as c:
        head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar() == head
    insp = inspect(engine)
    assert {"users", "projects", "refresh_tokens", "project_brain_revisions", "project_stages", "discovery_sessions", "discovery_questions", "research_reports", "strategy_documents", "prd_documents", "ux_artifacts", "design_artifacts", "architecture_documents", "optimization_artifacts", "documentation_exports"} <= set(insp.get_table_names())
    cols = {c["name"]: c["type"].__class__.__name__ for c in insp.get_columns("project_brain_revisions")}
    assert cols["snapshot"] == "JSONB" and cols["patch"] == "JSONB"


def test_json_round_trip_is_lossless(authed):
    pid = authed.post("/api/projects", json={"name": "J"}).json()["id"]
    value = [{"text": "கடை ☕ 日本語", "nested": {"a": [1, 2.5, None, True], "big": 2**53}, "empty": {}, "quote": 'say "hi"\n'}]
    authed.put(f"/api/projects/{pid}/brain/requirements", json={"value": value})
    assert authed.get(f"/api/projects/{pid}/brain").json()["brain"]["requirements"] == value
    with SessionLocal() as db:
        rev = db.query(BrainRevision).filter_by(project_id=pid, version=2).one()
        assert rev.patch == {"requirements": value}


def test_unique_revision_version_enforced():
    with SessionLocal() as db:
        db.execute(text("INSERT INTO users (id,email,password_hash,created_at) VALUES ('u','u@x.io','h',now())"))
        db.execute(text("INSERT INTO projects (id,owner_id,name,description,status,created_at,updated_at) VALUES ('p','u','n','','active',now(),now())"))
        ins = "INSERT INTO project_brain_revisions (id,project_id,version,change_type,patch,snapshot,created_by,created_at) VALUES (:i,'p',1,'t','{}','{}','u',now())"
        db.execute(text(ins), {"i": "r1"})
        with pytest.raises(IntegrityError):
            db.execute(text(ins), {"i": "r2"})
        db.rollback()


def test_foreign_keys_enforced_and_cascade(authed):
    pid = authed.post("/api/projects", json={"name": "C"}).json()["id"]
    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(text("INSERT INTO project_stages (id,project_id,stage,status) VALUES ('x','missing','research','not_started')"))
        db.rollback()
    authed.delete(f"/api/projects/{pid}")
    with SessionLocal() as db:
        for t in ("project_stages", "project_brain_revisions"):
            assert db.execute(text(f"SELECT count(*) FROM {t} WHERE project_id=:p"), {"p": pid}).scalar() == 0


def test_failed_intake_leaves_no_partial_state(authed):
    pid = authed.post("/api/projects", json={"name": "T"}).json()["id"]
    assert authed.post(f"/api/projects/{pid}/intake", json={"idea": "A marketplace for photographers"}).status_code == 503
    with SessionLocal() as db:
        assert db.query(BrainRevision).filter_by(project_id=pid).count() == 1


def test_refresh_tokens_revoked_in_database(authed):
    authed.post("/api/auth/refresh")
    with SessionLocal() as db:
        revoked = db.execute(text("SELECT count(*) FROM refresh_tokens WHERE revoked")).scalar()
        total = db.execute(text("SELECT count(*) FROM refresh_tokens")).scalar()
    assert (revoked, total) == (1, 2)


def test_models_match_migrations():
    command.check(Config("alembic.ini"))  # raises if the models and migrations have drifted
