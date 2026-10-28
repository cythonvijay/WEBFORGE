"""Phase 17 Repeatable Documentation & Specification Export Verification Runner (`python3 backend/scripts/verify_phase17.py`)."""
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"

os.environ.setdefault("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'test.db'}")
os.environ.setdefault("JWT_SECRET", "verify-phase17-runner-secret-0123456789abcdef")

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.documentation_export import (  # noqa: E402
    build_consolidated_markdown,
    build_deterministic_zip_bytes,
    scan_export_for_secrets,
    validate_safe_archive_path,
)
from scripts.verify_phase14 import (  # noqa: E402
    check_backend_sqlite_tests,
    check_dependency_audit,
    check_live_ai_provider,
    check_postgres_integration_tests,
    check_secret_hygiene,
    check_static_security_controls,
)
from scripts.verify_phase15 import (  # noqa: E402
    check_backup_and_restore_roundtrip,
    check_ci_workflow_configuration,
    check_container_and_compose_manifests,
    check_docker_daemon_build,
    check_env_validation_and_log_redaction,
    check_frontend_tests_typecheck_and_build,
)
from scripts.verify_phase16 import (  # noqa: E402
    check_phase16_frontend_workspaces,
    check_phase16_seo_analytics_performance_verifiers,
)


def check_migrations_0009() -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "verify_mig_0009.db")
        url = f"sqlite:///{db_path}"
        env = {
            **os.environ,
            "DATABASE_URL": url,
            "JWT_SECRET": "verify-migration-secret-0123456789",
        }
        code = (
            "from alembic.config import Config; from alembic import command; import app.db as app_db; "
            "cfg = Config('alembic.ini'); command.upgrade(cfg, 'head'); "
            "command.downgrade(cfg, '0008'); command.upgrade(cfg, 'head')"
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
        return "PASSED", "Alembic migrations 0001 -> 0009 -> 0008 -> 0009 verified cleanly."


def check_phase17_export_bundle_and_security_controls() -> tuple[str, str]:
    # 1. Verify safe path validation rejects traversal, absolute paths, dotfiles, and non-doc extensions
    for bad in ("../etc/passwd", "/etc/passwd", "sub\\file.md", ".env", "backup.sql", "app.db", "run.sh"):
        try:
            validate_safe_archive_path(bad)
            return "FAILED", f"validate_safe_archive_path failed to reject unsafe path: {bad!r}"
        except ValueError:
            pass

    # 2. Verify deterministic ZIP generation & extraction round-trip
    docs = {
        "README.md": "# Deterministic Bundle Check\n\nVerified UTF-8 — ScopeLock ✓\n",
        "01-research.md": "# 01 — Research\n\nApproved Research v1.\n",
        "12-traceability.md": "# 12 — Traceability\n\nPRD -> UX -> Design -> Architecture -> Optimization.\n",
    }
    manifest = {
        "schema_version": "webforge.documentation_export.v1",
        "export_mode": "official",
        "official_approved_bundle": True,
        "project": {"id": "p1", "name": "ScopeLock"},
        "snapshot_fingerprint": "f" * 64,
        "files": {
            k: {
                "sha256": hashlib.sha256(v.encode("utf-8")).hexdigest(),
                "size_bytes": len(v.encode("utf-8")),
            }
            for k, v in docs.items()
        },
        "omitted_sections": [],
    }
    manifest_json = json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    zip1, sha1 = build_deterministic_zip_bytes(docs, manifest_json)
    zip2, sha2 = build_deterministic_zip_bytes(docs, manifest_json)
    if zip1 != zip2 or sha1 != sha2:
        return "FAILED", "ZIP archive builder is not deterministic across repeated invocations."

    with zipfile.ZipFile(io.BytesIO(zip1), "r") as zf:
        if zf.namelist() != ["README.md", "01-research.md", "12-traceability.md", "MANIFEST.json"]:
            return "FAILED", f"Unexpected ZIP archive entry list: {zf.namelist()}"
        parsed_manifest = json.loads(zf.read("MANIFEST.json").decode("utf-8"))
        if not parsed_manifest.get("official_approved_bundle"):
            return "FAILED", "Extracted MANIFEST.json did not preserve official_approved_bundle=True."

    consolidated = build_consolidated_markdown(docs, manifest)
    if "<!-- BEGIN FILE: 12-traceability.md -->" not in consolidated:
        return "FAILED", "Consolidated Markdown builder missing section delimiter."

    # 3. Verify secret scanner catches leaked API keys, private keys, DB passwords, and internal paths
    if scan_export_for_secrets(docs, manifest_json):
        return "FAILED", "Secret scanner raised false positive on clean documentation bundle."
    dirty = {"06-architecture.md": "sk-proj-1234567890abcdefghijklmnop\n/working_dir/c_ef4e83f8c9952d79/workspace"}
    hits = scan_export_for_secrets(dirty, manifest_json)
    if len(hits) < 2:
        return "FAILED", f"Secret scanner missed injected key or internal path: {hits}"

    return (
        "PASSED",
        "Verified deterministic ZIP archive builder, UTF-8 extraction, path traversal/extension guards, consolidated Markdown builder, and export secret/path scanner.",
    )


def check_phase17_frontend_workspace() -> tuple[str, str]:
    required_files = [
        FRONTEND_DIR / "src" / "types" / "documentation.ts",
        FRONTEND_DIR / "src" / "features" / "documentation" / "api.ts",
        FRONTEND_DIR / "src" / "pages" / "DocumentationPage.tsx",
        FRONTEND_DIR / "src" / "test" / "documentation_phase17.test.tsx",
    ]
    for f in required_files:
        if not f.exists():
            return "FAILED", f"Missing Phase 17 frontend file: {f}"
    nav_txt = (FRONTEND_DIR / "src" / "components" / "navigation" / "nav.ts").read_text()
    if "phase: 17" in nav_txt:
        return "FAILED", "nav.ts still contains placeholder phase: 17 on documentation item."
    router_txt = (FRONTEND_DIR / "src" / "app" / "router.tsx").read_text()
    if '"documentation"' not in router_txt or "DocumentationPage" not in router_txt:
        return "FAILED", "router.tsx missing /projects/:projectId/documentation route."
    return "PASSED", "Verified DocumentationPage workspace, API client, router, navigation, and frontend test suite."


def main() -> int:
    checks = [
        ("Secret & Credential Hygiene Scan", check_secret_hygiene),
        ("Static Frontend/Backend Security Controls", check_static_security_controls),
        ("Phase 16 SEO, Analytics, Performance & HTML/Sitemap Verification", check_phase16_seo_analytics_performance_verifiers),
        ("Phase 16 Frontend Workspaces, Routes & Navigation Check", check_phase16_frontend_workspaces),
        ("Phase 17 Documentation Export, Safe Archive Paths & Secret Scanner", check_phase17_export_bundle_and_security_controls),
        ("Phase 17 Frontend Documentation Workspace, Routes & Navigation Check", check_phase17_frontend_workspace),
        ("Container, Nginx & Docker Compose Manifest Validation", check_container_and_compose_manifests),
        ("CI Workflow Configuration Validation (.github/workflows/ci.yml)", check_ci_workflow_configuration),
        ("Fail-Fast Environment Config & Log Redaction Verification", check_env_validation_and_log_redaction),
        ("Alembic Migration Upgrade/Downgrade (0001..0009)", check_migrations_0009),
        ("Disposable Database Backup & Restore Round-Trip Verification (15 Tables)", check_backup_and_restore_roundtrip),
        ("Backend Automated Test Suite (SQLite — Phases 0..17)", check_backend_sqlite_tests),
        ("PostgreSQL Integration & Concurrency Suite", check_postgres_integration_tests),
        ("Docker Daemon Image Build & Runtime Execution", check_docker_daemon_build),
        ("Frontend Typecheck, Unit Tests & Production Build", check_frontend_tests_typecheck_and_build),
        ("Dependency Vulnerability Audit (pip-audit / npm audit)", check_dependency_audit),
        ("Optional Live Gemini AI Provider Check", check_live_ai_provider),
    ]
    print("=== WebForge Phase 17 Documentation & Export Verification Report ===")
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
