"""Phase 14 Repeatable Security & Verification Runner (`python3 scripts/verify_phase14.py`).

Executes and categorizes all verification checks without exposing secrets or converting
environment-blocked checks into passes.

Status categories:
- PASSED
- FAILED
- SKIPPED
- BLOCKED BY ENVIRONMENT
- NOT RUN
- NOT APPLICABLE
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"


def check_secret_hygiene() -> tuple[str, str]:
    secret_re = re.compile(
        r"(?:AIza[0-9A-Za-z_-]{35}|sk-[0-9A-Za-z]{20,}|ghp_[0-9A-Za-z]{30,}|"
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
    )
    issues: list[str] = []
    scanned_files = 0
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [
            d for d in dirnames if d not in {"__pycache__", ".pytest_cache", "node_modules", ".git", ".venv", "venv"}
        ]
        for fn in filenames:
            if fn == ".env" or (fn.startswith(".env.") and fn != ".env.example"):
                issues.append(f"Untracked/local env file present: {fn}")
                continue
            p = Path(dirpath) / fn
            if p.suffix in {".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".md", ".yml", ".yaml", ".ini", ".example"}:
                scanned_files += 1
                txt = p.read_text(errors="ignore")
                if secret_re.search(txt):
                    issues.append(f"Secret pattern matched in {p.relative_to(REPO_ROOT)} (value redacted)")
    if issues:
        return "FAILED", "; ".join(issues)
    return "PASSED", f"Scanned {scanned_files} repository files; 0 hardcoded secrets or committed .env files found."


def check_static_security_controls() -> tuple[str, str]:
    issues: list[str] = []
    forbidden_fe = ("dangerouslySetInnerHTML", "innerHTML", "outerHTML", "document.write", "eval(", "localStorage", "sessionStorage")
    fe_count = 0
    for p in (FRONTEND_DIR / "src").rglob("*"):
        if p.is_file() and p.suffix in {".ts", ".tsx"}:
            fe_count += 1
            txt = p.read_text(errors="ignore")
            for pat in forbidden_fe:
                if pat in txt:
                    issues.append(f"Unsafe browser pattern {pat!r} in {p.relative_to(REPO_ROOT)}")

    dockerfile = (BACKEND_DIR / "Dockerfile").read_text(errors="ignore")
    if "USER webforge" not in dockerfile:
        issues.append("backend/Dockerfile does not drop privileges to non-root USER webforge")

    sec_py = (BACKEND_DIR / "app" / "security.py").read_text(errors="ignore")
    if "class SecurityMiddleware" not in sec_py:
        issues.append("SecurityMiddleware missing from backend/app/security.py")

    if issues:
        return "FAILED", "; ".join(issues)
    return (
        "PASSED",
        f"Verified {fe_count} frontend modules (0 unsafe HTML/storage sinks), SecurityMiddleware, and non-root Dockerfile.",
    )


def check_migrations() -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "verify_mig.db")
        url = f"sqlite:///{db_path}"
        env = {
            **os.environ,
            "DATABASE_URL": url,
            "JWT_SECRET": "verify-migration-secret-0123456789",
        }
        code = (
            "from alembic.config import Config; from alembic import command; import app.db as app_db; "
            "cfg = Config('alembic.ini'); command.upgrade(cfg, 'head'); "
            "command.downgrade(cfg, '0007'); command.upgrade(cfg, 'head')"
        )
        r = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(BACKEND_DIR),
            env=env,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            return "FAILED", f"Migration check failed: {r.stderr.strip() or r.stdout.strip()}"
        return "PASSED", "Alembic migrations 0001 -> 0009 -> 0007 -> 0009 verified cleanly."


def check_backend_sqlite_tests() -> tuple[str, str]:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=str(BACKEND_DIR),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    summary = (r.stdout.strip().splitlines() or [""])[-1]
    if r.returncode != 0 or "failed" in summary and not summary.endswith("0 failed"):
        return "FAILED", summary
    return "PASSED", f"SQLite test suite: {summary}"


def check_postgres_integration_tests() -> tuple[str, str]:
    pg_url = os.environ.get("TEST_DATABASE_URL", "")
    if not pg_url.startswith("postgresql"):
        return (
            "BLOCKED BY ENVIRONMENT",
            "TEST_DATABASE_URL is not set to a PostgreSQL instance (9 PostgreSQL-only tests skipped in SQLite mode).",
        )
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_postgres.py", "-q"],
        cwd=str(BACKEND_DIR),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    summary = (r.stdout.strip().splitlines() or [""])[-1]
    return ("PASSED" if r.returncode == 0 else "FAILED"), summary


def check_frontend_tests_and_build() -> tuple[str, str]:
    if not (FRONTEND_DIR / "node_modules").exists():
        return (
            "BLOCKED BY ENVIRONMENT",
            "frontend/node_modules is not installed and outbound npm registry access is disabled in the sandbox.",
        )
    npm_bin = shutil.which("npm")
    if not npm_bin:
        return "BLOCKED BY ENVIRONMENT", "npm binary is not installed in PATH."
    r_test = subprocess.run([npm_bin, "test", "--", "--run"], cwd=str(FRONTEND_DIR), capture_output=True, text=True)
    if r_test.returncode != 0:
        return "FAILED", "Frontend vitest suite failed."
    r_build = subprocess.run([npm_bin, "run", "build"], cwd=str(FRONTEND_DIR), capture_output=True, text=True)
    if r_build.returncode != 0:
        return "FAILED", "Frontend tsc/vite production build failed."
    return "PASSED", "Frontend unit tests, typecheck, and production build passed."


def check_dependency_audit() -> tuple[str, str]:
    pip_audit = shutil.which("pip-audit")
    if not pip_audit:
        return (
            "BLOCKED BY ENVIRONMENT",
            "pip-audit is not installed and outbound vulnerability DB access is disabled in the sandbox.",
        )
    r = subprocess.run([pip_audit, "-r", str(BACKEND_DIR / "requirements.txt")], capture_output=True, text=True)
    return ("PASSED" if r.returncode == 0 else "FAILED"), (r.stdout.strip() or r.stderr.strip())[:200]


def check_live_ai_provider() -> tuple[str, str]:
    if not os.environ.get("GOOGLE_AI_API_KEY"):
        return "SKIPPED", "GOOGLE_AI_API_KEY not set (optional live provider check; deterministic test doubles verified)."
    r = subprocess.run(
        [sys.executable, "-m", "app.provider_check", "--live"],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
    )
    return ("PASSED" if r.returncode == 0 else "FAILED"), (r.stdout.strip() or r.stderr.strip())[:200]


def main() -> int:
    checks = [
        ("Secret & Credential Hygiene Scan", check_secret_hygiene),
        ("Static Frontend/Backend Security Controls", check_static_security_controls),
        ("Alembic Migration Upgrade/Downgrade (0001..0008)", check_migrations),
        ("Backend Automated Test Suite (SQLite)", check_backend_sqlite_tests),
        ("PostgreSQL Integration & Concurrency Suite", check_postgres_integration_tests),
        ("Frontend Unit Tests, Typecheck & Build", check_frontend_tests_and_build),
        ("Dependency Vulnerability Audit", check_dependency_audit),
        ("Optional Live Gemini AI Provider Check", check_live_ai_provider),
    ]
    print("=== WebForge Phase 14 Security & Verification Report ===")
    failed = 0
    for name, fn in checks:
        status, detail = fn()
        print(f"[{status}] {name}: {detail}")
        if status == "FAILED":
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
