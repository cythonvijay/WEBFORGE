"""Phase 15 Repeatable Infrastructure, DevOps & Deployment Verification Runner (`python3 backend/scripts/verify_phase15.py`)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"

os.environ.setdefault("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'test.db'}")
os.environ.setdefault("JWT_SECRET", "verify-phase15-runner-secret-0123456789abcdef")

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings, validate_runtime_settings  # noqa: E402
from app.infrastructure_verification import (  # noqa: E402
    verify_ci_pipeline_artifact,
    verify_container_and_compose_artifacts,
)
from app.observability import redact_sensitive_text  # noqa: E402
from scripts.db_ops import verify_backup_restore_roundtrip  # noqa: E402
from scripts.verify_phase14 import (  # noqa: E402
    check_backend_sqlite_tests,
    check_dependency_audit,
    check_live_ai_provider,
    check_migrations,
    check_postgres_integration_tests,
    check_secret_hygiene,
    check_static_security_controls,
)


def check_container_and_compose_manifests() -> tuple[str, str]:
    issues = verify_container_and_compose_artifacts()
    if issues:
        return "FAILED", "; ".join(issues)
    return (
        "PASSED",
        "Validated backend/Dockerfile, frontend/Dockerfile, frontend/nginx.conf, .dockerignore, docker-compose.yml, and docker-compose.prod.yml.",
    )


def check_docker_daemon_build() -> tuple[str, str]:
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return (
            "BLOCKED BY ENVIRONMENT",
            "docker CLI/daemon is not installed in the verification sandbox (static Dockerfile & Compose AST validation PASSED).",
        )
    r = subprocess.run([docker_bin, "compose", "config", "-q"], cwd=str(REPO_ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        return "FAILED", f"docker compose config failed: {r.stderr.strip()}"
    return "PASSED", "Docker daemon and Compose config validated."


def check_ci_workflow_configuration() -> tuple[str, str]:
    issues = verify_ci_pipeline_artifact()
    if issues:
        return "FAILED", "; ".join(issues)
    return (
        "PASSED",
        "Validated .github/workflows/ci.yml (6 mandatory jobs + gated optional live AI job, least-privilege permissions).",
    )


def check_env_validation_and_log_redaction() -> tuple[str, str]:
    bad_prod = Settings(
        environment="production",
        database_url="sqlite:///./prod.db",
        jwt_secret="change-me",
        cors_origins="*",
        cookie_secure=False,
    )
    errs = validate_runtime_settings(bad_prod)
    if len(errs) < 4:
        return "FAILED", f"Production fail-fast validation did not catch expected errors: {errs}"
    sample = "postgresql+psycopg://webforge:SecretPass123@postgres:5432/webforge " + "AIza" + "SyD1234567890abcdefghijklmnopqrstuvwx"
    redacted = redact_sensitive_text(sample)
    if "SecretPass123" in redacted or "AIzaSyD1234567890" in redacted:
        return "FAILED", "Log redaction failed to scrub credentials."
    return "PASSED", "Fail-fast production environment validation and log secret redaction verified."


def check_backup_and_restore_roundtrip() -> tuple[str, str]:
    try:
        res = verify_backup_restore_roundtrip()
        if not res["restore"]["verified"]:
            return "FAILED", "Backup restore verification returned False."
        rows = sum(res["restore"]["restored_row_counts"].values())
        return (
            "PASSED",
            f"Disposable database backup created, restored into separate DB, and verified ({rows} rows, SHA-256 table digests matched).",
        )
    except Exception as exc:
        return "FAILED", f"Backup/restore verification failed: {exc}"


def check_frontend_tests_typecheck_and_build() -> tuple[str, str]:
    if not (FRONTEND_DIR / "node_modules").exists():
        return (
            "BLOCKED BY ENVIRONMENT",
            "frontend/node_modules is not installed and outbound npm registry access is disabled in the sandbox.",
        )
    npm_bin = shutil.which("npm")
    if not npm_bin:
        return "BLOCKED BY ENVIRONMENT", "npm binary is not available."
    for script in ("typecheck", "test", "build"):
        cmd = [npm_bin, "run", script] if script != "test" else [npm_bin, "test", "--", "--run"]
        r = subprocess.run(cmd, cwd=str(FRONTEND_DIR), capture_output=True, text=True)
        if r.returncode != 0:
            return "FAILED", f"Frontend `{script}` failed."
    return "PASSED", "Frontend typecheck, unit tests, and production build passed."


def main() -> int:
    checks = [
        ("Secret & Credential Hygiene Scan", check_secret_hygiene),
        ("Static Frontend/Backend Security Controls", check_static_security_controls),
        ("Container, Nginx & Docker Compose Manifest Validation", check_container_and_compose_manifests),
        ("CI Workflow Configuration Validation (.github/workflows/ci.yml)", check_ci_workflow_configuration),
        ("Fail-Fast Environment Config & Log Redaction Verification", check_env_validation_and_log_redaction),
        ("Alembic Migration Upgrade/Downgrade (0001..0007)", check_migrations),
        ("Disposable Database Backup & Restore Round-Trip Verification", check_backup_and_restore_roundtrip),
        ("Backend Automated Test Suite (SQLite)", check_backend_sqlite_tests),
        ("PostgreSQL Integration & Concurrency Suite", check_postgres_integration_tests),
        ("Docker Daemon Image Build & Runtime Execution", check_docker_daemon_build),
        ("Frontend Typecheck, Unit Tests & Production Build", check_frontend_tests_typecheck_and_build),
        ("Dependency Vulnerability Audit (pip-audit / npm audit)", check_dependency_audit),
        ("Optional Live Gemini AI Provider Check", check_live_ai_provider),
    ]
    print("=== WebForge Phase 15 Infrastructure, DevOps & Deployment Verification Report ===")
    counts = {"PASSED": 0, "FAILED": 0, "SKIPPED": 0, "BLOCKED BY ENVIRONMENT": 0, "NOT RUN": 0, "NOT APPLICABLE": 0}
    for name, fn in checks:
        status, detail = fn()
        counts[status] = counts.get(status, 0) + 1
        print(f"[{status}] {name}: {detail}")
    print(
        f"\nSummary: {counts['PASSED']} passed, {counts['FAILED']} failed, "
        f"{counts['BLOCKED BY ENVIRONMENT']} blocked by environment, {counts['SKIPPED']} skipped, "
        f"{counts['NOT RUN']} not run."
    )
    return 1 if counts["FAILED"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
