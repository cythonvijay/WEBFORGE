"""Phase 16 SEO, Analytics & Performance API workflow:
Routes, upstream Phase 9-13 prerequisite & staleness gates, copy-on-write edits,
exact-hash submission & approval, Project Brain pointer updates, runtime verification checks,
and `seo` / `analytics` lifecycle stage synchronization and invalidation.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai, architecture as arch, design as ds, optimization as opt, ux
from .api import commit_brain, current_user, latest_revision, owned
from .architecture_api import (
    _doc_staleness as _arch_staleness,
    architecture_stage_completion_check,
)
from .brain import UxArtifactPointer
from .config import settings
from .db import get_db
from .design_api import _doc_staleness as _design_staleness, design_stage_completion_check
from .discovery_api import txn
from .models import (
    ArchitectureDocument,
    DesignArtifact,
    OptimizationArtifact,
    PrdDocument,
    Project,
    ProjectStage,
    ResearchReport,
    StrategyDocument,
    User,
    UxArtifact,
    now,
)
from .security import as_utc
from .ux_api import WORKSPACE_PATHS as UX_PATHS, ux_stage_completion_check

router = APIRouter(prefix="/projects/{project_id}/optimization")
HASH = Field(min_length=64, max_length=64)

WORKSPACE_PATHS: dict[str, str] = {
    "seo": "seo",
    "analytics": "analytics",
    "performance": "performance",
}
AREA_STAGE: dict[str, str] = {
    "seo": "seo",
    "analytics": "analytics",
    "performance": "analytics",
}


class GenerateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supersede: bool = False


class Hashed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_hash: str = HASH


class PutContentIn(Hashed):
    content: dict[str, Any]


class PatchSectionIn(Hashed):
    section: str = Field(min_length=1, max_length=80)
    value: Any


class ApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_hash: str = HASH
    acknowledge_unverified: bool = False
    note: str | None = Field(default=None, max_length=1000)


class VerifyHtmlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_path: str = Field(default="/", min_length=1, max_length=240)
    html_content: str = Field(min_length=5, max_length=200_000)


def _check_area(area: str) -> opt.OptimizationArea:
    if area not in ("seo", "analytics", "performance"):
        raise HTTPException(status_code=404, detail=f"Unknown optimization area '{area}'.")
    return area  # type: ignore[return-value]


def _get_approved_and_draft(
    db: Session, project_id: str, area: str
) -> tuple[OptimizationArtifact | None, OptimizationArtifact | None, list[OptimizationArtifact]]:
    # Materialize the ScalarResult once. Iterating it with `next()` consumes it;
    # scanning it separately for approved and draft records could otherwise leave
    # `draft` and `rows` empty when no approved version exists.
    rows = list(
        db.scalars(
            select(OptimizationArtifact)
            .where(OptimizationArtifact.project_id == project_id, OptimizationArtifact.area == area)
            .order_by(OptimizationArtifact.version.desc())
        )
    )
    approved = next((r for r in rows if r.status == "approved"), None)
    draft = next((r for r in rows if r.status in ("draft", "in_review")), None)
    return approved, draft, rows


def evaluate_optimization_prerequisites(db: Session, project_id: str) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    blocking_reasons: list[str] = []
    remediation_links: list[dict[str, str]] = []

    def _add(
        artifact: str,
        label: str,
        workspace: str,
        approved_v: int | None,
        open_draft_v: int | None,
        extra_blocker: str | None = None,
    ) -> None:
        blocker = extra_blocker
        if approved_v is None:
            blocker = f"{label} has no approved version yet."
        elif open_draft_v is not None:
            blocker = f"{label} has an unapproved open draft (v{open_draft_v})."
        ready = blocker is None
        artifacts.append(
            {
                "artifact": artifact,
                "label": label,
                "workspace": workspace,
                "approved_version": approved_v,
                "open_draft_version": open_draft_v,
                "ready": ready,
                "blocker_reason": blocker,
            }
        )
        if blocker:
            blocking_reasons.append(blocker)
            remediation_links.append({"label": label, "workspace": workspace, "reason": blocker})

    # 1. Research
    res_rows = list(
        db.scalars(
            select(ResearchReport)
            .where(ResearchReport.project_id == project_id)
            .order_by(ResearchReport.version.desc())
        )
    )
    res_app = next((r for r in res_rows if r.status == "approved"), None)
    res_dr = next((r for r in res_rows if r.status in ("draft", "in_review")), None)
    _add("research", "User & Market Research", "research", res_app.version if res_app else None, res_dr.version if res_dr else None)

    # 2. Strategy
    st_rows = list(
        db.scalars(
            select(StrategyDocument)
            .where(StrategyDocument.project_id == project_id)
            .order_by(StrategyDocument.version.desc())
        )
    )
    st_app = next((r for r in st_rows if r.status == "approved"), None)
    st_dr = next((r for r in st_rows if r.status in ("draft", "in_review")), None)
    _add("strategy", "Product Strategy", "strategy", st_app.version if st_app else None, st_dr.version if st_dr else None)

    # 3. PRD
    prd_rows = list(
        db.scalars(
            select(PrdDocument)
            .where(PrdDocument.project_id == project_id)
            .order_by(PrdDocument.version.desc())
        )
    )
    prd_app = next((r for r in prd_rows if r.status == "approved"), None)
    prd_dr = next((r for r in prd_rows if r.status in ("draft", "in_review")), None)
    _add("prd", "Product Requirements Document (PRD)", "prd", prd_app.version if prd_app else None, prd_dr.version if prd_dr else None)

    # 4. UX Artifacts
    for utype in ux.ARTIFACT_TYPES:
        uws = UX_PATHS[utype]
        ux_rows = list(
            db.scalars(
                select(UxArtifact)
                .where(UxArtifact.project_id == project_id, UxArtifact.artifact_type == utype)
                .order_by(UxArtifact.version.desc())
            )
        )
        ux_app = next((r for r in ux_rows if r.status == "approved"), None)
        ux_dr = next((r for r in ux_rows if r.status in ("draft", "in_review")), None)
        _add(f"ux_{utype}", f"UX {utype.replace('_', ' ').title()}", uws, ux_app.version if ux_app else None, ux_dr.version if ux_dr else None)

    # 5. Design System & Prototype
    for dtype, dws, dlabel in (
        ("design_system", "design-system", "Design System"),
        ("prototype", "prototype", "Interactive Prototype"),
    ):
        d_rows = list(
            db.scalars(
                select(DesignArtifact)
                .where(DesignArtifact.project_id == project_id, DesignArtifact.artifact_type == dtype)
                .order_by(DesignArtifact.version.desc())
            )
        )
        d_app = next((r for r in d_rows if r.status == "approved"), None)
        d_dr = next((r for r in d_rows if r.status in ("draft", "in_review")), None)
        _add(dtype, dlabel, dws, d_app.version if d_app else None, d_dr.version if d_dr else None)

    # 6. Product Architecture
    arch_rows = list(
        db.scalars(
            select(ArchitectureDocument)
            .where(ArchitectureDocument.project_id == project_id)
            .order_by(ArchitectureDocument.version.desc())
        )
    )
    arch_app = next((r for r in arch_rows if r.status == "approved"), None)
    arch_dr = next((r for r in arch_rows if r.status in ("draft", "in_review")), None)
    arch_extra = None
    if arch_app and not arch_dr:
        arch_ok, arch_reasons = architecture_stage_completion_check(db, project_id)
        if not arch_ok and arch_reasons:
            arch_extra = "; ".join(arch_reasons)
    _add(
        "architecture",
        "Product Architecture",
        "architecture",
        arch_app.version if arch_app else None,
        arch_dr.version if arch_dr else None,
        extra_blocker=arch_extra,
    )

    return {
        "ready": len(blocking_reasons) == 0,
        "blocking_reasons": blocking_reasons,
        "remediation_links": remediation_links,
        "artifacts": artifacts,
    }


def _compute_staleness_warnings(db: Session, project_id: str, doc: OptimizationArtifact | None) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    prereq = evaluate_optimization_prerequisites(db, project_id)
    for item in prereq["artifacts"]:
        if item["open_draft_version"] is not None:
            warnings.append(
                {
                    "artifact": item["artifact"],
                    "workspace": item["workspace"],
                    "message": f"Upstream {item['label']} has an unapproved open draft (v{item['open_draft_version']}).",
                }
            )
    if not doc:
        return warnings

    basis = doc.basis_summary or {}
    current_basis = opt.build_optimization_basis(db, project_id)

    checks = [
        ("research", "research", basis.get("research_report_version"), current_basis.get("research_report_version"), basis.get("research_content_hash"), current_basis.get("research_content_hash"), "User & Market Research"),
        ("strategy", "strategy", basis.get("strategy_version"), current_basis.get("strategy_version"), basis.get("strategy_content_hash"), current_basis.get("strategy_content_hash"), "Product Strategy"),
        ("prd", "prd", basis.get("prd_version"), current_basis.get("prd_version"), basis.get("prd_content_hash"), current_basis.get("prd_content_hash"), "PRD"),
        ("design_system", "design-system", basis.get("design_system_version"), current_basis.get("design_system_version"), basis.get("design_system_hash"), current_basis.get("design_system_hash"), "Design System"),
        ("prototype", "prototype", basis.get("prototype_version"), current_basis.get("prototype_version"), basis.get("prototype_hash"), current_basis.get("prototype_hash"), "Interactive Prototype"),
        ("architecture", "architecture", basis.get("architecture_version"), current_basis.get("architecture_version"), basis.get("architecture_content_hash"), current_basis.get("architecture_content_hash"), "Product Architecture"),
    ]
    for key, ws, old_v, cur_v, old_h, cur_h, label in checks:
        if cur_v is not None and (old_v != cur_v or (old_h and cur_h and old_h != cur_h)):
            warnings.append(
                {
                    "artifact": key,
                    "workspace": ws,
                    "message": f"{label} was updated to v{cur_v} after this specification was created (based on v{old_v}).",
                }
            )

    old_ux_hashes = basis.get("ux_hashes") or {}
    cur_ux_hashes = current_basis.get("ux_hashes") or {}
    for utype in ux.ARTIFACT_TYPES:
        uws = UX_PATHS[utype]
        if cur_ux_hashes.get(utype) and old_ux_hashes.get(utype) != cur_ux_hashes.get(utype):
            warnings.append(
                {
                    "artifact": f"ux_{utype}",
                    "workspace": uws,
                    "message": f"UX {utype.replace('_', ' ').title()} changed after this specification was generated.",
                }
            )
    return warnings


def _serialize_doc(doc: OptimizationArtifact) -> dict[str, Any]:
    return {
        "id": doc.id,
        "project_id": doc.project_id,
        "area": doc.area,
        "version": doc.version,
        "status": doc.status,
        "supersedes_version": doc.supersedes_version,
        "generation_source": doc.generation_source,
        "ai_metadata": doc.ai_metadata or {},
        "content": doc.content,
        "basis_summary": doc.basis_summary or {},
        "content_hash": doc.content_hash,
        "approval_note": doc.approval_note,
        "approved_at": as_utc(doc.approved_at).isoformat() if doc.approved_at else None,
        "approved_by": doc.approved_by,
        "created_at": as_utc(doc.created_at).isoformat(),
        "updated_at": as_utc(doc.updated_at).isoformat(),
    }


def _build_area_state(db: Session, project_id: str, area: opt.OptimizationArea) -> dict[str, Any]:
    approved, draft, rows = _get_approved_and_draft(db, project_id, area)
    active = draft or approved
    prereq = evaluate_optimization_prerequisites(db, project_id)
    basis = opt.build_optimization_basis(db, project_id)

    stage_key = AREA_STAGE[area]
    stage_row = db.scalar(
        select(ProjectStage).where(ProjectStage.project_id == project_id, ProjectStage.stage == stage_key)
    )
    stage_status = stage_row.status if stage_row else "not_started"

    if active:
        completeness = opt.evaluate_optimization_completeness(area, active.content, basis).model_dump()
        if area == "seo":
            seo_model = opt.SeoContent.model_validate(active.content)
            traceability = opt.compute_seo_traceability(seo_model, basis).model_dump()
            sitemap_preview = opt.generate_sitemap_xml_preview(seo_model)
            robots_preview = opt.generate_robots_txt_preview(seo_model)
        elif area == "analytics":
            an_model = opt.AnalyticsContent.model_validate(active.content)
            traceability = opt.compute_analytics_traceability(an_model, basis).model_dump()
            sitemap_preview = None
            robots_preview = None
        else:
            pf_model = opt.PerformanceContent.model_validate(active.content)
            traceability = opt.compute_performance_traceability(pf_model, basis).model_dump()
            sitemap_preview = None
            robots_preview = None
    else:
        completeness = {
            "ready_for_submission": False,
            "ready_for_approval": False,
            "missing_fields": [f"No {area} specification exists yet."],
            "unresolved_constraint_errors": [],
            "unverified_items": [],
            "requires_review_items": [],
            "uncovered_requirement_ids": [],
            "item_count": 0,
        }
        traceability = {
            "area": area,
            "complete": False,
            "total_requirements": len(basis.get("requirements") or []),
            "covered_requirements": 0,
            "requirement_coverage": [],
            "valid_screen_ids": [s["id"] for s in basis.get("screens") or []],
            "valid_route_paths": [r["path"] for r in basis.get("routes") or []],
            "valid_endpoint_ids": [e["id"] for e in basis.get("endpoints") or []],
            "findings": [],
        }
        sitemap_preview = None
        robots_preview = None

    warnings = _compute_staleness_warnings(db, project_id, active)
    return {
        "area": area,
        "stage_key": stage_key,
        "stage_status": stage_status,
        "prerequisites": prereq,
        "current_approved": _serialize_doc(approved) if approved else None,
        "current_draft": _serialize_doc(draft) if draft else None,
        "versions": [
            {
                "version": r.version,
                "status": r.status,
                "supersedes_version": r.supersedes_version,
                "generation_source": r.generation_source,
                "content_hash": r.content_hash,
                "created_at": as_utc(r.created_at).isoformat(),
                "updated_at": as_utc(r.updated_at).isoformat(),
                "approved_at": as_utc(r.approved_at).isoformat() if r.approved_at else None,
            }
            for r in rows
        ],
        "completeness": completeness,
        "traceability": traceability,
        "warnings": warnings,
        "sitemap_xml_preview": sitemap_preview,
        "robots_txt_preview": robots_preview,
    }


def seo_stage_completion_check(db: Session, project_id: str) -> tuple[bool, list[str]]:
    prereq = evaluate_optimization_prerequisites(db, project_id)
    if not prereq["ready"]:
        return False, [f"SEO stage requires approved upstream prerequisites: {'; '.join(prereq['blocking_reasons'])}"]
    approved, draft, _ = _get_approved_and_draft(db, project_id, "seo")
    if not approved:
        return False, ["SEO specification must be approved before completing the SEO stage."]
    if draft:
        return False, [f"SEO specification has an unapproved open draft (v{draft.version}). Approve it before completing the SEO stage."]
    warnings = _compute_staleness_warnings(db, project_id, approved)
    if warnings:
        return False, [f"Approved SEO specification is stale against upstream changes: {warnings[0]['message']}"]
    basis = opt.build_optimization_basis(db, project_id)
    comp = opt.evaluate_optimization_completeness("seo", approved.content, basis)
    if not comp.ready_for_approval:
        return False, ["Approved SEO specification no longer satisfies completeness and traceability requirements."]
    return True, []


def analytics_stage_completion_check(db: Session, project_id: str) -> tuple[bool, list[str]]:
    prereq = evaluate_optimization_prerequisites(db, project_id)
    if not prereq["ready"]:
        return False, [f"Analytics & Performance stage requires approved upstream prerequisites: {'; '.join(prereq['blocking_reasons'])}"]
    for area, label in (("analytics", "Analytics"), ("performance", "Performance")):
        approved, draft, _ = _get_approved_and_draft(db, project_id, area)
        if not approved:
            return False, [f"{label} specification must be approved before completing the Analytics & Performance stage."]
        if draft:
            return False, [f"{label} specification has an unapproved open draft (v{draft.version}). Approve it before completing the stage."]
        warnings = _compute_staleness_warnings(db, project_id, approved)
        if warnings:
            return False, [f"Approved {label} specification is stale against upstream changes: {warnings[0]['message']}"]
        basis = opt.build_optimization_basis(db, project_id)
        comp = opt.evaluate_optimization_completeness(area, approved.content, basis)
        if not comp.ready_for_approval:
            return False, [f"Approved {label} specification no longer satisfies completeness and traceability requirements."]
    return True, []


def sync_optimization_stages(db: Session, project_id: str) -> None:
    # 1. Sync SEO stage
    seo_stage = db.scalar(
        select(ProjectStage).where(ProjectStage.project_id == project_id, ProjectStage.stage == "seo")
    )
    if seo_stage:
        _, _, seo_rows = _get_approved_and_draft(db, project_id, "seo")
        seo_ok, _ = seo_stage_completion_check(db, project_id)
        if seo_ok:
            seo_stage.status = "complete"
            seo_stage.updated_at = now()
        elif seo_rows or seo_stage.status == "complete":
            seo_stage.status = "in_progress"
            seo_stage.updated_at = now()

    # 2. Sync Analytics stage (covers both analytics and performance specifications)
    an_stage = db.scalar(
        select(ProjectStage).where(ProjectStage.project_id == project_id, ProjectStage.stage == "analytics")
    )
    if an_stage:
        _, _, an_rows = _get_approved_and_draft(db, project_id, "analytics")
        _, _, pf_rows = _get_approved_and_draft(db, project_id, "performance")
        an_ok, _ = analytics_stage_completion_check(db, project_id)
        if an_ok:
            an_stage.status = "complete"
            an_stage.updated_at = now()
        elif an_rows or pf_rows or an_stage.status == "complete":
            an_stage.status = "in_progress"
            an_stage.updated_at = now()

    # 3. Cascade invalidation across dependent stages if their upstream dependencies are no longer complete
    from .lifecycle import STAGES, unmet_deps

    stage_rows = {
        s.stage: s
        for s in db.scalars(select(ProjectStage).where(ProjectStage.project_id == project_id))
    }
    st_map = {k: r.status for k, r in stage_rows.items()}
    for stg_name in STAGES:
        if stg_name in ("research", "product", "ux", "design", "architecture", "seo", "analytics", "documentation"):
            continue
        s_row = stage_rows.get(stg_name)
        if s_row and s_row.status == "complete" and unmet_deps(stg_name, st_map):
            s_row.status = "needs_review"
            s_row.updated_at = now()
            st_map[stg_name] = "needs_review"

    # 4. Cascade upstream changes to final Documentation & Export stage
    from .documentation_api import sync_documentation_stage

    sync_documentation_stage(db, project_id)


@router.get("")
def get_optimization_overview(
    project_id: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    owned(project_id, u, db)
    sync_optimization_stages(db, project_id)
    db.commit()

    prereq = evaluate_optimization_prerequisites(db, project_id)
    seo_state = _build_area_state(db, project_id, "seo")
    an_state = _build_area_state(db, project_id, "analytics")
    pf_state = _build_area_state(db, project_id, "performance")

    seo_doc = (seo_state["current_draft"] or seo_state["current_approved"] or {}).get("content")
    an_doc = (an_state["current_draft"] or an_state["current_approved"] or {}).get("content")
    pf_doc = (pf_state["current_draft"] or pf_state["current_approved"] or {}).get("content")
    ver_report = opt.run_product_verification_checks(seo_doc, an_doc, pf_doc)

    return {
        "seo_stage_status": seo_state["stage_status"],
        "analytics_stage_status": an_state["stage_status"],
        "prerequisites": prereq,
        "areas": {
            "seo": seo_state,
            "analytics": an_state,
            "performance": pf_state,
        },
        "verification": ver_report,
    }


@router.get("/verification")
def get_optimization_verification(
    project_id: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    owned(project_id, u, db)
    seo_app, seo_dr, _ = _get_approved_and_draft(db, project_id, "seo")
    an_app, an_dr, _ = _get_approved_and_draft(db, project_id, "analytics")
    pf_app, pf_dr, _ = _get_approved_and_draft(db, project_id, "performance")
    seo_c = (seo_dr or seo_app).content if (seo_dr or seo_app) else None
    an_c = (an_dr or an_app).content if (an_dr or an_app) else None
    pf_c = (pf_dr or pf_app).content if (pf_dr or pf_app) else None
    return opt.run_product_verification_checks(seo_c, an_c, pf_c)


@router.post("/verify-html")
def verify_html_route(
    project_id: str,
    body: VerifyHtmlIn,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    owned(project_id, u, db)
    seo_app, seo_dr, _ = _get_approved_and_draft(db, project_id, "seo")
    active = seo_dr or seo_app
    page_spec = None
    if active:
        seo_model = opt.SeoContent.model_validate(active.content)
        page_spec = next(
            (p for p in seo_model.page_metadata if p.route_path == body.route_path),
            seo_model.page_metadata[0] if seo_model.page_metadata else None,
        )
    return opt.inspect_html_document(body.html_content, page_spec)


@router.get("/{area}")
def get_optimization_area(
    project_id: str,
    area: str,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    area_typed = _check_area(area)
    owned(project_id, u, db)
    sync_optimization_stages(db, project_id)
    db.commit()
    return _build_area_state(db, project_id, area_typed)


@router.get("/{area}/versions/{version}")
def get_optimization_version(
    project_id: str,
    area: str,
    version: int,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    area_typed = _check_area(area)
    owned(project_id, u, db)
    doc = db.scalar(
        select(OptimizationArtifact).where(
            OptimizationArtifact.project_id == project_id,
            OptimizationArtifact.area == area_typed,
            OptimizationArtifact.version == version,
        )
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"{area_typed} version {version} not found.")
    return _serialize_doc(doc)


def _persist_new_draft(
    db: Session,
    project_id: str,
    area: opt.OptimizationArea,
    content_dict: dict[str, Any],
    basis: dict[str, Any],
    source: str,
    ai_meta: dict[str, Any],
    supersede: bool,
) -> None:
    approved, draft, rows = _get_approved_and_draft(db, project_id, area)
    if draft and not supersede:
        raise HTTPException(
            status_code=409,
            detail=f"An open {area} draft (v{draft.version}) already exists. Pass supersede=true to replace it.",
        )

    with txn(db):
        if draft and supersede:
            draft.status = "superseded"
            draft.updated_at = now()
            db.flush()

        next_v = (max((r.version for r in rows), default=0)) + 1
        c_hash = opt.compute_optimization_hash(area, content_dict)
        summary = opt.OptimizationBasisSummary(
            research_report_version=basis.get("research_report_version"),
            research_content_hash=basis.get("research_content_hash"),
            strategy_version=basis.get("strategy_version"),
            strategy_content_hash=basis.get("strategy_content_hash"),
            prd_version=basis.get("prd_version"),
            prd_content_hash=basis.get("prd_content_hash"),
            ux_versions=basis.get("ux_versions") or {},
            ux_hashes=basis.get("ux_hashes") or {},
            design_system_version=basis.get("design_system_version"),
            design_system_hash=basis.get("design_system_hash"),
            prototype_version=basis.get("prototype_version"),
            prototype_hash=basis.get("prototype_hash"),
            architecture_version=basis.get("architecture_version"),
            architecture_content_hash=basis.get("architecture_content_hash"),
        ).model_dump()

        new_doc = OptimizationArtifact(
            project_id=project_id,
            area=area,
            version=next_v,
            status="draft",
            supersedes_version=approved.version if approved else (draft.version if draft else None),
            generation_source=source,
            ai_metadata=ai_meta,
            content=content_dict,
            basis_summary=summary,
            content_hash=c_hash,
        )
        db.add(new_doc)
        db.flush()
        sync_optimization_stages(db, project_id)


@router.post("/{area}/initialize")
def initialize_optimization_area(
    project_id: str,
    area: str,
    body: GenerateIn | None = None,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    area_typed = _check_area(area)
    owned(project_id, u, db)
    prereq = evaluate_optimization_prerequisites(db, project_id)
    if not prereq["ready"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Upstream prerequisites must be approved with no open drafts before initializing.",
                "blocking_reasons": prereq["blocking_reasons"],
                "remediation_links": prereq["remediation_links"],
            },
        )
    basis = opt.build_optimization_basis(db, project_id)
    content_dict = opt.build_default_optimization_content(area_typed, basis)
    model_cls = opt.OPTIMIZATION_MODEL_MAP[area_typed]
    validated = model_cls.model_validate(content_dict).model_dump()

    supersede = body.supersede if body else False
    _persist_new_draft(
        db=db,
        project_id=project_id,
        area=area_typed,
        content_dict=validated,
        basis=basis,
        source="manual",
        ai_meta={"initialized_from_basis": True},
        supersede=supersede,
    )
    return _build_area_state(db, project_id, area_typed)


@router.post("/{area}/generate")
async def generate_optimization_area(
    project_id: str,
    area: str,
    body: GenerateIn | None = None,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    area_typed = _check_area(area)
    p = owned(project_id, u, db)
    prereq = evaluate_optimization_prerequisites(db, project_id)
    if not prereq["ready"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Upstream prerequisites must be approved with no open drafts before generating.",
                "blocking_reasons": prereq["blocking_reasons"],
                "remediation_links": prereq["remediation_links"],
            },
        )
    supersede = body.supersede if body else False
    _, draft, _ = _get_approved_and_draft(db, project_id, area_typed)
    if draft and not supersede:
        raise HTTPException(
            status_code=409,
            detail=f"An open {area_typed} draft (v{draft.version}) already exists. Pass supersede=true to replace it.",
        )

    basis = opt.build_optimization_basis(db, project_id)
    rev = latest_revision(db, p.id)
    prompt = opt.build_optimization_generation_prompt(area_typed, p.name, rev.snapshot, basis)
    schema_cls = opt.GENERATED_SCHEMA_MAP[area_typed]

    import asyncio
    try:
        provider = ai.get_provider()
    except ai.ProviderNotConfigured:
        raise HTTPException(status_code=503, detail="AI provider is not configured.")
    try:
        generated = await asyncio.wait_for(
            provider.generate_structured(prompt, schema_cls),
            timeout=settings.optimization_generation_timeout_seconds,
        )
        content_dict = generated.model_dump()
        trace = opt.OPTIMIZATION_TRACEABILITY_MAP[area_typed](generated, basis)
        err_findings = [f for f in trace.findings if f.severity == "error"]
        if err_findings:
            raise HTTPException(
                status_code=502,
                detail=f"AI output failed cross-artifact reference validation: {err_findings[0].message}",
            )
    except ai.ProviderNotConfigured:
        raise HTTPException(status_code=503, detail="AI provider is not configured.")
    except ai.ProviderError as exc:
        raise HTTPException(status_code=502, detail=ai.user_message(exc))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="AI generation timed out.")
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail=f"AI output failed schema validation: {exc}")

    _persist_new_draft(
        db=db,
        project_id=project_id,
        area=area_typed,
        content_dict=content_dict,
        basis=basis,
        source="ai",
        ai_meta={"provider": provider.__class__.__name__, "area": area_typed},
        supersede=supersede,
    )
    return _build_area_state(db, project_id, area_typed)


def _prepare_editable_draft(
    db: Session,
    project_id: str,
    area: opt.OptimizationArea,
    version: int,
    base_hash: str,
) -> tuple[OptimizationArtifact, int | None]:
    target = db.scalar(
        select(OptimizationArtifact).where(
            OptimizationArtifact.project_id == project_id,
            OptimizationArtifact.area == area,
            OptimizationArtifact.version == version,
        )
    )
    if not target:
        raise HTTPException(status_code=404, detail=f"{area} version {version} not found.")
    if target.content_hash != base_hash:
        raise HTTPException(
            status_code=409,
            detail="Content hash mismatch. Reload the latest version before saving changes.",
        )

    approved, draft, rows = _get_approved_and_draft(db, project_id, area)
    if target.status in ("draft", "in_review"):
        return target, None

    if target.status == "approved":
        if draft:
            raise HTTPException(
                status_code=409,
                detail=f"Open draft v{draft.version} already exists. Edit the open draft instead of approved v{target.version}.",
            )
        next_v = (max((r.version for r in rows), default=0)) + 1
        copied = OptimizationArtifact(
            project_id=project_id,
            area=area,
            version=next_v,
            status="draft",
            supersedes_version=target.version,
            generation_source="hybrid" if target.generation_source == "ai" else target.generation_source,
            ai_metadata=dict(target.ai_metadata or {}),
            content=dict(target.content),
            basis_summary=dict(target.basis_summary or {}),
            content_hash=target.content_hash,
        )
        db.add(copied)
        db.flush()
        return copied, target.version

    raise HTTPException(status_code=409, detail=f"Cannot edit {area} version with status '{target.status}'.")


@router.put("/{area}/versions/{version}")
def put_optimization_version(
    project_id: str,
    area: str,
    version: int,
    body: PutContentIn,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    area_typed = _check_area(area)
    owned(project_id, u, db)
    model_cls = opt.OPTIMIZATION_MODEL_MAP[area_typed]
    try:
        validated = model_cls.model_validate(body.content)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    basis = opt.build_optimization_basis(db, project_id)
    trace = opt.OPTIMIZATION_TRACEABILITY_MAP[area_typed](validated, basis)
    err_findings = [f for f in trace.findings if f.severity == "error" and not f.code.endswith("UNCOVERED")]
    if err_findings:
        raise HTTPException(status_code=422, detail=err_findings[0].message)

    with txn(db):
        editable, copied_from = _prepare_editable_draft(db, project_id, area_typed, version, body.base_hash)
        content_dict = validated.model_dump()
        editable.content = content_dict
        editable.content_hash = opt.compute_optimization_hash(area_typed, content_dict)
        editable.status = "draft"
        if editable.generation_source == "ai":
            editable.generation_source = "hybrid"
        editable.updated_at = now()
        db.flush()
        sync_optimization_stages(db, project_id)

    return {
        "state": _build_area_state(db, project_id, area_typed),
        "edited_version": editable.version,
        "copied_from_approved": copied_from,
    }


@router.patch("/{area}/versions/{version}/section")
def patch_optimization_section(
    project_id: str,
    area: str,
    version: int,
    body: PatchSectionIn,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    area_typed = _check_area(area)
    owned(project_id, u, db)
    target = db.scalar(
        select(OptimizationArtifact).where(
            OptimizationArtifact.project_id == project_id,
            OptimizationArtifact.area == area_typed,
            OptimizationArtifact.version == version,
        )
    )
    if not target:
        raise HTTPException(status_code=404, detail=f"{area_typed} version {version} not found.")
    if body.section not in target.content:
        raise HTTPException(status_code=422, detail=f"Unknown section '{body.section}' for {area_typed}.")

    candidate = dict(target.content)
    candidate[body.section] = body.value
    model_cls = opt.OPTIMIZATION_MODEL_MAP[area_typed]
    try:
        validated = model_cls.model_validate(candidate)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    basis = opt.build_optimization_basis(db, project_id)
    trace = opt.OPTIMIZATION_TRACEABILITY_MAP[area_typed](validated, basis)
    err_findings = [f for f in trace.findings if f.severity == "error" and not f.code.endswith("UNCOVERED")]
    if err_findings:
        raise HTTPException(status_code=422, detail=err_findings[0].message)

    with txn(db):
        editable, copied_from = _prepare_editable_draft(db, project_id, area_typed, version, body.base_hash)
        content_dict = validated.model_dump()
        editable.content = content_dict
        editable.content_hash = opt.compute_optimization_hash(area_typed, content_dict)
        editable.status = "draft"
        if editable.generation_source == "ai":
            editable.generation_source = "hybrid"
        editable.updated_at = now()
        db.flush()
        sync_optimization_stages(db, project_id)

    return {
        "state": _build_area_state(db, project_id, area_typed),
        "edited_version": editable.version,
        "copied_from_approved": copied_from,
    }


@router.post("/{area}/versions/{version}/submit")
def submit_optimization_version(
    project_id: str,
    area: str,
    version: int,
    body: Hashed,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    area_typed = _check_area(area)
    owned(project_id, u, db)
    doc = db.scalar(
        select(OptimizationArtifact).where(
            OptimizationArtifact.project_id == project_id,
            OptimizationArtifact.area == area_typed,
            OptimizationArtifact.version == version,
        )
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"{area_typed} version {version} not found.")
    if doc.status not in ("draft", "in_review"):
        raise HTTPException(status_code=409, detail=f"Only draft versions can be submitted (current: {doc.status}).")
    if doc.content_hash != body.base_hash:
        raise HTTPException(status_code=409, detail="Content hash mismatch on submit.")

    basis = opt.build_optimization_basis(db, project_id)
    comp = opt.evaluate_optimization_completeness(area_typed, doc.content, basis)
    if not comp.ready_for_submission:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"{area_typed} specification is incomplete and cannot be submitted.",
                "missing_fields": comp.missing_fields,
                "unresolved_constraint_errors": comp.unresolved_constraint_errors,
                "requires_review_items": comp.requires_review_items,
                "uncovered_requirement_ids": comp.uncovered_requirement_ids,
            },
        )

    with txn(db):
        doc.status = "in_review"
        doc.updated_at = now()
        db.flush()
        sync_optimization_stages(db, project_id)

    return _build_area_state(db, project_id, area_typed)


def _promote_proposed_items(area: opt.OptimizationArea, content: dict[str, Any]) -> dict[str, Any]:
    cloned = dict(content)
    if area == "seo":
        cloned["page_metadata"] = [
            {**p, "status": "confirmed" if p.get("status") == "proposed" else p.get("status")}
            for p in cloned.get("page_metadata", [])
        ]
        cloned["technical_checklist"] = [
            {**t, "status": "confirmed" if t.get("status") == "proposed" else t.get("status")}
            for t in cloned.get("technical_checklist", [])
        ]
    elif area == "analytics":
        cloned["events"] = [
            {**e, "status": "confirmed" if e.get("status") == "proposed" else e.get("status")}
            for e in cloned.get("events", [])
        ]
        cloned["reporting_views"] = [
            {**r, "status": "confirmed" if r.get("status") == "proposed" else r.get("status")}
            for r in cloned.get("reporting_views", [])
        ]
    else:
        cloned["route_budgets"] = [
            {**r, "status": "confirmed" if r.get("status") == "proposed" else r.get("status")}
            for r in cloned.get("route_budgets", [])
        ]
        cloned["api_budgets"] = [
            {**a, "status": "confirmed" if a.get("status") == "proposed" else a.get("status")}
            for a in cloned.get("api_budgets", [])
        ]
    return cloned


@router.post("/{area}/versions/{version}/approve")
def approve_optimization_version(
    project_id: str,
    area: str,
    version: int,
    body: ApproveIn,
    u: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    area_typed = _check_area(area)
    p = owned(project_id, u, db)
    prereq = evaluate_optimization_prerequisites(db, project_id)
    if not prereq["ready"]:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Cannot approve while upstream prerequisites are missing or have open drafts.",
                "blocking_reasons": prereq["blocking_reasons"],
                "remediation_links": prereq["remediation_links"],
            },
        )

    doc = db.scalar(
        select(OptimizationArtifact).where(
            OptimizationArtifact.project_id == project_id,
            OptimizationArtifact.area == area_typed,
            OptimizationArtifact.version == version,
        )
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"{area_typed} version {version} not found.")
    if doc.status not in ("draft", "in_review"):
        raise HTTPException(status_code=409, detail=f"Version {version} cannot be approved from status '{doc.status}'.")
    if doc.content_hash != body.content_hash:
        raise HTTPException(status_code=409, detail="Content hash mismatch on approve.")

    warnings = _compute_staleness_warnings(db, project_id, doc)
    if warnings:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Specification is stale relative to upstream artifacts. Regenerate or update before approving.",
                "warnings": warnings,
            },
        )

    basis = opt.build_optimization_basis(db, project_id)
    comp = opt.evaluate_optimization_completeness(area_typed, doc.content, basis)
    if not comp.ready_for_approval:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"{area_typed} specification is not ready for approval.",
                "missing_fields": comp.missing_fields,
                "unresolved_constraint_errors": comp.unresolved_constraint_errors,
                "requires_review_items": comp.requires_review_items,
                "uncovered_requirement_ids": comp.uncovered_requirement_ids,
            },
        )

    if comp.unverified_items and not body.acknowledge_unverified:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"{len(comp.unverified_items)} item(s) are still marked as 'proposed'. Confirm them or set acknowledge_unverified=true.",
                "unverified_items": comp.unverified_items,
            },
        )

    prev_approved, _, _ = _get_approved_and_draft(db, project_id, area_typed)
    ts = now()

    with txn(db):
        if prev_approved and prev_approved.id != doc.id:
            prev_approved.status = "superseded"
            prev_approved.updated_at = ts
            db.flush()

        if comp.unverified_items and body.acknowledge_unverified:
            promoted = _promote_proposed_items(area_typed, doc.content)
            doc.content = promoted
            doc.content_hash = opt.compute_optimization_hash(area_typed, promoted)

        doc.status = "approved"
        doc.approval_note = body.note
        doc.approved_at = ts
        doc.approved_by = u.id
        doc.updated_at = ts
        db.flush()

        # Update Project Brain optimization_spec pointer
        rev = latest_revision(db, p.id)
        brain_snap = dict(rev.snapshot or {})
        opt_brain = dict(brain_snap.get("optimization_spec") or {})
        opt_brain[area_typed] = {
            "approved_version": doc.version,
            "document_id": doc.id,
            "content_hash": doc.content_hash,
            "approved_at": as_utc(ts).isoformat(),
            "basis_versions": {
                k: v for k, v in (doc.basis_summary or {}).items() if k.endswith("_version") and isinstance(v, int)
            },
            "item_count": comp.item_count,
            "unverified_acknowledged": bool(comp.unverified_items and body.acknowledge_unverified),
        }
        commit_brain(db, p, {"optimization_spec": opt_brain}, f"optimization_{area_typed}_approved", u.id, commit=False)

        sync_optimization_stages(db, project_id)

    return _build_area_state(db, project_id, area_typed)
