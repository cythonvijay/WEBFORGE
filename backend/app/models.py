import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="active")  # active | archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class BrainRevision(Base):
    """Append-only history. snapshot = full brain after this revision."""
    __tablename__ = "project_brain_revisions"
    __table_args__ = (UniqueConstraint("project_id", "version"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    change_type: Mapped[str] = mapped_column(String)
    patch: Mapped[dict] = mapped_column(JSONType)
    snapshot: Mapped[dict] = mapped_column(JSONType)
    created_by: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProjectStage(Base):
    __tablename__ = "project_stages"
    __table_args__ = (UniqueConstraint("project_id", "stage"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="not_started")


class DiscoverySession(Base):
    """One discovery conversation per project. Product facts live in the Project Brain; this holds the Q&A state."""
    __tablename__ = "discovery_sessions"
    __table_args__ = (UniqueConstraint("project_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String)  # generating | awaiting_answers | ready_for_review | completed | failed
    round: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)  # optimistic lock: concurrent writers get a 409
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __mapper_args__ = {"version_id_col": version}


class DiscoveryQuestion(Base):
    __tablename__ = "discovery_questions"
    __table_args__ = (UniqueConstraint("session_id", "fingerprint"), UniqueConstraint("session_id", "position"))
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)  # stable id handed to the client
    session_id: Mapped[str] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    round: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(String)
    qtype: Mapped[str] = mapped_column(String)
    options: Mapped[list] = mapped_column(JSONType, default=list)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")  # open | answered | skipped | deferred
    answer: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ResearchReport(Base):
    """One immutable-once-approved version of a project's research report. Content is a validated JSON document
    (brief, findings, sources, unresolved questions); approved versions are never edited in place (copy-on-write)."""
    __tablename__ = "research_reports"
    __table_args__ = (
        UniqueConstraint("project_id", "version"),
        # at most one generation in flight and one editable (draft / in_review) version per project
        Index("uq_research_one_generating", "project_id", unique=True,
              postgresql_where=text("status = 'generating'"), sqlite_where=text("status = 'generating'")),
        Index("uq_research_one_open", "project_id", unique=True,
              postgresql_where=text("status IN ('draft', 'in_review')"), sqlite_where=text("status IN ('draft', 'in_review')")),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # generating | failed | draft | in_review | approved | superseded
    mode: Mapped[str] = mapped_column(String, default="preliminary")  # preliminary = no web research was performed
    content: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    basis: Mapped[dict] = mapped_column(JSONType, default=dict)  # Brain version / discovery state the report was built from
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_via: Mapped[str] = mapped_column(String, default="generated")  # generated | copy_of_approved
    error: Mapped[str | None] = mapped_column(String, nullable=True)  # safe, categorized message only
    created_by: Mapped[str] = mapped_column(String)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_unverified: Mapped[bool] = mapped_column(Boolean, default=False)
    brain_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Brain revision written by the approval
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)  # optimistic lock
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __mapper_args__ = {"version_id_col": row_version}


class StrategyDocument(Base):
    """One immutable-once-approved version of a project's product strategy (Phase 10).
    Approved versions are never edited in place (copy-on-write creates a new draft version)."""
    __tablename__ = "strategy_documents"
    __table_args__ = (
        UniqueConstraint("project_id", "version"),
        Index("uq_strategy_one_generating", "project_id", unique=True,
              postgresql_where=text("status = 'generating'"), sqlite_where=text("status = 'generating'")),
        Index("uq_strategy_one_open", "project_id", unique=True,
              postgresql_where=text("status IN ('draft', 'in_review')"), sqlite_where=text("status IN ('draft', 'in_review')")),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # generating | failed | draft | in_review | approved | superseded
    content: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    basis: Mapped[dict] = mapped_column(JSONType, default=dict)  # Brain, discovery, and approved research metadata
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_via: Mapped[str] = mapped_column(String, default="generated")  # generated | copy_of_approved
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_unverified: Mapped[bool] = mapped_column(Boolean, default=False)
    brain_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __mapper_args__ = {"version_id_col": row_version}


class PrdDocument(Base):
    """One immutable-once-approved version of a project's PRD (Phase 10).
    Built from an approved StrategyDocument; approved versions are never edited in place (copy-on-write)."""
    __tablename__ = "prd_documents"
    __table_args__ = (
        UniqueConstraint("project_id", "version"),
        Index("uq_prd_one_generating", "project_id", unique=True,
              postgresql_where=text("status = 'generating'"), sqlite_where=text("status = 'generating'")),
        Index("uq_prd_one_open", "project_id", unique=True,
              postgresql_where=text("status IN ('draft', 'in_review')"), sqlite_where=text("status IN ('draft', 'in_review')")),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # generating | failed | draft | in_review | approved | superseded
    content: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    basis: Mapped[dict] = mapped_column(JSONType, default=dict)  # Brain, approved research, and approved strategy metadata
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_via: Mapped[str] = mapped_column(String, default="generated")  # generated | copy_of_approved
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_unverified: Mapped[bool] = mapped_column(Boolean, default=False)
    brain_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __mapper_args__ = {"version_id_col": row_version}


class UxArtifact(Base):
    """One immutable-once-approved version of a Phase 11 UX artifact (personas, journeys, ia, wireframes, ux_review).
    Approved versions are never edited in place (copy-on-write creates a new draft version)."""
    __tablename__ = "ux_artifacts"
    __table_args__ = (
        UniqueConstraint("project_id", "artifact_type", "version"),
        Index("uq_ux_one_generating", "project_id", "artifact_type", unique=True,
              postgresql_where=text("status = 'generating'"), sqlite_where=text("status = 'generating'")),
        Index("uq_ux_one_open", "project_id", "artifact_type", unique=True,
              postgresql_where=text("status IN ('draft', 'in_review')"), sqlite_where=text("status IN ('draft', 'in_review')")),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    artifact_type: Mapped[str] = mapped_column(String, index=True)  # personas | journeys | ia | wireframes | ux_review
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # generating | failed | draft | in_review | approved | superseded
    content: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    basis: Mapped[dict] = mapped_column(JSONType, default=dict)  # Exact upstream artifact IDs, versions, and hashes
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_via: Mapped[str] = mapped_column(String, default="generated")  # generated | copy_of_approved | manual
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_unverified: Mapped[bool] = mapped_column(Boolean, default=False)
    brain_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __mapper_args__ = {"version_id_col": row_version}


class DesignArtifact(Base):
    """One immutable-once-approved version of a Phase 12 Design artifact (design_system, prototype).
    Approved versions are never edited in place (copy-on-write creates a new draft version)."""
    __tablename__ = "design_artifacts"
    __table_args__ = (
        UniqueConstraint("project_id", "artifact_type", "version"),
        Index("uq_design_one_generating", "project_id", "artifact_type", unique=True,
              postgresql_where=text("status = 'generating'"), sqlite_where=text("status = 'generating'")),
        Index("uq_design_one_open", "project_id", "artifact_type", unique=True,
              postgresql_where=text("status IN ('draft', 'in_review')"), sqlite_where=text("status IN ('draft', 'in_review')")),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    artifact_type: Mapped[str] = mapped_column(String, index=True)  # design_system | prototype
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # generating | failed | draft | in_review | approved | superseded
    content: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    basis: Mapped[dict] = mapped_column(JSONType, default=dict)  # Exact upstream artifact IDs, versions, and hashes
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_via: Mapped[str] = mapped_column(String, default="generated")  # generated | copy_of_approved | manual
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_unverified: Mapped[bool] = mapped_column(Boolean, default=False)
    brain_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __mapper_args__ = {"version_id_col": row_version}


class ArchitectureDocument(Base):
    """One immutable-once-approved version of a project's technical architecture (Phase 13).
    Approved versions are never edited in place (copy-on-write creates a new draft version)."""
    __tablename__ = "architecture_documents"
    __table_args__ = (
        UniqueConstraint("project_id", "version"),
        Index("uq_arch_one_generating", "project_id", unique=True,
              postgresql_where=text("status = 'generating'"), sqlite_where=text("status = 'generating'")),
        Index("uq_arch_one_open", "project_id", unique=True,
              postgresql_where=text("status IN ('draft', 'in_review')"), sqlite_where=text("status IN ('draft', 'in_review')")),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # generating | failed | draft | in_review | approved | superseded
    content: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    basis: Mapped[dict] = mapped_column(JSONType, default=dict)  # Exact upstream artifact IDs, versions, and hashes
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_via: Mapped[str] = mapped_column(String, default="generated")  # generated | copy_of_approved | manual
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_unverified: Mapped[bool] = mapped_column(Boolean, default=False)
    brain_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __mapper_args__ = {"version_id_col": row_version}



class OptimizationArtifact(Base):
    """One immutable-once-approved version of a Phase 16 Optimization specification (seo, analytics, performance).
    Approved versions are never edited in place (copy-on-write creates a new draft version)."""
    __tablename__ = "optimization_artifacts"
    __table_args__ = (
        UniqueConstraint("project_id", "area", "version", name="uq_optimization_project_area_version"),
        Index(
            "uq_optimization_approved_per_project_area",
            "project_id",
            "area",
            unique=True,
            postgresql_where=text("status = 'approved'"),
            sqlite_where=text("status = 'approved'"),
        ),
        Index(
            "uq_optimization_open_draft_per_project_area",
            "project_id",
            "area",
            unique=True,
            postgresql_where=text("status IN ('draft', 'in_review')"),
            sqlite_where=text("status IN ('draft', 'in_review')"),
        ),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    area: Mapped[str] = mapped_column(String, index=True)  # seo | analytics | performance
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft | in_review | approved | superseded
    supersedes_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_source: Mapped[str] = mapped_column(String, default="ai")  # ai | manual | hybrid
    ai_metadata: Mapped[dict] = mapped_column(JSONType, default=dict)
    content: Mapped[dict] = mapped_column(JSONType, default=dict)
    basis_summary: Mapped[dict] = mapped_column(JSONType, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64))
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __mapper_args__ = {"version_id_col": row_version}


class DocumentationExport(Base):
    """Phase 17 versioned project documentation & specification export record.
    Stores validated source_snapshot, MANIFEST.json, UTF-8 Markdown documents, and deterministic SHA-256 digests."""
    __tablename__ = "documentation_exports"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_documentation_export_project_version"),
        Index(
            "uq_documentation_official_current",
            "project_id",
            unique=True,
            postgresql_where=text("export_mode = 'official' AND status = 'completed'"),
            sqlite_where=text("export_mode = 'official' AND status = 'completed'"),
        ),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    export_mode: Mapped[str] = mapped_column(String, default="official")  # official | preview
    status: Mapped[str] = mapped_column(String, default="completed")  # completed | superseded | failed
    source_snapshot: Mapped[dict] = mapped_column(JSONType, default=dict)
    manifest: Mapped[dict] = mapped_column(JSONType, default=dict)
    documents: Mapped[dict] = mapped_column(JSONType, default=dict)
    validation_summary: Mapped[dict] = mapped_column(JSONType, default=dict)
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    bundle_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String)
    export_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    brain_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __mapper_args__ = {"version_id_col": row_version}

