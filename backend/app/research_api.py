"""Research workflow: routes and database flows. See docs/RESEARCH.md for the rules.

Report status: generating -> draft | failed ; draft -> in_review -> approved ; draft/in_review -> superseded (by a regeneration).
Approved versions are immutable: editing one creates a NEW draft version (copy-on-write) that needs approval again.
Lifecycle (stage `research`): generation never changes it; submit -> needs_review; approve -> complete; creating a new draft
after an approval, or editing an in-review report, reopens it to in_progress. Approving writes a Brain pointer revision.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai, research as rs
from .api import commit_brain, current_user, latest_revision, owned
from .brain import ProjectBrain
from .config import settings
from .db import get_db
from .discovery_api import txn
from .models import DiscoveryQuestion, DiscoverySession, Project, ProjectStage, ResearchReport, User, now
from .security import as_utc

router = APIRouter(prefix="/projects/{project_id}/research")
HASH = Field(min_length=64, max_length=64)


# ---------- request schemas ----------
class GenerateIn(BaseModel):
    supersede: bool = False  # explicit consent to replace an existing draft / in-review version (it stays in history)


class Hashed(BaseModel):
    base_hash: str = HASH  # content hash the client last saw: guards against lost updates


class FindingIn(Hashed):
    topic: rs.Topic
    statement: str
    detail: str | None = None
    evidence: rs.Evidence = "user_provided"
    citations: list[rs.Citation] = []
    follow_up: bool = False
    follow_up_note: str | None = None


class FindingPatch(Hashed):
    topic: rs.Topic | None = None
    statement: str | None = None
    detail: str | None = None
    evidence: rs.Evidence | None = None
    citations: list[rs.Citation] | None = None
    follow_up: bool | None = None
    follow_up_note: str | None = None


class SourceIn(Hashed):
    title: str
    url: str
    publisher: str | None = None
    accessed_on: date | None = None
    examined: bool = False  # "I examined this source myself"
    note: str | None = None


class SourcePatch(Hashed):
    title: str | None = None
    url: str | None = None
    publisher: str | None = None
    accessed_on: date | None = None
    examined: bool | None = None
    note: str | None = None


class QuestionsIn(Hashed):
    questions: list[str] = Field(max_length=30)


class FollowUpIn(Hashed):
    finding_ids: list[str] = Field(min_length=1, max_length=60)
    follow_up: bool = True


class ApproveIn(BaseModel):
    content_hash: str = HASH
    acknowledge_unverified: bool = False
    note: str | None = Field(None, max_length=1000)


# ---------- helpers ----------
def _all(db: Session, pid: str) -> list[ResearchReport]:
    return list(db.scalars(select(ResearchReport).where(ResearchReport.project_id == pid).order_by(ResearchReport.version.desc())))


def _brain(db: Session, project: Project) -> dict:
    return ProjectBrain.model_validate(latest_revision(db, project.id).snapshot).model_dump()


def _idea_ready(brain: dict) -> bool:
    return bool(brain["idea"]["raw"].strip())


def _stage(db: Session, pid: str) -> ProjectStage:
    return db.scalar(select(ProjectStage).where(ProjectStage.project_id == pid, ProjectStage.stage == "research"))


def _reopen(db: Session, pid: str) -> None:
    st = _stage(db, pid)
    if st.status in ("complete", "needs_review"):
        st.status = "in_progress"
    from .ux_api import sync_ux_stage
    sync_ux_stage(db, pid)


def _stale(r: ResearchReport) -> bool:
    return r.status == "generating" and as_utc(r.updated_at) < datetime.now(timezone.utc) - timedelta(seconds=settings.research_generation_timeout_seconds)


def _discovery(db: Session, pid: str) -> tuple[str, list[str]]:
    s = db.scalar(select(DiscoverySession).where(DiscoverySession.project_id == pid))
    if s is None:
        return "not_started", []
    qs = db.scalars(select(DiscoveryQuestion).where(DiscoveryQuestion.session_id == s.id, DiscoveryQuestion.status.in_(("open", "deferred"))).order_by(DiscoveryQuestion.position))
    return s.status, [f"Unanswered discovery question: {q.prompt}" for q in qs]


def _iso(d: datetime | None) -> str | None:
    return as_utc(d).isoformat() if d else None


def _warnings(content: dict | None) -> list[dict]:
    if not content:
        return []
    w, f = [], content["findings"]
    if not content["sources"]:
        w.append({"code": "no_sources", "message": "No sources are attached. Every finding is a hypothesis, suggestion or unsupported claim."})
    n = sum(x["evidence"] == "unsupported" for x in f)
    if n:
        w.append({"code": "unsupported", "message": f"{n} finding(s) are unsupported claims that need evidence."})
    n = sum(x["follow_up"] for x in f)
    if n:
        w.append({"code": "follow_up", "message": f"{n} finding(s) are marked for follow-up."})
    if content["brief"]["missing_inputs"]:
        w.append({"code": "missing_inputs", "message": f"{len(content['brief']['missing_inputs'])} input(s) are missing or unconfirmed (see the brief)."})
    return w


def _summary(r: ResearchReport) -> dict:
    c = r.content
    return {"version": r.version, "status": r.status, "created_via": r.created_via, "parent_version": r.parent_version, "created_at": _iso(r.created_at),
            "updated_at": _iso(r.updated_at), "submitted_at": _iso(r.submitted_at), "approved_at": _iso(r.approved_at),
            "content_hash": r.content_hash, "finding_count": len(c["findings"]) if c else 0, "source_count": len(c["sources"]) if c else 0,
            "error": r.error}


def _out(r: ResearchReport) -> dict:
    c = r.content
    return {**_summary(r), "id": r.id, "mode": r.mode, "content": c, "basis": r.basis, "approval_note": r.approval_note,
            "acknowledged_unverified": r.acknowledged_unverified, "brain_revision": r.brain_revision,
            "evidence_counts": rs.evidence_counts(c) if c else None, "unverified_count": rs.unverified_count(c) if c else 0,
            "editable": r.status in ("draft", "in_review"), "warnings": _warnings(c)}


def build_state(db: Session, project: Project) -> dict:
    rows = _all(db, project.id)
    brain = _brain(db, project)
    ready = _idea_ready(brain)
    gen = next((r for r in rows if r.status == "generating" and not _stale(r)), None)
    open_ = next((r for r in rows if r.status in ("draft", "in_review")), None)
    approved = next((r for r in rows if r.status == "approved"), None)
    current = open_ or approved
    failed = rows[0] if rows and (rows[0].status == "failed" or _stale(rows[0])) else None
    status = "generating" if gen else (current.status if current else ("failed" if failed else "not_started"))
    disc_status, unresolved = _discovery(db, project.id)
    preview = None if current else rs.build_brief(brain, unresolved, disc_status).model_dump(mode="json")
    has_findings = bool(current and current.content and current.content["findings"])
    step = (
        {"key": "describe_idea", "label": "Describe your product idea first"} if not ready and not current else
        {"key": "wait", "label": "The report is being generated"} if gen else
        {"key": "retry_generation", "label": "Retry generating the report"} if status == "failed" else
        {"key": "start_research", "label": "Start preliminary research"} if status == "not_started" else
        {"key": "review_and_submit", "label": "Review the findings, attach sources you have examined, then submit for review"} if status == "draft" else
        {"key": "approve", "label": "Approve this version to complete the Research stage"} if status == "in_review" else
        {"key": "approved", "label": "Approved. Edit or regenerate to start a new version if anything changes."}
    )
    return {
        "status": status, "idea_ready": ready, "mode": "preliminary", "current": _out(current) if current else None,
        "approved_version": approved.version if approved else None,
        "history": [_summary(r) for r in rows if r.status != "failed" or r.content is not None],
        "last_error": failed.error if failed else None, "brief_preview": preview, "discovery_status": disc_status,
        "lifecycle": {"stage": "research", "status": _stage(db, project.id).status}, "next_step": step,
        "can_generate": ready and gen is None, "needs_supersede": open_ is not None,
        "can_submit": bool(current and current.status == "draft" and has_findings),
        "can_approve": bool(current and current.status == "in_review"),
        "limitations": rs.LIMITATIONS,
    }


def _get(db: Session, project: Project, version: int, lock: bool = False) -> ResearchReport:
    q = select(ResearchReport).where(ResearchReport.project_id == project.id, ResearchReport.version == version)
    r = db.scalar(q.with_for_update() if lock else q)
    if r is None:
        raise HTTPException(404, "Report version not found.")
    return r


def _validation_error(e: ValidationError) -> HTTPException:
    items = [{"loc": ["body", *map(str, x["loc"])], "msg": x["msg"].removeprefix("Value error, ")} for x in e.errors(include_input=False, include_url=False)]
    return HTTPException(422, items)


def _next_id(prefix: str, items: list[dict]) -> str:
    n = [int(i["id"].split("-")[-1]) for i in items if i["id"].startswith(prefix + "-") and i["id"].split("-")[-1].isdigit()]
    return f"{prefix}-{max(n, default=0) + 1}"


# ---------- generation ----------
@router.get("")
def get_research(project: Project = Depends(owned), db: Session = Depends(get_db)):
    return build_state(db, project)


@router.get("/reports/{version}")
def get_report(version: int, project: Project = Depends(owned), db: Session = Depends(get_db)):
    return _out(_get(db, project, version))


@router.post("/generate")
async def generate(body: GenerateIn, project: Project = Depends(owned), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Start, retry (after a failure) or regenerate. Calls the provider outside any transaction; persists only validated output."""
    brain = _brain(db, project)
    if not _idea_ready(brain):
        raise HTTPException(409, "Describe your product idea first; research builds on it.")
    disc_status, unresolved = _discovery(db, project.id)
    brief = rs.build_brief(brain, unresolved, disc_status)
    with txn(db):
        db.get(Project, project.id, with_for_update=True, populate_existing=True)  # serializes concurrent generate calls
        rows = _all(db, project.id)
        gen = next((r for r in rows if r.status == "generating"), None)
        if gen and not _stale(gen):
            raise HTTPException(409, "A research report is already being generated.")
        if any(r.status in ("draft", "in_review") for r in rows) and not body.supersede:
            raise HTTPException(409, "A draft already exists. Edit it, or regenerate with supersede=true to keep it in history and start a new version.")
        retry = gen or (rows[0] if rows and rows[0].status == "failed" else None)
        approved = next((r for r in rows if r.status == "approved"), None)
        basis = {"brain_version": latest_revision(db, project.id).version, "discovery_status": disc_status, "mode": "preliminary",
                 "confirmed_fact_ids": [f["question_id"] for f in brain["discovery"]["confirmed"]]}
        if retry:  # reuse the failed row: retries never create duplicate versions
            retry.status, retry.error, retry.basis, retry.mode, retry.content, retry.content_hash = "generating", None, basis, "preliminary", None, None
            retry.parent_version = approved.version if approved else None
            row = retry
        else:
            row = ResearchReport(project_id=project.id, version=(rows[0].version + 1) if rows else 1, status="generating", basis=basis,
                                 parent_version=approved.version if approved else None, created_by=user.id)
            db.add(row)
        db.flush()
        rid = row.id
    try:
        gen_out = await ai.get_provider().generate_structured(rs.build_prompt(brief, brain["idea"]), rs.GeneratedResearch)
        brief.objectives, brief.research_questions = list(gen_out.objectives), list(gen_out.research_questions)
        brief.scope_in, brief.scope_out = list(gen_out.scope_in), list(gen_out.scope_out)
        content = rs.ReportContent(brief=brief, findings=rs.to_findings(gen_out),
                                   unresolved_questions=[{"id": f"q-{i}", "question": q} for i, q in enumerate(gen_out.unresolved_questions, 1)])
        stored = content.model_dump(mode="json")
        failure = None
    except (ai.ProviderNotConfigured, ai.ProviderError, ValidationError) as e:
        failure = e
    if failure is not None:
        unconfigured = isinstance(failure, ai.ProviderNotConfigured)
        msg = "AI provider not configured." if unconfigured else (ai.user_message(failure) if isinstance(failure, ai.ProviderError) else ai.USER_MESSAGES["malformed"])
        with txn(db):
            r = db.get(ResearchReport, rid, with_for_update=True, populate_existing=True)
            if r.status == "generating":
                r.status, r.error = "failed", msg
        raise HTTPException(503 if unconfigured else 502, f"{msg} Nothing was changed.")
    with txn(db):
        r = db.get(ResearchReport, rid, with_for_update=True, populate_existing=True)
        if r.status != "generating":
            raise HTTPException(409, "Another request changed this report.")
        for old in _all(db, project.id):  # explicit supersede: the previous editable version stays in history
            if old.id != rid and old.status in ("draft", "in_review"):
                old.status = "superseded"
        db.flush()
        had_approval = any(x.status == "approved" for x in _all(db, project.id))
        r.status, r.content, r.content_hash, r.error = "draft", stored, rs.content_hash(stored), None
        if had_approval:
            _reopen(db, project.id)
    return build_state(db, project)


