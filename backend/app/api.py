from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai, security
from .brain import PROTECTED_SECTIONS, SECTIONS, Idea, IntakeResult, ProjectBrain
from .config import settings
from .db import get_db
from .lifecycle import NEEDS_DEPS, STAGE_DEPS, STAGES, STATUSES, next_action, unmet_deps
from .models import (
    ArchitectureDocument,
    BrainRevision,
    DesignArtifact,
    PrdDocument,
    Project,
    ProjectStage,
    RefreshToken,
    ResearchReport,
    StrategyDocument,
    User,
    UxArtifact,
)

router = APIRouter()

NonEmptyName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


# ---------- auth ----------
class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


def _cookie_kwargs() -> dict:
    return dict(httponly=True, secure=settings.cookie_secure, samesite="lax")


def _set_cookies(resp: Response, db: Session, user_id: str):
    raw, h = security.new_refresh_token()
    exp = datetime.now(timezone.utc) + timedelta(days=security.REFRESH_DAYS)
    db.add(RefreshToken(user_id=user_id, token_hash=h, expires_at=exp))
    db.commit()
    kw = _cookie_kwargs()
    resp.set_cookie(
        "access_token",
        security.create_access_token(user_id),
        max_age=security.ACCESS_MINUTES * 60,
        path="/",
        **kw,
    )
    resp.set_cookie(
        "refresh_token",
        raw,
        max_age=security.REFRESH_DAYS * 86400,
        path="/api/auth",
        **kw,
    )


def current_user(access_token: str | None = Cookie(None), db: Session = Depends(get_db)) -> User:
    uid = security.decode_access_token(access_token) if access_token else None
    user = db.get(User, uid) if uid else None
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


@router.post("/auth/register", status_code=201)
def register(c: Credentials, resp: Response, db: Session = Depends(get_db)):
    email = c.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = User(email=email, password_hash=security.hash_password(c.password))
    db.add(user)
    db.commit()
    _set_cookies(resp, db, user.id)
    return {"id": user.id, "email": user.email}


@router.post("/auth/login")
def login(c: Credentials, resp: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == c.email.lower()))
    if not user or not security.verify_password(user.password_hash, c.password):
        raise HTTPException(401, "Invalid email or password")
    _set_cookies(resp, db, user.id)
    return {"id": user.id, "email": user.email}


@router.post("/auth/refresh")
def refresh(resp: Response, refresh_token: str | None = Cookie(None), db: Session = Depends(get_db)):
    if not refresh_token or len(refresh_token) > 256:
        raise HTTPException(401, "Invalid refresh token")
    tok = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(refresh_token)).with_for_update()
    )
    if not tok:
        raise HTTPException(401, "Invalid refresh token")
    if tok.revoked:  # reuse of a rotated token: revoke all of this user's tokens
        for t in db.scalars(select(RefreshToken).where(RefreshToken.user_id == tok.user_id)):
            t.revoked = True
        db.commit()
        raise HTTPException(401, "Refresh token reuse detected")
    if security.as_utc(tok.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(401, "Refresh token expired")
    tok.revoked = True
    _set_cookies(resp, db, tok.user_id)
    return {"ok": True}


@router.post("/auth/logout", status_code=204)
def logout(resp: Response, refresh_token: str | None = Cookie(None), db: Session = Depends(get_db)):
    if refresh_token and len(refresh_token) <= 256:
        tok = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(refresh_token)))
        if tok:
            tok.revoked = True
            db.commit()
    kw = _cookie_kwargs()
    resp.delete_cookie("access_token", path="/", **kw)
    resp.delete_cookie("refresh_token", path="/api/auth", **kw)


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email}


# ---------- project brain (helpers first; used by project creation) ----------
def latest_revision(db: Session, project_id: str) -> BrainRevision | None:
    return db.scalar(
        select(BrainRevision)
        .where(BrainRevision.project_id == project_id)
        .order_by(BrainRevision.version.desc())
        .limit(1)
    )


def commit_brain(
    db: Session, p: Project, patch: dict, change_type: str, user_id: str, commit: bool = True
) -> BrainRevision:
    """commit=False flushes only, so the caller can make the revision part of a larger transaction."""
    last = latest_revision(db, p.id)
    snap = dict(last.snapshot) if last else ProjectBrain().model_dump()
    snap.update(patch)
    try:
        snap = ProjectBrain.model_validate(snap).model_dump()
    except ValidationError as e:
        raise HTTPException(422, f"Invalid brain content at {e.errors()[0]['loc']}")
    rev = BrainRevision(
        project_id=p.id,
        version=(last.version + 1) if last else 1,
        change_type=change_type,
        patch=patch,
        snapshot=snap,
        created_by=user_id,
    )
    db.add(rev)
    db.commit() if commit else db.flush()
    return rev


# ---------- projects ----------
class ProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: NonEmptyName
    description: str = Field("", max_length=5000)


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: NonEmptyName | None = None
    description: str | None = Field(None, max_length=5000)
    status: str | None = Field(None, pattern="^(active|archived)$")


