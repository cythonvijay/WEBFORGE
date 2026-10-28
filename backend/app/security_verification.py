"""Phase 14 Testing & Security Verification Engine:
Deterministic artifact integrity, SHA-256 content-hash verification,ProjectBrain pointer consistency,
PRD requirement traceability, and architecture security readiness checks gating the `testing` and `security` stages.
"""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import architecture as arch, design as ds, optimization as opt, prd, research as res_mod, strategy as stg_mod, ux
from .api import latest_revision, owned
from .architecture_api import architecture_stage_completion_check
from .brain import ProjectBrain
from .db import get_db
from .design_api import design_stage_completion_check
from .lifecycle import STAGE_DEPS, unmet_deps
from .models import (
    ArchitectureDocument,
    BrainRevision,
    DocumentationExport,
    OptimizationArtifact,
    DesignArtifact,
    PrdDocument,
    Project,
    ProjectStage,
    ResearchReport,
    StrategyDocument,
    UxArtifact,
)
from .ux_api import ux_stage_completion_check

router = APIRouter(prefix="/projects/{project_id}/security-verification")

HONEST_VERIFICATION_NOTICE = [
    "This verification report reflects deterministic server-side checks executed against your project's persisted Project Brain revisions, SHA-256 content hashes, lifecycle prerequisite gates, PRD traceability matrix, and approved Architecture security controls.",
    "It does not claim or substitute for a live external penetration test, dynamic application security scan (DAST), or formal compliance certification (SOC 2 / ISO 27001).",
]


def _statuses(db: Session, pid: str) -> dict[str, str]:
    return {s.stage: s.status for s in db.scalars(select(ProjectStage).where(ProjectStage.project_id == pid))}


