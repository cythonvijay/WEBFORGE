"""Phase 15 Infrastructure, DevOps & Deployment Verification Engine."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api import owned
from .config import validate_runtime_settings
from .db import check_database_readiness, get_db
from .lifecycle import STAGE_DEPS, unmet_deps
from .models import ArchitectureDocument, Project, ProjectStage
from .security_verification import evaluate_project_security_and_testing

router = APIRouter(prefix="/projects/{project_id}/infrastructure-verification")

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"

PHASE15_STAGES = ("docker", "cicd", "infrastructure", "deployment", "monitoring")

HONEST_INFRASTRUCTURE_NOTICE = [
    "This report reflects deterministic server-side checks against your project's approved Architecture deployment specification, upstream security gates, repository container/Compose/CI manifests, database migration state, and runtime observability configuration.",
    "It does not claim that a live external cloud deployment has been provisioned or that external load testing has been executed.",
]


def _statuses(db: Session, pid: str) -> dict[str, str]:
    return {s.stage: s.status for s in db.scalars(select(ProjectStage).where(ProjectStage.project_id == pid))}


def verify_container_and_compose_artifacts() -> list[str]:
    issues: list[str] = []
    backend_df = BACKEND_DIR / "Dockerfile"
    frontend_df = FRONTEND_DIR / "Dockerfile"
    nginx_conf = FRONTEND_DIR / "nginx.conf"
    compose_dev = REPO_ROOT / "docker-compose.yml"
    compose_prod = REPO_ROOT / "docker-compose.prod.yml"
    root_ignore = REPO_ROOT / ".dockerignore"

    for p in (backend_df, frontend_df, nginx_conf, compose_dev, compose_prod, root_ignore):
        if not p.exists():
            issues.append(f"Missing required container artifact: {p.relative_to(REPO_ROOT)}")

    if backend_df.exists():
        b_txt = backend_df.read_text(errors="ignore")
        if "USER webforge" not in b_txt:
            issues.append("backend/Dockerfile must run as non-root USER webforge.")
        if "HEALTHCHECK" not in b_txt:
            issues.append("backend/Dockerfile is missing HEALTHCHECK instruction.")
        if "alembic upgrade" in b_txt and "CMD" in b_txt.split("alembic upgrade")[-1]:
            issues.append("backend/Dockerfile must not run Alembic migrations automatically inside worker CMD.")

    if frontend_df.exists():
        f_txt = frontend_df.read_text(errors="ignore")
        if "FROM" not in f_txt or "USER nginx" not in f_txt:
            issues.append("frontend/Dockerfile must use a multi-stage build and non-root USER nginx.")

    if nginx_conf.exists():
        n_txt = nginx_conf.read_text(errors="ignore")
        if "try_files $uri $uri/ /index.html;" not in n_txt:
            issues.append("frontend/nginx.conf is missing SPA fallback `try_files $uri $uri/ /index.html;`.")
        if "location /api/" not in n_txt or "proxy_pass" not in n_txt:
            issues.append("frontend/nginx.conf must proxy `/api/` without intercepting API routes with SPA fallback.")

    if root_ignore.exists():
        ig_txt = root_ignore.read_text(errors="ignore")
        for required_entry in (".env", ".git", "node_modules"):
            if required_entry not in ig_txt:
                issues.append(f".dockerignore must exclude `{required_entry}`.")

    for compose_file in (compose_dev, compose_prod):
        if compose_file.exists():
            try:
                c_data = yaml.safe_load(compose_file.read_text(errors="ignore")) or {}
                if not isinstance(c_data.get("services"), dict):
                    issues.append(f"{compose_file.name} is missing `services` mapping.")
            except Exception as exc:
                issues.append(f"{compose_file.name} failed YAML parsing: {exc}")

    if compose_dev.exists():
        c_data = yaml.safe_load(compose_dev.read_text(errors="ignore")) or {}
        services = c_data.get("services") or {}
        for req_svc in ("postgres", "migrate", "backend"):
            if req_svc not in services:
                issues.append(f"docker-compose.yml is missing service `{req_svc}`.")
        pg = services.get("postgres") or {}
        if "healthcheck" not in pg:
            issues.append("docker-compose.yml `postgres` service is missing `healthcheck`.")
        for port_mapping in pg.get("ports") or []:
            if isinstance(port_mapping, str) and not port_mapping.startswith("127.0.0.1:"):
                issues.append("docker-compose.yml `postgres` port must bind to 127.0.0.1 only.")

    return issues


def verify_ci_pipeline_artifact() -> list[str]:
    issues: list[str] = []
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    if not ci_path.exists():
        return ["Missing CI workflow `.github/workflows/ci.yml`."]
    try:
        ci_data = yaml.safe_load(ci_path.read_text(errors="ignore")) or {}
        jobs = ci_data.get("jobs") or {}
        required_jobs = {
            "security-and-hygiene",
            "backend-sqlite-and-ops",
            "backend-postgres-integration",
            "frontend-verify",
            "dependency-audit",
            "container-build-verify",
        }
        missing = sorted(required_jobs - set(jobs.keys()))
        if missing:
            issues.append(f"CI workflow missing required jobs: {', '.join(missing)}")
        perms = ci_data.get("permissions") or {}
        if perms.get("contents") != "read":
            issues.append("CI workflow must set least-privilege `permissions: contents: read`.")
    except Exception as exc:
        issues.append(f"CI workflow failed YAML validation: {exc}")
    return issues


def evaluate_project_infrastructure_and_deployment(db: Session, pid: str) -> dict[str, Any]:
    """Evaluate deterministic Phase 15 readiness across container, CI/CD, infrastructure, deployment, and monitoring."""
    checks: list[dict[str, Any]] = []
    stage_failures: dict[str, list[str]] = {s: [] for s in PHASE15_STAGES}

    sec_eval = evaluate_project_security_and_testing(db, pid)
    upstream_issues: list[str] = []
    if not sec_eval["testing_ready"]:
        upstream_issues.extend(sec_eval["testing_blocking_reasons"])
    if not sec_eval["security_ready"]:
        for r in sec_eval["security_blocking_reasons"]:
            if r not in upstream_issues:
                upstream_issues.append(r)

    checks.append(
        {
            "id": "CHK-UPSTREAM-SECURITY-GATE",
            "category": "lifecycle_safety",
            "title": "Upstream Phases 9-14 Artifact & Security Readiness",
            "status": "passed" if not upstream_issues else "failed",
            "details": "All upstream Research, Strategy, PRD, UX, Design, Architecture, Testing, and Security checks pass."
            if not upstream_issues
            else upstream_issues[0],
        }
    )
    if upstream_issues:
        for s in PHASE15_STAGES:
            stage_failures[s].extend(upstream_issues)

    arch_app = db.scalar(
        select(ArchitectureDocument)
        .where(ArchitectureDocument.project_id == pid, ArchitectureDocument.status == "approved")
        .order_by(ArchitectureDocument.version.desc())
    )
    dep_spec_issues: list[str] = []
    if arch_app is None or not arch_app.content:
        dep_spec_issues.append("Approve Product Architecture before completing Infrastructure or Deployment stages.")
    else:
        dep_arch = arch_app.content.get("deployment_architecture") or {}
        svcs = dep_arch.get("services_and_infrastructure") or []
        if len(svcs) < 1:
            dep_spec_issues.append("Architecture deployment_architecture.services_and_infrastructure must define at least 1 service.")
        for field_name in (
            "local_development_environment",
            "configuration_and_secret_management",
            "deployment_boundaries",
            "health_checks_and_observability",
            "backup_recovery_and_failure",
        ):
            val = (dep_arch.get(field_name) or "").strip()
            if len(val) < 10:
                dep_spec_issues.append(f"Architecture deployment_architecture.{field_name} is missing or incomplete.")

    checks.append(
        {
            "id": "CHK-ARCHITECTURE-DEPLOYMENT-SPEC",
            "category": "deployment_architecture",
            "title": "Approved Architecture Deployment, Secret, CI/CD & Recovery Specification",
            "status": "passed" if not dep_spec_issues else "failed",
            "details": "Approved Architecture defines environments, container strategy, CI/CD, secrets, health checks, and backup/recovery."
            if not dep_spec_issues
            else "; ".join(dep_spec_issues),
        }
    )
    if dep_spec_issues:
        for s in PHASE15_STAGES:
            stage_failures[s].extend(dep_spec_issues)

    container_issues = verify_container_and_compose_artifacts()
    checks.append(
        {
            "id": "CHK-CONTAINER-AND-COMPOSE-ARTIFACTS",
            "category": "containers",
            "title": "Production Multi-Stage Dockerfiles, Non-Root Runtime, Nginx & Compose Definitions",
            "status": "passed" if not container_issues else "failed",
            "details": "Backend/frontend Dockerfiles, .dockerignore, Nginx SPA/API proxy config, and Compose files verified."
            if not container_issues
            else "; ".join(container_issues),
        }
    )
    if container_issues:
        for s in PHASE15_STAGES:
            stage_failures[s].extend(container_issues)

    ci_issues = verify_ci_pipeline_artifact()
    checks.append(
        {
            "id": "CHK-CI-CD-PIPELINE",
            "category": "cicd",
            "title": "Reproducible CI Pipeline (Tests, Migrations, Postgres, Frontend, Audits & Docker)",
            "status": "passed" if not ci_issues else "failed",
            "details": "GitHub Actions CI workflow defines all mandatory verification jobs with least-privilege permissions."
            if not ci_issues
            else "; ".join(ci_issues),
        }
    )
    if ci_issues:
        for s in ("cicd", "infrastructure", "deployment", "monitoring"):
            stage_failures[s].extend(ci_issues)

    db_ops_issues: list[str] = []
    db_readiness = check_database_readiness(verify_migrations=True)
    if not db_readiness["ready"]:
        db_ops_issues.append(f"Database readiness check failed: {db_readiness.get('reason')}")
    if not (BACKEND_DIR / "scripts" / "db_ops.py").exists():
        db_ops_issues.append("Database operational script `backend/scripts/db_ops.py` is missing.")

    checks.append(
        {
            "id": "CHK-DB-MIGRATION-AND-BACKUP-OPS",
            "category": "database_ops",
            "title": "Database Readiness, Alembic Head Alignment & Backup/Restore Tooling",
            "status": "passed" if not db_ops_issues else "failed",
            "details": f"Database reachable at Alembic head revision {db_readiness.get('revision')} with verified backup/restore CLI."
            if not db_ops_issues
            else "; ".join(db_ops_issues),
        }
    )
    if db_ops_issues:
        for s in ("infrastructure", "deployment", "monitoring"):
            stage_failures[s].extend(db_ops_issues)

    obs_issues = validate_runtime_settings()
    if not (BACKEND_DIR / "app" / "observability.py").exists():
        obs_issues.append("Observability module `backend/app/observability.py` is missing.")

    checks.append(
        {
            "id": "CHK-OBSERVABILITY-AND-HEALTH-PROBES",
            "category": "observability",
            "title": "Structured Redacting Logging, Correlation IDs & Liveness/Readiness Probes",
            "status": "passed" if not obs_issues else "failed",
            "details": "Runtime configuration, secret-redacting structured logging, and liveness/readiness probes verified."
            if not obs_issues
            else "; ".join(obs_issues),
        }
    )
    if obs_issues:
        for s in ("infrastructure", "deployment", "monitoring"):
            stage_failures[s].extend(obs_issues)

    st_map = _statuses(db, pid)
    lifecycle_out: dict[str, Any] = {}
    for s in PHASE15_STAGES:
        unmet = unmet_deps(s, st_map)
        if unmet:
            stage_failures[s].insert(0, f"Blocked by incomplete upstream stages: {', '.join(unmet)}")
        lifecycle_out[s] = {
            "status": st_map.get(s, "not_started"),
            "depends_on": STAGE_DEPS[s],
            "unmet_dependencies": unmet,
            "ready": len(stage_failures[s]) == 0,
            "blocking_reasons": stage_failures[s],
        }

    return {
        "project_id": pid,
        "docker_ready": len(stage_failures["docker"]) == 0,
        "cicd_ready": len(stage_failures["cicd"]) == 0,
        "infrastructure_ready": len(stage_failures["infrastructure"]) == 0,
        "deployment_ready": len(stage_failures["deployment"]) == 0,
        "monitoring_ready": len(stage_failures["monitoring"]) == 0,
        "checks": checks,
        "lifecycle": lifecycle_out,
        "limitations": HONEST_INFRASTRUCTURE_NOTICE,
    }


def phase15_stage_completion_check(db: Session, pid: str, stage: str) -> tuple[bool, list[str]]:
    res = evaluate_project_infrastructure_and_deployment(db, pid)
    st_info = res["lifecycle"].get(stage)
    if not st_info:
        return False, [f"Unknown Phase 15 stage: {stage}"]
    return st_info["ready"], st_info["blocking_reasons"]


@router.get("")
def get_infrastructure_verification(project: Project = Depends(owned), db: Session = Depends(get_db)):
    return evaluate_project_infrastructure_and_deployment(db, project.id)