def _out(p: Project):
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "status": p.status,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def owned(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Project:
    if len(project_id) > 64:
        raise HTTPException(404, "Project not found")
    p = db.get(Project, project_id)
    if not p or p.owner_id != user.id:
        raise HTTPException(404, "Project not found")
    return p


@router.post("/projects", status_code=201)
def create_project(b: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Project(owner_id=user.id, name=b.name, description=b.description)
    db.add(p)
    db.flush()
    db.add_all(ProjectStage(project_id=p.id, stage=s) for s in STAGES)
    commit_brain(db, p, {}, "created", user.id)
    return _out(p)


@router.get("/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.created_at.desc()))
    return [_out(p) for p in rows]


@router.get("/projects/{project_id}")
def get_project(p: Project = Depends(owned)):
    return _out(p)


@router.patch("/projects/{project_id}")
def update_project(b: ProjectPatch, p: Project = Depends(owned), db: Session = Depends(get_db)):
    for k, v in b.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    db.commit()
    return _out(p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(p: Project = Depends(owned), db: Session = Depends(get_db)):
    db.delete(p)
    db.commit()


# ---------- brain endpoints ----------
class SectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: dict | list


@router.get("/projects/{project_id}/brain")
def get_brain(p: Project = Depends(owned), db: Session = Depends(get_db)):
    r = latest_revision(db, p.id)
    return {"version": r.version, "brain": r.snapshot}


@router.put("/projects/{project_id}/brain/{section}")
def put_section(
    section: str,
    b: SectionIn,
    p: Project = Depends(owned),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if section not in SECTIONS:
        raise HTTPException(404, f"Unknown brain section '{section}'")
    if section in PROTECTED_SECTIONS:
        raise HTTPException(403, "This section is managed by the discovery workflow and cannot be edited directly.")
    try:
        security.validate_brain_section_payload(b.value)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"version": commit_brain(db, p, {section: b.value}, "edit", user.id).version}


@router.get("/projects/{project_id}/revisions")
def revisions(p: Project = Depends(owned), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(BrainRevision).where(BrainRevision.project_id == p.id).order_by(BrainRevision.version.desc())
    )
    return [
        {
            "id": r.id,
            "version": r.version,
            "change_type": r.change_type,
            "patch": r.patch,
            "created_by": r.created_by,
            "created_at": r.created_at,
        }
        for r in rows
    ]


# ---------- lifecycle ----------
def _statuses(db: Session, project_id: str) -> dict[str, str]:
    return {
        s.stage: s.status
        for s in db.scalars(select(ProjectStage).where(ProjectStage.project_id == project_id))
    }


class StageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


@router.put("/projects/{project_id}/stages/{stage}")
def set_stage(stage: str, b: StageIn, p: Project = Depends(owned), db: Session = Depends(get_db)):
    if stage not in STAGES:
        raise HTTPException(404, "Unknown stage")
    if b.status not in STATUSES:
        raise HTTPException(422, "Invalid status")
    missing = unmet_deps(stage, _statuses(db, p.id))
    if b.status in NEEDS_DEPS and missing:
        raise HTTPException(409, f"Blocked by incomplete stages: {', '.join(missing)}")
    if stage == "research" and b.status == "complete":
        used = list(
            db.scalars(
                select(ResearchReport).where(
                    ResearchReport.project_id == p.id, ResearchReport.status != "failed"
                )
            )
        )
        if used and max(used, key=lambda r: r.version).status != "approved":
            raise HTTPException(
                409,
                "Research has been started for this project. Approve the research report to complete this stage.",
            )
    if stage == "product" and b.status == "complete":
        stgs = list(
            db.scalars(
                select(StrategyDocument).where(
                    StrategyDocument.project_id == p.id, StrategyDocument.status != "failed"
                )
            )
        )
        prds = list(
            db.scalars(
                select(PrdDocument).where(PrdDocument.project_id == p.id, PrdDocument.status != "failed")
            )
        )
        if stgs or prds:
            stg_ok = bool(stgs and max(stgs, key=lambda r: r.version).status == "approved")
            prd_ok = bool(prds and max(prds, key=lambda r: r.version).status == "approved")
            if not (stg_ok and prd_ok):
                raise HTTPException(
                    409,
                    "Strategy or PRD has been started for this project. Approve both Strategy and PRD to complete the Product stage.",
                )
    if stage == "ux" and b.status == "complete":
        from .ux_api import ux_stage_completion_check

        ok, reasons = ux_stage_completion_check(db, p.id)
        if not ok:
            raise HTTPException(409, f"UX stage cannot be marked complete yet: {reasons[0]}")
    if stage == "design" and b.status == "complete":
        from .design_api import design_stage_completion_check

        ok, reasons = design_stage_completion_check(db, p.id)
        if not ok:
            raise HTTPException(409, f"Design stage cannot be marked complete yet: {reasons[0]}")
    if stage == "architecture" and b.status == "complete":
        from .architecture_api import architecture_stage_completion_check

        ok, reasons = architecture_stage_completion_check(db, p.id)
        if not ok:
            raise HTTPException(409, f"Architecture stage cannot be marked complete yet: {reasons[0]}")
    if stage == "testing" and b.status == "complete":
        from .security_verification import testing_stage_completion_check

        ok, reasons = testing_stage_completion_check(db, p.id)
        if not ok:
            raise HTTPException(409, f"Testing stage cannot be marked complete yet: {reasons[0]}")
    if stage == "security" and b.status == "complete":
        from .security_verification import security_stage_completion_check

        ok, reasons = security_stage_completion_check(db, p.id)
        if not ok:
            raise HTTPException(409, f"Security stage cannot be marked complete yet: {reasons[0]}")
    if stage in ("docker", "cicd", "infrastructure", "deployment", "monitoring") and b.status == "complete":
        from .infrastructure_verification import phase15_stage_completion_check

        ok, reasons = phase15_stage_completion_check(db, p.id, stage)
        if not ok:
            raise HTTPException(409, f"{stage.capitalize()} stage cannot be marked complete yet: {reasons[0]}")
    if stage == "seo" and b.status == "complete":
        from .optimization_api import seo_stage_completion_check

        ok, reasons = seo_stage_completion_check(db, p.id)
        if not ok:
            raise HTTPException(409, f"SEO stage cannot be marked complete yet: {reasons[0]}")
    if stage == "analytics" and b.status == "complete":
        from .optimization_api import analytics_stage_completion_check

        ok, reasons = analytics_stage_completion_check(db, p.id)
        if not ok:
            raise HTTPException(409, f"Analytics stage cannot be marked complete yet: {reasons[0]}")
    if stage == "documentation" and b.status == "complete":
        from .documentation_api import documentation_stage_completion_check

        ok, reasons = documentation_stage_completion_check(db, p.id)
        if not ok:
            raise HTTPException(409, f"Documentation stage cannot be marked complete yet: {reasons[0]}")
    row = db.scalar(select(ProjectStage).where(ProjectStage.project_id == p.id, ProjectStage.stage == stage))
    was_complete = row.status == "complete"
    row.status = b.status
    if was_complete and b.status != "complete":
        stage_rows = {
            s.stage: s
            for s in db.scalars(select(ProjectStage).where(ProjectStage.project_id == p.id))
        }
        st_map = {k: r.status for k, r in stage_rows.items()}
        for stg_name in STAGES:
            s_row = stage_rows.get(stg_name)
            if s_row and s_row.status == "complete" and unmet_deps(stg_name, st_map):
                s_row.status = "needs_review"
                st_map[stg_name] = "needs_review"
    db.commit()
    return {"stage": stage, "status": b.status}


@router.get("/projects/{project_id}/overview")
def overview(p: Project = Depends(owned), db: Session = Depends(get_db)):
    st = _statuses(db, p.id)
    done = [s for s in STAGES if st[s] == "complete"]
    revs = db.scalars(
        select(BrainRevision)
        .where(BrainRevision.project_id == p.id)
        .order_by(BrainRevision.version.desc())
        .limit(5)
    )
    return {
        "project": _out(p),
        "stages": [
            {
                "stage": s,
                "status": st[s],
                "depends_on": STAGE_DEPS[s],
                "unmet_dependencies": unmet_deps(s, st),
            }
            for s in STAGES
        ],
        "progress": round(100 * len(done) / len(STAGES)),
        "completed": done,
        "in_progress": [s for s in STAGES if st[s] == "in_progress"],
        "needs_review": [s for s in STAGES if st[s] == "needs_review"],
        "blocked": [s for s in STAGES if st[s] == "blocked"],
        "next_action": next_action(st),
        "recent_changes": [
            {"version": r.version, "change_type": r.change_type, "created_at": r.created_at} for r in revs
        ],
    }


# ---------- AI intake ----------
class IntakeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idea: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=5000)]


@router.post("/projects/{project_id}/intake")
async def intake(
    b: IntakeIn,
    p: Project = Depends(owned),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    prompt = (
        "You are a product analyst. Extract structure from this product idea. "
        "In 'questions', list only the most important missing information (max 3).\n\nIDEA:\n" + b.idea
    )
    try:
        r = await ai.get_provider().generate_structured(prompt, IntakeResult)
    except ai.ProviderNotConfigured as e:
        raise HTTPException(503, f"AI provider not configured: {e}")
    except ai.ProviderError as e:
        raise HTTPException(502, ai.user_message(e))
    idea = Idea(
        raw=b.idea,
        product_name=r.product_name,
        product_type=r.product_type,
        problem=r.problem,
        features=r.features,
        assumptions=r.assumptions,
        open_questions=r.questions,
    )
    rev = commit_brain(
        db,
        p,
        {"idea": idea.model_dump(), "target_users": r.target_users, "goals": r.goals},
        "ai_intake",
        user.id,
    )
    return {"version": rev.version, "result": r.model_dump()}
