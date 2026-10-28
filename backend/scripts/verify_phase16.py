"""Phase 16 Repeatable SEO, Analytics & Performance Verification Runner (`python3 backend/scripts/verify_phase16.py`)."""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"

os.environ.setdefault("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'test.db'}")
os.environ.setdefault("JWT_SECRET", "verify-phase16-runner-secret-0123456789abcdef")

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.observability import metrics  # noqa: E402
from app.optimization import (  # noqa: E402
    AnalyticsContent,
    PerformanceContent,
    SeoContent,
    build_default_optimization_content,
    generate_robots_txt_preview,
    generate_sitemap_xml_preview,
    inspect_html_document,
    run_product_verification_checks,
)
from scripts.verify_phase14 import (  # noqa: E402
    check_backend_sqlite_tests,
    check_dependency_audit,
    check_live_ai_provider,
    check_migrations,
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


def check_phase16_seo_analytics_performance_verifiers() -> tuple[str, str]:
    sample_basis = {
        "requirements": [
            {"id": "FR-1", "title": "Scope baseline locking", "priority": "must"},
            {"id": "NFR-1", "title": "Response latency budget", "priority": "must"},
        ],
        "screens": [
            {"id": "SCR-1", "name": "Public Landing", "route_path": "/", "primary_goal": "Discover ScopeLock"},
            {"id": "SCR-2", "name": "Private Projects Dashboard", "route_path": "/projects", "primary_goal": "Manage projects"},
        ],
        "journeys": [{"id": "J-1", "name": "Primary Flow", "goal": "Create and lock baseline"}],
        "interactions": [{"id": "INT-1", "screen_id": "SCR-1", "label": "Start Project"}],
        "endpoints": [{"id": "API-1", "method": "POST", "path": "/api/baselines", "purpose": "Lock baseline"}],
    }
    seo_dict = build_default_optimization_content("seo", sample_basis)
    an_dict = build_default_optimization_content("analytics", sample_basis)
    pf_dict = build_default_optimization_content("performance", sample_basis)

    seo_model = SeoContent.model_validate(seo_dict)
    AnalyticsContent.model_validate(an_dict)
    PerformanceContent.model_validate(pf_dict)

    sitemap_xml = generate_sitemap_xml_preview(seo_model)
    robots_txt = generate_robots_txt_preview(seo_model)
    if "/projects" in sitemap_xml:
        return "FAILED", "Private route /projects leaked into XML sitemap preview."
    if "Disallow: /projects" not in robots_txt:
        return "FAILED", "Private route /projects missing from robots.txt disallow directives."

    report = run_product_verification_checks(seo_dict, an_dict, pf_dict, REPO_ROOT)
    if report["overall_status"] != "passed":
        return "FAILED", f"run_product_verification_checks returned {report['overall_status']}: {report}"

    first_page = seo_model.page_metadata[0]
    sample_html = (
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'/>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'/>"
        f"<title>{first_page.title_template}</title>"
        f"<meta name='description' content='{first_page.meta_description}'/>"
        f"<meta name='robots' content='{first_page.robots_index},{first_page.robots_follow}'/>"
        f"<link rel='canonical' href='{first_page.canonical_path}'/></head>"
        f"<body><main><h1>{first_page.h1_heading}</h1></main></body></html>"
    )
    html_res = inspect_html_document(sample_html, first_page)
    if html_res["status"] != "passed":
        return "FAILED", f"HTML metadata verifier failed on valid sample: {html_res}"

    snap = metrics.snapshot()
    if snap.get("scope") != "webforge_platform_operational_only" or "duration_buckets_ms" not in snap:
        return "FAILED", "WebForge platform observability metrics missing scope separation or duration buckets."

    return (
        "PASSED",
        f"Verified SEO public/private indexability, XML sitemap & robots.txt generators, HTML semantic inspector, analytics PII/consent gates, CWV/API budgets, and platform observability separation ({report['passed_checks']}/{report['total_checks']} checks passed).",
    )


def check_phase16_frontend_workspaces() -> tuple[str, str]:
    required_files = [
        FRONTEND_DIR / "src" / "types" / "optimization.ts",
        FRONTEND_DIR / "src" / "features" / "optimization" / "api.ts",
        FRONTEND_DIR / "src" / "pages" / "OptimizationPage.tsx",
        FRONTEND_DIR / "src" / "test" / "optimization_phase16.test.tsx",
    ]
    for f in required_files:
        if not f.exists():
            return "FAILED", f"Missing frontend file: {f}"
    nav_txt = (FRONTEND_DIR / "src" / "components" / "navigation" / "nav.ts").read_text()
    if "phase: 16" in nav_txt:
        return "FAILED", "nav.ts still contains placeholder phase: 16 on seo/analytics/performance items."
    router_txt = (FRONTEND_DIR / "src" / "app" / "router.tsx").read_text()
    for route in ('"seo"', '"analytics"', '"performance"'):
        if route not in router_txt:
            return "FAILED", f"router.tsx missing route {route}"
    return "PASSED", "Verified SeoPage, AnalyticsPage, and PerformancePage workspaces, API client, router, and navigation."


def main() -> int:
    checks = [
        ("Secret & Credential Hygiene Scan", check_secret_hygiene),
        ("Static Frontend/Backend Security Controls", check_static_security_controls),
        ("Phase 16 SEO, Analytics, Performance & HTML/Sitemap Verification", check_phase16_seo_analytics_performance_verifiers),
        ("Phase 16 Frontend Workspaces, Routes & Navigation Check", check_phase16_frontend_workspaces),
        ("Container, Nginx & Docker Compose Manifest Validation", check_container_and_compose_manifests),
        ("CI Workflow Configuration Validation (.github/workflows/ci.yml)", check_ci_workflow_configuration),
        ("Fail-Fast Environment Config & Log Redaction Verification", check_env_validation_and_log_redaction),
        ("Alembic Migration Upgrade/Downgrade (0001..0008)", check_migrations),
        ("Disposable Database Backup & Restore Round-Trip Verification", check_backup_and_restore_roundtrip),
        ("Backend Automated Test Suite (SQLite — Phases 0..16)", check_backend_sqlite_tests),
        ("PostgreSQL Integration & Concurrency Suite", check_postgres_integration_tests),
        ("Docker Daemon Image Build & Runtime Execution", check_docker_daemon_build),
        ("Frontend Typecheck, Unit Tests & Production Build", check_frontend_tests_typecheck_and_build),
        ("Dependency Vulnerability Audit (pip-audit / npm audit)", check_dependency_audit),
        ("Optional Live Gemini AI Provider Check", check_live_ai_provider),
    ]
    print("=== WebForge Phase 16 SEO, Analytics & Performance Verification Report ===")
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
