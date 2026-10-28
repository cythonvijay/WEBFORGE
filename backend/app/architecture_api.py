"""Product Architecture workflow (Phase 13): routes, upstream Phase 9-12 prerequisite & staleness gates,
copy-on-write edits, exact-hash approval, and `architecture` lifecycle stage completion/invalidation.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai, architecture as arch, design as ds, ux
from .api import commit_brain, current_user, latest_revision, owned
from .config import settings
from .db import get_db
from .design_api import _doc_staleness as _design_staleness, design_stage_completion_check
from .discovery_api import txn
from .models import (
    ArchitectureDocument,
    DesignArtifact,
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

router = APIRouter(prefix="/projects/{project_id}/architecture")
HASH = Field(min_length=64, max_length=64)


class GenerateIn(BaseModel):
    supersede: bool = False


class Hashed(BaseModel):
    base_hash: str = HASH


class ApproveIn(BaseModel):
    content_hash: str = HASH
    acknowledge_unverified: bool = False
    note: str | None = Field(None, max_length=1000)


class ManualArchitectureInit(BaseModel):
    system_overview: dict
    application_architecture: dict
    data_architecture: dict
    api_architecture: dict
    deployment_architecture: dict
    decisions: list[dict]
    diagrams: list[dict]


class SystemOverviewPatch(Hashed):
    product_scope: str | None = None
    system_boundaries: list[str] | None = None
    user_roles_and_trust_boundaries: list[dict] | None = None


class ComponentIn(Hashed):
    name: str
    layer: arch.ComponentLayer = "backend"
    purpose: str
    responsibilities: list[str]
    communicates_with: list[str] = []
    prd_requirement_ids: list[str]
    design_refs: list[str] = []


class ComponentPatch(Hashed):
    name: str | None = None
    layer: arch.ComponentLayer | None = None
    purpose: str | None = None
    responsibilities: list[str] | None = None
    communicates_with: list[str] | None = None
    prd_requirement_ids: list[str] | None = None
    design_refs: list[str] | None = None


class IntegrationIn(Hashed):
    name: str
    purpose: str
    protocol_or_contract: str
    failure_mode_and_fallback: str
    implementation_status: arch.ImplementationStatus = "proposed_target"
    prd_requirement_ids: list[str]


class IntegrationPatch(Hashed):
    name: str | None = None
    purpose: str | None = None
    protocol_or_contract: str | None = None
    failure_mode_and_fallback: str | None = None
    implementation_status: arch.ImplementationStatus | None = None
    prd_requirement_ids: list[str] | None = None


class ApplicationPatch(Hashed):
    frontend_boundaries: list[dict] | None = None
    backend_modules: list[dict] | None = None
    authentication_and_authorization: str | None = None
    state_management_and_data_fetching: str | None = None
    error_handling_and_logging: str | None = None
    configuration_and_env_separation: str | None = None


class EntityIn(Hashed):
    name: str
    description: str
    owning_component_id: str
    key_fields: list[str]
    access_boundary: str
    retention_and_lifecycle: str
    sensitive_data_handling: str
    status: arch.EntityDecisionStatus = "proposed"
    prd_requirement_ids: list[str]


class EntityPatch(Hashed):
    name: str | None = None
    description: str | None = None
    owning_component_id: str | None = None
    key_fields: list[str] | None = None
    access_boundary: str | None = None
    retention_and_lifecycle: str | None = None
    sensitive_data_handling: str | None = None
    status: arch.EntityDecisionStatus | None = None
    prd_requirement_ids: list[str] | None = None


class RelationshipIn(Hashed):
    source_entity_id: str
    target_entity_id: str
    cardinality: arch.RelationshipCardinality = "1:N"
    description: str


class DataPoliciesPatch(Hashed):
    relationships: list[dict] | None = None
    transaction_and_integrity_rules: list[str] | None = None
    migration_strategy: str | None = None


class EndpointIn(Hashed):
    method: arch.HttpMethod = "GET"
    path: str
    summary: str
    component_id: str
    entity_ids: list[str] = []
    auth_requirement: arch.ApiAuthRequirement = "authenticated"
    request_contract: str
    response_contract: str
    validation_and_error_handling: str
    pagination_and_filtering: str = "Not applicable for single-resource operation"
    implementation_status: arch.ImplementationStatus = "proposed_target"
    prototype_screen_ids: list[str] = []
    prd_requirement_ids: list[str]


class EndpointPatch(Hashed):
    method: arch.HttpMethod | None = None
    path: str | None = None
    summary: str | None = None
    component_id: str | None = None
    entity_ids: list[str] | None = None
    auth_requirement: arch.ApiAuthRequirement | None = None
    request_contract: str | None = None
    response_contract: str | None = None
    validation_and_error_handling: str | None = None
    pagination_and_filtering: str | None = None
    implementation_status: arch.ImplementationStatus | None = None
    prototype_screen_ids: list[str] | None = None
    prd_requirement_ids: list[str] | None = None


class ApiConventionsPatch(Hashed):
    request_response_conventions: str | None = None
    validation_and_error_conventions: str | None = None
    integration_contracts_and_failure_behavior: str | None = None


class DeploymentPatch(Hashed):
    local_development_environment: str | None = None
    services_and_infrastructure: list[dict] | None = None
    configuration_and_secret_management: str | None = None
    deployment_boundaries: str | None = None
    health_checks_and_observability: str | None = None
    backup_recovery_and_failure: str | None = None


class DecisionIn(Hashed):
    title: str
    status: arch.DecisionStatus = "proposed"
    context_and_problem: str
    decision: str
    alternatives_and_tradeoffs: list[str]
    rationale: str
    consequences_and_risks: list[str]
    prd_requirement_ids: list[str]
    source_refs: list[str]


class DecisionPatch(Hashed):
    title: str | None = None
    status: arch.DecisionStatus | None = None
    context_and_problem: str | None = None
    decision: str | None = None
    alternatives_and_tradeoffs: list[str] | None = None
    rationale: str | None = None
    consequences_and_risks: list[str] | None = None
    prd_requirement_ids: list[str] | None = None
    source_refs: list[str] | None = None


class DiagramIn(Hashed):
    diagram_type: arch.DiagramType = "component"
    title: str
    summary: str
    nodes: list[dict]
    edges: list[dict]
    mermaid: str | None = None


class DiagramPatch(Hashed):
    diagram_type: arch.DiagramType | None = None
    title: str | None = None
    summary: str | None = None
    nodes: list[dict] | None = None
    edges: list[dict] | None = None
    mermaid: str | None = None


# ---------- DB & upstream helpers ----------
def _iso(d: datetime | None) -> str | None:
    return as_utc(d).isoformat() if d else None


def _stage(db: Session, pid: str, name: str = "architecture") -> ProjectStage:
    return db.scalar(select(ProjectStage).where(ProjectStage.project_id == pid, ProjectStage.stage == name))


def _all_arch(db: Session, pid: str) -> list[ArchitectureDocument]:
    return list(
        db.scalars(
            select(ArchitectureDocument)
            .where(ArchitectureDocument.project_id == pid)
            .order_by(ArchitectureDocument.version.desc())
        )
    )


def _stale_gen(r: ArchitectureDocument) -> bool:
    return r.status == "generating" and as_utc(r.updated_at) < datetime.now(timezone.utc) - timedelta(
        seconds=settings.architecture_generation_timeout_seconds
    )


def _upstream_state(db: Session, pid: str) -> dict[str, Any]:
    res_rows = list(
        db.scalars(
            select(ResearchReport)
            .where(ResearchReport.project_id == pid, ResearchReport.status != "failed")
            .order_by(ResearchReport.version.desc())
        )
    )
    stg_rows = list(
        db.scalars(
            select(StrategyDocument)
            .where(StrategyDocument.project_id == pid, StrategyDocument.status != "failed")
            .order_by(StrategyDocument.version.desc())
        )
    )
    prd_rows = list(
        db.scalars(
            select(PrdDocument)
            .where(PrdDocument.project_id == pid, PrdDocument.status != "failed")
            .order_by(PrdDocument.version.desc())
        )
    )

    res_open = next((r for r in res_rows if r.status in ("draft", "in_review", "generating")), None)
    res_app = next((r for r in res_rows if r.status == "approved"), None)

    stg_open = next((r for r in stg_rows if r.status in ("draft", "in_review", "generating")), None)
    stg_app = next((r for r in stg_rows if r.status == "approved"), None)

    prd_open = next((r for r in prd_rows if r.status in ("draft", "in_review", "generating")), None)
    prd_app = next((r for r in prd_rows if r.status == "approved"), None)

    ux_by_type: dict[ux.ArtifactType, dict[str, UxArtifact | None]] = {}
    for t in ux.ARTIFACT_TYPES:
        rows = list(
            db.scalars(
                select(UxArtifact)
                .where(UxArtifact.project_id == pid, UxArtifact.artifact_type == t, UxArtifact.status != "failed")
                .order_by(UxArtifact.version.desc())
            )
        )
        ux_by_type[t] = {
            "open": next((r for r in rows if r.status in ("draft", "in_review", "generating")), None),
            "approved": next((r for r in rows if r.status == "approved"), None),
        }

    design_by_type: dict[ds.DesignArtifactType, dict[str, DesignArtifact | None]] = {}
    for t in ds.DESIGN_ARTIFACT_TYPES:
        rows = list(
            db.scalars(
                select(DesignArtifact)
                .where(DesignArtifact.project_id == pid, DesignArtifact.artifact_type == t, DesignArtifact.status != "failed")
                .order_by(DesignArtifact.version.desc())
            )
        )
        design_by_type[t] = {
            "open": next((r for r in rows if r.status in ("draft", "in_review", "generating")), None),
            "approved": next((r for r in rows if r.status == "approved"), None),
        }

    res_stage = _stage(db, pid, "research")
    prod_stage = _stage(db, pid, "product")
    ux_stage = _stage(db, pid, "ux")
    design_stage = _stage(db, pid, "design")
    ux_ok, ux_reasons = ux_stage_completion_check(db, pid)
    design_ok, design_reasons = design_stage_completion_check(db, pid)

    return {
        "res_stage": res_stage.status if res_stage else "not_started",
        "prod_stage": prod_stage.status if prod_stage else "not_started",
        "ux_stage": ux_stage.status if ux_stage else "not_started",
        "design_stage": design_stage.status if design_stage else "not_started",
        "ux_ok": ux_ok,
        "ux_reasons": ux_reasons,
        "design_ok": design_ok,
        "design_reasons": design_reasons,
        "res_open": res_open,
        "res_app": res_app,
        "stg_open": stg_open,
        "stg_app": stg_app,
        "prd_open": prd_open,
        "prd_app": prd_app,
        "ux": ux_by_type,
        "design": design_by_type,
    }


def check_prerequisites(db: Session, pid: str) -> dict[str, Any]:
    """Verify upstream Phase 9 (Research), Phase 10 (Strategy & PRD), Phase 11 (UX), and Phase 12 (Design System & Prototype) prerequisites."""
    up = _upstream_state(db, pid)
    missing: list[dict[str, str]] = []

    if up["res_stage"] != "complete" or up["res_app"] is None or up["res_open"] is not None:
        missing.append(
            {
                "artifact": "research",
                "label": "Research",
                "message": "Research has an unapproved draft in progress."
                if up["res_open"]
                else "Approve your Research report first.",
                "workspace_path": f"/projects/{pid}/research",
            }
        )
    if up["stg_app"] is None or up["stg_open"] is not None:
        missing.append(
            {
                "artifact": "strategy",
                "label": "Product Strategy",
                "message": "Product Strategy has an unapproved draft in progress."
                if up["stg_open"]
                else "Approve your Product Strategy first.",
                "workspace_path": f"/projects/{pid}/strategy",
            }
        )
    if up["prd_app"] is None or up["prd_open"] is not None or up["prod_stage"] != "complete":
        missing.append(
            {
                "artifact": "prd",
                "label": "PRD",
                "message": "PRD has an unapproved draft in progress."
                if up["prd_open"]
                else "Approve your PRD first.",
                "workspace_path": f"/projects/{pid}/prd",
            }
        )

    ux_labels = {
        "personas": "Personas",
        "journeys": "User Journeys",
        "ia": "Information Architecture",
        "wireframes": "Wireframes",
        "ux_review": "UX Review",
    }
    for t in ux.ARTIFACT_TYPES:
        u_app = up["ux"][t]["approved"]
        u_open = up["ux"][t]["open"]
        wpath = f"/projects/{pid}/{UX_PATHS[t]}"
        if u_app is None or u_open is not None:
            missing.append(
                {
                    "artifact": t,
                    "label": ux_labels[t],
                    "message": f"{ux_labels[t]} has an unapproved draft open; approve it first."
                    if u_open
                    else f"Approve {ux_labels[t]} before starting Phase 13 Product Architecture.",
                    "workspace_path": wpath,
                }
            )
        elif t == "ux_review" and u_app.content:
            rc = ux.review_counts(u_app.content)
            if rc["critical_open"] > 0:
                missing.append(
                    {
                        "artifact": "ux_review",
                        "label": "UX Review",
                        "message": f"UX Review has {rc['critical_open']} unresolved critical finding(s).",
                        "workspace_path": wpath,
                    }
                )

    if not missing and (up["ux_stage"] != "complete" or not up["ux_ok"]):
        reason = up["ux_reasons"][0] if up["ux_reasons"] else "Complete and approve all Phase 11 UX artifacts first."
        missing.append(
            {
                "artifact": "ux_review",
                "label": "UX Review",
                "message": reason,
                "workspace_path": f"/projects/{pid}/ux-review",
            }
        )

    design_meta = {
        "design_system": ("Design System", f"/projects/{pid}/design-system"),
        "prototype": ("Interactive Prototype", f"/projects/{pid}/prototype"),
    }
    for dt in ds.DESIGN_ARTIFACT_TYPES:
        d_label, d_path = design_meta[dt]
        d_app = up["design"][dt]["approved"]
        d_open = up["design"][dt]["open"]
        if d_app is None or d_open is not None:
            missing.append(
                {
                    "artifact": dt,
                    "label": d_label,
                    "message": f"{d_label} has an unapproved draft open; approve it first."
                    if d_open
                    else f"Approve your {d_label} before starting Phase 13 Product Architecture.",
                    "workspace_path": d_path,
                }
            )
        else:
            d_stale = _design_staleness(d_app, up)
            if d_stale:
                missing.append(
                    {
                        "artifact": dt,
                        "label": d_label,
                        "message": f"Approved {d_label} v{d_app.version} is stale ({d_stale[0]}). Update and re-approve {d_label} first.",
                        "workspace_path": d_path,
                    }
                )

    if not missing and (up["design_stage"] != "complete" or not up["design_ok"]):
        reason = up["design_reasons"][0] if up["design_reasons"] else "Complete and approve Phase 12 Design System and Interactive Prototype first."
        missing.append(
            {
                "artifact": "prototype",
                "label": "Interactive Prototype",
                "message": reason,
                "workspace_path": f"/projects/{pid}/prototype",
            }
        )

    return {
        "ready": len(missing) == 0,
        "missing": missing,
        "upstream_versions": {
            "research": up["res_app"].version if up["res_app"] else None,
            "strategy": up["stg_app"].version if up["stg_app"] else None,
            "prd": up["prd_app"].version if up["prd_app"] else None,
            "personas": up["ux"]["personas"]["approved"].version if up["ux"]["personas"]["approved"] else None,
            "journeys": up["ux"]["journeys"]["approved"].version if up["ux"]["journeys"]["approved"] else None,
            "ia": up["ux"]["ia"]["approved"].version if up["ux"]["ia"]["approved"] else None,
            "wireframes": up["ux"]["wireframes"]["approved"].version if up["ux"]["wireframes"]["approved"] else None,
            "ux_review": up["ux"]["ux_review"]["approved"].version if up["ux"]["ux_review"]["approved"] else None,
            "design_system": up["design"]["design_system"]["approved"].version if up["design"]["design_system"]["approved"] else None,
            "prototype": up["design"]["prototype"]["approved"].version if up["design"]["prototype"]["approved"] else None,
        },
        "_up": up,
    }


def _doc_staleness(doc: ArchitectureDocument | None, up: dict[str, Any]) -> list[str]:
    if doc is None:
        return []
    reasons: list[str] = []
    b = doc.basis or {}
    if up["res_open"] is not None or (up["res_app"] and b.get("research_version") != up["res_app"].version):
        reasons.append("Upstream Research changed since this architecture version was created.")
    if up["stg_open"] is not None or (up["stg_app"] and b.get("strategy_version") != up["stg_app"].version):
        reasons.append("Upstream Product Strategy changed since this architecture version was created.")
    if up["prd_open"] is not None or (up["prd_app"] and b.get("prd_version") != up["prd_app"].version):
        reasons.append(
            f"Built from PRD v{b.get('prd_version')}, while PRD v{up['prd_app'].version if up['prd_app'] else '?'} is now current."
        )
    elif up["prd_app"] and b.get("prd_hash") and b.get("prd_hash") != up["prd_app"].content_hash:
        reasons.append("Upstream PRD content hash changed since this architecture version was created.")

    ux_labels = {
        "personas": "Personas",
        "journeys": "User Journeys",
        "ia": "Information Architecture",
        "wireframes": "Wireframes",
        "ux_review": "UX Review",
    }
    for t in ux.ARTIFACT_TYPES:
        u_open = up["ux"][t]["open"]
        u_app = up["ux"][t]["approved"]
        if u_open is not None:
            reasons.append(f"{ux_labels[t]} has an unapproved draft open.")
        elif u_app and b.get(f"{t}_version") != u_app.version:
            reasons.append(
                f"Built from {ux_labels[t]} v{b.get(f'{t}_version')}, while {ux_labels[t]} v{u_app.version} is now approved."
            )

    design_labels = {"design_system": "Design System", "prototype": "Interactive Prototype"}
    for dt in ds.DESIGN_ARTIFACT_TYPES:
        d_open = up["design"][dt]["open"]
        d_app = up["design"][dt]["approved"]
        if d_open is not None:
            reasons.append(f"{design_labels[dt]} has an unapproved draft open.")
        elif d_app and b.get(f"{dt}_version") != d_app.version:
            reasons.append(
                f"Built from {design_labels[dt]} v{b.get(f'{dt}_version')}, while {design_labels[dt]} v{d_app.version} is now approved."
            )
        elif d_app and b.get(f"{dt}_hash") and b.get(f"{dt}_hash") != d_app.content_hash:
            reasons.append(f"Upstream {design_labels[dt]} content hash changed.")
        elif d_app:
            d_stale = _design_staleness(d_app, up)
            if d_stale:
                reasons.append(f"Upstream {design_labels[dt]} is stale: {d_stale[0]}")

    return reasons


def architecture_stage_completion_check(db: Session, pid: str) -> tuple[bool, list[str]]:
    """Verify whether the `architecture` lifecycle stage meets all documented completion criteria."""
    up = _upstream_state(db, pid)
    reasons: list[str] = []
    if up["prod_stage"] != "complete":
        reasons.append("Upstream Product stage (Strategy & PRD) must be complete and current.")
    if up["ux_stage"] != "complete" or not up["ux_ok"]:
        reasons.append("Upstream UX stage must be complete and current.")
    if up["design_stage"] != "complete" or not up["design_ok"]:
        reasons.append("Upstream Design stage (Design System & Interactive Prototype) must be complete and current.")

    rows = [r for r in _all_arch(db, pid) if r.status != "failed"]
    open_doc = next(
        (r for r in rows if r.status in ("draft", "in_review") or (r.status == "generating" and not _stale_gen(r))),
        None,
    )
    app_doc = next((r for r in rows if r.status == "approved"), None)

    if app_doc is None:
        reasons.append("Product Architecture has not been approved yet.")
    elif open_doc is not None:
        reasons.append(f"Product Architecture has an unapproved draft (v{open_doc.version}) open.")
    else:
        st_reasons = _doc_staleness(app_doc, up)
        if st_reasons:
            reasons.append(f"Product Architecture v{app_doc.version} is stale: {st_reasons[0]}")
        elif app_doc.content:
            comp_check = arch.evaluate_architecture_completeness(app_doc.content)
            if not comp_check["complete_traceability"]:
                reasons.append("Approved Product Architecture is missing complete requirement traceability.")
    return len(reasons) == 0, reasons


def sync_architecture_stage(db: Session, pid: str) -> None:
    """Synchronize the `architecture` lifecycle stage based on persisted ArchitectureDocument rows and upstream state."""
    from .optimization_api import sync_optimization_stages

    st = _stage(db, pid, "architecture")
    if st is None:
        return
    all_rows = [r for r in _all_arch(db, pid) if r.status != "failed"]
    if not all_rows:
        sync_optimization_stages(db, pid)
        return
    complete_ok, _ = architecture_stage_completion_check(db, pid)
    if complete_ok:
        st.status = "complete"
        sync_optimization_stages(db, pid)
        return
    any_in_review = any(r.status == "in_review" for r in all_rows)
    any_draft = any(r.status == "draft" for r in all_rows)
    prod_ok = _stage(db, pid, "product").status == "complete"
    design_ok = _stage(db, pid, "design").status == "complete"
    if any_in_review and not any_draft and prod_ok and design_ok:
        st.status = "needs_review"
    else:
        if st.status in ("complete", "needs_review") or any(r.status in ("draft", "approved") for r in all_rows):
            if (prod_ok and design_ok) or st.status in ("complete", "needs_review"):
                st.status = "in_progress"
    sync_optimization_stages(db, pid)


def _build_basis_and_summary(db: Session, pid: str) -> tuple[dict, arch.ArchitectureBasisSummary, dict[str, Any]]:
    prereq = check_prerequisites(db, pid)
    if not prereq["ready"]:
        raise HTTPException(
            409,
            {
                "message": prereq["missing"][0]["message"],
                "missing": prereq["missing"],
            },
        )
    up = prereq["_up"]
    res_app, stg_app, prd_app = up["res_app"], up["stg_app"], up["prd_app"]
    p_app = up["ux"]["personas"]["approved"]
    j_app = up["ux"]["journeys"]["approved"]
    ia_app = up["ux"]["ia"]["approved"]
    wf_app = up["ux"]["wireframes"]["approved"]
    rev_app = up["ux"]["ux_review"]["approved"]
    ds_app = up["design"]["design_system"]["approved"]
    proto_app = up["design"]["prototype"]["approved"]

    summary = arch.build_architecture_basis(
        research_ver=res_app.version,
        strategy_ver=stg_app.version,
        prd_doc=prd_app.content,
        prd_ver=prd_app.version,
        personas_doc=p_app.content,
        personas_ver=p_app.version,
        journeys_doc=j_app.content,
        journeys_ver=j_app.version,
        ia_doc=ia_app.content,
        ia_ver=ia_app.version,
        wireframes_doc=wf_app.content,
        wireframes_ver=wf_app.version,
        ux_review_doc=rev_app.content,
        ux_review_ver=rev_app.version,
        design_system_doc=ds_app.content,
        design_system_ver=ds_app.version,
        prototype_doc=proto_app.content,
        prototype_ver=proto_app.version,
    )
    basis_meta = {
        "brain_version": latest_revision(db, pid).version,
        "research_id": res_app.id,
        "research_version": res_app.version,
        "research_hash": res_app.content_hash,
        "strategy_id": stg_app.id,
        "strategy_version": stg_app.version,
        "strategy_hash": stg_app.content_hash,
        "prd_id": prd_app.id,
        "prd_version": prd_app.version,
        "prd_hash": prd_app.content_hash,
        "personas_id": p_app.id,
        "personas_version": p_app.version,
        "personas_hash": p_app.content_hash,
        "journeys_id": j_app.id,
        "journeys_version": j_app.version,
        "journeys_hash": j_app.content_hash,
        "ia_id": ia_app.id,
        "ia_version": ia_app.version,
        "ia_hash": ia_app.content_hash,
        "wireframes_id": wf_app.id,
        "wireframes_version": wf_app.version,
        "wireframes_hash": wf_app.content_hash,
        "ux_review_id": rev_app.id,
        "ux_review_version": rev_app.version,
        "ux_review_hash": rev_app.content_hash,
        "design_system_id": ds_app.id,
        "design_system_version": ds_app.version,
        "design_system_hash": ds_app.content_hash,
        "prototype_id": proto_app.id,
        "prototype_version": proto_app.version,
        "prototype_hash": proto_app.content_hash,
    }
    return basis_meta, summary, up


def _item_count(content: dict | None) -> int:
    if not content:
        return 0
    return (
        len(content.get("system_overview", {}).get("components", []))
        + len(content.get("data_architecture", {}).get("entities", []))
        + len(content.get("api_architecture", {}).get("endpoints", []))
        + len(content.get("decisions", []))
        + len(content.get("diagrams", []))
    )


def _unverified_count(content: dict | None) -> int:
    if not content:
        return 0
    decisions_unv = sum(
        d.get("status") in ("proposed", "requires_review") for d in content.get("decisions", [])
    )
    entities_unv = sum(
        e.get("status") in ("proposed", "requires_review")
        for e in content.get("data_architecture", {}).get("entities", [])
    )
    return decisions_unv + entities_unv


def _warnings(doc: ArchitectureDocument, stale_reasons: list[str]) -> list[dict[str, str]]:
    w: list[dict[str, str]] = []
    for reason in stale_reasons:
        w.append({"code": "stale_upstream", "message": reason})
    c = doc.content
    if not c:
        return w
    comp_eval = arch.evaluate_architecture_completeness(c)
    if comp_eval["uncovered_requirements"]:
        w.append(
            {
                "code": "uncovered_requirements",
                "message": f"PRD requirements lacking full architecture traceability: {', '.join(comp_eval['uncovered_requirements'])}",
            }
        )
    if comp_eval["unreferenced_components"]:
        w.append(
            {
                "code": "unreferenced_components",
                "message": f"Architecture components not linked to modules/entities/endpoints: {', '.join(comp_eval['unreferenced_components'])}",
            }
        )
    if comp_eval["requires_review_decisions"] or comp_eval["requires_review_entities"]:
        items = comp_eval["requires_review_decisions"] + comp_eval["requires_review_entities"]
        w.append(
            {
                "code": "requires_review",
                "message": f"Items marked 'requires_review' must be resolved before submission: {', '.join(items)}",
            }
        )
    if comp_eval["proposed_decisions"]:
        w.append(
            {
                "code": "proposed_decisions",
                "message": f"{len(comp_eval['proposed_decisions'])} technical decision(s) are marked 'proposed' ({', '.join(comp_eval['proposed_decisions'])}).",
            }
        )
    return w


def _summary(r: ArchitectureDocument) -> dict:
    return {
        "version": r.version,
        "status": r.status,
        "created_via": r.created_via,
        "parent_version": r.parent_version,
        "created_at": _iso(r.created_at),
        "updated_at": _iso(r.updated_at),
        "submitted_at": _iso(r.submitted_at),
        "approved_at": _iso(r.approved_at),
        "content_hash": r.content_hash,
        "item_count": _item_count(r.content),
        "error": r.error,
    }


def _out(r: ArchitectureDocument, up: dict[str, Any]) -> dict:
    stale_reasons = _doc_staleness(r, up)
    comp_eval = arch.evaluate_architecture_completeness(r.content) if r.content else None
    return {
        **_summary(r),
        "id": r.id,
        "content": r.content,
        "basis": r.basis,
        "approval_note": r.approval_note,
        "acknowledged_unverified": r.acknowledged_unverified,
        "brain_revision": r.brain_revision,
        "unverified_count": _unverified_count(r.content),
        "completeness": comp_eval,
        "is_stale": len(stale_reasons) > 0,
        "stale_reasons": stale_reasons,
        "editable": r.status in ("draft", "in_review"),
        "warnings": _warnings(r, stale_reasons),
    }


def build_architecture_state(db: Session, project: Project) -> dict:
    prereq = check_prerequisites(db, project.id)
    up = prereq["_up"]
    rows = _all_arch(db, project.id)
    gen = next((r for r in rows if r.status == "generating" and not _stale_gen(r)), None)
    open_ = next((r for r in rows if r.status in ("draft", "in_review")), None)
    approved = next((r for r in rows if r.status == "approved"), None)
    current = open_ or approved
    failed = rows[0] if rows and (rows[0].status == "failed" or _stale_gen(rows[0])) else None
    status = "generating" if gen else (current.status if current else ("failed" if failed else "not_started"))

    cur_out = _out(current, up) if current else None
    is_stale = cur_out["is_stale"] if cur_out else False
    stale_reasons = cur_out["stale_reasons"] if cur_out else []
    comp_eval = cur_out["completeness"] if cur_out else None
    traceability_ok = bool(
        comp_eval
        and comp_eval["complete_traceability"]
        and not comp_eval["requires_review_decisions"]
        and not comp_eval["requires_review_entities"]
    )

    basis_preview = None
    if prereq["ready"] and not current:
        _, b_sum, _ = _build_basis_and_summary(db, project.id)
        basis_preview = b_sum.model_dump(mode="json")

    step = (
        {
            "key": "fix_prerequisites",
            "label": prereq["missing"][0]["message"],
            "workspace_path": prereq["missing"][0]["workspace_path"],
        }
        if not prereq["ready"]
        else {"key": "wait", "label": "Product Architecture is being generated"}
        if gen
        else {"key": "retry_generation", "label": "Retry generating Product Architecture"}
        if status == "failed"
        else {
            "key": "start",
            "label": "Generate Product Architecture from approved PRD, UX, Design System, and Prototype",
        }
        if status == "not_started"
        else {
            "key": "stale_upstream",
            "label": f"Upstream artifacts changed ({stale_reasons[0]}). Regenerate or update this architecture.",
        }
        if is_stale
        else {
            "key": "resolve_gaps",
            "label": "Resolve uncovered requirements or items marked 'requires_review' before submitting",
        }
        if status == "draft" and not traceability_ok
        else {
            "key": "review_and_submit",
            "label": "Review components, data entities, APIs, decisions, and diagrams, then submit for review",
        }
        if status == "draft"
        else {"key": "approve", "label": "Approve this Product Architecture version"}
        if status == "in_review"
        else {
            "key": "approved",
            "label": "Product Architecture approved — Architecture stage complete",
            "workspace_path": f"/projects/{project.id}/overview",
        }
    )

    arch_complete, arch_missing = architecture_stage_completion_check(db, project.id)
    downstream = {
        s: _stage(db, project.id, s).status
        for s in ("frontend", "backend", "database", "api")
        if _stage(db, project.id, s) is not None
    }
    return {
        "status": status,
        "prerequisites": {k: v for k, v in prereq.items() if k != "_up"},
        "is_stale": is_stale,
        "stale_reasons": stale_reasons,
        "current": cur_out,
        "approved_version": approved.version if approved else None,
        "history": [_summary(r) for r in rows if r.status != "failed" or r.content is not None],
        "last_error": failed.error if failed else None,
        "basis_preview": basis_preview,
        "lifecycle": {
            "stage": "architecture",
            "status": _stage(db, project.id, "architecture").status,
            "architecture_complete": arch_complete,
            "pending_criteria": arch_missing,
            "downstream_stages": downstream,
        },
        "next_step": step,
        "can_generate": prereq["ready"] and gen is None,
        "needs_supersede": open_ is not None,
        "can_submit": bool(
            current and current.status == "draft" and traceability_ok and prereq["ready"] and not is_stale
        ),
        "can_approve": bool(
            current and current.status == "in_review" and traceability_ok and prereq["ready"] and not is_stale
        ),
        "limitations": arch.ARCHITECTURE_LIMITATIONS,
    }


def _get_doc(db: Session, project: Project, version: int, lock: bool = False) -> ArchitectureDocument:
    q = select(ArchitectureDocument).where(
        ArchitectureDocument.project_id == project.id,
        ArchitectureDocument.version == version,
    )
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None:
        raise HTTPException(404, f"Architecture version {version} not found.")
    return r


def _validation_error(e: ValidationError) -> HTTPException:
    items = [
        {"loc": ["body", *map(str, x["loc"])], "msg": x["msg"].removeprefix("Value error, ")}
        for x in e.errors(include_input=False, include_url=False)
    ]
    return HTTPException(422, items)


def _next_id(prefix: str, items: list[dict]) -> str:
    n = [
        int(i["id"].split("-")[-1])
        for i in items
        if i.get("id", "").startswith(prefix + "-") and i["id"].split("-")[-1].isdigit()
    ]
    return f"{prefix}-{max(n, default=0) + 1}"


# ---------- Routes ----------
@router.get("")
def get_architecture(project: Project = Depends(owned), db: Session = Depends(get_db)):
    return build_architecture_state(db, project)


@router.get("/versions/{version}")
def get_architecture_version(version: int, project: Project = Depends(owned), db: Session = Depends(get_db)):
    up = _upstream_state(db, project.id)
    return _out(_get_doc(db, project, version), up)


@router.post("/generate")
async def generate_architecture(
    body: GenerateIn,
    project: Project = Depends(owned),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    basis_meta, basis_summary, up = _build_basis_and_summary(db, project.id)
    prd_content = up["prd_app"].content
    p_content = up["ux"]["personas"]["approved"].content
    j_content = up["ux"]["journeys"]["approved"].content
    ia_content = up["ux"]["ia"]["approved"].content
    wf_content = up["ux"]["wireframes"]["approved"].content
    rev_content = up["ux"]["ux_review"]["approved"].content
    ds_content = up["design"]["design_system"]["approved"].content
    proto_content = up["design"]["prototype"]["approved"].content

    with txn(db):
        db.get(Project, project.id, with_for_update=True, populate_existing=True)
        rows = _all_arch(db, project.id)
        gen = next((r for r in rows if r.status == "generating"), None)
        if gen and not _stale_gen(gen):
            raise HTTPException(409, "Product Architecture is already being generated.")
        if any(r.status in ("draft", "in_review") for r in rows) and not body.supersede:
            raise HTTPException(
                409,
                "A draft already exists. Edit it, or regenerate with supersede=true to keep it in history and start a new version.",
            )
        retry = gen or (rows[0] if rows and rows[0].status == "failed" else None)
        approved = next((r for r in rows if r.status == "approved"), None)
        if retry:
            retry.status, retry.error, retry.basis, retry.content, retry.content_hash = (
                "generating",
                None,
                basis_meta,
                None,
                None,
            )
            retry.parent_version = approved.version if approved else None
            row = retry
        else:
            row = ArchitectureDocument(
                project_id=project.id,
                version=(rows[0].version + 1) if rows else 1,
                status="generating",
                basis=basis_meta,
                parent_version=approved.version if approved else None,
                created_via="generated",
                created_by=user.id,
            )
            db.add(row)
        db.flush()
        doc_id = row.id

    try:
        prov = ai.get_provider()
        gen_out = await prov.generate_structured(
            arch.build_architecture_prompt(
                project.name,
                prd_content,
                p_content,
                j_content,
                ia_content,
                wf_content,
                rev_content,
                ds_content,
                proto_content,
                basis_summary,
            ),
            arch.GeneratedArchitecture,
        )
        content_obj = arch.to_architecture_content(gen_out, basis_summary)
        stored = content_obj.model_dump(mode="json")
        failure = None
    except (ai.ProviderNotConfigured, ai.ProviderError, ValidationError, ValueError) as e:
        failure = e

    if failure is not None:
        unconfigured = isinstance(failure, ai.ProviderNotConfigured)
        msg = (
            "AI provider not configured."
            if unconfigured
            else (ai.user_message(failure) if isinstance(failure, ai.ProviderError) else ai.USER_MESSAGES["malformed"])
        )
        with txn(db):
            r = db.get(ArchitectureDocument, doc_id, with_for_update=True, populate_existing=True)
            if r.status == "generating":
                r.status, r.error = "failed", msg
        raise HTTPException(503 if unconfigured else 502, f"{msg} Nothing was changed.")

    with txn(db):
        r = db.get(ArchitectureDocument, doc_id, with_for_update=True, populate_existing=True)
        if r.status != "generating":
            raise HTTPException(409, "Another request changed this Architecture document.")
        for old in _all_arch(db, project.id):
            if old.id != doc_id and old.status in ("draft", "in_review"):
                old.status = "superseded"
        db.flush()
        r.status, r.content, r.content_hash, r.error = "draft", stored, arch.content_hash(stored), None
        sync_architecture_stage(db, project.id)
    return build_architecture_state(db, project)


@router.post("/manual")
def create_manual_architecture(
    body: ManualArchitectureInit,
    project: Project = Depends(owned),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Create a manual Product Architecture draft when the AI provider is unconfigured."""
    basis_meta, basis_summary, _ = _build_basis_and_summary(db, project.id)
    with txn(db):
        rows = _all_arch(db, project.id)
        if any(r.status in ("draft", "in_review", "generating") for r in rows):
            raise HTTPException(409, "An open Architecture draft already exists. Edit that version instead.")
        try:
            content_obj = arch.ArchitectureContent(
                basis=basis_summary,
                system_overview=body.system_overview,
                application_architecture=body.application_architecture,
                data_architecture=body.data_architecture,
                api_architecture=body.api_architecture,
                deployment_architecture=body.deployment_architecture,
                decisions=body.decisions,
                diagrams=body.diagrams,
            )
            stored = content_obj.model_dump(mode="json")
        except ValidationError as e:
            raise _validation_error(e) from None
        approved = next((r for r in rows if r.status == "approved"), None)
        row = ArchitectureDocument(
            project_id=project.id,
            version=(rows[0].version + 1) if rows else 1,
            status="draft",
            content=stored,
            content_hash=arch.content_hash(stored),
            basis=basis_meta,
            parent_version=approved.version if approved else None,
            created_via="manual",
            created_by=user.id,
        )
        db.add(row)
        db.flush()
        sync_architecture_stage(db, project.id)
    return build_architecture_state(db, project)


