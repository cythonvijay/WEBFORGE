"""UX Design & Experience workflow (Phase 11): routes, upstream staleness gates, copy-on-write edits,
exact-hash approval, and `ux` lifecycle stage completion/invalidation.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai, ux
from .api import commit_brain, current_user, latest_revision, owned
from .brain import ProjectBrain
from .config import settings
from .db import get_db
from .discovery_api import txn
from .models import PrdDocument, Project, ProjectStage, ResearchReport, StrategyDocument, User, UxArtifact, now
from .security import as_utc

router = APIRouter(prefix="/projects/{project_id}/ux")
HASH = Field(min_length=64, max_length=64)

UPSTREAM_UX_DEPS: dict[ux.ArtifactType, tuple[ux.ArtifactType, ...]] = {
    "personas": (),
    "journeys": ("personas",),
    "ia": ("personas", "journeys"),
    "wireframes": ("personas", "journeys", "ia"),
    "ux_review": ("personas", "journeys", "ia", "wireframes"),
}

WORKSPACE_PATHS: dict[str, str] = {
    "research": "research",
    "strategy": "strategy",
    "prd": "prd",
    "personas": "personas",
    "journeys": "journeys",
    "ia": "ia",
    "wireframes": "wireframes",
    "ux_review": "ux-review",
}


class GenerateIn(BaseModel):
    supersede: bool = False


class Hashed(BaseModel):
    base_hash: str = HASH


class ApproveIn(BaseModel):
    content_hash: str = HASH
    acknowledge_unverified: bool = False
    note: str | None = Field(None, max_length=1000)


# ---------- Personas payloads ----------
class PersonaIn(Hashed):
    name: str
    segment: str
    context: str
    goals: list[str]
    tasks_behaviors: list[str]
    needs_pain_points: list[str]
    frustrations_barriers: list[str] = []
    accessibility_device_notes: list[str]
    motivations: list[str] = []
    user_story_ids: list[str] = []
    prd_requirement_ids: list[str]
    evidence_refs: list[str] = []
    unverified_assumptions: list[str] = []
    evidence_status: ux.PersonaEvidenceStatus = "hypothesis"


class PersonaPatch(Hashed):
    name: str | None = None
    segment: str | None = None
    context: str | None = None
    goals: list[str] | None = None
    tasks_behaviors: list[str] | None = None
    needs_pain_points: list[str] | None = None
    frustrations_barriers: list[str] | None = None
    accessibility_device_notes: list[str] | None = None
    motivations: list[str] | None = None
    user_story_ids: list[str] | None = None
    prd_requirement_ids: list[str] | None = None
    evidence_refs: list[str] | None = None
    unverified_assumptions: list[str] | None = None
    evidence_status: ux.PersonaEvidenceStatus | None = None


class ManualPersonaInit(BaseModel):
    name: str
    segment: str
    context: str
    goals: list[str]
    tasks_behaviors: list[str]
    needs_pain_points: list[str]
    frustrations_barriers: list[str] = []
    accessibility_device_notes: list[str]
    motivations: list[str] = []
    user_story_ids: list[str] = []
    prd_requirement_ids: list[str]
    evidence_refs: list[str] = []
    unverified_assumptions: list[str] = []
    evidence_status: ux.PersonaEvidenceStatus = "hypothesis"


# ---------- Journeys payloads ----------
class JourneyIn(Hashed):
    title: str
    persona_id: str
    scenario: str
    desired_outcome: str
    entry_point: str
    preconditions: list[str] = []
    stages: list[dict]
    accessibility_considerations: list[str]
    prd_requirement_ids: list[str]
    opportunities: list[str] = []
    unresolved_questions: list[str] = []


class JourneyPatch(Hashed):
    title: str | None = None
    persona_id: str | None = None
    scenario: str | None = None
    desired_outcome: str | None = None
    entry_point: str | None = None
    preconditions: list[str] | None = None
    stages: list[dict] | None = None
    accessibility_considerations: list[str] | None = None
    prd_requirement_ids: list[str] | None = None
    opportunities: list[str] | None = None
    unresolved_questions: list[str] | None = None


# ---------- IA payloads ----------
class IaNodeIn(Hashed):
    name: str
    path: str
    parent_id: str | None = None
    order: int = 0
    purpose: str
    navigation_group: ux.NavGroup = "primary"
    content_groups: list[str]
    key_actions: list[str]
    access_role: str = "Authenticated user"
    prd_requirement_ids: list[str]


class IaNodePatch(Hashed):
    name: str | None = None
    path: str | None = None
    parent_id: str | None = None
    clear_parent: bool = False
    order: int | None = None
    purpose: str | None = None
    navigation_group: ux.NavGroup | None = None
    content_groups: list[str] | None = None
    key_actions: list[str] | None = None
    access_role: str | None = None
    prd_requirement_ids: list[str] | None = None


class IaNavPatch(Hashed):
    primary_nav: list[str] | None = None
    secondary_nav: list[str] | None = None
    utility_nav: list[str] | None = None
    open_questions: list[str] | None = None
    assumptions: list[str] | None = None


# ---------- Wireframes payloads ----------
class WireframeIn(Hashed):
    page_name: str
    purpose: str
    ia_node_id: str
    target_viewport: ux.ViewportKind = "responsive"
    regions: list[dict]
    primary_actions: list[str]
    secondary_actions: list[str] = []
    form_fields: list[dict] = []
    states: dict
    responsive_behavior: dict
    accessibility_keyboard: list[str]
    persona_ids: list[str]
    journey_ids: list[str]
    prd_requirement_ids: list[str]


class WireframePatch(Hashed):
    page_name: str | None = None
    purpose: str | None = None
    ia_node_id: str | None = None
    target_viewport: ux.ViewportKind | None = None
    regions: list[dict] | None = None
    primary_actions: list[str] | None = None
    secondary_actions: list[str] | None = None
    form_fields: list[dict] | None = None
    states: dict | None = None
    responsive_behavior: dict | None = None
    accessibility_keyboard: list[str] | None = None
    persona_ids: list[str] | None = None
    journey_ids: list[str] | None = None
    prd_requirement_ids: list[str] | None = None


# ---------- UX Review payloads ----------
class UxFindingIn(Hashed):
    severity: ux.FindingSeverity = "medium"
    category: ux.FindingCategory = "consistency"
    affected_artifact: ux.AffectedArtifact = "wireframes"
    affected_item_id: str | None = None
    title: str
    reasoning: str
    prd_requirement_ids: list[str] = []
    recommended_action: str
    status: ux.FindingStatus = "open"
    resolution_note: str | None = None


class UxFindingPatch(Hashed):
    severity: ux.FindingSeverity | None = None
    category: ux.FindingCategory | None = None
    title: str | None = None
    reasoning: str | None = None
    prd_requirement_ids: list[str] | None = None
    recommended_action: str | None = None
    status: ux.FindingStatus | None = None
    resolution_note: str | None = None


# ---------- DB & upstream helpers ----------
def _iso(d: datetime | None) -> str | None:
    return as_utc(d).isoformat() if d else None


def _stage(db: Session, pid: str, name: str = "ux") -> ProjectStage:
    return db.scalar(select(ProjectStage).where(ProjectStage.project_id == pid, ProjectStage.stage == name))


def _all_ux(db: Session, pid: str, atype: ux.ArtifactType) -> list[UxArtifact]:
    return list(
        db.scalars(
            select(UxArtifact)
            .where(UxArtifact.project_id == pid, UxArtifact.artifact_type == atype)
            .order_by(UxArtifact.version.desc())
        )
    )


def _stale_gen(r: UxArtifact) -> bool:
    return r.status == "generating" and as_utc(r.updated_at) < datetime.now(timezone.utc) - timedelta(seconds=settings.ux_generation_timeout_seconds)


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

    res_stage = _stage(db, pid, "research")
    prod_stage = _stage(db, pid, "product")

    ux_by_type: dict[ux.ArtifactType, dict[str, UxArtifact | None]] = {}
    for t in ux.ARTIFACT_TYPES:
        rows = [r for r in _all_ux(db, pid, t) if r.status != "failed"]
        ux_by_type[t] = {
            "open": next((r for r in rows if r.status in ("draft", "in_review") or (r.status == "generating" and not _stale_gen(r))), None),
            "approved": next((r for r in rows if r.status == "approved"), None),
        }

    return {
        "res_stage": res_stage.status if res_stage else "not_started",
        "prod_stage": prod_stage.status if prod_stage else "not_started",
        "res_open": res_open,
        "res_app": res_app,
        "stg_open": stg_open,
        "stg_app": stg_app,
        "prd_open": prd_open,
        "prd_app": prd_app,
        "ux": ux_by_type,
    }


def check_prerequisites(db: Session, pid: str, atype: ux.ArtifactType) -> dict[str, Any]:
    """Verify upstream Phase 9, Phase 10, and earlier Phase 11 prerequisites for `atype`."""
    up = _upstream_state(db, pid)
    missing: list[dict[str, str]] = []

    res_app, res_open = up["res_app"], up["res_open"]
    stg_app, stg_open = up["stg_app"], up["stg_open"]
    prd_app, prd_open = up["prd_app"], up["prd_open"]

    if up["res_stage"] != "complete" or res_app is None or res_open is not None:
        missing.append({
            "artifact": "research",
            "label": "Research",
            "message": "Research has an unapproved draft in progress." if res_open else "Approve your Research report first.",
            "workspace_path": f"/projects/{pid}/research",
        })
    if stg_app is None or stg_open is not None:
        missing.append({
            "artifact": "strategy",
            "label": "Product Strategy",
            "message": "Product Strategy has an unapproved draft in progress." if stg_open else "Approve your Product Strategy first.",
            "workspace_path": f"/projects/{pid}/strategy",
        })
    elif res_app and stg_app.basis.get("research_version") != res_app.version:
        missing.append({
            "artifact": "strategy",
            "label": "Product Strategy",
            "message": f"Strategy v{stg_app.version} was built from Research v{stg_app.basis.get('research_version')}, while Research v{res_app.version} is now approved.",
            "workspace_path": f"/projects/{pid}/strategy",
        })

    if prd_app is None or prd_open is not None or up["prod_stage"] != "complete":
        missing.append({
            "artifact": "prd",
            "label": "PRD",
            "message": "PRD has an unapproved draft in progress." if prd_open else "Approve your PRD to complete the Product stage first.",
            "workspace_path": f"/projects/{pid}/prd",
        })
    elif stg_app and prd_app.basis.get("strategy_version") != stg_app.version:
        missing.append({
            "artifact": "prd",
            "label": "PRD",
            "message": f"PRD v{prd_app.version} was built from Strategy v{prd_app.basis.get('strategy_version')}, while Strategy v{stg_app.version} is now approved.",
            "workspace_path": f"/projects/{pid}/prd",
        })

    for dep in UPSTREAM_UX_DEPS[atype]:
        dep_info = up["ux"][dep]
        dep_app, dep_open = dep_info["approved"], dep_info["open"]
        label = {"personas": "Personas", "journeys": "User Journeys", "ia": "Information Architecture", "wireframes": "Wireframes"}[dep]
        wpath = f"/projects/{pid}/{WORKSPACE_PATHS[dep]}"
        if dep_app is None or dep_open is not None:
            missing.append({
                "artifact": dep,
                "label": label,
                "message": f"{label} has an unapproved draft open; approve it first." if dep_open else f"Generate and approve {label} before starting this workspace.",
                "workspace_path": wpath,
            })
        else:
            dep_stale = _doc_staleness(dep_app, up)
            if dep_stale:
                missing.append({
                    "artifact": dep,
                    "label": label,
                    "message": f"Approved {label} v{dep_app.version} is stale ({dep_stale[0]}). Update and re-approve {label} first.",
                    "workspace_path": wpath,
                })

    return {
        "ready": len(missing) == 0,
        "missing": missing,
        "upstream_versions": {
            "research": res_app.version if res_app else None,
            "strategy": stg_app.version if stg_app else None,
            "prd": prd_app.version if prd_app else None,
            "personas": up["ux"]["personas"]["approved"].version if up["ux"]["personas"]["approved"] else None,
            "journeys": up["ux"]["journeys"]["approved"].version if up["ux"]["journeys"]["approved"] else None,
            "ia": up["ux"]["ia"]["approved"].version if up["ux"]["ia"]["approved"] else None,
            "wireframes": up["ux"]["wireframes"]["approved"].version if up["ux"]["wireframes"]["approved"] else None,
        },
        "_up": up,
    }


def _doc_staleness(doc: UxArtifact | None, up: dict[str, Any]) -> list[str]:
    if doc is None:
        return []
    reasons: list[str] = []
    b = doc.basis or {}
    if up["res_open"] is not None:
        reasons.append("Research has a new unapproved draft in progress.")
    elif up["res_app"] and b.get("research_version") != up["res_app"].version:
        reasons.append(f"Built from Research v{b.get('research_version')}, while Research v{up['res_app'].version} is now approved.")

    if up["stg_open"] is not None:
        reasons.append("Product Strategy has a new unapproved draft in progress.")
    elif up["stg_app"] and b.get("strategy_version") != up["stg_app"].version:
        reasons.append(f"Built from Strategy v{b.get('strategy_version')}, while Strategy v{up['stg_app'].version} is now approved.")

    if up["prd_open"] is not None:
        reasons.append("PRD has a new unapproved draft in progress.")
    elif up["prd_app"] and b.get("prd_version") != up["prd_app"].version:
        reasons.append(f"Built from PRD v{b.get('prd_version')}, while PRD v{up['prd_app'].version} is now approved.")

    for dep in UPSTREAM_UX_DEPS[doc.artifact_type]:
        dep_open = up["ux"][dep]["open"]
        dep_app = up["ux"][dep]["approved"]
        label = {"personas": "Personas", "journeys": "User Journeys", "ia": "Information Architecture", "wireframes": "Wireframes"}[dep]
        if dep_open is not None:
            reasons.append(f"{label} has an unapproved draft open.")
        elif dep_app and b.get(f"{dep}_version") != dep_app.version:
            reasons.append(f"Built from {label} v{b.get(f'{dep}_version')}, while {label} v{dep_app.version} is now approved.")
    return reasons


def ux_stage_completion_check(db: Session, pid: str) -> tuple[bool, list[str]]:
    """Verify whether the `ux` lifecycle stage meets all documented completion criteria."""
    up = _upstream_state(db, pid)
    reasons: list[str] = []
    if up["res_stage"] != "complete" or up["prod_stage"] != "complete" or up["res_open"] or up["stg_open"] or up["prd_open"]:
        reasons.append("Upstream Research, Strategy, and PRD must be approved and complete.")
    for t in ux.ARTIFACT_TYPES:
        app_doc = up["ux"][t]["approved"]
        open_doc = up["ux"][t]["open"]
        if app_doc is None:
            reasons.append(f"UX artifact '{t}' has not been approved yet.")
        elif open_doc is not None:
            reasons.append(f"UX artifact '{t}' has an unapproved draft (v{open_doc.version}) open.")
        else:
            st_reasons = _doc_staleness(app_doc, up)
            if st_reasons:
                reasons.append(f"UX artifact '{t}' v{app_doc.version} is stale: {st_reasons[0]}")
            if t == "ux_review" and app_doc.content:
                counts = ux.review_counts(app_doc.content)
                if counts["critical_open"] > 0:
                    reasons.append(f"UX review v{app_doc.version} has {counts['critical_open']} unresolved critical finding(s).")
    return len(reasons) == 0, reasons


def sync_ux_stage(db: Session, pid: str) -> None:
    """Synchronize the `ux` lifecycle stage based on persisted UX artifacts and upstream state."""
    st = _stage(db, pid, "ux")
    if st is None:
        return
    all_rows = list(db.scalars(select(UxArtifact).where(UxArtifact.project_id == pid, UxArtifact.status != "failed")))
    if not all_rows:
        return
    complete_ok, _ = ux_stage_completion_check(db, pid)
    if complete_ok:
        st.status = "complete"
        from .design_api import sync_design_stage
        sync_design_stage(db, pid)
        return
    any_in_review = any(r.status == "in_review" for r in all_rows)
    any_draft = any(r.status == "draft" for r in all_rows)
    if any_in_review and not any_draft and _stage(db, pid, "product").status == "complete":
        st.status = "needs_review"
    else:
        if st.status in ("complete", "needs_review") or any(r.status in ("draft", "approved") for r in all_rows):
            if _stage(db, pid, "product").status == "complete" or st.status in ("complete", "needs_review"):
                st.status = "in_progress"
    from .design_api import sync_design_stage
    sync_design_stage(db, pid)


def _build_basis_and_summary(db: Session, pid: str, atype: ux.ArtifactType) -> tuple[dict, ux.UxBasisSummary, dict[str, Any]]:
    prereq = check_prerequisites(db, pid, atype)
    if not prereq["ready"]:
        raise HTTPException(409, prereq["missing"][0]["message"])
    up = prereq["_up"]
    res_app, stg_app, prd_app = up["res_app"], up["stg_app"], up["prd_app"]
    p_app = up["ux"]["personas"]["approved"] if atype in ("journeys", "ia", "wireframes", "ux_review") else None
    j_app = up["ux"]["journeys"]["approved"] if atype in ("ia", "wireframes", "ux_review") else None
    ia_app = up["ux"]["ia"]["approved"] if atype in ("wireframes", "ux_review") else None
    wf_app = up["ux"]["wireframes"]["approved"] if atype == "ux_review" else None

    summary = ux.build_ux_basis(
        research_doc=res_app.content,
        research_ver=res_app.version,
        strategy_doc=stg_app.content,
        strategy_ver=stg_app.version,
        prd_doc=prd_app.content,
        prd_ver=prd_app.version,
        personas_doc=p_app.content if p_app else None,
        personas_ver=p_app.version if p_app else None,
        journeys_doc=j_app.content if j_app else None,
        journeys_ver=j_app.version if j_app else None,
        ia_doc=ia_app.content if ia_app else None,
        ia_ver=ia_app.version if ia_app else None,
        wireframes_doc=wf_app.content if wf_app else None,
        wireframes_ver=wf_app.version if wf_app else None,
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
    }
    if p_app:
        basis_meta.update(personas_id=p_app.id, personas_version=p_app.version, personas_hash=p_app.content_hash)
    if j_app:
        basis_meta.update(journeys_id=j_app.id, journeys_version=j_app.version, journeys_hash=j_app.content_hash)
    if ia_app:
        basis_meta.update(ia_id=ia_app.id, ia_version=ia_app.version, ia_hash=ia_app.content_hash)
    if wf_app:
        basis_meta.update(wireframes_id=wf_app.id, wireframes_version=wf_app.version, wireframes_hash=wf_app.content_hash)
    return basis_meta, summary, up


def _item_count(atype: ux.ArtifactType, content: dict | None) -> int:
    if not content:
        return 0
    key = {"personas": "personas", "journeys": "journeys", "ia": "nodes", "wireframes": "wireframes", "ux_review": "findings"}[atype]
    return len(content.get(key, []))


def _unverified_count(atype: ux.ArtifactType, content: dict | None) -> int:
    if not content:
        return 0
    if atype == "personas":
        return sum(p.get("needs_evidence", False) or p.get("evidence_status") == "hypothesis" for p in content.get("personas", []))
    if atype == "journeys":
        return sum(bool(j.get("unresolved_questions")) for j in content.get("journeys", []))
    if atype == "ia":
        return len(content.get("open_questions", [])) + len(content.get("assumptions", []))
    if atype == "wireframes":
        return 0
    if atype == "ux_review":
        return sum(f.get("status") in ("open", "needs_evidence") and f.get("severity") != "critical" for f in content.get("findings", []))
    return 0


def _critical_open_count(atype: ux.ArtifactType, content: dict | None) -> int:
    if atype != "ux_review" or not content:
        return 0
    return ux.review_counts(content)["critical_open"]


def _warnings(doc: UxArtifact, stale_reasons: list[str]) -> list[dict[str, str]]:
    w: list[dict[str, str]] = []
    for reason in stale_reasons:
        w.append({"code": "stale_upstream", "message": reason})
    c = doc.content
    if not c:
        return w
    if doc.artifact_type == "personas":
        hyp = sum(p.get("evidence_status") == "hypothesis" or p.get("needs_evidence") for p in c.get("personas", []))
        if hyp:
            w.append({"code": "hypothesis_personas", "message": f"{hyp} persona(s) contain unverified hypotheses or assumptions."})
    elif doc.artifact_type == "ux_review":
        rc = ux.review_counts(c)
        if rc["critical_open"] > 0:
            w.append({"code": "critical_blockers", "message": f"{rc['critical_open']} critical UX finding(s) are open and block approval until resolved or accepted with a rationale."})
        if rc["open"] + rc["needs_evidence"] > rc["critical_open"]:
            rem = (rc["open"] + rc["needs_evidence"]) - rc["critical_open"]
            w.append({"code": "open_findings", "message": f"{rem} non-critical UX finding(s) remain open or need evidence."})
    return w


def _summary(r: UxArtifact) -> dict:
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


def _out(r: UxArtifact, up: dict[str, Any]) -> dict:
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
        "critical_open_count": _critical_open_count(r.artifact_type, r.content),
        "review_counts": ux.review_counts(r.content) if r.artifact_type == "ux_review" and r.content else None,
        "is_stale": len(stale_reasons) > 0,
        "stale_reasons": stale_reasons,
        "editable": r.status in ("draft", "in_review"),
        "warnings": _warnings(r, stale_reasons),
    }


def build_artifact_state(db: Session, project: Project, atype: ux.ArtifactType) -> dict:
    prereq = check_prerequisites(db, project.id, atype)
    up = prereq["_up"]
    rows = _all_ux(db, project.id, atype)
    gen = next((r for r in rows if r.status == "generating" and not _stale_gen(r)), None)
    open_ = next((r for r in rows if r.status in ("draft", "in_review")), None)
    approved = next((r for r in rows if r.status == "approved"), None)
    current = open_ or approved
    failed = rows[0] if rows and (rows[0].status == "failed" or _stale_gen(rows[0])) else None
    status = "generating" if gen else (current.status if current else ("failed" if failed else "not_started"))

    cur_out = _out(current, up) if current else None
    is_stale = cur_out["is_stale"] if cur_out else False
    stale_reasons = cur_out["stale_reasons"] if cur_out else []
    has_items = bool(current and _item_count(atype, current.content) > 0 or (atype == "ux_review" and current and current.content is not None))
    crit_open = cur_out["critical_open_count"] if cur_out else 0

    basis_preview = None
    if prereq["ready"] and not current:
        _, b_sum, _ = _build_basis_and_summary(db, project.id, atype)
        basis_preview = b_sum.model_dump(mode="json")

    next_workspace = {
        "personas": ("journeys", "Continue to User Journeys", f"/projects/{project.id}/journeys"),
        "journeys": ("ia", "Continue to Information Architecture", f"/projects/{project.id}/ia"),
        "ia": ("wireframes", "Continue to Wireframes", f"/projects/{project.id}/wireframes"),
        "wireframes": ("ux_review", "Continue to UX Review", f"/projects/{project.id}/ux-review"),
        "ux_review": ("design-system", "UX stage complete — view Overview", f"/projects/{project.id}/overview"),
    }[atype]

    step = (
        {"key": "fix_prerequisites", "label": prereq["missing"][0]["message"], "workspace_path": prereq["missing"][0]["workspace_path"]} if not prereq["ready"] else
        {"key": "wait", "label": f"{atype} is being generated"} if gen else
        {"key": "retry_generation", "label": f"Retry generating {atype}"} if status == "failed" else
        {"key": "start", "label": f"Generate {atype} from approved upstream artifacts"} if status == "not_started" else
        {"key": "stale_upstream", "label": f"Upstream artifacts changed ({stale_reasons[0]}). Regenerate or update this workspace."} if is_stale else
        {"key": "review_and_submit", "label": "Review and edit items, then submit for review"} if status == "draft" else
        {"key": "resolve_critical", "label": f"Resolve or explicitly accept {crit_open} critical finding(s) before approving."} if status == "in_review" and crit_open > 0 else
        {"key": "approve", "label": f"Approve this {atype} version"} if status == "in_review" else
        {"key": "approved", "label": f"Approved. {next_workspace[1]}", "workspace_path": next_workspace[2]}
    )

    ux_complete, ux_missing = ux_stage_completion_check(db, project.id)
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
            "stage": "ux",
            "status": _stage(db, project.id, "ux").status,
            "ux_complete": ux_complete,
            "pending_criteria": ux_missing,
        },
        "next_step": step,
        "can_generate": prereq["ready"] and gen is None,
        "needs_supersede": open_ is not None,
        "can_submit": bool(current and current.status == "draft" and has_items and prereq["ready"] and not is_stale),
        "can_approve": bool(current and current.status == "in_review" and prereq["ready"] and not is_stale and crit_open == 0),
        "limitations": ux.UX_LIMITATIONS[atype],
    }


def _get_doc(db: Session, project: Project, atype: ux.ArtifactType, version: int, lock: bool = False) -> UxArtifact:
    q = select(UxArtifact).where(UxArtifact.project_id == project.id, UxArtifact.artifact_type == atype, UxArtifact.version == version)
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


def _content_model(atype: ux.ArtifactType):
    return {
        "personas": ux.PersonasContent,
        "journeys": ux.JourneysContent,
        "ia": ux.IaContent,
        "wireframes": ux.WireframesContent,
        "ux_review": ux.UxReviewContent,
    }[atype]


def _check_atype(artifact: str) -> ux.ArtifactType:
    if artifact not in ux.ARTIFACT_TYPES:
        raise HTTPException(404, f"Unknown UX artifact type '{artifact}'.")
    return artifact  # type: ignore[return-value]


# ---------- Overview endpoint ----------
@router.get("")
def get_ux_overview(project: Project = Depends(owned), db: Session = Depends(get_db)):
    up = _upstream_state(db, project.id)
    ux_ok, missing_reasons = ux_stage_completion_check(db, project.id)
    artifacts_summary = {}
    for t in ux.ARTIFACT_TYPES:
        st = build_artifact_state(db, project, t)
        artifacts_summary[t] = {
            "status": st["status"],
            "approved_version": st["approved_version"],
            "is_stale": st["is_stale"],
            "prerequisites_ready": st["prerequisites"]["ready"],
            "item_count": st["current"]["item_count"] if st["current"] else 0,
        }
    return {
        "stage": "ux",
        "status": _stage(db, project.id, "ux").status,
        "ux_complete": ux_ok,
        "pending_criteria": missing_reasons,
        "upstream": {
            "research_version": up["res_app"].version if up["res_app"] else None,
            "strategy_version": up["stg_app"].version if up["stg_app"] else None,
            "prd_version": up["prd_app"].version if up["prd_app"] else None,
        },
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

    res_content = up["res_app"].content
    stg_content = up["stg_app"].content
    prd_content = up["prd_app"].content
    p_content = up["ux"]["personas"]["approved"].content if up["ux"]["personas"]["approved"] else {}
    j_content = up["ux"]["journeys"]["approved"].content if up["ux"]["journeys"]["approved"] else {}
    ia_content = up["ux"]["ia"]["approved"].content if up["ux"]["ia"]["approved"] else {}
    wf_content = up["ux"]["wireframes"]["approved"].content if up["ux"]["wireframes"]["approved"] else {}

    with txn(db):
        db.get(Project, project.id, with_for_update=True, populate_existing=True)
        rows = _all_ux(db, project.id, atype)
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
            row = UxArtifact(
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
        if atype == "personas":
            gen_out = await prov.generate_structured(ux.build_personas_prompt(basis_summary, res_content, stg_content, prd_content), ux.GeneratedPersonas)
            content_obj = ux.to_personas_content(basis_summary, gen_out)
        elif atype == "journeys":
            gen_out = await prov.generate_structured(ux.build_journeys_prompt(basis_summary, prd_content, p_content), ux.GeneratedJourneys)
            content_obj = ux.to_journeys_content(basis_summary, gen_out)
        elif atype == "ia":
            gen_out = await prov.generate_structured(ux.build_ia_prompt(basis_summary, prd_content, p_content, j_content), ux.GeneratedIa)
            content_obj = ux.to_ia_content(basis_summary, gen_out)
        elif atype == "wireframes":
            gen_out = await prov.generate_structured(ux.build_wireframes_prompt(basis_summary, prd_content, p_content, j_content, ia_content), ux.GeneratedWireframes)
            content_obj = ux.to_wireframes_content(basis_summary, gen_out)
        else:
            det_findings = ux.build_deterministic_ux_findings(basis_summary, prd_content, p_content, j_content, ia_content, wf_content)
            gen_out = await prov.generate_structured(
                ux.build_ux_review_prompt(basis_summary, prd_content, p_content, j_content, ia_content, wf_content, det_findings),
                ux.GeneratedUxReview,
            )
            content_obj = ux.to_ux_review_content(basis_summary, det_findings, gen_out)
        stored = content_obj.model_dump(mode="json")
        failure = None
    except (ai.ProviderNotConfigured, ai.ProviderError, ValidationError, ValueError) as e:
        failure = e

    if failure is not None:
        unconfigured = isinstance(failure, ai.ProviderNotConfigured)
        msg = "AI provider not configured." if unconfigured else (ai.user_message(failure) if isinstance(failure, ai.ProviderError) else ai.USER_MESSAGES["malformed"])
        with txn(db):
            r = db.get(UxArtifact, doc_id, with_for_update=True, populate_existing=True)
            if r.status == "generating":
                r.status, r.error = "failed", msg
        raise HTTPException(503 if unconfigured else 502, f"{msg} Nothing was changed.")

    with txn(db):
        r = db.get(UxArtifact, doc_id, with_for_update=True, populate_existing=True)
        if r.status != "generating":
            raise HTTPException(409, "Another request changed this UX artifact.")
        for old in _all_ux(db, project.id, atype):
            if old.id != doc_id and old.status in ("draft", "in_review"):
                old.status = "superseded"
        db.flush()
        r.status, r.content, r.content_hash, r.error = "draft", stored, ux.content_hash(stored), None
        sync_ux_stage(db, project.id)
    return build_artifact_state(db, project, atype)


@router.post("/personas/manual")
def create_manual_personas_draft(body: ManualPersonaInit, project: Project = Depends(owned), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Allows creating a manual Personas draft even when the AI provider is unconfigured."""
    basis_meta, basis_summary, _ = _build_basis_and_summary(db, project.id, "personas")
    with txn(db):
        rows = _all_ux(db, project.id, "personas")
        if any(r.status in ("draft", "in_review", "generating") for r in rows):
            raise HTTPException(409, "An open Personas draft already exists. Edit that version instead.")
        p_data = body.model_dump(mode="json")
        try:
            content_obj = ux.PersonasContent(
                basis=basis_summary,
                personas=[{**p_data, "id": "P-1", "origin": "user", "edited_by_user": False, "note": None}],
            )
            stored = content_obj.model_dump(mode="json")
        except ValidationError as e:
            raise _validation_error(e) from None
        approved = next((r for r in rows if r.status == "approved"), None)
        row = UxArtifact(
            project_id=project.id,
            artifact_type="personas",
            version=(rows[0].version + 1) if rows else 1,
            status="draft",
            content=stored,
            content_hash=ux.content_hash(stored),
            basis=basis_meta,
            parent_version=approved.version if approved else None,
            created_via="manual",
            created_by=user.id,
        )
        db.add(row)
        db.flush()
        sync_ux_stage(db, project.id)
    return build_artifact_state(db, project, "personas")


