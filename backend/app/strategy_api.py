"""Product Strategy workflow (Phase 10): routes and database flows.

Document status: generating -> draft | failed ; draft -> in_review -> approved ; draft/in_review -> superseded (by regeneration).
Approved versions are immutable: editing one creates a NEW draft version (copy-on-write) that requires approval again.
Lifecycle (stage `product`): requires `research` complete to start; Strategy approval writes a Brain pointer revision (`strategy_approved`)
and keeps `product` stage `in_progress` until PRD is also approved (or `complete` if an up-to-date PRD is already approved).
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai, strategy as stg
from .api import commit_brain, current_user, latest_revision, owned
from .brain import ProjectBrain
from .config import settings
from .db import get_db
from .discovery_api import txn
from .models import DiscoveryQuestion, DiscoverySession, PrdDocument, Project, ProjectStage, ResearchReport, StrategyDocument, User, now
from .security import as_utc

router = APIRouter(prefix="/projects/{project_id}/strategy")
HASH = Field(min_length=64, max_length=64)


class GenerateIn(BaseModel):
    supersede: bool = False


class Hashed(BaseModel):
    base_hash: str = HASH


class OverviewPatch(Hashed):
    product_vision: str | None = None
    value_proposition: str | None = None
    differentiation: str | None = None
    business_model: str | None = None
    constraints: list[str] | None = None


class RecommendationIn(Hashed):
    area: stg.RecArea
    title: str
    recommendation: str
    rationale: str
    status: stg.RecStatus = "ai_suggestion"
    supporting_refs: list[str] = []
    needs_evidence: bool = False


class RecommendationPatch(Hashed):
    area: stg.RecArea | None = None
    title: str | None = None
    recommendation: str | None = None
    rationale: str | None = None
    status: stg.RecStatus | None = None
    supporting_refs: list[str] | None = None
    needs_evidence: bool | None = None


class MvpScopeIn(Hashed):
    item: str
    boundary: str = "in_mvp"
    rationale: str
    supporting_refs: list[str] = []


class GoalIn(Hashed):
    goal: str
    rationale: str
    supporting_refs: list[str] = []
    status: str = "user_confirmed"


class DecisionsIn(Hashed):
    decisions: list[dict] = Field(max_length=20)


class ApproveIn(BaseModel):
    content_hash: str = HASH
    acknowledge_unverified: bool = False
    note: str | None = Field(None, max_length=1000)


# ---------- helpers ----------
def _all(db: Session, pid: str) -> list[StrategyDocument]:
    return list(db.scalars(select(StrategyDocument).where(StrategyDocument.project_id == pid).order_by(StrategyDocument.version.desc())))


def _brain(db: Session, project: Project) -> dict:
    return ProjectBrain.model_validate(latest_revision(db, project.id).snapshot).model_dump()


def _idea_ready(brain: dict) -> bool:
    return bool(brain["idea"]["raw"].strip())


def _approved_research(db: Session, pid: str) -> ResearchReport | None:
    rows = list(db.scalars(select(ResearchReport).where(ResearchReport.project_id == pid, ResearchReport.status == "approved").order_by(ResearchReport.version.desc())))
    return rows[0] if rows else None


def _stage(db: Session, pid: str, name: str = "product") -> ProjectStage:
    return db.scalar(select(ProjectStage).where(ProjectStage.project_id == pid, ProjectStage.stage == name))


def sync_product_stage(db: Session, pid: str) -> None:
    """Update lifecycle stage `product` based on Strategy and PRD document states.
    `product` is `complete` ONLY when both Strategy and PRD have an approved version and neither has an open draft/in_review version."""
    st = _stage(db, pid, "product")
    s_rows = [r for r in _all(db, pid) if r.status != "failed"]
    p_rows = list(db.scalars(select(PrdDocument).where(PrdDocument.project_id == pid, PrdDocument.status != "failed").order_by(PrdDocument.version.desc())))

    s_open = next((r for r in s_rows if r.status in ("draft", "in_review")), None)
    s_app = next((r for r in s_rows if r.status == "approved"), None)
    p_open = next((r for r in p_rows if r.status in ("draft", "in_review")), None)
    p_app = next((r for r in p_rows if r.status == "approved"), None)

    if s_app and p_app and not s_open and not p_open and p_app.basis.get("strategy_version") == s_app.version:
        st.status = "complete"
    elif (s_open and s_open.status == "in_review" and not p_open) or (p_open and p_open.status == "in_review" and not s_open):
        st.status = "needs_review"
    elif s_rows or p_rows:
        if st.status in ("complete", "needs_review") or s_app or p_app:
            st.status = "in_progress"
    from .ux_api import sync_ux_stage
    from .architecture_api import sync_architecture_stage
    sync_ux_stage(db, pid)
    sync_architecture_stage(db, pid)


def _stale(r: StrategyDocument) -> bool:
    return r.status == "generating" and as_utc(r.updated_at) < datetime.now(timezone.utc) - timedelta(seconds=settings.strategy_generation_timeout_seconds)


def _discovery(db: Session, pid: str) -> tuple[str, list[str]]:
    s = db.scalar(select(DiscoverySession).where(DiscoverySession.project_id == pid))
    if s is None:
        return "not_started", []
    qs = db.scalars(select(DiscoveryQuestion).where(DiscoveryQuestion.session_id == s.id, DiscoveryQuestion.status.in_(("open", "deferred"))).order_by(DiscoveryQuestion.position))
    return s.status, [f"Unanswered discovery question: {q.prompt}" for q in qs]


def _iso(d: datetime | None) -> str | None:
    return as_utc(d).isoformat() if d else None


def _warnings(content: dict | None, current_res_ver: int | None, basis_res_ver: int | None) -> list[dict]:
    if not content:
        return []
    w = []
    unsup = stg.unsupported_count(content)
    if unsup:
        w.append({"code": "unsupported", "message": f"{unsup} recommendation(s) are unsupported or lack input references and need evidence."})
    missing = content["inputs"]["missing_inputs"]
    if missing:
        w.append({"code": "missing_inputs", "message": f"{len(missing)} input(s) are missing or unconfirmed in your Project Brain / Discovery."})
    if current_res_ver and basis_res_ver and current_res_ver != basis_res_ver:
        w.append({"code": "stale_research", "message": f"Built from Research v{basis_res_ver}, while Research v{current_res_ver} is now approved."})
    return w


def _summary(r: StrategyDocument) -> dict:
    c = r.content
    return {
        "version": r.version, "status": r.status, "created_via": r.created_via, "parent_version": r.parent_version,
        "created_at": _iso(r.created_at), "updated_at": _iso(r.updated_at), "submitted_at": _iso(r.submitted_at),
        "approved_at": _iso(r.approved_at), "content_hash": r.content_hash,
        "recommendation_count": len(c["recommendations"]) if c else 0,
        "unsupported_count": stg.unsupported_count(c) if c else 0,
        "error": r.error,
    }


def _out(r: StrategyDocument, current_res_ver: int | None = None) -> dict:
    c = r.content
    return {
        **_summary(r), "id": r.id, "content": c, "basis": r.basis, "approval_note": r.approval_note,
        "acknowledged_unverified": r.acknowledged_unverified, "brain_revision": r.brain_revision,
        "recommendation_counts": stg.recommendation_counts(c) if c else None,
        "unverified_count": stg.unverified_count(c) if c else 0,
        "editable": r.status in ("draft", "in_review"),
        "warnings": _warnings(c, current_res_ver, r.basis.get("research_version")),
    }


def build_state(db: Session, project: Project) -> dict:
    rows = _all(db, project.id)
    brain = _brain(db, project)
    idea_ok = _idea_ready(brain)
    res_stage = _stage(db, project.id, "research")
    app_res = _approved_research(db, project.id)
    res_ready = res_stage.status == "complete" and app_res is not None
    gen = next((r for r in rows if r.status == "generating" and not _stale(r)), None)
    open_ = next((r for r in rows if r.status in ("draft", "in_review")), None)
    approved = next((r for r in rows if r.status == "approved"), None)
    current = open_ or approved
    failed = rows[0] if rows and (rows[0].status == "failed" or _stale(rows[0])) else None
    status = "generating" if gen else (current.status if current else ("failed" if failed else "not_started"))
    disc_status, unresolved = _discovery(db, project.id)
    inputs_preview = (
        None if current else stg.build_inputs(brain, app_res.content if app_res else None, app_res.version if app_res else None, disc_status, unresolved).model_dump(mode="json")
    )
    has_recs = bool(current and current.content and current.content["recommendations"])
    step = (
        {"key": "describe_idea", "label": "Describe your product idea first"} if not idea_ok and not current else
        {"key": "complete_research", "label": "Approve your Research report first to unlock Product Strategy"} if not res_ready and not current else
        {"key": "wait", "label": "Product Strategy is being generated"} if gen else
        {"key": "retry_generation", "label": "Retry generating Product Strategy"} if status == "failed" else
        {"key": "start_strategy", "label": "Generate Product Strategy from your Brain, Discovery, and Research"} if status == "not_started" else
        {"key": "review_and_submit", "label": "Review strategy recommendations and provenance, then submit for review"} if status == "draft" else
        {"key": "approve", "label": "Approve this Strategy version to unlock the PRD"} if status == "in_review" else
        {"key": "approved", "label": "Strategy approved. Proceed to PRD, or edit/regenerate to start a new version."}
    )
    return {
        "status": status,
        "idea_ready": idea_ok,
        "research_ready": res_ready,
        "approved_research_version": app_res.version if app_res else None,
        "current": _out(current, app_res.version if app_res else None) if current else None,
        "approved_version": approved.version if approved else None,
        "history": [_summary(r) for r in rows if r.status != "failed" or r.content is not None],
        "last_error": failed.error if failed else None,
        "inputs_preview": inputs_preview,
        "discovery_status": disc_status,
        "lifecycle": {"stage": "product", "status": _stage(db, project.id, "product").status},
        "next_step": step,
        "can_generate": idea_ok and res_ready and gen is None,
        "needs_supersede": open_ is not None,
        "can_submit": bool(current and current.status == "draft" and has_recs),
        "can_approve": bool(current and current.status == "in_review" and res_ready),
        "limitations": stg.STRATEGY_LIMITATIONS,
    }


def _get(db: Session, project: Project, version: int, lock: bool = False) -> StrategyDocument:
    q = select(StrategyDocument).where(StrategyDocument.project_id == project.id, StrategyDocument.version == version)
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None:
        raise HTTPException(404, "Strategy version not found.")
    return r


def _validation_error(e: ValidationError) -> HTTPException:
    items = [{"loc": ["body", *map(str, x["loc"])], "msg": x["msg"].removeprefix("Value error, ")} for x in e.errors(include_input=False, include_url=False)]
    return HTTPException(422, items)


def _next_id(prefix: str, items: list[dict]) -> str:
    n = [int(i["id"].split("-")[-1]) for i in items if i["id"].startswith(prefix + "-") and i["id"].split("-")[-1].isdigit()]
    return f"{prefix}-{max(n, default=0) + 1}"


# ---------- endpoints ----------
@router.get("")
def get_strategy(project: Project = Depends(owned), db: Session = Depends(get_db)):
    return build_state(db, project)


@router.get("/versions/{version}")
def get_strategy_version(version: int, project: Project = Depends(owned), db: Session = Depends(get_db)):
    app_res = _approved_research(db, project.id)
    return _out(_get(db, project, version), app_res.version if app_res else None)


@router.post("/generate")
async def generate(body: GenerateIn, project: Project = Depends(owned), user: User = Depends(current_user), db: Session = Depends(get_db)):
    brain = _brain(db, project)
    if not _idea_ready(brain):
        raise HTTPException(409, "Describe your product idea first; strategy builds on it.")
    res_stage = _stage(db, project.id, "research")
    app_res = _approved_research(db, project.id)
    if res_stage.status != "complete" or app_res is None:
        raise HTTPException(409, "Approve a Research report first; Product Strategy requires approved research.")
    disc_status, unresolved = _discovery(db, project.id)
    inputs = stg.build_inputs(brain, app_res.content, app_res.version, disc_status, unresolved)
    with txn(db):
        db.get(Project, project.id, with_for_update=True, populate_existing=True)
        rows = _all(db, project.id)
        gen = next((r for r in rows if r.status == "generating"), None)
        if gen and not _stale(gen):
            raise HTTPException(409, "A product strategy is already being generated.")
        if any(r.status in ("draft", "in_review") for r in rows) and not body.supersede:
            raise HTTPException(409, "A draft already exists. Edit it, or regenerate with supersede=true to keep it in history and start a new version.")
        retry = gen or (rows[0] if rows and rows[0].status == "failed" else None)
        approved = next((r for r in rows if r.status == "approved"), None)
        basis = {
            "brain_version": latest_revision(db, project.id).version,
            "discovery_status": disc_status,
            "research_version": app_res.version,
            "research_hash": app_res.content_hash,
            "confirmed_fact_ids": [f["question_id"] for f in brain["discovery"]["confirmed"]],
        }
        if retry:
            retry.status, retry.error, retry.basis, retry.content, retry.content_hash = "generating", None, basis, None, None
            retry.parent_version = approved.version if approved else None
            row = retry
        else:
            row = StrategyDocument(
                project_id=project.id, version=(rows[0].version + 1) if rows else 1, status="generating",
                basis=basis, parent_version=approved.version if approved else None, created_by=user.id,
            )
            db.add(row)
        db.flush()
        sid = row.id
    try:
        gen_out = await ai.get_provider().generate_structured(stg.build_prompt(inputs, brain["idea"]), stg.GeneratedStrategy)
        content = stg.to_strategy_content(inputs, gen_out)
        stored = content.model_dump(mode="json")
        failure = None
    except (ai.ProviderNotConfigured, ai.ProviderError, ValidationError) as e:
        failure = e
    if failure is not None:
        unconfigured = isinstance(failure, ai.ProviderNotConfigured)
        msg = "AI provider not configured." if unconfigured else (ai.user_message(failure) if isinstance(failure, ai.ProviderError) else ai.USER_MESSAGES["malformed"])
        with txn(db):
            r = db.get(StrategyDocument, sid, with_for_update=True, populate_existing=True)
            if r.status == "generating":
                r.status, r.error = "failed", msg
        raise HTTPException(503 if unconfigured else 502, f"{msg} Nothing was changed.")
    with txn(db):
        r = db.get(StrategyDocument, sid, with_for_update=True, populate_existing=True)
        if r.status != "generating":
            raise HTTPException(409, "Another request changed this strategy document.")
        for old in _all(db, project.id):
            if old.id != sid and old.status in ("draft", "in_review"):
                old.status = "superseded"
        db.flush()
        had_approval = any(x.status == "approved" for x in _all(db, project.id))
        r.status, r.content, r.content_hash, r.error = "draft", stored, stg.content_hash(stored), None
        if had_approval:
            sync_product_stage(db, project.id)
    return build_state(db, project)


# ---------- edits (copy-on-write for approved versions) ----------
def _mutate(db: Session, project: Project, version: int, base_hash: str, fn) -> StrategyDocument:
    with txn(db):
        r = _get(db, project, version, lock=True)
        if r.status not in ("draft", "in_review", "approved"):
            raise HTTPException(409, f"A {r.status} strategy version cannot be edited.")
        if r.content_hash != base_hash:
            raise HTTPException(409, "This strategy changed since you loaded it. Reload and try again.")
        data = fn(stg.StrategyContent.model_validate(r.content).model_dump(mode="json"))
        try:
            stored = stg.StrategyContent.model_validate(data).model_dump(mode="json")
        except ValidationError as e:
            raise _validation_error(e) from None
        target = r
        if r.status == "approved":
            if any(x.status in ("draft", "in_review", "generating") and not _stale(x) for x in _all(db, project.id)):
                raise HTTPException(409, "A newer version is already open. Edit that version instead.")
            top = _all(db, project.id)[0]
            target = StrategyDocument(
                project_id=project.id, version=top.version + 1, status="draft", basis=r.basis, parent_version=r.version,
                created_via="copy_of_approved", created_by=r.created_by,
            )
            db.add(target)
        elif r.status == "in_review":
            r.status, r.submitted_at = "draft", None
        target.content, target.content_hash = stored, stg.content_hash(stored)
        db.flush()
        sync_product_stage(db, project.id)
        return target


def _respond(db: Session, project: Project, doc: StrategyDocument) -> dict:
    app_res = _approved_research(db, project.id)
    return {"document": _out(doc, app_res.version if app_res else None), "state": build_state(db, project)}


@router.patch("/versions/{version}/overview")
def patch_overview(version: int, body: OverviewPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        c.update(data)
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.post("/versions/{version}/recommendations")
def add_recommendation(version: int, body: RecommendationIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        rec = body.model_dump(mode="json", exclude={"base_hash"})
        c["recommendations"].append({**rec, "id": _next_id("rec", c["recommendations"]), "origin": "user", "edited_by_user": False, "note": None})
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/versions/{version}/recommendations/{rid}")
def patch_recommendation(version: int, rid: str, body: RecommendationPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        rec = next((x for x in c["recommendations"] if x["id"] == rid), None)
        if rec is None:
            raise HTTPException(404, "Recommendation not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        rec.update(data)
        if data.keys() & {"area", "title", "recommendation", "rationale", "status", "supporting_refs"}:
            rec["edited_by_user"], rec["note"] = True, None
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.delete("/versions/{version}/recommendations/{rid}")
def delete_recommendation(version: int, rid: str, base_hash: str = Query(..., min_length=64, max_length=64), project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        if not any(x["id"] == rid for x in c["recommendations"]):
            raise HTTPException(404, "Recommendation not found.")
        c["recommendations"] = [x for x in c["recommendations"] if x["id"] != rid]
        return c
    return _respond(db, project, _mutate(db, project, version, base_hash, fn))


@router.post("/versions/{version}/mvp-scope")
def add_mvp_item(version: int, body: MvpScopeIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        item = body.model_dump(mode="json", exclude={"base_hash"})
        c["mvp_scope"].append({**item, "id": _next_id("mvp", c["mvp_scope"])})
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.post("/versions/{version}/goals")
def add_goal(version: int, body: GoalIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        g = body.model_dump(mode="json", exclude={"base_hash"})
        c["goals"].append({**g, "id": _next_id("sg", c["goals"])})
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.put("/versions/{version}/decisions")
def set_decisions(version: int, body: DecisionsIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        c["open_decisions"] = [{"id": f"od-{i}", "question": d.get("question", ""), "impact": d.get("impact", "")} for i, d in enumerate(body.decisions, 1)]
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
            raise HTTPException(409, "This strategy changed since you loaded it. Reload and try again.")
        if not r.content["recommendations"]:
            raise HTTPException(409, "Add at least one strategy recommendation before submitting for review.")
        r.status, r.submitted_at = "in_review", now()
        sync_product_stage(db, project.id)
    return build_state(db, project)


@router.post("/versions/{version}/approve")
def approve(version: int, body: ApproveIn, project: Project = Depends(owned), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Approves one specific Strategy version identified by its content hash. Writes a `strategy_approved` Brain pointer revision."""
    with txn(db):
        r = _get(db, project, version, lock=True)
        if r.status == "approved" and r.content_hash == body.content_hash:
            return build_state(db, project)
        if r.status != "in_review":
            raise HTTPException(409, f"Only a version that is in review can be approved (this version is {r.status}).")
        if r.content_hash != body.content_hash:
            raise HTTPException(409, "This strategy changed after you opened it. Reload and review the current version.")
        if _stage(db, project.id, "research").status != "complete" or _approved_research(db, project.id) is None:
            raise HTTPException(409, "Complete and approve Research before approving Product Strategy.")
        n = stg.unverified_count(r.content)
        if n and not body.acknowledge_unverified:
            raise HTTPException(409, f"{n} recommendation(s) are AI suggestions, hypotheses, or unsupported claims. Acknowledge that to approve.")
        counts = stg.recommendation_counts(r.content)
        pointer = {
            "approved_version": r.version,
            "document_id": r.id,
            "content_hash": r.content_hash,
            "approved_at": now().isoformat(),
            "basis_brain_version": r.basis.get("brain_version"),
            "research_version": r.basis.get("research_version"),
            "recommendation_counts": counts,
            "unsupported_count": stg.unsupported_count(r.content),
            "unverified_acknowledged": bool(n),
        }
        rev = commit_brain(db, project, {"strategy": pointer}, "strategy_approved", user.id, commit=False)
        r.status, r.approved_at, r.approved_by, r.approval_note = "approved", now(), user.id, body.note
        r.acknowledged_unverified, r.brain_revision = bool(n), rev.version
        st = _stage(db, project.id, "product")
        if st.status == "not_started":
            st.status = "in_progress"
        sync_product_stage(db, project.id)
    return build_state(db, project)
