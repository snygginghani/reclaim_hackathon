"""Seed a realistic demo workspace. Run from apps/api:  uv run python scripts/seed.py

Creates a demo user (demo@lore.local / demo-password-1) with a workspace of
nested pages, a database with rows, and document content — enough to explore
every feature (and to give the AI assistant something to cite once a model is
configured). Idempotent: re-running resets the demo user's data.
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from lore_api.blocks import blocks_to_text  # noqa: E402
from lore_api.db import SessionLocal  # noqa: E402
from lore_api.models import (  # noqa: E402
    DbProperty,
    DbValue,
    DbView,
    Document,
    Page,
    User,
    Workspace,
    WorkspaceMember,
)
from lore_api.security import hash_password  # noqa: E402

DEMO_EMAIL = "demo@lore.local"


def para(text: str) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "type": "paragraph",
        "content": [{"type": "text", "text": text, "styles": {}}],
        "children": [],
    }


def heading(text: str, level: int = 2) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "type": "heading",
        "props": {"level": level},
        "content": [{"type": "text", "text": text, "styles": {}}],
        "children": [],
    }


async def main() -> None:
    async with SessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == DEMO_EMAIL))
        ).scalar_one_or_none()
        if existing:
            # Reset: workspaces cascade-delete pages/docs/chunks/etc.
            ws_ids = (
                await db.execute(
                    select(Workspace.id)
                    .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
                    .where(WorkspaceMember.user_id == existing.id)
                )
            ).scalars().all()
            for wid in ws_ids:
                await db.execute(delete(Workspace).where(Workspace.id == wid))
            user = existing
        else:
            user = User(
                email=DEMO_EMAIL,
                password_hash=hash_password("demo-password-1"),
                name="Demo User",
                avatar_hue=265,
            )
            db.add(user)
            await db.flush()

        ws = Workspace(name="Acme Product", icon="🚀")
        db.add(ws)
        await db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))

        async def make_page(title, icon, blocks, parent=None, pos=1024.0):
            page = Page(
                workspace_id=ws.id,
                parent_id=parent,
                title=title,
                icon=icon,
                position=pos,
                created_by=user.id,
            )
            db.add(page)
            await db.flush()
            if blocks:
                text = blocks_to_text(blocks)
                db.add(Document(page_id=page.id, blocks=blocks, text_content=text))
            return page

        home = await make_page(
            "Getting started",
            "👋",
            [
                heading("Welcome to Acme Product", 1),
                para("This is a demo workspace. Everything here is a real page you can edit."),
                heading("How we work"),
                para("We ship weekly. The deploy pipeline runs on GitHub Actions every Friday at 4pm."),
                para("Decisions live in the Roadmap. Ask Lore anything — it cites the exact page."),
            ],
            pos=1024,
        )
        await make_page(
            "Engineering",
            "🛠️",
            [
                heading("Engineering handbook", 1),
                para("The backend is FastAPI + Postgres with pgvector for embeddings."),
                para("The frontend is Next.js with a BlockNote editor and Yjs for real-time collaboration."),
                heading("On-call"),
                para("Rotations are weekly. Page the on-call in #incidents for anything customer-facing."),
            ],
            parent=home.id,
            pos=1024,
        )
        await make_page(
            "Roadmap decisions",
            "🧭",
            [
                heading("Q3 roadmap", 1),
                para("We decided to prioritise the AI assistant over the mobile app this quarter."),
                para("The pricing change to usage-based billing was approved and ships in August."),
            ],
            parent=home.id,
            pos=2048,
        )

        # A database with rows.
        db_page = Page(
            workspace_id=ws.id,
            title="Tasks",
            icon="✅",
            kind="database",
            position=3072,
            created_by=user.id,
        )
        db.add(db_page)
        await db.flush()
        status = DbProperty(
            database_id=db_page.id,
            name="Status",
            type="select",
            position=1024,
            options={
                "choices": [
                    {"id": "todo", "name": "To do", "color": "#64748B"},
                    {"id": "doing", "name": "In progress", "color": "#5E6AD2"},
                    {"id": "done", "name": "Done", "color": "#16A34A"},
                ]
            },
        )
        db.add_all(
            [
                status,
                DbView(database_id=db_page.id, name="Board", type="board", position=1024,
                       config={"group_by": str(status.id)} if False else {}),
                DbView(database_id=db_page.id, name="Table", type="table", position=512),
            ]
        )
        await db.flush()
        # board view needs the real status id in group_by
        board = (
            await db.execute(
                select(DbView).where(DbView.database_id == db_page.id, DbView.type == "board")
            )
        ).scalar_one()
        board.config = {"group_by": str(status.id)}

        rows = [
            ("Ship the AI assistant", "doing"),
            ("Migrate billing to usage-based", "todo"),
            ("Fix the mobile sidebar", "done"),
        ]
        for i, (title, st) in enumerate(rows):
            row = Page(
                workspace_id=ws.id,
                parent_id=db_page.id,
                title=title,
                kind="row",
                position=1024 * (i + 1),
                created_by=user.id,
            )
            db.add(row)
            await db.flush()
            db.add(DbValue(row_id=row.id, property_id=status.id, value={"select": st}))

        await db.commit()
        print(f"Seeded workspace 'Acme Product' for {DEMO_EMAIL} (password: demo-password-1)")


if __name__ == "__main__":
    asyncio.run(main())
