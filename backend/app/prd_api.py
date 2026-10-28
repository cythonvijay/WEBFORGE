"""PRD workflow (Phase 10): routes and database flows.

Document status: generating -> draft | failed ; draft -> in_review -> approved ; draft/in_review -> superseded (by regeneration).
Approved versions are immutable: editing one creates a NEW draft version (copy-on-write) that requires approval again.
Lifecycle (stage `product`): requires an approved StrategyDocument to generate; approving the PRD writes a `prd_approved`
Brain pointer revision and marks the `product` stage `complete` (provided the approved Strategy is still current).
"""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai, prd as pm
from .api import commit_brain, current_user, latest_revision, owned
from .brain import ProjectBrain
from .config import settings
from .db import get_db
from .discovery_api import txn
from .models import PrdDocument, Project, ProjectStage, StrategyDocument, User, now
from .security import as_utc
from .strategy_api import sync_product_stage

router = APIRouter(prefix="/projects/{project_id}/prd")
HASH = Field(min_length=64, max_length=64)


class GenerateIn(BaseModel):
    supersede: bool = False


class Hashed(BaseModel):
    base_hash: str = HASH


class OverviewPatch(Hashed):
    problem_statement: str | None = None
    target_users: list[str] | None = None
    mvp_boundaries: pm.PrdMvpBoundary | None = None
    dependencies: list[str] | None = None


class FunctionalReqIn(Hashed):
    title: str
    description: str
    priority: pm.Priority = "must_have"
    mvp_boundary: pm.MvpBoundary = "in_mvp"
    status: pm.ReqStatus = "proposed"
    user_story_ids: list[str] = []
    source_refs: list[str] = []
    acceptance_criteria: list[str]
    edge_cases: list[str] = []
    dependencies: list[str] = []


class FunctionalReqPatch(Hashed):
    title: str | None = None
    description: str | None = None
    priority: pm.Priority | None = None
    mvp_boundary: pm.MvpBoundary | None = None
    status: pm.ReqStatus | None = None
    user_story_ids: list[str] | None = None
    source_refs: list[str] | None = None
    acceptance_criteria: list[str] | None = None
    edge_cases: list[str] | None = None
    dependencies: list[str] | None = None


class NonFunctionalReqIn(Hashed):
    category: Literal["performance", "security", "reliability", "usability", "scalability", "compliance", "maintainability"] = "reliability"
    title: str
    description: str
    priority: pm.Priority = "should_have"
    mvp_boundary: pm.MvpBoundary = "in_mvp"
    status: pm.ReqStatus = "proposed"
    source_refs: list[str] = []
    acceptance_criteria: list[str]


class NonFunctionalReqPatch(Hashed):
    category: Literal["performance", "security", "reliability", "usability", "scalability", "compliance", "maintainability"] | None = None
    title: str | None = None
    description: str | None = None
    priority: pm.Priority | None = None
    mvp_boundary: pm.MvpBoundary | None = None
    status: pm.ReqStatus | None = None
    source_refs: list[str] | None = None
    acceptance_criteria: list[str] | None = None


class ReqApprovalIn(Hashed):
    requirement_ids: list[str] = Field(min_length=1, max_length=80)
    status: pm.ReqStatus = "approved"


class QuestionsIn(Hashed):
    questions: list[str] = Field(max_length=20)


class ApproveIn(BaseModel):
    content_hash: str = HASH
    acknowledge_unverified: bool = False
    note: str | None = Field(None, max_length=1000)


# ---------- helpers ----------
def _all(db: Session, pid: str) -> list[PrdDocument]:
    return list(db.scalars(select(PrdDocument).where(PrdDocument.project_id == pid).order_by(PrdDocument.version.desc())))


def _brain(db: Session, project: Project) -> dict:
    return ProjectBrain.model_validate(latest_revision(db, project.id).snapshot).model_dump()