# ---------- edits (copy-on-write for approved versions) ----------
def _mutate(db: Session, project: Project, version: int, base_hash: str, fn) -> ResearchReport:
    with txn(db):
        r = _get(db, project, version, lock=True)
        if r.status not in ("draft", "in_review", "approved"):
            raise HTTPException(409, f"A {r.status} report version cannot be edited.")
        if r.content_hash != base_hash:
            raise HTTPException(409, "This report changed since you loaded it. Reload and try again.")
        data = fn(rs.ReportContent.model_validate(r.content).model_dump(mode="json"))
        try:
            stored = rs.ReportContent.model_validate(data).model_dump(mode="json")
        except ValidationError as e:
            raise _validation_error(e) from None
        target = r
        if r.status == "approved":
            if any(x.status in ("draft", "in_review", "generating") and not _stale(x) for x in _all(db, project.id)):
                raise HTTPException(409, "A newer version is already open. Edit that version instead.")
            top = _all(db, project.id)[0]
            target = ResearchReport(project_id=project.id, version=top.version + 1, status="draft", mode=r.mode, basis=r.basis, parent_version=r.version,
                                    created_via="copy_of_approved", created_by=r.created_by)
            db.add(target)
            _reopen(db, project.id)
        elif r.status == "in_review":
            r.status, r.submitted_at = "draft", None  # not approved yet, so it may return to draft in place
            _reopen(db, project.id)
        target.content, target.content_hash = stored, rs.content_hash(stored)
        db.flush()
        return target


