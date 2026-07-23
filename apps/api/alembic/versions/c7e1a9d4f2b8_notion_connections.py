"""notion connections

Revision ID: c7e1a9d4f2b8
Revises: b2f4a1c9d3e7
Create Date: 2026-07-23 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7e1a9d4f2b8'
down_revision: Union[str, None] = 'b2f4a1c9d3e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notion_connections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('token_encrypted', sa.Text(), nullable=False),
        sa.Column('notion_workspace_name', sa.String(length=200), nullable=True),
        sa.Column('bot_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'user_id'),
    )
    op.create_index(op.f('ix_notion_connections_workspace_id'), 'notion_connections', ['workspace_id'])
    op.create_index(op.f('ix_notion_connections_user_id'), 'notion_connections', ['user_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_notion_connections_user_id'), table_name='notion_connections')
    op.drop_index(op.f('ix_notion_connections_workspace_id'), table_name='notion_connections')
    op.drop_table('notion_connections')
