"""username replaces email on users

Login is keyed on a username instead of an email address. Email was never
verified, so it was not a usable recovery channel; it is dropped outright.

NOTE: this migration assumes an empty `users` table. There is no backfill, so
the NOT NULL `username` column fails on a table with rows -- that is deliberate.
Reset local data first: `docker compose down -v && docker compose up -d db`.

Revision ID: f3a8c21b90de
Revises: ebf99c4595a5
Create Date: 2026-07-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a8c21b90de'
down_revision: Union[str, None] = 'ebf99c4595a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_column('users', 'email')
    op.add_column('users', sa.Column('username', sa.String(length=30), nullable=False))
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_column('users', 'username')
    op.add_column('users', sa.Column('email', sa.String(length=320), nullable=False))
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
