"""ux_artifacts table for Phase 11 UX workspaces

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-12 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ux_artifacts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('artifact_type', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('content', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('basis', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('parent_version', sa.Integer(), nullable=True),
        sa.Column('created_via', sa.String(), nullable=False),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by', sa.String(), nullable=True),
        sa.Column('approval_note', sa.Text(), nullable=True),
        sa.Column('acknowledged_unverified', sa.Boolean(), nullable=False),
        sa.Column('brain_revision', sa.Integer(), nullable=True),
        sa.Column('row_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'artifact_type', 'version'),
    )
    op.create_index(op.f('ix_ux_artifacts_project_id'), 'ux_artifacts', ['project_id'], unique=False)
    op.create_index(op.f('ix_ux_artifacts_artifact_type'), 'ux_artifacts', ['artifact_type'], unique=False)
    op.create_index(
        'uq_ux_one_generating', 'ux_artifacts', ['project_id', 'artifact_type'], unique=True,
        postgresql_where=sa.text("status = 'generating'"), sqlite_where=sa.text("status = 'generating'"),
    )
    op.create_index(
        'uq_ux_one_open', 'ux_artifacts', ['project_id', 'artifact_type'], unique=True,
        postgresql_where=sa.text("status IN ('draft', 'in_review')"), sqlite_where=sa.text("status IN ('draft', 'in_review')"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_ux_one_open', table_name='ux_artifacts', postgresql_where=sa.text("status IN ('draft', 'in_review')"), sqlite_where=sa.text("status IN ('draft', 'in_review')"))
    op.drop_index('uq_ux_one_generating', table_name='ux_artifacts', postgresql_where=sa.text("status = 'generating'"), sqlite_where=sa.text("status = 'generating'"))
    op.drop_index(op.f('ix_ux_artifacts_artifact_type'), table_name='ux_artifacts')
    op.drop_index(op.f('ix_ux_artifacts_project_id'), table_name='ux_artifacts')
    op.drop_table('ux_artifacts')
