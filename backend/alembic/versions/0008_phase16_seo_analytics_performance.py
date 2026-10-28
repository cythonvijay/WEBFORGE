"""optimization_artifacts table for Phase 16 SEO, Analytics & Performance

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-28 05:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
    op.create_table(
        "optimization_artifacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("area", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("supersedes_version", sa.Integer(), nullable=True),
        sa.Column("generation_source", sa.String(), nullable=False),
        sa.Column("ai_metadata", json_type, nullable=False),
        sa.Column("content", json_type, nullable=False),
        sa.Column("basis_summary", json_type, nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("approval_note", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "area", "version", name="uq_optimization_project_area_version"),
    )
    op.create_index("ix_optimization_artifacts_project_id", "optimization_artifacts", ["project_id"], unique=False)
    op.create_index("ix_optimization_artifacts_area", "optimization_artifacts", ["area"], unique=False)
    op.create_index(
        "uq_optimization_approved_per_project_area",
        "optimization_artifacts",
        ["project_id", "area"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
        sqlite_where=sa.text("status = 'approved'"),
    )
    op.create_index(
        "uq_optimization_open_draft_per_project_area",
        "optimization_artifacts",
        ["project_id", "area"],
        unique=True,
        postgresql_where=sa.text("status IN ('draft', 'in_review')"),
        sqlite_where=sa.text("status IN ('draft', 'in_review')"),
    )


def downgrade() -> None:
    op.drop_index("uq_optimization_open_draft_per_project_area", table_name="optimization_artifacts")
    op.drop_index("uq_optimization_approved_per_project_area", table_name="optimization_artifacts")
    op.drop_index("ix_optimization_artifacts_area", table_name="optimization_artifacts")
    op.drop_index("ix_optimization_artifacts_project_id", table_name="optimization_artifacts")
    op.drop_table("optimization_artifacts")
