"""search: text_content + fts index

Revision ID: 759ce1740351
Revises: 8407887ece57
Create Date: 2026-07-20 20:11:40.258525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '759ce1740351'
down_revision: Union[str, None] = '8407887ece57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('text_content', sa.Text(), server_default='', nullable=False))

    # Backfill from the stored BlockNote JSON.
    import json

    from lore_api.blocks import blocks_to_text

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT page_id, blocks FROM documents")).fetchall()
    for page_id, blocks in rows:
        parsed = blocks if isinstance(blocks, list) else json.loads(blocks or "[]")
        conn.execute(
            sa.text("UPDATE documents SET text_content = :t WHERE page_id = :p"),
            {"t": blocks_to_text(parsed), "p": page_id},
        )

    # FTS expression index over the extracted text (title joins at query time;
    # title matching is also served by the ILIKE fallback).
    op.execute(
        "CREATE INDEX ix_documents_text_fts ON documents "
        "USING GIN (to_tsvector('english', text_content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_documents_text_fts")
    op.drop_column('documents', 'text_content')
