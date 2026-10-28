from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings
from .observability import logger

_BACKEND_DIR = Path(__file__).resolve().parents[1]


def build_engine(db_url: str | None = None):
    url = db_url or settings.database_url
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if not url.startswith("sqlite"):
        kwargs.update(
            {
                "pool_size": settings.db_pool_size,
                "max_overflow": settings.db_max_overflow,
                "pool_timeout": settings.db_pool_timeout,
            }
        )
    eng = create_engine(url, **kwargs)
    if eng.dialect.name == "sqlite":  # SQLite ignores foreign keys unless enabled; PostgreSQL always enforces them
        @event.listens_for(eng, "connect")
        def _sqlite_fk(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return eng


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def expected_alembic_heads() -> list[str]:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    if hasattr(cfg, "set_main_option"):
        cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    if hasattr(script, "get_heads"):
        return list(script.get_heads())
    head = script.get_current_head()
    return [head] if head else []


def check_database_readiness(target_engine=None, verify_migrations: bool = True) -> dict[str, Any]:
    """Check database connectivity and Alembic migration head state without leaking credentials or internal details."""
    eng = target_engine or engine
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
            if not verify_migrations:
                return {"ready": True, "database": "ok", "migrations": "skipped"}
            try:
                rows = [r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()]
            except Exception:
                return {
                    "ready": False,
                    "database": "ok",
                    "migrations": "unmigrated",
                    "reason": "Database schema is not initialized (alembic_version table missing).",
                }
            heads = expected_alembic_heads()
            if not rows or sorted(rows) != sorted(heads):
                return {
                    "ready": False,
                    "database": "ok",
                    "migrations": "out_of_sync",
                    "current_revisions": rows,
                    "expected_heads": heads,
                    "reason": "Database migration revision does not match application head.",
                }
            return {
                "ready": True,
                "database": "ok",
                "migrations": "up_to_date",
                "revision": rows[0] if len(rows) == 1 else rows,
            }
    except Exception as exc:
        logger.warning(f"Database readiness check failed: {type(exc).__name__}")
        return {
            "ready": False,
            "database": "unavailable",
            "migrations": "unknown",
            "reason": "Database connection unavailable.",
        }


def wait_for_database(
    target_engine=None,
    retries: int | None = None,
    delay_seconds: float | None = None,
) -> bool:
    """Bounded retry loop waiting for the database to accept connections."""
    eng = target_engine or engine
    max_retries = settings.db_connect_retries if retries is None else max(0, retries)
    delay = settings.db_connect_retry_delay_seconds if delay_seconds is None else max(0.0, delay_seconds)
    attempts = max_retries + 1
    for attempt in range(1, attempts + 1):
        try:
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning(f"Database connection attempt {attempt}/{attempts} failed ({type(exc).__name__})")
            if attempt < attempts and delay > 0:
                time.sleep(delay)
    return False
