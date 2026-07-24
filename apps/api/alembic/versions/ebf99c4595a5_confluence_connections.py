"""confluence connections

Revision ID: ebf99c4595a5
Revises: c7e1a9d4f2b8
Create Date: 2026-07-24 15:56:56.548528

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ebf99c4595a5'
down_revision: Union[str, None] = 'c7e1a9d4f2b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('confluence_connections',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_encrypted', sa.Text(), nullable=False),
    sa.Column('cloud_id', sa.String(length=64), nullable=False),
    sa.Column('site_name', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workspace_id', 'user_id')
    )
    op.create_index(op.f('ix_confluence_connections_user_id'), 'confluence_connections', ['user_id'], unique=False)
    op.create_index(op.f('ix_confluence_connections_workspace_id'), 'confluence_connections', ['workspace_id'], unique=False)
    # NOTE: the custom HNSW/FTS indexes (ix_chunks_embedding_hnsw, ix_chunks_text_fts,
    # ix_documents_text_fts) that autogenerate wanted to drop are intentional and
    # created by earlier migrations; leave them in place.


def downgrade() -> None:
    op.drop_index(op.f('ix_confluence_connections_workspace_id'), table_name='confluence_connections')
    op.drop_index(op.f('ix_confluence_connections_user_id'), table_name='confluence_connections')
    op.drop_table('confluence_connections')