def evaluate_project_security_and_testing(db: Session, pid: str) -> dict[str, Any]:
    """Run deterministic verification checks across Phases 3-13 for a project."""
    checks: list[dict[str, Any]] = []
    testing_Failures: list[str] = []
    security_failures: list[str] = []

    # 1. Project Brain revision sequence & schema integrity
    revs = list(
        db.scalars(
            select(BrainRevision).where(BrainRevision.project_id == pid).order_by(BrainRevision.version.asc())
        )
    )
    brain_issues: list[str] = []
    snap_obj: ProjectBrain | None = None
    if not revs:
        brain_issues.append("No Project Brain revisions found.")
    else:
        expected_versions = list(range(1, len(revs) + 1))
        actual_versions = [r.version for r in revs]
        if actual_versions != expected_versions:
            brain_issues.append(f"Non-sequential Brain revision versions: {actual_versions}")
        try:
            snap_obj = ProjectBrain.model_validate(revs[-1].snapshot)
        except Exception as e:
            brain_issues.append(f"Latest Project Brain snapshot failed schema validation: {e}")

    checks.append(
        {
            "id": "CHK-BRAIN-INTEGRITY",
            "category": "artifact_integrity",
            "title": "Project Brain Append-Only & Schema Integrity",
            "status": "passed" if not brain_issues else "failed",
            "details": f"Verified {len(revs)} sequential Brain revision(s)." if not brain_issues else "; ".join(brain_issues),
        }
    )
    if brain_issues:
        testing_Failures.extend(brain_issues)
        security_failures.extend(brain_issues)

    # 2. Content-Hash & Pointer Integrity across all approved artifacts
    hash_issues: list[str] = []
    res_app = db.scalar(
        select(ResearchReport)
        .where(ResearchReport.project_id == pid, ResearchReport.status == "approved")
        .order_by(ResearchReport.version.desc())
    )
    if res_app and res_app.content:
        if res_mod.content_hash(res_app.content) != res_app.content_hash:
            hash_issues.append(f"Approved Research v{res_app.version} content_hash mismatch.")
        if snap_obj and snap_obj.research.content_hash != res_app.content_hash:
            hash_issues.append("ProjectBrain.research pointer hash does not match approved ResearchReport.")

    stg_app = db.scalar(
        select(StrategyDocument)
        .where(StrategyDocument.project_id == pid, StrategyDocument.status == "approved")
        .order_by(StrategyDocument.version.desc())
    )
    if stg_app and stg_app.content:
        if stg_mod.content_hash(stg_app.content) != stg_app.content_hash:
            hash_issues.append(f"Approved Strategy v{stg_app.version} content_hash mismatch.")
        if snap_obj and snap_obj.strategy.content_hash != stg_app.content_hash:
            hash_issues.append("ProjectBrain.strategy pointer hash does not match approved StrategyDocument.")

    prd_app = db.scalar(
        select(PrdDocument)
        .where(PrdDocument.project_id == pid, PrdDocument.status == "approved")
        .order_by(PrdDocument.version.desc())
    )
    if prd_app and prd_app.content:
        if prd.content_hash(prd_app.content) != prd_app.content_hash:
            hash_issues.append(f"Approved PRD v{prd_app.version} content_hash mismatch.")
        if snap_obj and snap_obj.prd.content_hash != prd_app.content_hash:
            hash_issues.append("ProjectBrain.prd pointer hash does not match approved PrdDocument.")

    for ut in ux.ARTIFACT_TYPES:
        u_app = db.scalar(
            select(UxArtifact)
            .where(UxArtifact.project_id == pid, UxArtifact.artifact_type == ut, UxArtifact.status == "approved")
            .order_by(UxArtifact.version.desc())
        )
        if u_app and u_app.content and ux.content_hash(u_app.content) != u_app.content_hash:
            hash_issues.append(f"Approved UX {ut} v{u_app.version} content_hash mismatch.")

    for dt in ds.DESIGN_ARTIFACT_TYPES:
        d_app = db.scalar(
            select(DesignArtifact)
            .where(DesignArtifact.project_id == pid, DesignArtifact.artifact_type == dt, DesignArtifact.status == "approved")
            .order_by(DesignArtifact.version.desc())
        )
        if d_app and d_app.content and ds.content_hash(d_app.content) != d_app.content_hash:
            hash_issues.append(f"Approved Design {dt} v{d_app.version} content_hash mismatch.")

    arch_app = db.scalar(
        select(ArchitectureDocument)
        .where(ArchitectureDocument.project_id == pid, ArchitectureDocument.status == "approved")
        .order_by(ArchitectureDocument.version.desc())
    )
    if arch_app and arch_app.content:
        if arch.content_hash(arch_app.content) != arch_app.content_hash:
            hash_issues.append(f"Approved Architecture v{arch_app.version} content_hash mismatch.")
        if snap_obj and snap_obj.architecture_spec.content_hash != arch_app.content_hash:
            hash_issues.append("ProjectBrain.architecture_spec pointer hash does not match approved ArchitectureDocument.")


    for ot in opt.OPTIMIZATION_AREAS:
        o_app = db.scalar(
            select(OptimizationArtifact)
            .where(OptimizationArtifact.project_id == pid, OptimizationArtifact.area == ot, OptimizationArtifact.status == "approved")
            .order_by(OptimizationArtifact.version.desc())
        )
        if o_app and o_app.content and opt.compute_optimization_hash(ot, o_app.content) != o_app.content_hash:
            hash_issues.append(f"Approved Optimization {ot} v{o_app.version} content_hash mismatch.")

    doc_exp_app = db.scalar(
        select(DocumentationExport)
        .where(
            DocumentationExport.project_id == pid,
            DocumentationExport.export_mode == "official",
            DocumentationExport.status == "completed",
        )
        .order_by(DocumentationExport.version.desc())
    )
    if doc_exp_app:
        from .documentation_api import verify_export_record_integrity

        exp_integ = verify_export_record_integrity(doc_exp_app)
        if not exp_integ["verified"]:
            hash_issues.append(
                f"Official DocumentationExport v{doc_exp_app.version} manifest or ZIP bundle SHA-256 mismatch."
            )
        if snap_obj and snap_obj.documentation_spec.bundle_sha256 != doc_exp_app.bundle_sha256:
            hash_issues.append(
                "ProjectBrain.documentation_spec pointer bundle_sha256 does not match official DocumentationExport."
            )

    checks.append(
        {
            "id": "CHK-HASH-PROVENANCE",
            "category": "artifact_integrity",
            "title": "Approved Artifact SHA-256 Content-Hash & Brain Pointer Consistency",
            "status": "passed" if not hash_issues else "failed",
            "details": "All approved artifacts match their recomputed SHA-256 hashes and Project Brain pointers."
            if not hash_issues
            else "; ".join(hash_issues),
        }
    )
    if hash_issues:
        testing_Failures.extend(hash_issues)
        security_failures.extend(hash_issues)

    # 3. Upstream Phase 9-13 Completion & Staleness Gate
    ux_ok, ux_reasons = ux_stage_completion_check(db, pid)
    design_ok, design_reasons = design_stage_completion_check(db, pid)
    arch_ok, arch_reasons = architecture_stage_completion_check(db, pid)
    chain_issues = ux_reasons + design_reasons + arch_reasons
    checks.append(
        {
            "id": "CHK-UPSTREAM-GATES",
            "category": "lifecycle_safety",
            "title": "Phases 9-13 Artifact Approval & Zero-Staleness Verification",
            "status": "passed" if (ux_ok and design_ok and arch_ok) else "failed",
            "details": "Research, Strategy, PRD, UX, Design System, Interactive Prototype, and Product Architecture are approved and current."
            if (ux_ok and design_ok and arch_ok)
            else chain_issues[0],
        }
    )
    if not (ux_ok and design_ok and arch_ok):
        testing_Failures.extend(chain_issues)
        security_failures.extend(chain_issues)

    # 4. PRD -> Architecture -> Data/API -> Design/Prototype Traceability
    trace_issues: list[str] = []
    if arch_app is None or not arch_app.content:
        trace_issues.append("Approve Product Architecture to verify PRD requirement traceability.")
    else:
        comp_eval = arch.evaluate_architecture_completeness(arch_app.content)
        if not comp_eval["complete_traceability"]:
            trace_issues.append(
                f"Uncovered PRD requirements ({comp_eval['uncovered_requirements']}) or unreferenced components ({comp_eval['unreferenced_components']})."
            )
    checks.append(
        {
            "id": "CHK-PRD-TRACEABILITY",
            "category": "traceability",
            "title": "End-to-End PRD Requirement Traceability Matrix",
            "status": "passed" if not trace_issues else "failed",
            "details": "100% of approved PRD requirements map to architecture components, data/API boundaries, and design/prototype refs."
            if not trace_issues
            else "; ".join(trace_issues),
        }
    )
    if trace_issues:
        testing_Failures.extend(trace_issues)
        security_failures.extend(trace_issues)

    # 5. Architecture Security Controls Check
    sec_arch_issues: list[str] = []
    if arch_app is None or not arch_app.content:
        sec_arch_issues.append("Approve Product Architecture before completing the Security stage.")
    else:
        c = arch_app.content
        roles = c.get("system_overview", {}).get("user_roles_and_trust_boundaries", [])
        if not roles or not any(r.get("trust_zone") != "public_unauthenticated" for r in roles):
            sec_arch_issues.append("Architecture must define at least one authenticated or internal trust boundary role.")
        app_arch = c.get("application_architecture", {})
        if len((app_arch.get("authentication_and_authorization") or "").strip()) < 15:
            sec_arch_issues.append("Application architecture authentication_and_authorization specification is missing.")
        if len((app_arch.get("error_handling_and_logging") or "").strip()) < 15:
            sec_arch_issues.append("Application architecture error_handling_and_logging specification is missing.")
        for ent in c.get("data_architecture", {}).get("entities", []):
            if ent.get("status") == "requires_review":
                sec_arch_issues.append(f"Domain entity {ent.get('id')} is marked 'requires_review'.")
            if not (ent.get("access_boundary") and ent.get("sensitive_data_handling")):
                sec_arch_issues.append(f"Domain entity {ent.get('id')} is missing access_boundary or sensitive_data_handling.")
        for ep in c.get("api_architecture", {}).get("endpoints", []):
            if not (ep.get("auth_requirement") and ep.get("validation_and_error_handling")):
                sec_arch_issues.append(f"API endpoint {ep.get('id')} is missing auth_requirement or validation_and_error_handling.")
        dep_arch = c.get("deployment_architecture", {})
        if not (dep_arch.get("configuration_and_secret_management") and dep_arch.get("backup_recovery_and_failure")):
            sec_arch_issues.append("Deployment architecture is missing secret management or backup/recovery policies.")
        for adr in c.get("decisions", []):
            if adr.get("status") == "requires_review":
                sec_arch_issues.append(f"Technical decision {adr.get('id')} is marked 'requires_review'.")

    checks.append(
        {
            "id": "CHK-SECURITY-ARCHITECTURE",
            "category": "security_controls",
            "title": "Architecture Trust Boundaries, Authz, Sensitive Data & Secret Controls",
            "status": "passed" if not sec_arch_issues else "failed",
            "details": "Trust boundaries, auth/authz, entity access boundaries, API validation, and secret/recovery policies verified."
            if not sec_arch_issues
            else "; ".join(sec_arch_issues),
        }
    )
    if sec_arch_issues:
        security_failures.extend(sec_arch_issues)

    st_map = _statuses(db, pid)
    testing_unmet = unmet_deps("testing", st_map)
    security_unmet = unmet_deps("security", st_map)

    if testing_unmet:
        testing_Failures.insert(0, f"Blocked by incomplete upstream stages: {', '.join(testing_unmet)}")
    if security_unmet:
        security_failures.insert(0, f"Blocked by incomplete upstream stages: {', '.join(security_unmet)}")

    return {
        "project_id": pid,
        "testing_ready": len(testing_Failures) == 0,
        "testing_blocking_reasons": testing_Failures,
        "security_ready": len(security_failures) == 0,
        "security_blocking_reasons": security_failures,
        "checks": checks,
        "lifecycle": {
            "testing": {
                "status": st_map.get("testing", "not_started"),
                "depends_on": STAGE_DEPS["testing"],
                "unmet_dependencies": testing_unmet,
            },
            "security": {
                "status": st_map.get("security", "not_started"),
                "depends_on": STAGE_DEPS["security"],
                "unmet_dependencies": security_unmet,
            },
        },
        "limitations": HONEST_VERIFICATION_NOTICE,
    }


def testing_stage_completion_check(db: Session, pid: str) -> tuple[bool, list[str]]:
    res = evaluate_project_security_and_testing(db, pid)
    return res["testing_ready"], res["testing_blocking_reasons"]


def security_stage_completion_check(db: Session, pid: str) -> tuple[bool, list[str]]:
    res = evaluate_project_security_and_testing(db, pid)
    return res["security_ready"], res["security_blocking_reasons"]


@router.get("")
def get_security_verification(project: Project = Depends(owned), db: Session = Depends(get_db)):
    return evaluate_project_security_and_testing(db, project.id)