def _mutate(db: Session, project: Project, version: int, base_hash: str, fn) -> ArchitectureDocument:
    prereq = check_prerequisites(db, project.id)
    if not prereq["ready"]:
        raise HTTPException(
            409,
            {
                "message": prereq["missing"][0]["message"],
                "missing": prereq["missing"],
            },
        )
    basis_meta, basis_summary, _ = _build_basis_and_summary(db, project.id)
    with txn(db):
        r = _get_doc(db, project, version, lock=True)
        if r.status not in ("draft", "in_review", "approved"):
            raise HTTPException(409, f"A {r.status} architecture version cannot be edited.")
        if r.content_hash != base_hash:
            raise HTTPException(409, "This architecture document changed since you loaded it. Reload and try again.")
        raw = arch.ArchitectureContent.model_validate(r.content).model_dump(mode="json")
        raw["basis"] = basis_summary.model_dump(mode="json")
        data = fn(raw)
        try:
            stored = arch.ArchitectureContent.model_validate(data).model_dump(mode="json")
        except ValidationError as e:
            raise _validation_error(e) from None
        target = r
        if r.status == "approved":
            if any(
                x.status in ("draft", "in_review") or (x.status == "generating" and not _stale_gen(x))
                for x in _all_arch(db, project.id)
            ):
                raise HTTPException(409, "A newer version is already open. Edit that version instead.")
            top = _all_arch(db, project.id)[0]
            target = ArchitectureDocument(
                project_id=project.id,
                version=top.version + 1,
                status="draft",
                basis=basis_meta,
                parent_version=r.version,
                created_via="copy_of_approved",
                created_by=r.created_by,
            )
            db.add(target)
        elif r.status == "in_review":
            r.status, r.submitted_at = "draft", None
            r.basis = basis_meta
        else:
            r.basis = basis_meta
        target.content, target.content_hash = stored, arch.content_hash(stored)
        db.flush()
        sync_architecture_stage(db, project.id)
        return target


