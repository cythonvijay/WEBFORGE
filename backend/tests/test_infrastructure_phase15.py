"""Phase 15 Infrastructure, DevOps & Deployment Automated Test Suite."""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.config import Settings, enforce_startup_settings, settings, validate_runtime_settings
from app.db import build_engine, check_database_readiness, wait_for_database
from app.infrastructure_verification import (
    verify_ci_pipeline_artifact,
    verify_container_and_compose_artifacts,
)
from app.observability import (
    RedactingFilter,
    RedactingTextFormatter,
    StructuredJsonFormatter,
    redact_mapping,
    redact_sensitive_text,
)
from scripts.db_ops import (
    create_logical_backup,
    restore_logical_backup,
    run_migrate,
    verify_backup_restore_roundtrip,
)
from tests.test_architecture import _setup_project_with_approved_phase12
from tests.test_strategy_prd import auth


def test_runtime_settings_validation_and_fail_fast_startup():
    dev_cfg = Settings(
        environment="development",
        database_url="sqlite:///./dev.db",
        jwt_secret="dev-secret",
        cors_origins="http://localhost:5173",
        cookie_secure=False,
    )
    assert validate_runtime_settings(dev_cfg) == []
    enforce_startup_settings(dev_cfg)

    bad_env = Settings(
        environment="invalid_env",
        log_level="VERBOSE",
        database_url="sqlite:///./dev.db",
    )
    errs = validate_runtime_settings(bad_env)
    assert any("ENVIRONMENT" in e for e in errs)
    assert any("LOG_LEVEL" in e for e in errs)

    bad_prod = Settings(
        environment="production",
        database_url="postgresql+psycopg://webforge:change-me@db.internal:5432/webforge",
        jwt_secret="change-me",
        cors_origins="http://localhost:5173,*",
        cookie_secure=False,
        google_ai_api_key="change-me",
    )
    prod_errs = validate_runtime_settings(bad_prod)
    assert any("JWT_SECRET" in e for e in prod_errs)
    assert any("DATABASE_URL password" in e for e in prod_errs)
    assert any("wildcard '*'" in e for e in prod_errs)
    assert any("https://" in e for e in prod_errs)
    assert any("COOKIE_SECURE" in e for e in prod_errs)
    assert any("GOOGLE_AI_API_KEY" in e for e in prod_errs)
    with pytest.raises(RuntimeError) as exc_info:
        enforce_startup_settings(bad_prod)
    assert "Invalid runtime configuration" in str(exc_info.value)

    good_prod = Settings(
        environment="production",
        database_url="postgresql+psycopg://webforge:S3cureProdDbPass_987654321@postgres:5432/webforge",
        jwt_secret="prod-super-strong-jwt-signing-key-0123456789abcdef",
        cors_origins="https://app.webforge.example.com",
        cookie_secure=True,
        google_ai_api_key="",
    )
    assert validate_runtime_settings(good_prod) == []
    enforce_startup_settings(good_prod)


