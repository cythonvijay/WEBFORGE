"""Test DB selection: TEST_DATABASE_URL (default: SQLite file). Schema always comes from Alembic migrations."""
import os

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite:///./test.db")
os.environ["JWT_SECRET"] = "webforge-test-secret-for-jwt-signing-32-bytes"
os.environ["GOOGLE_AI_API_KEY"] = ""

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import Base, engine
from app.main import app

IS_PG = engine.dialect.name == "postgresql"


@pytest.fixture(scope="session", autouse=True)
def migrated_schema():
    with engine.begin() as c:  # start from a blank database (test DB only)
        c.execute(text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.drop_all(engine)
    command.upgrade(Config("alembic.ini"), "head")
    yield


@pytest.fixture
def client():
    with engine.begin() as c:  # reset data between tests; FK cascade clears children
        c.execute(text("DELETE FROM users"))
    with TestClient(app) as c:
        yield c