def _approved_strategy(db: Session, pid: str) -> StrategyDocument | None:
    rows = list(db.scalars(select(StrategyDocument).where(StrategyDocument.project_id == pid, StrategyDocument.status == "approved").order_by(StrategyDocument.version.desc())))
    return rows[0] if rows else None


def _open_strategy(db: Session, pid: str) -> StrategyDocument | None:
    rows = list(db.scalars(select(StrategyDocument).where(StrategyDocument.project_id == pid, StrategyDocument.status.in_(("draft", "in_review"))).order_by(StrategyDocument.version.desc())))
    return rows[0] if rows else None


def _stage(db: Session, pid: str, name: str = "product") -> ProjectStage:
    return db.scalar(select(ProjectStage).where(ProjectStage.project_id == pid, ProjectStage.stage == name))


def _stale(r: PrdDocument) -> bool:
    return r.status == "generating" and as_utc(r.updated_at) < datetime.now(timezone.utc) - timedelta(seconds=settings.prd_generation_timeout_seconds)


def _iso(d: datetime | None) -> str | None:
    return as_utc(d).isoformat() if d else None


def _warnings(content: dict | None, current_stg_ver: int | None, basis_stg_ver: int | None, has_open_stg: bool) -> list[dict]:
    if not content:
        return []
    w = []
    prop = pm.proposed_count(content)
    if prop:
        w.append({"code": "proposed_requirements", "message": f"{prop} requirement(s) are still marked 'proposed' and have not been individually approved."})
    unlinked = pm.unlinked_count(content)
    if unlinked:
        w.append({"code": "unlinked_requirements", "message": f"{unlinked} requirement(s) have no linked source strategy reference."})
    if current_stg_ver and basis_stg_ver and current_stg_ver != basis_stg_ver:
        w.append({"code": "stale_strategy", "message": f"Built from Strategy v{basis_stg_ver}, while Strategy v{current_stg_ver} is now approved."})
    if has_open_stg:
        w.append({"code": "strategy_open_draft", "message": "Product Strategy has an unapproved draft in progress; approve Strategy before finalizing the PRD."})
    return w


def _summary(r: PrdDocument) -> dict:
    c = r.content
    counts = pm.requirement_counts(c) if c else {"total": 0, "approved": 0, "proposed": 0}
    return {
        "version": r.version, "status": r.status, "created_via": r.created_via, "parent_version": r.parent_version,
        "created_at": _iso(r.created_at), "updated_at": _iso(r.updated_at), "submitted_at": _iso(r.submitted_at),
        "approved_at": _iso(r.approved_at), "content_hash": r.content_hash,
        "requirement_count": counts["total"],
        "approved_requirement_count": counts["approved"],
        "proposed_requirement_count": counts["proposed"],
        "error": r.error,
    }


def _out(r: PrdDocument, current_stg_ver: int | None = None, has_open_stg: bool = False) -> dict:
    c = r.content
    return {
        **_summary(r), "id": r.id, "content": c, "basis": r.basis, "approval_note": r.approval_note,
        "acknowledged_unverified": r.acknowledged_unverified, "brain_revision": r.brain_revision,
        "requirement_counts": pm.requirement_counts(c) if c else None,
        "proposed_count": pm.proposed_count(c) if c else 0,
        "unlinked_count": pm.unlinked_count(c) if c else 0,
        "editable": r.status in ("draft", "in_review"),
        "warnings": _warnings(c, current_stg_ver, r.basis.get("strategy_version"), has_open_stg),
    }


