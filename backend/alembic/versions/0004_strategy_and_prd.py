"""strategy_documents and prd_documents

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_doc_table(table_name: str, prefix: str) -> None:
    op.create_table(
        table_name,
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
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
        sa.UniqueConstraint('project_id', 'version'),
    )
    op.create_index(op.f(f'ix_{table_name}_project_id'), table_name, ['project_id'], unique=False)
    op.create_index(
        f'uq_{prefix}_one_generating', table_name, ['project_id'], unique=True,
        postgresql_where=sa.text("status = 'generating'"), sqlite_where=sa.text("status = 'generating'"),
    )
    op.create_index(
        f'uq_{prefix}_one_open', table_name, ['project_id'], unique=True,
        postgresql_where=sa.text("status IN ('draft', 'in_review')"), sqlite_where=sa.text("status IN ('draft', 'in_review')"),
    )


def upgrade() -> None:
    """Upgrade schema."""
    _create_doc_table('strategy_documents', 'strategy')
    _create_doc_table('prd_documents', 'prd')


def downgrade() -> None:
    """Downgrade schema."""
    for table_name, prefix in (('prd_documents', 'prd'), ('strategy_documents', 'strategy')):
        op.drop_index(f'uq_{prefix}_one_open', table_name=table_name, postgresql_where=sa.text("status IN ('draft', 'in_review')"), sqlite_where=sa.text("status IN ('draft', 'in_review')"))
        op.drop_index(f'uq_{prefix}_one_generating', table_name=table_name, postgresql_where=sa.text("status = 'generating'"), sqlite_where=sa.text("status = 'generating'"))
        op.drop_index(op.f(f'ix_{table_name}_project_id'), table_name=table_name)
        op.drop_table(table_name)
