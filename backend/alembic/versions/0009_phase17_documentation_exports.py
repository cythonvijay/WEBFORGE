"""Phase 17: Documentation & Export table (documentation_exports).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-28 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "documentation_exports",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("export_mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_snapshot", JSONType, nullable=False),
        sa.Column("manifest", JSONType, nullable=False),
        sa.Column("documents", JSONType, nullable=False),
        sa.Column("validation_summary", JSONType, nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("bundle_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("export_note", sa.Text(), nullable=True),
        sa.Column("brain_revision", sa.Integer(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version", name="uq_documentation_export_project_version"),
    )
    op.create_index(
        "ix_documentation_exports_project_id",
        "documentation_exports",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "uq_documentation_official_current",
        "documentation_exports",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("export_mode = 'official' AND status = 'completed'"),
        sqlite_where=sa.text("export_mode = 'official' AND status = 'completed'"),
    )


def downgrade() -> None:
    op.drop_index("uq_documentation_official_current", table_name="documentation_exports")
    op.drop_index("ix_documentation_exports_project_id", table_name="documentation_exports")
    op.drop_table("documentation_exports")