def build_state(db: Session, project: Project) -> dict:
    rows = _all(db, project.id)
    brain = _brain(db, project)
    idea_ok = bool(brain["idea"]["raw"].strip())
    app_stg = _approved_strategy(db, project.id)
    open_stg = _open_strategy(db, project.id)
    stg_ready = app_stg is not None and open_stg is None
    gen = next((r for r in rows if r.status == "generating" and not _stale(r)), None)
    open_ = next((r for r in rows if r.status in ("draft", "in_review")), None)
    approved = next((r for r in rows if r.status == "approved"), None)
    current = open_ or approved
    failed = rows[0] if rows and (rows[0].status == "failed" or _stale(rows[0])) else None
    status = "generating" if gen else (current.status if current else ("failed" if failed else "not_started"))
    basis_preview = None if current or not app_stg else pm.build_strategy_basis(app_stg.content, app_stg.version).model_dump(mode="json")
    has_reqs = bool(current and current.content and current.content["functional_requirements"])
    stale_stg = bool(current and app_stg and current.basis.get("strategy_version") != app_stg.version)
    step = (
        {"key": "approve_strategy", "label": "Approve your Product Strategy first to unlock PRD generation"} if not stg_ready and not current else
        {"key": "wait", "label": "The PRD is being generated"} if gen else
        {"key": "retry_generation", "label": "Retry generating the PRD"} if status == "failed" else
        {"key": "start_prd", "label": "Generate a structured PRD from your approved Product Strategy"} if status == "not_started" else
        {"key": "review_and_submit", "label": "Review requirements, acceptance criteria, and MVP boundaries, then submit for review"} if status == "draft" else
        {"key": "approve", "label": "Approve this PRD version to complete the Product stage"} if status == "in_review" and not stale_stg else
        {"key": "stale_strategy", "label": f"Strategy v{app_stg.version} is now approved. Regenerate or update the PRD to complete the Product stage."} if stale_stg else
        {"key": "approved", "label": "PRD approved and Product stage complete. Edit or regenerate to start a new version."}
    )
    return {
        "status": status,
        "idea_ready": idea_ok,
        "strategy_ready": stg_ready,
        "approved_strategy_version": app_stg.version if app_stg else None,
        "current": _out(current, app_stg.version if app_stg else None, open_stg is not None) if current else None,
        "approved_version": approved.version if approved else None,
        "history": [_summary(r) for r in rows if r.status != "failed" or r.content is not None],
        "last_error": failed.error if failed else None,
        "basis_preview": basis_preview,
        "lifecycle": {"stage": "product", "status": _stage(db, project.id, "product").status},
        "next_step": step,
        "can_generate": idea_ok and stg_ready and gen is None,
        "needs_supersede": open_ is not None,
        "can_submit": bool(current and current.status == "draft" and has_reqs),
        "can_approve": bool(current and current.status == "in_review" and stg_ready and not stale_stg),
        "limitations": pm.PRD_LIMITATIONS,
    }


def _get(db: Session, project: Project, version: int, lock: bool = False) -> PrdDocument:
    q = select(PrdDocument).where(PrdDocument.project_id == project.id, PrdDocument.version == version)
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None:
        raise HTTPException(404, "PRD version not found.")
    return r


def _validation_error(e: ValidationError) -> HTTPException:
    items = [{"loc": ["body", *map(str, x["loc"])], "msg": x["msg"].removeprefix("Value error, ")} for x in e.errors(include_input=False, include_url=False)]
    return HTTPException(422, items)


def _next_id(prefix: str, items: list[dict]) -> str:
    n = [int(i["id"].split("-")[-1]) for i in items if i["id"].startswith(prefix + "-") and i["id"].split("-")[-1].isdigit()]
    return f"{prefix}-{max(n, default=0) + 1}"


# ---------- endpoints ----------
@router.get("")
def get_prd(project: Project = Depends(owned), db: Session = Depends(get_db)):
    return build_state(db, project)


@router.get("/versions/{version}")
def get_prd_version(version: int, project: Project = Depends(owned), db: Session = Depends(get_db)):
    app_stg = _approved_strategy(db, project.id)
    open_stg = _open_strategy(db, project.id)
    return _out(_get(db, project, version), app_stg.version if app_stg else None, open_stg is not None)