def test_observability_logging_redaction_and_correlation_ids(client):
    raw_msg = (
        "Connect failed for postgresql+psycopg://webforge:SuperSecretDbPass123@postgres:5432/webforge "
        "with key " + "AIza" + "SyD1234567890abcdefghijklmnopqrstuvwx" + " and cookie access_token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc12345 "
        "and password='MyPlainPassword99!'"
    )
    redacted = redact_sensitive_text(raw_msg)
    assert "SuperSecretDbPass123" not in redacted
    assert ("AIza" + "SyD1234567890abcdefghijklmnopqrstuvwx") not in redacted
    assert "MyPlainPassword99!" not in redacted
    assert "[REDACTED]" in redacted
    assert "[REDACTED_GOOGLE_API_KEY]" in redacted

    mapped = redact_mapping(
        {
            "user": "alice@example.com",
            "password": "MyPlainPassword99!",
            "database_url": "postgresql+psycopg://webforge:SuperSecretDbPass123@postgres:5432/webforge",
            "nested": {"refresh_token": "tok_secret_value", "safe": "visible"},
        }
    )
    assert mapped["password"] == "[REDACTED]"
    assert "SuperSecretDbPass123" not in mapped["database_url"]
    assert mapped["nested"]["refresh_token"] == "[REDACTED]"
    assert mapped["nested"]["safe"] == "visible"

    record = logging.LogRecord(
        name="webforge",
        level=logging.ERROR,
        pathname=__file__,
        lineno=42,
        msg="Auth error with Bearer secret_token_xyz and password=topsecret",
        args=(),
        exc_info=None,
    )
    RedactingFilter().filter(record)
    json_line = StructuredJsonFormatter().format(record)
    parsed = json.loads(json_line)
    assert parsed["level"] == "ERROR"
    assert "secret_token_xyz" not in json_line
    assert "topsecret" not in json_line

    txt_line = RedactingTextFormatter().format(record)
    assert "secret_token_xyz" not in txt_line
    assert "topsecret" not in txt_line

    r1 = client.get("/api/health/live", headers={"X-Request-ID": "req-custom-trace-001"})
    assert r1.status_code == 200
    assert r1.headers.get("x-request-id") == "req-custom-trace-001"

    r2 = client.get("/api/health/live", headers={"X-Request-ID": "bad id with spaces\r\nSet-Cookie: evil=1"})
    assert r2.status_code == 200
    gen_id = r2.headers.get("x-request-id", "")
    assert gen_id and " " not in gen_id and "evil" not in gen_id


def test_liveness_and_readiness_probes_and_database_unavailable(client):
    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json() == {"status": "ok"}

    r_live = client.get("/api/health/live")
    assert r_live.status_code == 200
    live_body = r_live.json()
    assert live_body["status"] == "ok"
    assert live_body["check"] == "liveness"
    assert "metrics" in live_body
    assert live_body["metrics"]["requests_total"] >= 1

    r_ready = client.get("/api/ready")
    assert r_ready.status_code == 200
    assert r_ready.json() == {"status": "ready"}

    r_hready = client.get("/api/health/ready")
    assert r_hready.status_code == 200
    hr_body = r_hready.json()
    assert hr_body["status"] == "ready"
    assert hr_body["checks"] == {"database": "ok", "migrations": "up_to_date", "configuration": "ok"}
    raw_dump = json.dumps(hr_body)
    assert "sqlite" not in raw_dump and "postgresql" not in raw_dump and settings.jwt_secret not in raw_dump

    with patch(
        "app.main.check_database_readiness",
        return_value={"ready": False, "database": "unavailable", "migrations": "unknown", "reason": "Database connection unavailable."},
    ):
        assert client.get("/api/health/live").status_code == 200
        assert client.get("/api/ready").status_code == 503
        r_deg = client.get("/api/health/ready")
        assert r_deg.status_code == 503
        deg_body = r_deg.json()
        assert deg_body["status"] == "not_ready"
        assert deg_body["checks"]["database"] == "unavailable"

    with tempfile.TemporaryDirectory() as tmp:
        unmig_eng = create_engine(f"sqlite:///{Path(tmp) / 'unmigrated.db'}")
        try:
            st = check_database_readiness(unmig_eng, verify_migrations=True)
            assert st["ready"] is False
            assert st["database"] == "ok"
            assert st["migrations"] == "unmigrated"
        finally:
            if hasattr(unmig_eng, "dispose"):
                unmig_eng.dispose()

        ok_eng = build_engine(f"sqlite:///{Path(tmp) / 'wait.db'}")
        try:
            assert wait_for_database(ok_eng, retries=1, delay_seconds=0.01) is True
        finally:
            if hasattr(ok_eng, "dispose"):
                ok_eng.dispose()


