"""ai settings become per-user instead of per-workspace

Configuring AI once per workspace meant re-entering the provider, key and model
for every new workspace. The config belongs to the person, not the workspace.

Existing rows are attributed to the workspace owner so nobody has to re-enter a
key; when one user owned several configured workspaces, the most recently
updated row wins.

Revision ID: b2f4a1c9d3e7
Revises: 0679d129e17b
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2f4a1c9d3e7'
down_revision: Union[str, None] = '0679d129e17b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ai_settings', sa.Column('user_id', sa.UUID(), nullable=True))

    # Attribute each existing config to its workspace owner.
    op.execute(
        """
        UPDATE ai_settings AS s
           SET user_id = (
                SELECT m.user_id FROM workspace_members m
                WHERE m.workspace_id = s.workspace_id AND m.role = 'owner'
                ORDER BY m.user_id LIMIT 1
            )
        """
    )
    # Rows whose workspace has no owner can't be attributed to anyone.
    op.execute("DELETE FROM ai_settings WHERE user_id IS NULL")

    # One row per user: keep the most recently updated.
    op.execute(
        """
        DELETE FROM ai_settings a
        USING ai_settings b
        WHERE a.user_id = b.user_id
          AND (a.updated_at < b.updated_at
               OR (a.updated_at = b.updated_at AND a.workspace_id < b.workspace_id))
        """
    )

    op.drop_constraint('ai_settings_pkey', 'ai_settings', type_='primary')
    op.drop_constraint('ai_settings_workspace_id_fkey', 'ai_settings', type_='foreignkey')
    op.drop_column('ai_settings', 'workspace_id')
    op.alter_column('ai_settings', 'user_id', nullable=False)
    op.create_primary_key('ai_settings_pkey', 'ai_settings', ['user_id'])
    op.create_foreign_key(
        'ai_settings_user_id_fkey', 'ai_settings', 'users', ['user_id'], ['id'], ondelete='CASCADE'
    )


def downgrade() -> None:
    op.add_column('ai_settings', sa.Column('workspace_id', sa.UUID(), nullable=True))
    op.execute(
        """
        UPDATE ai_settings AS s
           SET workspace_id = (
                SELECT m.workspace_id FROM workspace_members m
                WHERE m.user_id = s.user_id AND m.role = 'owner'
                ORDER BY m.workspace_id LIMIT 1
            )
        """
    )
    op.execute("DELETE FROM ai_settings WHERE workspace_id IS NULL")
    op.drop_constraint('ai_settings_pkey', 'ai_settings', type_='primary')
    op.drop_constraint('ai_settings_user_id_fkey', 'ai_settings', type_='foreignkey')
    op.drop_column('ai_settings', 'user_id')
    op.alter_column('ai_settings', 'workspace_id', nullable=False)
    op.create_primary_key('ai_settings_pkey', 'ai_settings', ['workspace_id'])
    op.create_foreign_key(
        'ai_settings_workspace_id_fkey',
        'ai_settings',
        'workspaces',
        ['workspace_id'],
        ['id'],
        ondelete='CASCADE',
    )