# ---------- Copy-on-write mutation helper ----------
def _mutate(db: Session, project: Project, atype: ux.ArtifactType, version: int, base_hash: str, fn) -> UxArtifact:
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
            if any(x.status in ("draft", "in_review") or (x.status == "generating" and not _stale_gen(x)) for x in _all_ux(db, project.id, atype)):
                raise HTTPException(409, "A newer version is already open. Edit that version instead.")
            top = _all_ux(db, project.id, atype)[0]
            target = UxArtifact(
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
        target.content, target.content_hash = stored, ux.content_hash(stored)
        db.flush()
        sync_ux_stage(db, project.id)
        return target


def _respond(db: Session, project: Project, doc: UxArtifact) -> dict:
    up = _upstream_state(db, project.id)
    return {"document": _out(doc, up), "state": build_artifact_state(db, project, doc.artifact_type)}


# ---------- 1. Personas item routes ----------
@router.post("/personas/versions/{version}/items")
def add_persona(version: int, body: PersonaIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        p = body.model_dump(mode="json", exclude={"base_hash"})
        c["personas"].append({**p, "id": _next_id("P", c["personas"]), "origin": "user", "edited_by_user": False, "note": None})
        return c
    return _respond(db, project, _mutate(db, project, "personas", version, body.base_hash, fn))


@router.patch("/personas/versions/{version}/items/{item_id}")
def patch_persona(version: int, item_id: str, body: PersonaPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        p = next((x for x in c["personas"] if x["id"] == item_id), None)
        if p is None:
            raise HTTPException(404, "Persona not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        p.update(data)
        p["edited_by_user"], p["note"] = True, None
        return c
    return _respond(db, project, _mutate(db, project, "personas", version, body.base_hash, fn))


@router.delete("/personas/versions/{version}/items/{item_id}")
def delete_persona(version: int, item_id: str, base_hash: str = Query(..., min_length=64, max_length=64), project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        if not any(x["id"] == item_id for x in c["personas"]):
            raise HTTPException(404, "Persona not found.")
        c["personas"] = [x for x in c["personas"] if x["id"] != item_id]
        return c
    return _respond(db, project, _mutate(db, project, "personas", version, base_hash, fn))


# ---------- 2. Journeys item routes ----------
@router.post("/journeys/versions/{version}/items")
def add_journey(version: int, body: JourneyIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        j = body.model_dump(mode="json", exclude={"base_hash"})
        for idx, st in enumerate(j["stages"], 1):
            st.setdefault("stage_number", idx)
        c["journeys"].append({**j, "id": _next_id("J", c["journeys"]), "origin": "user", "edited_by_user": False})
        return c
    return _respond(db, project, _mutate(db, project, "journeys", version, body.base_hash, fn))


@router.patch("/journeys/versions/{version}/items/{item_id}")
def patch_journey(version: int, item_id: str, body: JourneyPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        j = next((x for x in c["journeys"] if x["id"] == item_id), None)
        if j is None:
            raise HTTPException(404, "User journey not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        if "stages" in data and data["stages"] is not None:
            for idx, st in enumerate(data["stages"], 1):
                st.setdefault("stage_number", idx)
        j.update(data)
        j["edited_by_user"] = True
        return c
    return _respond(db, project, _mutate(db, project, "journeys", version, body.base_hash, fn))


@router.delete("/journeys/versions/{version}/items/{item_id}")
def delete_journey(version: int, item_id: str, base_hash: str = Query(..., min_length=64, max_length=64), project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        if not any(x["id"] == item_id for x in c["journeys"]):
            raise HTTPException(404, "User journey not found.")
        c["journeys"] = [x for x in c["journeys"] if x["id"] != item_id]
        return c
    return _respond(db, project, _mutate(db, project, "journeys", version, base_hash, fn))


# ---------- 3. IA node & navigation routes ----------
@router.post("/ia/versions/{version}/nodes")
def add_ia_node(version: int, body: IaNodeIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        n = body.model_dump(mode="json", exclude={"base_hash"})
        c["nodes"].append({**n, "id": _next_id("IA", c["nodes"]), "origin": "user", "edited_by_user": False})
        return c
    return _respond(db, project, _mutate(db, project, "ia", version, body.base_hash, fn))


@router.patch("/ia/versions/{version}/nodes/{node_id}")
def patch_ia_node(version: int, node_id: str, body: IaNodePatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        n = next((x for x in c["nodes"] if x["id"] == node_id), None)
        if n is None:
            raise HTTPException(404, "IA node not found.")
        data = body.model_dump(mode="json", exclude={"base_hash", "clear_parent"}, exclude_unset=True)
        if body.clear_parent:
            data["parent_id"] = None
        n.update(data)
        n["edited_by_user"] = True
        return c
    return _respond(db, project, _mutate(db, project, "ia", version, body.base_hash, fn))


@router.delete("/ia/versions/{version}/nodes/{node_id}")
def delete_ia_node(version: int, node_id: str, base_hash: str = Query(..., min_length=64, max_length=64), project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        if not any(x["id"] == node_id for x in c["nodes"]):
            raise HTTPException(404, "IA node not found.")
        children = [x["id"] for x in c["nodes"] if x.get("parent_id") == node_id]
        if children:
            raise HTTPException(409, f"Cannot delete node {node_id} because child nodes ({', '.join(children)}) depend on it. Re-parent or remove child nodes first.")
        c["nodes"] = [x for x in c["nodes"] if x["id"] != node_id]
        return c
    return _respond(db, project, _mutate(db, project, "ia", version, base_hash, fn))


@router.patch("/ia/versions/{version}/navigation")
def patch_ia_nav(version: int, body: IaNavPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        for k in ("primary_nav", "secondary_nav", "utility_nav"):
            if k in data and data[k] is not None:
                c["navigation_model"][k] = data[k]
        for k in ("open_questions", "assumptions"):
            if k in data and data[k] is not None:
                c[k] = data[k]
        return c
    return _respond(db, project, _mutate(db, project, "ia", version, body.base_hash, fn))


# ---------- 4. Wireframes item routes ----------
@router.post("/wireframes/versions/{version}/items")
def add_wireframe(version: int, body: WireframeIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        w = body.model_dump(mode="json", exclude={"base_hash"})
        c["wireframes"].append({**w, "id": _next_id("WF", c["wireframes"]), "origin": "user", "edited_by_user": False})
        return c
    return _respond(db, project, _mutate(db, project, "wireframes", version, body.base_hash, fn))


@router.patch("/wireframes/versions/{version}/items/{item_id}")
def patch_wireframe(version: int, item_id: str, body: WireframePatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        w = next((x for x in c["wireframes"] if x["id"] == item_id), None)
        if w is None:
            raise HTTPException(404, "Wireframe not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        w.update(data)
        w["edited_by_user"] = True
        return c
    return _respond(db, project, _mutate(db, project, "wireframes", version, body.base_hash, fn))


@router.delete("/wireframes/versions/{version}/items/{item_id}")
def delete_wireframe(version: int, item_id: str, base_hash: str = Query(..., min_length=64, max_length=64), project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        if not any(x["id"] == item_id for x in c["wireframes"]):
            raise HTTPException(404, "Wireframe not found.")
        c["wireframes"] = [x for x in c["wireframes"] if x["id"] != item_id]
        return c
    return _respond(db, project, _mutate(db, project, "wireframes", version, base_hash, fn))


# ---------- 5. UX Review finding routes ----------
@router.post("/ux_review/versions/{version}/findings")
def add_ux_finding(version: int, body: UxFindingIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        f = body.model_dump(mode="json", exclude={"base_hash"})
        ver_map = {
            "personas": c["basis"].get("personas_version") or 1,
            "journeys": c["basis"].get("journeys_version") or 1,
            "ia": c["basis"].get("ia_version") or 1,
            "wireframes": c["basis"].get("wireframes_version") or 1,
            "cross_artifact": c["basis"].get("prd_version") or 1,
        }
        c["findings"].append({
            **f,
            "id": _next_id("UXF", c["findings"]),
            "affected_version": ver_map.get(f["affected_artifact"], 1),
            "origin": "user",
            "edited_by_user": False,
        })
        return c
    return _respond(db, project, _mutate(db, project, "ux_review", version, body.base_hash, fn))


@router.patch("/ux_review/versions/{version}/findings/{finding_id}")
def patch_ux_finding(version: int, finding_id: str, body: UxFindingPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        f = next((x for x in c["findings"] if x["id"] == finding_id), None)
        if f is None:
            raise HTTPException(404, "UX review finding not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        f.update(data)
        f["edited_by_user"] = True
        return c
    return _respond(db, project, _mutate(db, project, "ux_review", version, body.base_hash, fn))


@router.delete("/ux_review/versions/{version}/findings/{finding_id}")
def delete_ux_finding(version: int, finding_id: str, base_hash: str = Query(..., min_length=64, max_length=64), project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        if not any(x["id"] == finding_id for x in c["findings"]):
            raise HTTPException(404, "UX review finding not found.")
        c["findings"] = [x for x in c["findings"] if x["id"] != finding_id]
        return c
    return _respond(db, project, _mutate(db, project, "ux_review", version, base_hash, fn))


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
        if atype != "ux_review" and _item_count(atype, r.content) == 0:
            raise HTTPException(409, f"Add at least one item to {atype} before submitting for review.")
        r.status, r.submitted_at = "in_review", now()
        sync_ux_stage(db, project.id)
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

        crit_open = _critical_open_count(atype, r.content)
        if crit_open > 0:
            raise HTTPException(409, f"{crit_open} critical UX finding(s) are still open. Resolve them or mark them accepted with a resolution note before approving.")

        unv = _unverified_count(atype, r.content)
        if unv > 0 and not body.acknowledge_unverified:
            raise HTTPException(409, f"{unv} item(s) contain unverified hypotheses, open questions, or open findings. Acknowledge that to approve.")

        brain_snap = ProjectBrain.model_validate(latest_revision(db, project.id).snapshot).model_dump()
        ux_brain = brain_snap.get("ux", {})
        ux_brain[atype] = {
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
        rev = commit_brain(db, project, {"ux": ux_brain}, f"ux_{atype}_approved", user.id, commit=False)
        r.status, r.approved_at, r.approved_by, r.approval_note = "approved", now(), user.id, body.note
        r.acknowledged_unverified, r.brain_revision = bool(unv), rev.version
        db.flush()
        sync_ux_stage(db, project.id)
    return build_artifact_state(db, project, atype)