@router.post("/generate")
async def generate(body: GenerateIn, project: Project = Depends(owned), user: User = Depends(current_user), db: Session = Depends(get_db)):
    brain = _brain(db, project)
    if not brain["idea"]["raw"].strip():
        raise HTTPException(409, "Describe your product idea first.")
    app_stg = _approved_strategy(db, project.id)
    open_stg = _open_strategy(db, project.id)
    if app_stg is None or open_stg is not None:
        raise HTTPException(409, "Approve your Product Strategy first; PRD generation requires an approved Strategy with no unapproved draft open.")
    basis_summary = pm.build_strategy_basis(app_stg.content, app_stg.version)
    with txn(db):
        db.get(Project, project.id, with_for_update=True, populate_existing=True)
        rows = _all(db, project.id)
        gen = next((r for r in rows if r.status == "generating"), None)
        if gen and not _stale(gen):
            raise HTTPException(409, "A PRD is already being generated.")
        if any(r.status in ("draft", "in_review") for r in rows) and not body.supersede:
            raise HTTPException(409, "A PRD draft already exists. Edit it, or regenerate with supersede=true to keep it in history and start a new version.")
        retry = gen or (rows[0] if rows and rows[0].status == "failed" else None)
        approved = next((r for r in rows if r.status == "approved"), None)
        basis = {
            "brain_version": latest_revision(db, project.id).version,
            "strategy_version": app_stg.version,
            "strategy_hash": app_stg.content_hash,
            "research_version": app_stg.basis.get("research_version"),
        }
        if retry:
            retry.status, retry.error, retry.basis, retry.content, retry.content_hash = "generating", None, basis, None, None
            retry.parent_version = approved.version if approved else None
            row = retry
        else:
            row = PrdDocument(
                project_id=project.id, version=(rows[0].version + 1) if rows else 1, status="generating",
                basis=basis, parent_version=approved.version if approved else None, created_by=user.id,
            )
            db.add(row)
        db.flush()
        pid_doc = row.id
    try:
        gen_out = await ai.get_provider().generate_structured(pm.build_prompt(basis_summary, app_stg.content, brain["idea"]), pm.GeneratedPrd)
        content = pm.to_prd_content(basis_summary, gen_out)
        stored = content.model_dump(mode="json")
        failure = None
    except (ai.ProviderNotConfigured, ai.ProviderError, ValidationError) as e:
        failure = e
    if failure is not None:
        unconfigured = isinstance(failure, ai.ProviderNotConfigured)
        msg = "AI provider not configured." if unconfigured else (ai.user_message(failure) if isinstance(failure, ai.ProviderError) else ai.USER_MESSAGES["malformed"])
        with txn(db):
            r = db.get(PrdDocument, pid_doc, with_for_update=True, populate_existing=True)
            if r.status == "generating":
                r.status, r.error = "failed", msg
        raise HTTPException(503 if unconfigured else 502, f"{msg} Nothing was changed.")
    with txn(db):
        r = db.get(PrdDocument, pid_doc, with_for_update=True, populate_existing=True)
        if r.status != "generating":
            raise HTTPException(409, "Another request changed this PRD.")
        for old in _all(db, project.id):
            if old.id != pid_doc and old.status in ("draft", "in_review"):
                old.status = "superseded"
        db.flush()
        r.status, r.content, r.content_hash, r.error = "draft", stored, pm.content_hash(stored), None
        sync_product_stage(db, project.id)
    return build_state(db, project)


# ---------- edits (copy-on-write for approved versions) ----------
def _mutate(db: Session, project: Project, version: int, base_hash: str, fn) -> PrdDocument:
    with txn(db):
        r = _get(db, project, version, lock=True)
        if r.status not in ("draft", "in_review", "approved"):
            raise HTTPException(409, f"A {r.status} PRD version cannot be edited.")
        if r.content_hash != base_hash:
            raise HTTPException(409, "This PRD changed since you loaded it. Reload and try again.")
        data = fn(pm.PrdContent.model_validate(r.content).model_dump(mode="json"))
        try:
            stored = pm.PrdContent.model_validate(data).model_dump(mode="json")
        except ValidationError as e:
            raise _validation_error(e) from None
        target = r
        if r.status == "approved":
            if any(x.status in ("draft", "in_review", "generating") and not _stale(x) for x in _all(db, project.id)):
                raise HTTPException(409, "A newer version is already open. Edit that version instead.")
            top = _all(db, project.id)[0]
            target = PrdDocument(
                project_id=project.id, version=top.version + 1, status="draft", basis=r.basis, parent_version=r.version,
                created_via="copy_of_approved", created_by=r.created_by,
            )
            db.add(target)
        elif r.status == "in_review":
            r.status, r.submitted_at = "draft", None
        target.content, target.content_hash = stored, pm.content_hash(stored)
        db.flush()
        sync_product_stage(db, project.id)
        return target


