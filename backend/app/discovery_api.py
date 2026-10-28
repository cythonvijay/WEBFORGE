"""Progressive AI questions: routes and database flows.

State machine (DB statuses; `not_started` is "no session row yet"):
  not_started --start--> generating --ok--> awaiting_answers | ready_for_review (nothing useful left to ask)
                                    --provider error--> failed --start(retry)--> generating
  awaiting_answers --next-round--> generating --ok--> awaiting_answers   (provider error: status restored)
  awaiting_answers --review--> ready_for_review --next-round--> generating
  ready_for_review --complete--> completed (terminal; explicit)
Answers may be edited in awaiting_answers and ready_for_review. A 'generating' session older than the configured
timeout is treated as abandoned and may be retried.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from . import ai, discovery as dz
from .api import commit_brain, current_user, latest_revision, owned
from .brain import ProjectBrain
from .config import settings
from .db import get_db
from .models import DiscoveryQuestion, DiscoverySession, Project, User, now
from .security import as_utc

router = APIRouter(prefix="/projects/{project_id}/discovery")
ACTIVE = ("awaiting_answers", "ready_for_review")


# ---------- schemas ----------
class OptionOut(BaseModel):
    id: str
    label: str


class QuestionOut(BaseModel):
    id: str
    round: int
    prompt: str
    rationale: str
    target: str
    qtype: str
    options: list[OptionOut]
    required: bool
    priority: int
    max_length: int | None
    status: str
    answer: Any | None
    answered_at: datetime | None


class StateOut(BaseModel):
    status: str
    session_id: str | None
    idea_ready: bool
    round: int
    max_rounds: int
    questions: list[QuestionOut]
    counts: dict[str, int]
    outstanding_questions: list[str]
    unresolved_assumptions: list[dict]
    summary: dict | None
    next_step: dict
    last_error: str | None
    can_generate_next_round: bool
    can_review: bool
    can_complete: bool


class AnswerIn(BaseModel):
    question_id: str = Field(min_length=1, max_length=64)
    value: Any


class AnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _unique(self):
        ids = [a.question_id for a in self.answers]
        if len(set(ids)) != len(ids):
            raise ValueError("each question may be answered once per request")
        return self


class CompleteIn(BaseModel):
    accept_assumptions: bool = False


# ---------- helpers ----------
@contextmanager
def txn(db: Session):
    """One transaction per mutation: commit on success, roll back on any failure (no partial updates)."""
    try:
        yield
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except (IntegrityError, StaleDataError):
        db.rollback()
        raise HTTPException(409, "Another update happened at the same time. Reload and try again.")
    except Exception:
        db.rollback()
        raise


def _brain(db: Session, project: Project) -> dict:
    return ProjectBrain.model_validate(latest_revision(db, project.id).snapshot).model_dump()


def _questions(db: Session, session_id: str) -> list[DiscoveryQuestion]:
    return list(db.scalars(select(DiscoveryQuestion).where(DiscoveryQuestion.session_id == session_id).order_by(DiscoveryQuestion.position)))


def _get(db: Session, project_id: str, lock: bool = False) -> DiscoverySession | None:
    q = select(DiscoverySession).where(DiscoverySession.project_id == project_id)
    return db.scalar(q.with_for_update() if lock else q)


def _stale(s: DiscoverySession) -> bool:
    return s.status == "generating" and as_utc(s.updated_at) < datetime.now(timezone.utc) - timedelta(seconds=settings.discovery_generation_timeout_seconds)


def _unstick(db: Session, s: DiscoverySession) -> None:
    """Turn an abandoned 'generating' session back into a retryable state."""
    if _stale(s):
        s.status = "awaiting_answers" if s.round > 0 else "failed"
        s.last_error = "The previous attempt did not finish."
        db.commit()


def _require_session(db: Session, project: Project, lock: bool = True) -> DiscoverySession:
    s = _get(db, project.id, lock)
    if s is None:
        raise HTTPException(404, "Discovery hasn't been started for this project.")
    _unstick(db, s)
    return s


def _require_active(s: DiscoverySession) -> None:
    if s.status == "completed":
        raise HTTPException(409, "Discovery is already completed.")
    if s.status == "generating":
        raise HTTPException(409, "Questions are still being generated.")
    if s.status not in ACTIVE:
        raise HTTPException(409, "Discovery has no questions yet. Start or retry it first.")


def _idea_ready(brain: dict) -> bool:
    return bool(brain["idea"]["raw"].strip())


def _require_idea(db: Session, project: Project) -> dict:
    brain = _brain(db, project)
    if not _idea_ready(brain):
        raise HTTPException(409, "Describe your product idea first; discovery builds on it.")
    return brain


def _qout(q: DiscoveryQuestion) -> QuestionOut:
    return QuestionOut(id=q.id, round=q.round, prompt=q.prompt, rationale=q.rationale, target=q.target, qtype=q.qtype,
                       options=[OptionOut(**o) for o in (q.options or [])], required=q.required, priority=q.priority,
                       max_length=q.max_length, status=q.status, answer=q.answer, answered_at=q.answered_at)


def build_state(db: Session, project: Project, s: DiscoverySession | None) -> StateOut:
    brain = _brain(db, project)
    ready = _idea_ready(brain)
    qs = _questions(db, s.id) if s else []
    c = {k: sum(q.status == k for q in qs) for k in ("open", "answered", "skipped", "deferred")}
    c["total"] = len(qs)
    status = s.status if s else "not_started"
    if s and _stale(s):  # read-only view of an abandoned generation
        status = "awaiting_answers" if s.round > 0 else "failed"
    can_next = status in ACTIVE and c["open"] == 0 and s.round < settings.discovery_max_rounds and ready
    step = (
        {"key": "describe_idea", "label": "Describe your product idea first"} if not ready and status in ("not_started", "failed") else
        {"key": "start_discovery", "label": "Start discovery"} if status == "not_started" else
        {"key": "retry_generation", "label": "Retry generating questions"} if status == "failed" else
        {"key": "wait", "label": "Questions are being generated"} if status == "generating" else
        {"key": "answer_questions", "label": "Answer or skip the open questions"} if status == "awaiting_answers" and c["open"] else
        {"key": "review", "label": "Review what WebForge has learned"} if status == "awaiting_answers" else
        {"key": "complete_discovery", "label": "Confirm the summary to complete discovery"} if status == "ready_for_review" else
        {"key": "return_to_overview", "label": "Return to the project overview",
         "note": "Discovery clarifies your idea only. Proceed to Research, Strategy and PRD; later lifecycle stages are not available yet."}
    )
    summary = build_summary_for(brain, qs) if status in ("ready_for_review", "completed") else None
    assumptions = (summary or dz.build_summary(brain, qs))["assumptions"] if s else []
    return StateOut(
        status=status, session_id=s.id if s else None, idea_ready=ready, round=s.round if s else 0,
        max_rounds=settings.discovery_max_rounds, questions=[_qout(q) for q in qs], counts=c,
        outstanding_questions=[q.id for q in qs if q.status in ("open", "deferred")],
        unresolved_assumptions=[a for a in assumptions if a["status"] == "unverified"], summary=summary, next_step=step,
        last_error=s.last_error if s else None, can_generate_next_round=can_next,
        can_review=status == "awaiting_answers", can_complete=status == "ready_for_review",
    )


def build_summary_for(brain: dict, qs: list[DiscoveryQuestion]) -> dict:
    return dz.build_summary(brain, qs)


# ---------- generation (the only place the provider is called) ----------
async def _generate(db: Session, project: Project, session_id: str, prev_status: str) -> None:
    """Session is already committed as 'generating'. Calls the provider outside any DB transaction."""
    s = db.get(DiscoverySession, session_id, populate_existing=True)
    expected_round = s.round
    prompt = dz.build_prompt(_brain(db, project), _questions(db, s.id), expected_round + 1, settings.discovery_questions_per_round)
    try:
        result = await ai.get_provider().generate_structured(prompt, dz.DiscoveryRound)
    except (ai.ProviderNotConfigured, ai.ProviderError) as e:
        unconfigured = isinstance(e, ai.ProviderNotConfigured)
        msg = "AI provider not configured." if unconfigured else ai.user_message(e)
        with txn(db):
            s = db.get(DiscoverySession, session_id, with_for_update=True, populate_existing=True)
            if s.status == "generating" and s.round == expected_round:
                s.status, s.last_error = prev_status, msg
        raise HTTPException(503 if unconfigured else 502, f"{msg} Your answers and project are unchanged.")
    with txn(db):
        s = db.get(DiscoverySession, session_id, with_for_update=True, populate_existing=True)
        if s.status != "generating" or s.round != expected_round:
            raise HTTPException(409, "Another request changed this discovery session.")
        existing = _questions(db, s.id)
        chosen = dz.select_questions(result.questions, existing, settings.discovery_questions_per_round)
        for i, g in enumerate(chosen):
            db.add(DiscoveryQuestion(
                session_id=s.id, position=len(existing) + i, round=expected_round + 1, fingerprint=dz.fingerprint(g.prompt),
                prompt=g.prompt, rationale=g.rationale, target=g.target, qtype=g.qtype,
                options=[o.model_dump() for o in g.options], required=g.required, priority=g.priority, max_length=g.max_length))
        s.round = expected_round + 1
        s.status = "awaiting_answers" if chosen else "ready_for_review"
        s.last_error = None


# ---------- routes ----------
@router.get("", response_model=StateOut)
def get_discovery(project: Project = Depends(owned), db: Session = Depends(get_db)):
    return build_state(db, project, _get(db, project.id))


@router.post("", response_model=StateOut)
async def start_or_resume(project: Project = Depends(owned), db: Session = Depends(get_db)):
    """Idempotent: creates the session and first round once; later calls resume (or retry a failed generation)."""
    _require_idea(db, project)
    s = _get(db, project.id, lock=True)
    if s is None:
        db.add(DiscoverySession(project_id=project.id, status="generating", round=0))
        try:
            db.commit()
        except IntegrityError:  # a concurrent request created it first: resume theirs
            db.rollback()
            return build_state(db, project, _get(db, project.id))
        s = _get(db, project.id)
    else:
        _unstick(db, s)
        if s.status != "failed":
            return build_state(db, project, s)
        with txn(db):
            s.status, s.last_error = "generating", None
    await _generate(db, project, s.id, "failed")
    return build_state(db, project, _get(db, project.id))


@router.post("/answers", response_model=StateOut)
def submit_answers(body: AnswersIn, project: Project = Depends(owned), user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _require_session(db, project)
    _require_active(s)
    by_id = {q.id: q for q in _questions(db, s.id)}
    if any(a.question_id not in by_id for a in body.answers):  # tampering/cross-session ids: reject before any mutation
        raise HTTPException(404, "Question not found in this discovery session.")
    errors, applied = [], []
    for a in body.answers:
        norm, err = dz.validate_answer(by_id[a.question_id], a.value)
        (errors if err else applied).append({"loc": ["body", "answers", a.question_id], "msg": err} if err else (by_id[a.question_id], norm))
    if errors:
        raise HTTPException(422, errors)
    changed = [(q, n) for q, n in applied if q.status != "answered" or q.answer != n]
    if changed:
        with txn(db):
            patch = dz.answers_patch(latest_revision(db, project.id).snapshot, changed, dz.iso())
            for q, n in changed:
                q.answer, q.status, q.answered_at = n, "answered", now()
            s.updated_at = now()  # bumps the session version: concurrent writers conflict instead of overwriting
            if patch:
                commit_brain(db, project, patch, "discovery_answer", user.id, commit=False)
    return build_state(db, project, _get(db, project.id))


def _set_question_status(project: Project, db: Session, qid: str, new: str) -> StateOut:
    s = _require_session(db, project)
    _require_active(s)
    q = db.get(DiscoveryQuestion, qid)
    if q is None or q.session_id != s.id:
        raise HTTPException(404, "Question not found in this discovery session.")
    if q.status == "answered":
        raise HTTPException(409, "This question is already answered. Submit a new answer to change it.")
    if new == "skipped" and q.required:
        raise HTTPException(409, "Required questions can be deferred but not skipped.")
    if q.status != new:
        with txn(db):
            q.status = new
            s.updated_at = now()
    return build_state(db, project, _get(db, project.id))


@router.post("/questions/{question_id}/skip", response_model=StateOut)
def skip_question(question_id: str, project: Project = Depends(owned), db: Session = Depends(get_db)):
    return _set_question_status(project, db, question_id, "skipped")


@router.post("/questions/{question_id}/defer", response_model=StateOut)
def defer_question(question_id: str, project: Project = Depends(owned), db: Session = Depends(get_db)):
    return _set_question_status(project, db, question_id, "deferred")


@router.post("/next-round", response_model=StateOut)
async def next_round(project: Project = Depends(owned), db: Session = Depends(get_db)):
    s = _require_session(db, project)
    _require_active(s)
    _require_idea(db, project)
    if any(q.status == "open" for q in _questions(db, s.id)):
        raise HTTPException(409, "Answer, skip or defer the open questions before asking for more.")
    if s.round >= settings.discovery_max_rounds:
        raise HTTPException(409, "The question limit has been reached. Review the summary and continue with documented assumptions.")
    prev = s.status
    with txn(db):
        s.status, s.last_error = "generating", None
    await _generate(db, project, s.id, prev)
    return build_state(db, project, _get(db, project.id))


@router.post("/review", response_model=StateOut)
def request_review(project: Project = Depends(owned), db: Session = Depends(get_db)):
    s = _require_session(db, project)
    if s.status != "ready_for_review":
        _require_active(s)
        with txn(db):
            s.status = "ready_for_review"
    return build_state(db, project, _get(db, project.id))


@router.post("/complete", response_model=StateOut)
def complete(body: CompleteIn, project: Project = Depends(owned), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Explicit confirmation. Unanswered/deferred questions block completion unless the user accepts them as documented assumptions."""
    s = _require_session(db, project)
    if s.status == "completed":
        return build_state(db, project, s)  # idempotent
    if s.status != "ready_for_review":
        raise HTTPException(409, "Review the summary before completing discovery.")
    unresolved = [q for q in _questions(db, s.id) if q.status in ("open", "deferred")]
    if unresolved and not body.accept_assumptions:
        raise HTTPException(409, f"{len(unresolved)} question(s) are unanswered or deferred. Answer them, or complete with documented assumptions.")
    with txn(db):
        if unresolved:
            brain = _brain(db, project)
            have = {a["id"] for a in brain["discovery"]["assumptions"]}
            add = [{"id": f"q:{q.id}", "text": f"Unresolved: {q.prompt}", "source": "unanswered_question", "status": "unverified"}
                   for q in unresolved if f"q:{q.id}" not in have]
            if add:
                disc = {**brain["discovery"], "assumptions": brain["discovery"]["assumptions"] + add}
                commit_brain(db, project, {"discovery": disc}, "discovery_completed", user.id, commit=False)
        s.status, s.completed_at, s.last_error = "completed", now(), None
    return build_state(db, project, _get(db, project.id))