def _respond(db: Session, project: Project, report: ResearchReport) -> dict:
    return {"report": _out(report), "state": build_state(db, project)}


@router.post("/reports/{version}/findings")
def add_finding(version: int, body: FindingIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        f = body.model_dump(mode="json", exclude={"base_hash"})
        c["findings"].append({**f, "id": _next_id("f", c["findings"]), "origin": "user", "edited_by_user": False, "note": None})
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/reports/{version}/findings/{fid}")
def patch_finding(version: int, fid: str, body: FindingPatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        f = next((x for x in c["findings"] if x["id"] == fid), None)
        if f is None:
            raise HTTPException(404, "Finding not found.")
        data = body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True)
        f.update(data)
        if data.keys() & {"topic", "statement", "detail", "evidence", "citations"}:
            f["edited_by_user"], f["note"] = True, None
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.delete("/reports/{version}/findings/{fid}")
def delete_finding(version: int, fid: str, base_hash: str = Query(..., min_length=64, max_length=64), project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        if not any(x["id"] == fid for x in c["findings"]):
            raise HTTPException(404, "Finding not found.")
        c["findings"] = [x for x in c["findings"] if x["id"] != fid]
        return c
    return _respond(db, project, _mutate(db, project, version, base_hash, fn))


@router.post("/reports/{version}/follow-up")
def follow_up(version: int, body: FollowUpIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        ids = {x["id"] for x in c["findings"]}
        if not set(body.finding_ids) <= ids:
            raise HTTPException(404, "Finding not found.")
        for f in c["findings"]:
            if f["id"] in body.finding_ids:
                f["follow_up"] = body.follow_up
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.post("/reports/{version}/sources")
def add_source(version: int, body: SourceIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        s = body.model_dump(mode="json", exclude={"base_hash"})
        s.update(id=_next_id("src", c["sources"]), examined_by="user" if s["examined"] else None)  # only the person adding it can attest to examining it
        c["sources"].append(s)
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.patch("/reports/{version}/sources/{sid}")
def patch_source(version: int, sid: str, body: SourcePatch, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        s = next((x for x in c["sources"] if x["id"] == sid), None)
        if s is None:
            raise HTTPException(404, "Source not found.")
        s.update(body.model_dump(mode="json", exclude={"base_hash"}, exclude_unset=True))
        s["examined_by"] = "user" if s["examined"] else None
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


@router.delete("/reports/{version}/sources/{sid}")
def delete_source(version: int, sid: str, base_hash: str = Query(..., min_length=64, max_length=64), project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        if not any(x["id"] == sid for x in c["sources"]):
            raise HTTPException(404, "Source not found.")
        cited = [f["id"] for f in c["findings"] if any(ct["source_id"] == sid for ct in f["citations"])]
        if cited:
            raise HTTPException(409, f"This source is cited by {', '.join(cited)}. Remove those citations first.")
        c["sources"] = [x for x in c["sources"] if x["id"] != sid]
        return c
    return _respond(db, project, _mutate(db, project, version, base_hash, fn))


@router.put("/reports/{version}/questions")
def set_questions(version: int, body: QuestionsIn, project: Project = Depends(owned), db: Session = Depends(get_db)):
    def fn(c):
        c["unresolved_questions"] = [{"id": f"q-{i}", "question": q} for i, q in enumerate(body.questions, 1)]
        return c
    return _respond(db, project, _mutate(db, project, version, body.base_hash, fn))


# ---------- review and approval ----------
@router.post("/reports/{version}/submit")
def submit(version: int, body: Hashed, project: Project = Depends(owned), db: Session = Depends(get_db)):
    with txn(db):
        r = _get(db, project, version, lock=True)
        if r.status == "in_review" and r.content_hash == body.base_hash:
            return build_state(db, project)  # idempotent
        if r.status != "draft":
            raise HTTPException(409, f"Only a draft can be submitted for review (this version is {r.status}).")
        if r.content_hash != body.base_hash:
            raise HTTPException(409, "This report changed since you loaded it. Reload and try again.")
        if not r.content["findings"]:
            raise HTTPException(409, "Add at least one finding before submitting for review.")
        r.status, r.submitted_at = "in_review", now()
        _stage(db, project.id).status = "needs_review"
    return build_state(db, project)


@router.post("/reports/{version}/approve")
def approve(version: int, body: ApproveIn, project: Project = Depends(owned), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Approves one specific version identified by its content hash. Atomically: report, lifecycle stage and a Brain pointer revision."""
    with txn(db):
        r = _get(db, project, version, lock=True)
        if r.status == "approved" and r.content_hash == body.content_hash:
            return build_state(db, project)  # idempotent
        if r.status != "in_review":
            raise HTTPException(409, f"Only a version that is in review can be approved (this version is {r.status}).")
        if r.content_hash != body.content_hash:
            raise HTTPException(409, "This report changed after you opened it. Reload and review the current version.")
        n = rs.unverified_count(r.content)
        if n and not body.acknowledge_unverified:
            raise HTTPException(409, f"{n} finding(s) are not backed by a source you examined. Acknowledge that to approve.")
        counts = rs.evidence_counts(r.content)
        pointer = {"approved_version": r.version, "report_id": r.id, "content_hash": r.content_hash, "approved_at": now().isoformat(),
                   "basis_brain_version": r.basis.get("brain_version"), "mode": r.mode, "finding_counts": counts,
                   "source_count": len(r.content["sources"]), "unverified_acknowledged": bool(n)}
        rev = commit_brain(db, project, {"research": pointer}, "research_approved", user.id, commit=False)
        r.status, r.approved_at, r.approved_by, r.approval_note = "approved", now(), user.id, body.note
        r.acknowledged_unverified, r.brain_revision = bool(n), rev.version
        _stage(db, project.id).status = "complete"
        from .ux_api import sync_ux_stage
        sync_ux_stage(db, project.id)
    return build_state(db, project)