def test_database_operations_migrate_check_and_backup_restore():
    summary = verify_backup_restore_roundtrip()
    assert summary["restore"]["verified"] is True
    assert summary["backup"]["row_counts"]["users"] == 1
    assert summary["backup"]["row_counts"]["projects"] == 1
    assert summary["backup"]["row_counts"]["project_brain_revisions"] == 1
    assert summary["restore"]["restored_row_counts"] == summary["backup"]["row_counts"]
    assert summary["restore"]["restored_checksums"] == summary["backup"]["table_checksums"]

    with tempfile.TemporaryDirectory() as tmp:
        src_url = f"sqlite:///{Path(tmp) / 'src.db'}"
        src_eng = build_engine(src_url)
        assert run_migrate(src_url, target_engine=src_eng) == 0
        b_path = Path(tmp) / "test.wfbackup.json"
        create_logical_backup(b_path, db_url=src_url, target_engine=src_eng)

        with pytest.raises(PermissionError) as perm_err:
            restore_logical_backup(b_path, target_db_url=settings.database_url, allow_same_db=False)
        assert "Refusing to overwrite active DATABASE_URL" in str(perm_err.value)

        tampered = json.loads(b_path.read_text())
        tampered["alembic_revisions"] = ["0001"]
        bad_path = Path(tmp) / "tampered.wfbackup.json"
        bad_path.write_text(json.dumps(tampered))
        with pytest.raises(ValueError) as val_err:
            restore_logical_backup(bad_path, target_db_url=f"sqlite:///{Path(tmp) / 'dst.db'}")
        assert "does not match current application head" in str(val_err.value)


def test_container_compose_nginx_and_ci_configurations():
    assert verify_container_and_compose_artifacts() == []
    assert verify_ci_pipeline_artifact() == []


def test_phase15_stage_completion_guards_and_verification_endpoint(client, monkeypatch):
    h, pid, _ = _setup_project_with_approved_phase12(client, monkeypatch, email="phase15_owner@example.com")

    # Cross-user isolation on /infrastructure-verification returns 404
    with TestClient(client.app) as outsider:
        h_outsider = auth(outsider, "phase15_outsider@example.com")
        assert outsider.get(f"/api/projects/{pid}/infrastructure-verification", headers=h_outsider).status_code == 404

    # 1. Before Architecture, Testing, and Security are approved/completed, Phase 15 readiness is False
    v0 = client.get(f"/api/projects/{pid}/infrastructure-verification", headers=h)
    assert v0.status_code == 200
    v0_data = v0.json()
    assert v0_data["docker_ready"] is False
    assert v0_data["deployment_ready"] is False

    # 2. Generate, submit, and approve Phase 13 Product Architecture
    arch_gen = client.post(f"/api/projects/{pid}/architecture/generate", json={}, headers=h).json()
    arch_hash = arch_gen["current"]["content_hash"]
    client.post(f"/api/projects/{pid}/architecture/versions/1/submit", json={"base_hash": arch_hash}, headers=h)
    arch_app = client.post(
        f"/api/projects/{pid}/architecture/versions/1/approve",
        json={"content_hash": arch_hash, "acknowledge_unverified": True},
        headers=h,
    )
    assert arch_app.status_code == 200

    # Complete frontend, backend, database, api, testing, and security stages
    for st in ("frontend", "backend", "database", "api", "testing", "security"):
        r = client.put(f"/api/projects/{pid}/stages/{st}", json={"status": "complete"}, headers=h)
        assert r.status_code == 200, r.text

    # 3. Attempting to mark `deployment` complete before `docker`, `cicd`, `infrastructure` fails with 409
    r_dep_early = client.put(f"/api/projects/{pid}/stages/deployment", json={"status": "complete"}, headers=h)
    assert r_dep_early.status_code == 409
    assert "infrastructure" in r_dep_early.json()["detail"]

    # 4. Complete Phase 15 stages in dependency order: docker -> cicd -> infrastructure -> deployment -> monitoring
    for st in ("docker", "cicd", "infrastructure", "deployment", "monitoring"):
        v_check = client.get(f"/api/projects/{pid}/infrastructure-verification", headers=h).json()
        assert v_check[f"{st}_ready"] is True, v_check["lifecycle"][st]["blocking_reasons"]
        r_ok = client.put(f"/api/projects/{pid}/stages/{st}", json={"status": "complete"}, headers=h)
        assert r_ok.status_code == 200, r_ok.text

    # 5. Verify all 6 infrastructure checks report passed
    v_final = client.get(f"/api/projects/{pid}/infrastructure-verification", headers=h).json()
    assert all(c["status"] == "passed" for c in v_final["checks"])
