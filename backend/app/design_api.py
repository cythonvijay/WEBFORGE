"""Design System & Interactive Prototype workflow (Phase 12): routes, upstream UX/PRD staleness gates,
copy-on-write edits, exact-hash approval, and `design` lifecycle stage completion/invalidation.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai, design as ds, ux
from .api import commit_brain, current_user, latest_revision, owned
from .brain import ProjectBrain
from .config import settings
from .db import get_db
from .discovery_api import txn
from .models import DesignArtifact, PrdDocument, Project, ProjectStage, ResearchReport, StrategyDocument, User, UxArtifact, now
from .security import as_utc
from .ux_api import WORKSPACE_PATHS as UX_PATHS, ux_stage_completion_check

router = APIRouter(prefix="/projects/{project_id}/design")
HASH = Field(min_length=64, max_length=64)


class GenerateIn(BaseModel):
    supersede: bool = False


class Hashed(BaseModel):
    base_hash: str = HASH


class ApproveIn(BaseModel):
    content_hash: str = HASH
    acknowledge_unverified: bool = False
    note: str | None = Field(None, max_length=1000)


# ---------- Design System payloads ----------
class FoundationsPatch(Hashed):
    color_tokens: list[dict] | None = None
    typography_scale: list[dict] | None = None
    spacing_scale: list[dict] | None = None
    grid_breakpoints: dict | None = None
    surface_tokens: dict | None = None
    icon_guidelines: list[str] | None = None
    accessibility_notes: list[str] | None = None


class ComponentIn(Hashed):
    name: str
    category: ds.ComponentCategory = "buttons_links"
    purpose: str
    variants: list[str]
    states: list[ds.ComponentState] = ["default", "hover", "focus", "disabled"]
    design_tokens_used: list[str]
    responsive_behavior: str
    accessibility_notes: str
    wireframe_ids: list[str]
    prd_requirement_ids: list[str]


class ComponentPatch(Hashed):
    name: str | None = None
    category: ds.ComponentCategory | None = None
    purpose: str | None = None
    variants: list[str] | None = None
    states: list[ds.ComponentState] | None = None
    design_tokens_used: list[str] | None = None
    responsive_behavior: str | None = None
    accessibility_notes: str | None = None
    wireframe_ids: list[str] | None = None
    prd_requirement_ids: list[str] | None = None


class DecisionIn(Hashed):
    title: str
    chosen_value_or_rule: str
    rationale: str
    supporting_refs: list[str]
    assumptions: list[str] = []
    unresolved_questions: list[str] = []
    status: ds.DecisionStatus = "proposed"


class DecisionPatch(Hashed):
    title: str | None = None
    chosen_value_or_rule: str | None = None
    rationale: str | None = None
    supporting_refs: list[str] | None = None
    assumptions: list[str] | None = None
    unresolved_questions: list[str] | None = None
    status: ds.DecisionStatus | None = None


class ManualDesignSystemInit(BaseModel):
    foundations: dict
    components: list[dict]
    decisions: list[dict]


# ---------- Prototype payloads ----------
class ScreenPatch(Hashed):
    title: str | None = None
    route_path: str | None = None
    purpose: str | None = None
    component_ids: list[str] | None = None
    form_fields: list[dict] | None = None
    interactions: list[dict] | None = None
    states: dict | None = None
    responsive_behavior: dict | None = None
    mock_data_note: str | None = None


class FlowPatch(Hashed):
    title: str | None = None
    start_screen_id: str | None = None
    ordered_screen_ids: list[str] | None = None
    happy_path_steps: list[str] | None = None


# ---------- DB & upstream helpers ----------
def _iso(d: datetime | None) -> str | None:
    return as_utc(d).isoformat() if d else None


def _stage(db: Session, pid: str, name: str = "design") -> ProjectStage:
    return db.scalar(select(ProjectStage).where(ProjectStage.project_id == pid, ProjectStage.stage == name))


def _all_design(db: Session, pid: str, atype: ds.DesignArtifactType) -> list[DesignArtifact]:
    return list(
        db.scalars(
            select(DesignArtifact)
            .where(DesignArtifact.project_id == pid, DesignArtifact.artifact_type == atype)
            .order_by(DesignArtifact.version.desc())
        )
    )


def _stale_gen(r: DesignArtifact) -> bool:
    return r.status == "generating" and as_utc(r.updated_at) < datetime.now(timezone.utc) - timedelta(seconds=settings.design_generation_timeout_seconds)


def _upstream_state(db: Session, pid: str) -> dict[str, Any]:
    res_rows = list(db.scalars(select(ResearchReport).where(ResearchReport.project_id == pid, ResearchReport.status != "failed").order_by(ResearchReport.version.desc())))
    stg_rows = list(db.scalars(select(StrategyDocument).where(StrategyDocument.project_id == pid, StrategyDocument.status != "failed").order_by(StrategyDocument.version.desc())))
    prd_rows = list(db.scalars(select(PrdDocument).where(PrdDocument.project_id == pid, PrdDocument.status != "failed").order_by(PrdDocument.version.desc())))

    res_open = next((r for r in res_rows if r.status in ("draft", "in_review", "generating")), None)
    res_app = next((r for r in res_rows if r.status == "approved"), None)

    stg_open = next((r for r in stg_rows if r.status in ("draft", "in_review", "generating")), None)
    stg_app = next((r for r in stg_rows if r.status == "approved"), None)

    prd_open = next((r for r in prd_rows if r.status in ("draft", "in_review", "generating")), None)
    prd_app = next((r for r in prd_rows if r.status == "approved"), None)

    ux_by_type: dict[ux.ArtifactType, dict[str, UxArtifact | None]] = {}
    for t in ux.ARTIFACT_TYPES:
        rows = list(db.scalars(select(UxArtifact).where(UxArtifact.project_id == pid, UxArtifact.artifact_type == t, UxArtifact.status != "failed").order_by(UxArtifact.version.desc())))
        ux_by_type[t] = {
            "open": next((r for r in rows if r.status in ("draft", "in_review", "generating")), None),
            "approved": next((r for r in rows if r.status == "approved"), None),
        }

    design_by_type: dict[ds.DesignArtifactType, dict[str, DesignArtifact | None]] = {}
    for t in ds.DESIGN_ARTIFACT_TYPES:
        rows = [r for r in _all_design(db, pid, t) if r.status != "failed"]
        design_by_type[t] = {
            "open": next((r for r in rows if r.status in ("draft", "in_review") or (r.status == "generating" and not _stale_gen(r))), None),
            "approved": next((r for r in rows if r.status == "approved"), None),
        }

    res_stage = _stage(db, pid, "research")
    prod_stage = _stage(db, pid, "product")
    ux_stage = _stage(db, pid, "ux")
    ux_ok, ux_reasons = ux_stage_completion_check(db, pid)

    return {
        "res_stage": res_stage.status if res_stage else "not_started",
        "prod_stage": prod_stage.status if prod_stage else "not_started",
        "ux_stage": ux_stage.status if ux_stage else "not_started",
        "ux_ok": ux_ok,
        "ux_reasons": ux_reasons,
        "res_open": res_open,
        "res_app": res_app,
        "stg_open": stg_open,
        "stg_app": stg_app,
        "prd_open": prd_open,
        "prd_app": prd_app,
        "ux": ux_by_type,
        "design": design_by_type,
    }


def check_prerequisites(db: Session, pid: str, atype: ds.DesignArtifactType) -> dict[str, Any]:
    """Verify upstream Phase 9, Phase 10, Phase 11 (and for `prototype`, Phase 12 `design_system`) prerequisites."""
    up = _upstream_state(db, pid)
    missing: list[dict[str, str]] = []

    if up["res_stage"] != "complete" or up["res_app"] is None or up["res_open"] is not None:
        missing.append({
            "artifact": "research",
            "label": "Research",
            "message": "Research has an unapproved draft in progress." if up["res_open"] else "Approve your Research report first.",
            "workspace_path": f"/projects/{pid}/research",
        })
    if up["stg_app"] is None or up["stg_open"] is not None:
        missing.append({
            "artifact": "strategy",
            "label": "Product Strategy",
            "message": "Product Strategy has an unapproved draft in progress." if up["stg_open"] else "Approve your Product Strategy first.",
            "workspace_path": f"/projects/{pid}/strategy",
        })
    if up["prd_app"] is None or up["prd_open"] is not None or up["prod_stage"] != "complete":
        missing.append({
            "artifact": "prd",
            "label": "PRD",
            "message": "PRD has an unapproved draft in progress." if up["prd_open"] else "Approve your PRD first.",
            "workspace_path": f"/projects/{pid}/prd",
        })

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
            missing.append({
                "artifact": t,
                "label": ux_labels[t],
                "message": f"{ux_labels[t]} has an unapproved draft open; approve it first." if u_open else f"Approve {ux_labels[t]} before starting Phase 12 Design.",
                "workspace_path": wpath,
            })
        elif t == "ux_review" and u_app.content:
            rc = ux.review_counts(u_app.content)
            if rc["critical_open"] > 0:
                missing.append({
                    "artifact": "ux_review",
                    "label": "UX Review",
                    "message": f"UX Review has {rc['critical_open']} unresolved critical finding(s).",
                    "workspace_path": wpath,
                })

    if not missing and (up["ux_stage"] != "complete" or not up["ux_ok"]):
        reason = up["ux_reasons"][0] if up["ux_reasons"] else "Complete and approve all Phase 11 UX artifacts first."
        missing.append({
            "artifact": "ux_review",
            "label": "UX Review",
            "message": reason,
            "workspace_path": f"/projects/{pid}/ux-review",
        })

    if atype == "prototype":
        ds_app = up["design"]["design_system"]["approved"]
        ds_open = up["design"]["design_system"]["open"]
        if ds_app is None or ds_open is not None:
            missing.append({
                "artifact": "design_system",
                "label": "Design System",
                "message": "Design System has an unapproved draft open; approve it first." if ds_open else "Generate and approve your Design System before building the Interactive Prototype.",
                "workspace_path": f"/projects/{pid}/design-system",
            })
        else:
            ds_stale = _doc_staleness(ds_app, up)
            if ds_stale:
                missing.append({
                    "artifact": "design_system",
                    "label": "Design System",
                    "message": f"Approved Design System v{ds_app.version} is stale ({ds_stale[0]}). Update and re-approve Design System first.",
                    "workspace_path": f"/projects/{pid}/design-system",
                })

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
        },
        "_up": up,
    }


def _doc_staleness(doc: DesignArtifact | None, up: dict[str, Any]) -> list[str]:
    if doc is None:
        return []
    reasons: list[str] = []
    b = doc.basis or {}
    if up["res_open"] is not None or (up["res_app"] and b.get("research_version") != up["res_app"].version):
        reasons.append("Upstream Research changed since this design version was created.")
    if up["stg_open"] is not None or (up["stg_app"] and b.get("strategy_version") != up["stg_app"].version):
        reasons.append("Upstream Product Strategy changed since this design version was created.")
    if up["prd_open"] is not None or (up["prd_app"] and b.get("prd_version") != up["prd_app"].version):
        reasons.append(f"Built from PRD v{b.get('prd_version')}, while PRD v{up['prd_app'].version if up['prd_app'] else '?'} is now current.")

    ux_labels = {"personas": "Personas", "journeys": "User Journeys", "ia": "Information Architecture", "wireframes": "Wireframes", "ux_review": "UX Review"}
    for t in ux.ARTIFACT_TYPES:
        u_open = up["ux"][t]["open"]
        u_app = up["ux"][t]["approved"]
        if u_open is not None:
            reasons.append(f"{ux_labels[t]} has an unapproved draft open.")
        elif u_app and b.get(f"{t}_version") != u_app.version:
            reasons.append(f"Built from {ux_labels[t]} v{b.get(f'{t}_version')}, while {ux_labels[t]} v{u_app.version} is now approved.")

    if doc.artifact_type == "prototype":
        ds_open = up["design"]["design_system"]["open"]
        ds_app = up["design"]["design_system"]["approved"]
        if ds_open is not None:
            reasons.append("Design System has an unapproved draft open.")
        elif ds_app and b.get("design_system_version") != ds_app.version:
            reasons.append(f"Built from Design System v{b.get('design_system_version')}, while Design System v{ds_app.version} is now approved.")
    return reasons


def design_stage_completion_check(db: Session, pid: str) -> tuple[bool, list[str]]:
    """Verify whether the `design` lifecycle stage meets all documented completion criteria."""
    up = _upstream_state(db, pid)
    reasons: list[str] = []
    if up["ux_stage"] != "complete" or not up["ux_ok"]:
        reasons.append("Upstream UX stage must be complete and current.")
    for t in ds.DESIGN_ARTIFACT_TYPES:
        app_doc = up["design"][t]["approved"]
        open_doc = up["design"][t]["open"]
        label = "Design System" if t == "design_system" else "Interactive Prototype"
        if app_doc is None:
            reasons.append(f"{label} has not been approved yet.")
        elif open_doc is not None:
            reasons.append(f"{label} has an unapproved draft (v{open_doc.version}) open.")
        else:
            st_reasons = _doc_staleness(app_doc, up)
            if st_reasons:
                reasons.append(f"{label} v{app_doc.version} is stale: {st_reasons[0]}")
    return len(reasons) == 0, reasons


def sync_design_stage(db: Session, pid: str) -> None:
    """Synchronize the `design` lifecycle stage based on persisted Design artifacts and upstream UX state."""
    from .architecture_api import sync_architecture_stage
    st = _stage(db, pid, "design")
    if st is None:
        return
    all_rows = list(db.scalars(select(DesignArtifact).where(DesignArtifact.project_id == pid, DesignArtifact.status != "failed")))
    if not all_rows:
        sync_architecture_stage(db, pid)
        return
    complete_ok, _ = design_stage_completion_check(db, pid)
    if complete_ok:
        st.status = "complete"
        sync_architecture_stage(db, pid)
        return
    any_in_review = any(r.status == "in_review" for r in all_rows)
    any_draft = any(r.status == "draft" for r in all_rows)
    if any_in_review and not any_draft and _stage(db, pid, "ux").status == "complete":
        st.status = "needs_review"
    else:
        if st.status in ("complete", "needs_review") or any(r.status in ("draft", "approved") for r in all_rows):
            if _stage(db, pid, "ux").status == "complete" or st.status in ("complete", "needs_review"):
                st.status = "in_progress"
    sync_architecture_stage(db, pid)


def _build_basis_and_summary(db: Session, pid: str, atype: ds.DesignArtifactType) -> tuple[dict, ds.DesignBasisSummary, dict[str, Any]]:
    prereq = check_prerequisites(db, pid, atype)
    if not prereq["ready"]:
        raise HTTPException(409, prereq["missing"][0]["message"])
    up = prereq["_up"]
    res_app, stg_app, prd_app = up["res_app"], up["stg_app"], up["prd_app"]
    p_app = up["ux"]["personas"]["approved"]
    j_app = up["ux"]["journeys"]["approved"]
    ia_app = up["ux"]["ia"]["approved"]
    wf_app = up["ux"]["wireframes"]["approved"]
    rev_app = up["ux"]["ux_review"]["approved"]
    ds_app = up["design"]["design_system"]["approved"] if atype == "prototype" else None

    summary = ds.build_design_basis(
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
        design_system_doc=ds_app.content if ds_app else None,
        design_system_ver=ds_app.version if ds_app else None,
    )
    basis_meta = {
        "brain_version": latest_revision(db, pid).version,
        "research_id": res_app.id,
        "research_version": res_app.version,
        "strategy_id": stg_app.id,
        "strategy_version": stg_app.version,
        "prd_id": prd_app.id,
        "prd_version": prd_app.version,
        "personas_id": p_app.id,
        "personas_version": p_app.version,
        "journeys_id": j_app.id,
        "journeys_version": j_app.version,
        "ia_id": ia_app.id,
        "ia_version": ia_app.version,
        "wireframes_id": wf_app.id,
        "wireframes_version": wf_app.version,
        "ux_review_id": rev_app.id,
        "ux_review_version": rev_app.version,
    }
    if ds_app:
        basis_meta.update(
            design_system_id=ds_app.id,
            design_system_version=ds_app.version,
            design_system_hash=ds_app.content_hash,
        )
    return basis_meta, summary, up


def _item_count(atype: ds.DesignArtifactType, content: dict | None) -> int:
    if not content:
        return 0
    if atype == "design_system":
        return len(content.get("components", [])) + len(content.get("decisions", []))
    return len(content.get("screens", []))


def _unverified_count(atype: ds.DesignArtifactType, content: dict | None) -> int:
    if not content:
        return 0
    if atype == "design_system":
        return sum(
            d.get("status") == "proposed" or bool(d.get("assumptions")) or bool(d.get("unresolved_questions"))
            for d in content.get("decisions", [])
        )
    return 0


def _warnings(doc: DesignArtifact, stale_reasons: list[str]) -> list[dict[str, str]]:
    w: list[dict[str, str]] = []
    for reason in stale_reasons:
        w.append({"code": "stale_upstream", "message": reason})
    c = doc.content
    if not c:
        return w
    if doc.artifact_type == "design_system":
        prop = sum(d.get("status") == "proposed" for d in c.get("decisions", []))
        if prop:
            w.append({"code": "proposed_decisions", "message": f"{prop} design decision(s) are still marked 'proposed'."})
    return w


def _summary(r: DesignArtifact) -> dict:
    return {
        "version": r.version,
        "status": r.status,
        "artifact_type": r.artifact_type,
        "created_via": r.created_via,
        "parent_version": r.parent_version,
        "created_at": _iso(r.created_at),
        "updated_at": _iso(r.updated_at),
        "submitted_at": _iso(r.submitted_at),
        "approved_at": _iso(r.approved_at),
        "content_hash": r.content_hash,
        "item_count": _item_count(r.artifact_type, r.content),
        "error": r.error,
    }


def _out(r: DesignArtifact, up: dict[str, Any]) -> dict:
    stale_reasons = _doc_staleness(r, up)
    return {
        **_summary(r),
        "id": r.id,
        "content": r.content,
        "basis": r.basis,
        "approval_note": r.approval_note,
        "acknowledged_unverified": r.acknowledged_unverified,
        "brain_revision": r.brain_revision,
        "unverified_count": _unverified_count(r.artifact_type, r.content),
        "is_stale": len(stale_reasons) > 0,
        "stale_reasons": stale_reasons,
        "editable": r.status in ("draft", "in_review"),
        "warnings": _warnings(r, stale_reasons),
    }


def build_artifact_state(db: Session, project: Project, atype: ds.DesignArtifactType) -> dict:
    prereq = check_prerequisites(db, project.id, atype)
    up = prereq["_up"]
    rows = _all_design(db, project.id, atype)
    gen = next((r for r in rows if r.status == "generating" and not _stale_gen(r)), None)
    open_ = next((r for r in rows if r.status in ("draft", "in_review")), None)
    approved = next((r for r in rows if r.status == "approved"), None)
    current = open_ or approved
    failed = rows[0] if rows and (rows[0].status == "failed" or _stale_gen(rows[0])) else None
    status = "generating" if gen else (current.status if current else ("failed" if failed else "not_started"))

    cur_out = _out(current, up) if current else None
    is_stale = cur_out["is_stale"] if cur_out else False
    stale_reasons = cur_out["stale_reasons"] if cur_out else []
    has_items = bool(current and _item_count(atype, current.content) > 0)

    basis_preview = None
    if prereq["ready"] and not current:
        _, b_sum, _ = _build_basis_and_summary(db, project.id, atype)
        basis_preview = b_sum.model_dump(mode="json")

    next_workspace = {
        "design_system": ("prototype", "Continue to Interactive Prototype", f"/projects/{project.id}/prototype"),
        "prototype": ("architecture", "Continue to Product Architecture", f"/projects/{project.id}/architecture"),
    }[atype]

    step = (
        {"key": "fix_prerequisites", "label": prereq["missing"][0]["message"], "workspace_path": prereq["missing"][0]["workspace_path"]} if not prereq["ready"] else
        {"key": "wait", "label": f"{atype} is being generated"} if gen else
        {"key": "retry_generation", "label": f"Retry generating {atype}"} if status == "failed" else
        {"key": "start", "label": f"Generate {atype.replace('_', ' ')} from approved UX and PRD artifacts"} if status == "not_started" else
        {"key": "stale_upstream", "label": f"Upstream artifacts changed ({stale_reasons[0]}). Regenerate or update this workspace."} if is_stale else
        {"key": "review_and_submit", "label": "Review and edit specifications, then submit for review"} if status == "draft" else
        {"key": "approve", "label": f"Approve this {atype.replace('_', ' ')} version"} if status == "in_review" else
        {"key": "approved", "label": f"Approved. {next_workspace[1]}", "workspace_path": next_workspace[2]}
    )

    design_complete, design_missing = design_stage_completion_check(db, project.id)
    return {
        "artifact_type": atype,
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
            "stage": "design",
            "status": _stage(db, project.id, "design").status,
            "design_complete": design_complete,
            "pending_criteria": design_missing,
        },
        "next_step": step,
        "can_generate": prereq["ready"] and gen is None,
        "needs_supersede": open_ is not None,
        "can_submit": bool(current and current.status == "draft" and has_items and prereq["ready"] and not is_stale),
        "can_approve": bool(current and current.status == "in_review" and prereq["ready"] and not is_stale),
        "limitations": ds.DESIGN_LIMITATIONS[atype],
    }


def _get_doc(db: Session, project: Project, atype: ds.DesignArtifactType, version: int, lock: bool = False) -> DesignArtifact:
    q = select(DesignArtifact).where(DesignArtifact.project_id == project.id, DesignArtifact.artifact_type == atype, DesignArtifact.version == version)
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None:
        raise HTTPException(404, f"{atype} version {version} not found.")
    return r


def _validation_error(e: ValidationError) -> HTTPException:
    items = [{"loc": ["body", *map(str, x["loc"])], "msg": x["msg"].removeprefix("Value error, ")} for x in e.errors(include_input=False, include_url=False)]
    return HTTPException(422, items)


def _next_id(prefix: str, items: list[dict]) -> str:
    n = [int(i["id"].split("-")[-1]) for i in items if i["id"].startswith(prefix + "-") and i["id"].split("-")[-1].isdigit()]
    return f"{prefix}-{max(n, default=0) + 1}"


def _content_model(atype: ds.DesignArtifactType):
    return {"design_system": ds.DesignSystemContent, "prototype": ds.PrototypeContent}[atype]


def _check_atype(artifact: str) -> ds.DesignArtifactType:
    if artifact not in ds.DESIGN_ARTIFACT_TYPES:
        raise HTTPException(404, f"Unknown Design artifact type '{artifact}'.")
    return artifact  # type: ignore[return-value]


# ---------- Overview endpoint ----------
@router.get("")
def get_design_overview(project: Project = Depends(owned), db: Session = Depends(get_db)):
    design_ok, missing_reasons = design_stage_completion_check(db, project.id)
    artifacts_summary = {}
    for t in ds.DESIGN_ARTIFACT_TYPES:
        st = build_artifact_state(db, project, t)
        artifacts_summary[t] = {
            "status": st["status"],
            "approved_version": st["approved_version"],
            "is_stale": st["is_stale"],
            "prerequisites_ready": st["prerequisites"]["ready"],
            "item_count": st["current"]["item_count"] if st["current"] else 0,
        }
    return {
        "stage": "design",
        "status": _stage(db, project.id, "design").status,
        "design_complete": design_ok,
        "pending_criteria": missing_reasons,
        "artifacts": artifacts_summary,
    }


# ---------- Shared state / version / generate / submit / approve endpoints ----------
@router.get("/{artifact}")
def get_artifact(artifact: str, project: Project = Depends(owned), db: Session = Depends(get_db)):
    return build_artifact_state(db, project, _check_atype(artifact))


@router.get("/{artifact}/versions/{version}")
def get_artifact_version(artifact: str, version: int, project: Project = Depends(owned), db: Session = Depends(get_db)):
    atype = _check_atype(artifact)
    up = _upstream_state(db, project.id)
    return _out(_get_doc(db, project, atype, version), up)


@router.post("/{artifact}/generate")
async def generate_artifact(artifact: str, body: GenerateIn, project: Project = Depends(owned), user: User = Depends(current_user), db: Session = Depends(get_db)):
    atype = _check_atype(artifact)
    basis_meta, basis_summary, up = _build_basis_and_summary(db, project.id, atype)

    prd_content = up["prd_app"].content
    p_content = up["ux"]["personas"]["approved"].content
    j_content = up["ux"]["journeys"]["approved"].content
    ia_content = up["ux"]["ia"]["approved"].content
    wf_content = up["ux"]["wireframes"]["approved"].content
    rev_content = up["ux"]["ux_review"]["approved"].content
    ds_content = up["design"]["design_system"]["approved"].content if up["design"]["design_system"]["approved"] else {}

    with txn(db):
        db.get(Project, project.id, with_for_update=True, populate_existing=True)
        rows = _all_design(db, project.id, atype)
        gen = next((r for r in rows if r.status == "generating"), None)
        if gen and not _stale_gen(gen):
            raise HTTPException(409, f"{atype} is already being generated.")
        if any(r.status in ("draft", "in_review") for r in rows) and not body.supersede:
            raise HTTPException(409, "A draft already exists. Edit it, or regenerate with supersede=true to keep it in history and start a new version.")
        retry = gen or (rows[0] if rows and rows[0].status == "failed" else None)
        approved = next((r for r in rows if r.status == "approved"), None)
        if retry:
            retry.status, retry.error, retry.basis, retry.content, retry.content_hash = "generating", None, basis_meta, None, None
            retry.parent_version = approved.version if approved else None
            row = retry
        else:
            row = DesignArtifact(
                project_id=project.id,
                artifact_type=atype,
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
        if atype == "design_system":
            gen_out = await prov.generate_structured(
                ds.build_design_system_prompt(basis_summary, prd_content, p_content, ia_content, wf_content, rev_content),
                ds.GeneratedDesignSystem,
            )
            content_obj = ds.to_design_system_content(basis_summary, gen_out)
        else:
            gen_out = await prov.generate_structured(
                ds.build_prototype_prompt(basis_summary, prd_content, j_content, ia_content, wf_content, ds_content),
                ds.GeneratedPrototype,
            )
            content_obj = ds.to_prototype_content(basis_summary, wf_content, gen_out)
        stored = content_obj.model_dump(mode="json")
        failure = None
    except (ai.ProviderNotConfigured, ai.ProviderError, ValidationError, ValueError) as e:
        failure = e

    if failure is not None:
        unconfigured = isinstance(failure, ai.ProviderNotConfigured)
        msg = "AI provider not configured." if unconfigured else (ai.user_message(failure) if isinstance(failure, ai.ProviderError) else ai.USER_MESSAGES["malformed"])
        with txn(db):
            r = db.get(DesignArtifact, doc_id, with_for_update=True, populate_existing=True)
            if r.status == "generating":
                r.status, r.error = "failed", msg
        raise HTTPException(503 if unconfigured else 502, f"{msg} Nothing was changed.")

    with txn(db):
        r = db.get(DesignArtifact, doc_id, with_for_update=True, populate_existing=True)
        if r.status != "generating":
            raise HTTPException(409, "Another request changed this Design artifact.")
        for old in _all_design(db, project.id, atype):
            if old.id != doc_id and old.status in ("draft", "in_review"):
                old.status = "superseded"
        db.flush()
        r.status, r.content, r.content_hash, r.error = "draft", stored, ds.content_hash(stored), None
        sync_design_stage(db, project.id)
    return build_artifact_state(db, project, atype)


@router.post("/design_system/manual")
def create_manual_design_system(body: ManualDesignSystemInit, project: Project = Depends(owned), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Allows creating a manual Design System draft when the AI provider is unavailable."""
    basis_meta, basis_summary, _ = _build_basis_and_summary(db, project.id, "design_system")
    with txn(db):
        rows = _all_design(db, project.id, "design_system")
        if any(r.status in ("draft", "in_review", "generating") for r in rows):
            raise HTTPException(409, "An open Design System draft already exists. Edit that version instead.")
        try:
            content_obj = ds.DesignSystemContent(
                basis=basis_summary,
                foundations=body.foundations,
                components=[{**c, "id": f"CMP-{i}", "origin": "user", "edited_by_user": False} for i, c in enumerate(body.components, 1)],
                decisions=[{**d, "id": f"DD-{i}", "origin": "user", "edited_by_user": False} for i, d in enumerate(body.decisions, 1)],
            )
            stored = content_obj.model_dump(mode="json")
        except ValidationError as e:
            raise _validation_error(e) from None
        approved = next((r for r in rows if r.status == "approved"), None)
        row = DesignArtifact(
            project_id=project.id,
            artifact_type="design_system",
            version=(rows[0].version + 1) if rows else 1,
            status="draft",
            content=stored,
            content_hash=ds.content_hash(stored),
            basis=basis_meta,
            parent_version=approved.version if approved else None,
            created_via="manual",
            created_by=user.id,
        )
        db.add(row)
        db.flush()
        sync_design_stage(db, project.id)
    return build_artifact_state(db, project, "design_system")