def _respond(db: Session, project: Project, doc: ArchitectureDocument) -> dict:
    up = _upstream_state(db, project.id)
    return {"document": _out(doc, up), "state": build_architecture_state(db, project)}


@router.patch("/versions/{version}/overview")
def patch_overview(
    version: int,
    body: SystemOverviewPatch,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        c["system_overview"].update(data)
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.post("/versions/{version}/components")
def add_component(
    version: int,
    body: ComponentIn,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        item = body.model_dump(mode="json", exclude={"base_hash"})
        comps = c["system_overview"]["components"]
        comps.append({"id": _next_id("COMP", comps), **item})
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/components/{comp_id}")
def patch_component(
    version: int,
    comp_id: str,
    body: ComponentPatch,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        comps = c["system_overview"]["components"]
        target = next((x for x in comps if x["id"] == comp_id), None)
        if target is None:
            raise HTTPException(404, f"Architecture component '{comp_id}' not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        target.update(data)
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.delete("/versions/{version}/components/{comp_id}")
def delete_component(
    version: int,
    comp_id: str,
    base_hash: str = Query(..., min_length=64, max_length=64),
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        comps = c["system_overview"]["components"]
        if not any(x["id"] == comp_id for x in comps):
            raise HTTPException(404, f"Architecture component '{comp_id}' not found.")
        c["system_overview"]["components"] = [x for x in comps if x["id"] != comp_id]
        return c

    return _respond(db, project, _mutate(db, project, version, base_hash, fn))


@router.post("/versions/{version}/integrations")
def add_integration(
    version: int,
    body: IntegrationIn,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        item = body.model_dump(mode="json", exclude={"base_hash"})
        ints = c["system_overview"]["external_integrations"]
        ints.append({"id": _next_id("INT", ints), **item})
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/integrations/{int_id}")
def patch_integration(
    version: int,
    int_id: str,
    body: IntegrationPatch,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        ints = c["system_overview"]["external_integrations"]
        target = next((x for x in ints if x["id"] == int_id), None)
        if target is None:
            raise HTTPException(404, f"External integration '{int_id}' not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        target.update(data)
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/application")
def patch_application(
    version: int,
    body: ApplicationPatch,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        c["application_architecture"].update(data)
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.post("/versions/{version}/entities")
def add_entity(
    version: int,
    body: EntityIn,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        item = body.model_dump(mode="json", exclude={"base_hash"})
        ents = c["data_architecture"]["entities"]
        ents.append({"id": _next_id("ENT", ents), **item})
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/entities/{ent_id}")
def patch_entity(
    version: int,
    ent_id: str,
    body: EntityPatch,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        ents = c["data_architecture"]["entities"]
        target = next((x for x in ents if x["id"] == ent_id), None)
        if target is None:
            raise HTTPException(404, f"Domain entity '{ent_id}' not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        target.update(data)
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.post("/versions/{version}/relationships")
def add_relationship(
    version: int,
    body: RelationshipIn,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        item = body.model_dump(mode="json", exclude={"base_hash"})
        c["data_architecture"]["relationships"].append(item)
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/data-policies")
def patch_data_policies(
    version: int,
    body: DataPoliciesPatch,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        c["data_architecture"].update(data)
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.post("/versions/{version}/endpoints")
def add_endpoint(
    version: int,
    body: EndpointIn,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        item = body.model_dump(mode="json", exclude={"base_hash"})
        eps = c["api_architecture"]["endpoints"]
        eps.append({"id": _next_id("API", eps), **item})
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/endpoints/{api_id}")
def patch_endpoint(
    version: int,
    api_id: str,
    body: EndpointPatch,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        eps = c["api_architecture"]["endpoints"]
        target = next((x for x in eps if x["id"] == api_id), None)
        if target is None:
            raise HTTPException(404, f"API endpoint '{api_id}' not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        target.update(data)
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/api-conventions")
def patch_api_conventions(
    version: int,
    body: ApiConventionsPatch,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        c["api_architecture"].update(data)
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/deployment")
def patch_deployment(
    version: int,
    body: DeploymentPatch,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        c["deployment_architecture"].update(data)
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.post("/versions/{version}/decisions")
def add_decision(
    version: int,
    body: DecisionIn,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        item = body.model_dump(mode="json", exclude={"base_hash"})
        decs = c["decisions"]
        decs.append({"id": _next_id("ADR", decs), **item})
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/decisions/{adr_id}")
def patch_decision(
    version: int,
    adr_id: str,
    body: DecisionPatch,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        decs = c["decisions"]
        target = next((x for x in decs if x["id"] == adr_id), None)
        if target is None:
            raise HTTPException(404, f"Architecture decision '{adr_id}' not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        target.update(data)
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.post("/versions/{version}/diagrams")
def add_diagram(
    version: int,
    body: DiagramIn,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        item = body.model_dump(mode="json", exclude={"base_hash"})
        if not item.get("mermaid"):
            try:
                nodes = [arch.DiagramNode.model_validate(n) for n in item["nodes"]]
                edges = [arch.DiagramEdge.model_validate(e) for e in item["edges"]]
                item["mermaid"] = arch.render_mermaid_from_spec(item["diagram_type"], nodes, edges)
            except ValidationError as e:
                raise _validation_error(e) from None
        diags = c["diagrams"]
        diags.append({"id": _next_id("DIAG", diags), **item})
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/diagrams/{diag_id}")
def patch_diagram(
    version: int,
    diag_id: str,
    body: DiagramPatch,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    def fn(c):
        diags = c["diagrams"]
        target = next((x for x in diags if x["id"] == diag_id), None)
        if target is None:
            raise HTTPException(404, f"Architecture diagram '{diag_id}' not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        target.update(data)
        if ("nodes" in data or "edges" in data) and "mermaid" not in data:
            try:
                nodes = [arch.DiagramNode.model_validate(n) for n in target["nodes"]]
                edges = [arch.DiagramEdge.model_validate(e) for e in target["edges"]]
                target["mermaid"] = arch.render_mermaid_from_spec(target["diagram_type"], nodes, edges)
            except ValidationError as e:
                raise _validation_error(e) from None
        return c

    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


# ---------- Submit & Approve ----------
@router.post("/versions/{version}/submit")
def submit_architecture(
    version: int,
    body: Hashed,
    project: Project = Depends(owned),
    db: Session = Depends(get_db),
):
    prereq = check_prerequisites(db, project.id)
    if not prereq["ready"]:
        raise HTTPException(
            409,
            {
                "message": prereq["missing"][0]["message"],
                "missing": prereq["missing"],
            },
        )
    up = prereq["_up"]
    with txn(db):
        r = _get_doc(db, project, version, lock=True)
        if r.status == "in_review" and r.content_hash == body.base_hash:
            return build_architecture_state(db, project)
        if r.status != "draft":
            raise HTTPException(409, f"Only a draft can be submitted for review (this version is {r.status}).")
        if r.content_hash != body.base_hash:
            raise HTTPException(409, "This architecture document changed since you loaded it. Reload and try again.")
        stale_reasons = _doc_staleness(r, up)
        if stale_reasons:
            raise HTTPException(409, f"Cannot submit a stale architecture version: {stale_reasons[0]}")
        comp_eval = arch.evaluate_architecture_completeness(r.content)
        if comp_eval["uncovered_requirements"]:
            raise HTTPException(
                422,
                f"Cannot submit architecture while PRD requirements lack coverage: {', '.join(comp_eval['uncovered_requirements'])}",
            )
        if comp_eval["unreferenced_components"]:
            raise HTTPException(
                422,
                f"Cannot submit architecture while components lack module/entity/endpoint linkage: {', '.join(comp_eval['unreferenced_components'])}",
            )
        if comp_eval["requires_review_decisions"] or comp_eval["requires_review_entities"]:
            items = comp_eval["requires_review_decisions"] + comp_eval["requires_review_entities"]
            raise HTTPException(
                422,
                f"Resolve items marked 'requires_review' before submitting for review: {', '.join(items)}",
            )
        r.status, r.submitted_at = "in_review", now()
        sync_architecture_stage(db, project.id)
    return build_architecture_state(db, project)


@router.post("/versions/{version}/approve")
def approve_architecture(
    version: int,
    body: ApproveIn,
    project: Project = Depends(owned),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    prereq = check_prerequisites(db, project.id)
    if not prereq["ready"]:
        raise HTTPException(
            409,
            {
                "message": prereq["missing"][0]["message"],
                "missing": prereq["missing"],
            },
        )
    up = prereq["_up"]
    with txn(db):
        r = _get_doc(db, project, version, lock=True)
        if r.status == "approved" and r.content_hash == body.content_hash:
            return build_architecture_state(db, project)
        if r.status != "in_review":
            raise HTTPException(409, f"Only a version that is in review can be approved (this version is {r.status}).")
        if r.content_hash != body.content_hash:
            raise HTTPException(
                409,
                "This architecture document changed after you opened it. Reload and review the current version.",
            )
        stale_reasons = _doc_staleness(r, up)
        if stale_reasons:
            raise HTTPException(409, f"Cannot approve a stale architecture version: {stale_reasons[0]}")

        comp_eval = arch.evaluate_architecture_completeness(r.content)
        if comp_eval["uncovered_requirements"]:
            raise HTTPException(
                422,
                f"Cannot approve architecture while PRD requirements lack coverage: {', '.join(comp_eval['uncovered_requirements'])}",
            )
        if comp_eval["unreferenced_components"]:
            raise HTTPException(
                422,
                f"Cannot approve architecture while components lack module/entity/endpoint linkage: {', '.join(comp_eval['unreferenced_components'])}",
            )
        if comp_eval["requires_review_decisions"] or comp_eval["requires_review_entities"]:
            items = comp_eval["requires_review_decisions"] + comp_eval["requires_review_entities"]
            raise HTTPException(
                422,
                f"Resolve items marked 'requires_review' before approving: {', '.join(items)}",
            )

        unv = _unverified_count(r.content)
        if unv > 0 and not body.acknowledge_unverified:
            raise HTTPException(
                409,
                f"{unv} architecture item(s) are still marked 'proposed'. Accept individual items or pass acknowledge_unverified=true to approve.",
            )

        c = r.content or {}
        arch_brain = {
            "approved_version": r.version,
            "document_id": r.id,
            "content_hash": r.content_hash,
            "approved_at": now().isoformat(),
            "basis_versions": {
                k: v for k, v in (r.basis or {}).items() if k.endswith("_version") and isinstance(v, int)
            },
            "component_count": len(c.get("system_overview", {}).get("components", [])),
            "entity_count": len(c.get("data_architecture", {}).get("entities", [])),
            "endpoint_count": len(c.get("api_architecture", {}).get("endpoints", [])),
            "decision_count": len(c.get("decisions", [])),
            "diagram_count": len(c.get("diagrams", [])),
            "unverified_acknowledged": bool(unv),
        }
        rev = commit_brain(
            db,
            project,
            {"architecture_spec": arch_brain},
            "architecture_approved",
            user.id,
            commit=False,
        )
        r.status, r.approved_at, r.approved_by, r.approval_note = "approved", now(), user.id, body.note
        r.acknowledged_unverified, r.brain_revision = bool(unv), rev.version
        db.flush()
        sync_architecture_stage(db, project.id)
    return build_architecture_state(db, project)