def _respond(db: Session, project: Project, doc: PrdDocument) -> dict:
    app_stg = _approved_strategy(db, project.id)
    open_stg = _open_strategy(db, project.id)
    return {"document": _out(doc, app_stg.version if app_stg else None, open_stg is not None), "state": build_state(db, project)}


@router.patch("/versions/{version}/overview")
def patch_overview(version: int, body: OverviewPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        c.update(data)
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.post("/versions/{version}/functional-requirements")
def add_functional_req(version: int, body: FunctionalReqIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        req = body.model_dump(mode="json", exclude={"base_hash"})
        c["functional_requirements"].append({
            **req, "id": _next_id("FR", c["functional_requirements"]), "origin": "user", "edited_by_user": False, "unlinked": len(req["source_refs"]) == 0,
        })
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/functional-requirements/{req_id}")
def patch_functional_req(version: int, req_id: str, body: FunctionalReqPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        req = next((x for x in c["functional_requirements"] if x["id"] == req_id), None)
        if req is None:
            raise HTTPException(404, "Functional requirement not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        req.update(data)
        if data.keys() & {"title", "description", "priority", "mvp_boundary", "acceptance_criteria", "edge_cases", "source_refs"}:
            req["edited_by_user"] = True
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.delete("/versions/{version}/functional-requirements/{req_id}")
def delete_functional_req(version: int, req_id: str, base_hash: str = Query(..., min_length=64, max_length=64), project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        if not any(x["id"] == req_id for x in c["functional_requirements"]):
            raise HTTPException(404, "Functional requirement not found.")
        c["functional_requirements"] = [x for x in c["functional_requirements"] if x["id"] != req_id]
        return c
    return _respond(db, project, _mutate(db, project, version, base_hash, fn))


@router.post("/versions/{version}/non-functional-requirements")
def add_non_functional_req(version: int, body: NonFunctionalReqIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        req = body.model_dump(mode="json", exclude={"base_hash"})
        c["non_functional_requirements"].append({
            **req, "id": _next_id("NFR", c["non_functional_requirements"]), "origin": "user", "edited_by_user": False, "unlinked": len(req["source_refs"]) == 0,
        })
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/non-functional-requirements/{req_id}")
def patch_non_functional_req(version: int, req_id: str, body: NonFunctionalReqPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        req = next((x for x in c["non_functional_requirements"] if x["id"] == req_id), None)
        if req is None:
            raise HTTPException(404, "Non-functional requirement not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        req.update(data)
        if data.keys() & {"category", "title", "description", "priority", "mvp_boundary", "acceptance_criteria", "source_refs"}:
            req["edited_by_user"] = True
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.delete("/versions/{version}/non-functional-requirements/{req_id}")
def delete_non_functional_req(version: int, req_id: str, base_hash: str = Query(..., min_length=64, max_length=64), project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        if not any(x["id"] == req_id for x in c["non_functional_requirements"]):
            raise HTTPException(404, "Non-functional requirement not found.")
        c["non_functional_requirements"] = [x for x in c["non_functional_requirements"] if x["id"] != req_id]
        return c
    return _respond(db, project, _mutate(db, project, version, base_hash, fn))


@router.post("/versions/{version}/requirements/status")
def set_requirement_status(version: int, body: ReqApprovalIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    """Explicitly mark one or more requirements as 'approved' or 'proposed'."""
    def fn(c):
        all_reqs = [*c["functional_requirements"], *c["non_functional_requirements"]]
        ids = {r["id"] for r in all_reqs}
        if not set(body.requirement_ids) <= ids:
            raise HTTPException(404, "Requirement not found.")
        for r in all_reqs:
            if r["id"] in body.requirement_ids:
                r["status"] = body.status
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.put("/versions/{version}/questions")
def set_questions(version: int, body: QuestionsIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        c["open_questions"] = [{"id": f"pq-{i}", "question": q} for i, q in enumerate(body.questions, 1)]
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


# ---------- review and approval ----------
@router.post("/versions/{version}/submit")
def submit(version: int, body: Hashed, project: Project = Depends(owned), db: Session = Depends(get_db)):
    with txn(db):
        r = _get(db, project, version, lock=True)
        if r.status == "in_review" and r.content_hash == body.base_hash:
            return build_state(db, project)
        if r.status != "draft":
            raise HTTPException(409, f"Only a draft can be submitted for review (this version is {r.status}).")
        if r.content_hash != body.base_hash:
            raise HTTPException(409, "This PRD changed since you loaded it. Reload and try again.")
        if not r.content["functional_requirements"]:
            raise HTTPException(409, "Add at least one functional requirement before submitting for review.")
        r.status, r.submitted_at = "in_review", now()
        sync_product_stage(db, project.id)
    return build_state(db, project)


@router.post("/versions/{version}/approve")
def approve(version: int, body: ApproveIn, project: Project = Depends(owned), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Approves one specific PRD version identified by its content hash. Atomically writes a `prd_approved` Brain pointer revision
    and completes the `product` lifecycle stage (when Strategy is also approved and current)."""
    with txn(db):
        r = _get(db, project, version, lock=True)
        if r.status == "approved" and r.content_hash == body.content_hash:
            return build_state(db, project)
        if r.status != "in_review":
            raise HTTPException(409, f"Only a version that is in review can be approved (this version is {r.status}).")
        if r.content_hash != body.content_hash:
            raise HTTPException(409, "This PRD changed after you opened it. Reload and review the current version.")
        if _stage(db, project.id, "research").status != "complete":
            raise HTTPException(409, "Complete and approve Research before approving the PRD.")
        app_stg = _approved_strategy(db, project.id)
        open_stg = _open_strategy(db, project.id)
        if app_stg is None or open_stg is not None:
            raise HTTPException(409, "Approve the current Product Strategy before approving the PRD.")
        if r.basis.get("strategy_version") != app_stg.version:
            raise HTTPException(409, f"This PRD was built from Strategy v{r.basis.get('strategy_version')}, but Strategy v{app_stg.version} is now approved. Regenerate or update the PRD first.")
        prop = pm.proposed_count(r.content)
        unlinked = pm.unlinked_count(r.content)
        if (prop or unlinked) and not body.acknowledge_unverified:
            raise HTTPException(409, f"{prop} proposed requirement(s) and {unlinked} unlinked requirement(s) remain. Approve individual requirements or acknowledge unverified items to approve.")
        counts = pm.requirement_counts(r.content)
        pointer = {
            "approved_version": r.version,
            "document_id": r.id,
            "content_hash": r.content_hash,
            "approved_at": now().isoformat(),
            "basis_brain_version": r.basis.get("brain_version"),
            "strategy_version": r.basis.get("strategy_version"),
            "research_version": r.basis.get("research_version"),
            "requirement_counts": counts,
            "approved_requirement_count": counts["approved"],
            "unverified_acknowledged": bool(prop or unlinked),
        }
        rev = commit_brain(db, project, {"prd": pointer}, "prd_approved", user.id, commit=False)
        r.status, r.approved_at, r.approved_by, r.approval_note = "approved", now(), user.id, body.note
        r.acknowledged_unverified, r.brain_revision = bool(prop or unlinked), rev.version
        sync_product_stage(db, project.id)
    return build_state(db, project)