# ---------- Copy-on-write mutation helper ----------
def _mutate(db: Session, project: Project, atype: ds.DesignArtifactType, version: int, base_hash: str, fn) -> DesignArtifact:
    prereq = check_prerequisites(db, project.id, atype)
    if not prereq["ready"]:
        raise HTTPException(409, prereq["missing"][0]["message"])
    basis_meta, basis_summary, _ = _build_basis_and_summary(db, project.id, atype)
    model_cls = _content_model(atype)
    with txn(db):
        r = _get_doc(db, project, atype, version, lock=True)
        if r.status not in ("draft", "in_review", "approved"):
            raise HTTPException(409, f"A {r.status} {atype} version cannot be edited.")
        if r.content_hash != base_hash:
            raise HTTPException(409, f"This {atype} document changed since you loaded it. Reload and try again.")
        raw = model_cls.model_validate(r.content).model_dump(mode="json")
        raw["basis"] = basis_summary.model_dump(mode="json")
        data = fn(raw)
        try:
            stored = model_cls.model_validate(data).model_dump(mode="json")
        except ValidationError as e:
            raise _validation_error(e) from None
        target = r
        if r.status == "approved":
            if any(x.status in ("draft", "in_review") or (x.status == "generating" and not _stale_gen(x)) for x in _all_design(db, project.id, atype)):
                raise HTTPException(409, "A newer version is already open. Edit that version instead.")
            top = _all_design(db, project.id, atype)[0]
            target = DesignArtifact(
                project_id=project.id,
                artifact_type=atype,
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
        target.content, target.content_hash = stored, ds.content_hash(stored)
        db.flush()
        sync_design_stage(db, project.id)
        return target


def _respond(db: Session, project: Project, doc: DesignArtifact) -> dict:
    up = _upstream_state(db, project.id)
    return {"document": _out(doc, up), "state": build_artifact_state(db, project, doc.artifact_type)}


# ---------- 1. Design System routes ----------
@router.patch("/design_system/versions/{version}/foundations")
def patch_foundations(version: int, body: FoundationsPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        c["foundations"].update(data)
        return c
    return _respond(db, project, _mutate(db, project, "design_system", version, body.base_hash, fn))


@router.post("/design_system/versions/{version}/components")
def add_component(version: int, body: ComponentIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        cmp = body.model_dump(mode="json", exclude={"base_hash"})
        c["components"].append({**cmp, "id": _next_id("CMP", c["components"]), "origin": "user", "edited_by_user": False})
        return c
    return _respond(db, project, _mutate(db, project, "design_system", version, body.base_hash, fn))


@router.patch("/design_system/versions/{version}/components/{cmp_id}")
def patch_component(version: int, cmp_id: str, body: ComponentPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        cmp = next((x for x in c["components"] if x["id"] == cmp_id), None)
        if cmp is None:
            raise HTTPException(404, "Component specification not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        cmp.update(data)
        cmp["edited_by_user"] = True
        return c
    return _respond(db, project, _mutate(db, project, "design_system", version, body.base_hash, fn))


@router.delete("/design_system/versions/{version}/components/{cmp_id}")
def delete_component(version: int, cmp_id: str, base_hash: str = Query(..., min_length=64, max_length=64), project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        if not any(x["id"] == cmp_id for x in c["components"]):
            raise HTTPException(404, "Component specification not found.")
        c["components"] = [x for x in c["components"] if x["id"] != cmp_id]
        return c
    return _respond(db, project, _mutate(db, project, "design_system", version, base_hash, fn))


@router.post("/design_system/versions/{version}/decisions")
def add_decision(version: int, body: DecisionIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        dec = body.model_dump(mode="json", exclude={"base_hash"})
        c["decisions"].append({**dec, "id": _next_id("DD", c["decisions"]), "origin": "user", "edited_by_user": False, "note": None})
        return c
    return _respond(db, project, _mutate(db, project, "design_system", version, body.base_hash, fn))


@router.patch("/design_system/versions/{version}/decisions/{dec_id}")
def patch_decision(version: int, dec_id: str, body: DecisionPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        dec = next((x for x in c["decisions"] if x["id"] == dec_id), None)
        if dec is None:
            raise HTTPException(404, "Design decision not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        dec.update(data)
        dec["edited_by_user"] = True
        return c
    return _respond(db, project, _mutate(db, project, "design_system", version, body.base_hash, fn))


# ---------- 2. Prototype routes ----------
@router.patch("/prototype/versions/{version}/screens/{scr_id}")
def patch_screen(version: int, scr_id: str, body: ScreenPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        scr = next((x for x in c["screens"] if x["id"] == scr_id), None)
        if scr is None:
            raise HTTPException(404, "Prototype screen not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        scr.update(data)
        scr["edited_by_user"] = True
        return c
    return _respond(db, project, _mutate(db, project, "prototype", version, body.base_hash, fn))


@router.patch("/prototype/versions/{version}/flows/{flow_id}")
def patch_flow(version: int, flow_id: str, body: FlowPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        fl = next((x for x in c["flows"] if x["id"] == flow_id), None)
        if fl is None:
            raise HTTPException(404, "Prototype flow not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        fl.update(data)
        return c
    return _respond(db, project, _mutate(db, project, "prototype", version, body.base_hash, fn))


# ---------- Submit & Approve ----------
@router.post("/{artifact}/versions/{version}/submit")
def submit_artifact(artifact: str, version: int, body: Hashed, project: Project = Depends(owned), db: Session = Depends(get_db)):
    atype = _check_atype(artifact)
    prereq = check_prerequisites(db, project.id, atype)
    if not prereq["ready"]:
        raise HTTPException(409, prereq["missing"][0]["message"])
    up = prereq["_up"]
    with txn(db):
        r = _get_doc(db, project, atype, version, lock=True)
        if r.status == "in_review" and r.content_hash == body.base_hash:
            return build_artifact_state(db, project, atype)
        if r.status != "draft":
            raise HTTPException(409, f"Only a draft can be submitted for review (this version is {r.status}).")
        if r.content_hash != body.base_hash:
            raise HTTPException(409, f"This {atype} document changed since you loaded it. Reload and try again.")
        stale_reasons = _doc_staleness(r, up)
        if stale_reasons:
            raise HTTPException(409, f"Cannot submit a stale {atype} version: {stale_reasons[0]}")
        if _item_count(atype, r.content) == 0:
            raise HTTPException(409, f"Add at least one item to {atype} before submitting for review.")
        r.status, r.submitted_at = "in_review", now()
        sync_design_stage(db, project.id)
    return build_artifact_state(db, project, atype)


@router.post("/{artifact}/versions/{version}/approve")
def approve_artifact(artifact: str, version: int, body: ApproveIn, project: Project = Depends(owned), user: User = Depends(current_user), db: Session = Depends(get_db)):
    atype = _check_atype(artifact)
    prereq = check_prerequisites(db, project.id, atype)
    if not prereq["ready"]:
        raise HTTPException(409, prereq["missing"][0]["message"])
    up = prereq["_up"]
    with txn(db):
        r = _get_doc(db, project, atype, version, lock=True)
        if r.status == "approved" and r.content_hash == body.content_hash:
            return build_artifact_state(db, project, atype)
        if r.status != "in_review":
            raise HTTPException(409, f"Only a version that is in review can be approved (this version is {r.status}).")
        if r.content_hash != body.content_hash:
            raise HTTPException(409, f"This {atype} document changed after you opened it. Reload and review the current version.")
        stale_reasons = _doc_staleness(r, up)
        if stale_reasons:
            raise HTTPException(409, f"Cannot approve a stale {atype} version: {stale_reasons[0]}")

        unv = _unverified_count(atype, r.content)
        if unv > 0 and not body.acknowledge_unverified:
            raise HTTPException(409, f"{unv} design decision(s) are still marked proposed or contain unverified assumptions. Approve individual decisions or acknowledge unverified items to approve.")

        brain_snap = ProjectBrain.model_validate(latest_revision(db, project.id).snapshot).model_dump()
        design_brain = brain_snap.get("design_spec", {})
        design_brain[atype] = {
            "approved_version": r.version,
            "document_id": r.id,
            "content_hash": r.content_hash,
            "approved_at": now().isoformat(),
            "basis_versions": {
                k: v for k, v in (r.basis or {}).items() if k.endswith("_version") and isinstance(v, int)
            },
            "item_count": _item_count(atype, r.content),
            "unverified_acknowledged": bool(unv),
        }
        rev = commit_brain(db, project, {"design_spec": design_brain}, f"design_{atype}_approved", user.id, commit=False)
        r.status, r.approved_at, r.approved_by, r.approval_note = "approved", now(), user.id, body.note
        r.acknowledged_unverified, r.brain_revision = bool(unv), rev.version
        db.flush()
        sync_design_stage(db, project.id)
    return build_artifact_state(db, project, atype)
