"""Phase 15 Database Operations, Safe Migrations, and Verified Backup/Restore CLI (`python -m scripts.db_ops`)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

import app.db as app_db
from app import models
from app.config import settings
from app.db import build_engine, check_database_readiness, expected_alembic_heads, wait_for_database
from app.observability import logger, redact_sensitive_text

ORDERED_MODELS = [
    (m.__tablename__, m)
    for m in (
        models.User,
        models.RefreshToken,
        models.Project,
        models.BrainRevision,
        models.ProjectStage,
        models.DiscoverySession,
        models.DiscoveryQuestion,
        models.ResearchReport,
        models.StrategyDocument,
        models.PrdDocument,
        models.UxArtifact,
        models.DesignArtifact,
        models.ArchitectureDocument,
        models.OptimizationArtifact,
        models.DocumentationExport,
    )
]


def _alembic_cfg(db_url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    if hasattr(cfg, "set_main_option"):
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    if db_url:
        os.environ["DATABASE_URL"] = db_url
    return cfg


def _dispose_engine(eng) -> None:
    if hasattr(eng, "dispose"):
        eng.dispose()


def _model_columns(model_cls) -> list[str]:
    if hasattr(model_cls, "__table__"):
        return [c.name for c in model_cls.__table__.columns]
    return list(getattr(model_cls, "__columns__", {}).keys())


def _serialize_val(v: Any) -> Any:
    if isinstance(v, datetime):
        dt = v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)
        return {"__wf_datetime__": dt.isoformat()}
    if isinstance(v, date):
        return {"__wf_date__": v.isoformat()}
    return v


def _deserialize_val(v: Any) -> Any:
    if isinstance(v, dict):
        if "__wf_datetime__" in v and len(v) == 1:
            return datetime.fromisoformat(v["__wf_datetime__"])
        if "__wf_date__" in v and len(v) == 1:
            return date.fromisoformat(v["__wf_date__"])
    return v


def _table_rows_digest(rows: list[dict[str, Any]]) -> str:
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=_serialize_val)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_migrate(db_url: str | None = None, target_engine=None) -> int:
    url = db_url or settings.database_url
    eng = target_engine or build_engine(url)
    if not wait_for_database(eng):
        logger.error("Migration aborted: database did not become reachable within bounded retry window.")
        return 1
    prev_url = os.environ.get("DATABASE_URL")
    old_settings_url = settings.database_url
    old_engine = app_db.engine
    migration_lock_conn = None
    migration_lock_id = 0x574542464F524745  # Stable PostgreSQL advisory lock key: "WEBFORGE".
    migration_lock_acquired = False
    try:
        settings.database_url = url
        app_db.engine = eng

        # Multiple Render services may share one PostgreSQL database. Hold a
        # session-level advisory lock while Alembic uses its own connection so
        # their startup migrations cannot run concurrently.
        if eng.dialect.name == "postgresql":
            migration_lock_conn = eng.connect()
            migration_lock_conn.execute(
                text("SELECT pg_advisory_lock(:lock_id)"),
                {"lock_id": migration_lock_id},
            )
            migration_lock_conn.commit()
            migration_lock_acquired = True

        cfg = _alembic_cfg(url)
        command.upgrade(cfg, "head")
        status = check_database_readiness(eng, verify_migrations=True)
        if not status["ready"]:
            logger.error(f"Migration verification failed: {status.get('reason')}")
            return 1
        logger.info(f"Database migrated cleanly to head revision {status.get('revision')}.")
        return 0
    except Exception as exc:
        logger.error(f"Database migration failed ({type(exc).__name__}): {redact_sensitive_text(str(exc))}")
        return 1
    finally:
        if migration_lock_conn is not None:
            try:
                if migration_lock_acquired:
                    migration_lock_conn.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": migration_lock_id},
                    )
                    migration_lock_conn.commit()
            except Exception as lock_exc:
                logger.warning(f"Could not explicitly release migration advisory lock ({type(lock_exc).__name__}); closing the connection will release it.")
            finally:
                migration_lock_conn.close()
        app_db.engine = old_engine
        settings.database_url = old_settings_url
        if prev_url is not None:
            os.environ["DATABASE_URL"] = prev_url
        if target_engine is None:
            _dispose_engine(eng)


def create_logical_backup(output_path: Path, db_url: str | None = None, target_engine=None) -> dict[str, Any]:
    """Export a deterministic, checksummed logical backup of the database without logging credentials."""
    url = db_url or settings.database_url
    eng = target_engine or build_engine(url)
    try:
        readiness = check_database_readiness(eng, verify_migrations=True)
        if not readiness["ready"]:
            raise RuntimeError(f"Cannot back up an unready or unmigrated database: {readiness.get('reason')}")

        tables_payload: dict[str, list[dict[str, Any]]] = {}
        table_checksums: dict[str, str] = {}
        row_counts: dict[str, int] = {}

        with eng.connect() as conn:
            rev_rows = [r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()]

        SessionMaker = sessionmaker(bind=eng, expire_on_commit=False)
        with SessionMaker() as db:
            for tbl_name, model_cls in ORDERED_MODELS:
                cols = _model_columns(model_cls)
                stmt = select(model_cls).order_by(getattr(model_cls, "id").asc())
                objs = list(db.scalars(stmt))
                serialized_rows = [
                    {c: _serialize_val(getattr(obj, c)) for c in cols}
                    for obj in objs
                ]
                tables_payload[tbl_name] = serialized_rows
                row_counts[tbl_name] = len(serialized_rows)
                table_checksums[tbl_name] = _table_rows_digest(serialized_rows)

        pg_dump_status = "not_applicable"
        if eng.dialect.name == "postgresql":
            pg_dump_bin = shutil.which("pg_dump")
            if pg_dump_bin:
                pg_dump_out = output_path.with_suffix(".pgdump")
                p = urlsplit(url.replace("postgresql+psycopg://", "postgresql://"))
                pg_env = {**os.environ}
                if p.password:
                    pg_env["PGPASSWORD"] = p.password
                cmd = [
                    pg_dump_bin,
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "-h",
                    p.hostname or "127.0.0.1",
                    "-p",
                    str(p.port or 5432),
                    "-U",
                    p.username or "webforge",
                    "-f",
                    str(pg_dump_out),
                    (p.path or "/webforge").lstrip("/"),
                ]
                res = subprocess.run(cmd, env=pg_env, capture_output=True, text=True)
                pg_dump_status = "created" if res.returncode == 0 else "failed"
            else:
                pg_dump_status = "pg_dump_binary_unavailable_used_logical_snapshot"

        manifest = {
            "format": "webforge-logical-backup-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dialect": eng.dialect.name,
            "alembic_revisions": rev_rows,
            "pg_dump_sidecar": pg_dump_status,
            "row_counts": row_counts,
            "table_checksums": table_checksums,
            "tables": tables_payload,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        output_path.write_bytes(raw_bytes)
        logger.info(
            f"Backup written to {output_path.name} ({len(raw_bytes)} bytes, total rows={sum(row_counts.values())})."
        )
        return {
            "output_path": str(output_path),
            "bytes": len(raw_bytes),
            "alembic_revisions": rev_rows,
            "row_counts": row_counts,
            "table_checksums": table_checksums,
            "pg_dump_sidecar": pg_dump_status,
        }
    finally:
        if target_engine is None:
            _dispose_engine(eng)


def restore_logical_backup(
    input_path: Path,
    target_db_url: str,
    allow_same_db: bool = False,
    target_engine=None,
) -> dict[str, Any]:
    """Restore a WebForge logical backup into a disposable target database and verify checksums."""
    if not input_path.exists():
        raise FileNotFoundError(f"Backup file not found: {input_path}")
    if not target_db_url or not target_db_url.strip():
        raise ValueError("A disposable target database URL (--target-url) is required for restore.")
    if not allow_same_db and target_db_url.strip() == settings.database_url.strip():
        raise PermissionError(
            "Refusing to overwrite active DATABASE_URL during restore without explicit --allow-same-db flag. "
            "Always restore into a separate disposable database first."
        )

    manifest = json.loads(input_path.read_text(encoding="utf-8"))
    if manifest.get("format") != "webforge-logical-backup-v1":
        raise ValueError(f"Unsupported backup format: {manifest.get('format')!r}")

    expected_heads = expected_alembic_heads()
    backup_revs = manifest.get("alembic_revisions") or []
    if sorted(backup_revs) != sorted(expected_heads):
        raise ValueError(
            f"Backup Alembic revision {backup_revs} does not match current application head {expected_heads}."
        )

    eng = target_engine or build_engine(target_db_url)
    try:
        rc = run_migrate(target_db_url, target_engine=eng)
        if rc != 0:
            raise RuntimeError("Failed to apply Alembic migrations to target restore database.")

        with eng.begin() as conn:
            for tbl_name, _ in reversed(ORDERED_MODELS):
                conn.execute(text(f"DELETE FROM {tbl_name}"))

        SessionMaker = sessionmaker(bind=eng, expire_on_commit=False)
        with SessionMaker() as db:
            for tbl_name, model_cls in ORDERED_MODELS:
                raw_rows = manifest["tables"].get(tbl_name, [])
                for row in raw_rows:
                    deserialized = {k: _deserialize_val(v) for k, v in row.items()}
                    db.add(model_cls(**deserialized))
                # Models do not declare ORM relationships for every FK, so force
                # parent tables to be inserted before dependent rows.
                db.flush()
            db.commit()

        restored_counts: dict[str, int] = {}
        restored_checksums: dict[str, str] = {}
        mismatches: list[str] = []

        with SessionMaker() as db:
            for tbl_name, model_cls in ORDERED_MODELS:
                cols = _model_columns(model_cls)
                stmt = select(model_cls).order_by(getattr(model_cls, "id").asc())
                objs = list(db.scalars(stmt))
                serialized_rows = [
                    {c: _serialize_val(getattr(obj, c)) for c in cols}
                    for obj in objs
                ]
                restored_counts[tbl_name] = len(serialized_rows)
                restored_checksums[tbl_name] = _table_rows_digest(serialized_rows)
                expected_sum = manifest["table_checksums"].get(tbl_name)
                if expected_sum and restored_checksums[tbl_name] != expected_sum:
                    mismatches.append(f"Checksum mismatch on table '{tbl_name}'")

        if mismatches:
            raise RuntimeError("Backup restore verification failed: " + "; ".join(mismatches))

        logger.info(
            f"Backup restored and verified cleanly ({sum(restored_counts.values())} rows across {len(ORDERED_MODELS)} tables)."
        )
        return {
            "verified": True,
            "restored_row_counts": restored_counts,
            "restored_checksums": restored_checksums,
        }
    finally:
        if target_engine is None:
            _dispose_engine(eng)


def verify_backup_restore_roundtrip() -> dict[str, Any]:
    """Create a populated disposable database, back it up, restore into a second disposable database, and verify."""
    with tempfile.TemporaryDirectory() as tmp:
        src_url = f"sqlite:///{Path(tmp) / 'source.db'}"
        dst_url = f"sqlite:///{Path(tmp) / 'restored.db'}"
        backup_file = Path(tmp) / "sample.wfbackup.json"

        src_eng = build_engine(src_url)
        dst_eng = build_engine(dst_url)
        try:
            if run_migrate(src_url, target_engine=src_eng) != 0:
                raise RuntimeError("Failed to migrate disposable source database.")

            now = datetime.now(timezone.utc)
            SessionMaker = sessionmaker(bind=src_eng, expire_on_commit=False)
            with SessionMaker() as db:
                db.add(
                    models.User(
                        id="u-backup-1",
                        email="ops@webforge.local",
                        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
                        created_at=now,
                    )
                )
                db.flush()  # Persist the referenced owner before inserting the project.
                db.add(
                    models.Project(
                        id="p-backup-1",
                        owner_id="u-backup-1",
                        name="Backup Verification Project",
                        description="Disposable round-trip backup verification",
                        status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
                db.flush()  # Persist the project before inserting its revisions and stages.
                db.add(
                    models.BrainRevision(
                        id="br-backup-1",
                        project_id="p-backup-1",
                        version=1,
                        change_type="created",
                        patch={},
                        snapshot={"idea": {"raw": "Backup test"}},
                        created_by="u-backup-1",
                        created_at=now,
                    )
                )
                db.add(
                    models.ProjectStage(
                        id="ps-backup-1",
                        project_id="p-backup-1",
                        stage="research",
                        status="complete",
                    )
                )
                db.commit()

            b_info = create_logical_backup(backup_file, db_url=src_url, target_engine=src_eng)
            r_info = restore_logical_backup(backup_file, target_db_url=dst_url, target_engine=dst_eng)
            return {
                "backup": b_info,
                "restore": r_info,
            }
        finally:
            _dispose_engine(src_eng)
            _dispose_engine(dst_eng)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WebForge Database Operations CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("wait", help="Wait for database connectivity with bounded retries")
    sub.add_parser("check", help="Check database connectivity and Alembic head alignment")
    sub.add_parser("migrate", help="Apply Alembic migrations safely and verify head")

    p_backup = sub.add_parser("backup", help="Create a verified logical database backup")
    p_backup.add_argument("--output", required=True, help="Output backup file path (.wfbackup.json)")
    p_backup.add_argument("--db-url", default=None, help="Optional database URL override")

    p_restore = sub.add_parser("restore", help="Restore a logical backup into a disposable database")
    p_restore.add_argument("--input", required=True, help="Input backup file path (.wfbackup.json)")
    p_restore.add_argument("--target-url", required=True, help="Target disposable database URL")
    p_restore.add_argument("--allow-same-db", action="store_true", help="Explicitly allow restoring into active DATABASE_URL")

    sub.add_parser("verify-backup-restore", help="Run disposable database backup & restore verification round-trip")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "wait":
            ok = wait_for_database()
            return 0 if ok else 1
        if args.cmd == "check":
            res = check_database_readiness(verify_migrations=True)
            print(json.dumps(res))
            return 0 if res["ready"] else 1
        if args.cmd == "migrate":
            return run_migrate()
        if args.cmd == "backup":
            info = create_logical_backup(Path(args.output), db_url=args.db_url)
            print(json.dumps(info))
            return 0
        if args.cmd == "restore":
            info = restore_logical_backup(
                Path(args.input),
                target_db_url=args.target_url,
                allow_same_db=args.allow_same_db,
            )
            print(json.dumps(info))
            return 0
        if args.cmd == "verify-backup-restore":
            info = verify_backup_restore_roundtrip()
            print(json.dumps(info))
            return 0
    except Exception as exc:
        logger.error(f"db_ops '{args.cmd}' failed: {redact_sensitive_text(str(exc))}")
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
