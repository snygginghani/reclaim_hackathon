"""The contract between a source (Notion/Confluence/…) and the import engine.

An adapter does all source-specific work — API calls, OAuth, and translating the
source's content into Lore's BlockNote block shapes — then yields normalized
`SourceItem`s. The engine (`engine.py`) does everything source-independent: create
pages/documents/databases, re-host assets, and rewrite cross-page links/relations.

Adapters never import the DB models or touch the session."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol, runtime_checkable


@dataclass
class PropSpec:
    """One database column. `source_id` correlates a column with the cells that
    reference it (row `CellSpec.source_id`)."""

    source_id: str
    name: str
    type: str  # Lore property type: text/number/select/multi_select/date/checkbox/url/relation
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class CellSpec:
    """One database cell. `value` is already in Lore's cell JSONB shape. When
    `is_relation` is set, `value["relation"]` holds *source* ids that the engine
    remaps to Lore page ids in its second pass."""

    source_id: str  # the PropSpec.source_id this cell belongs to
    value: dict[str, Any]
    is_relation: bool = False


@dataclass
class RowSpec:
    """One database row. A row is also a page, so it can carry a block body."""

    source_id: str
    title: str
    values: list[CellSpec] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SourceItem:
    """A page or database in the source. Parents are yielded before children so
    the engine has resolved the parent's Lore id by the time a child arrives.

    Internal links inside `blocks` use the adapter's `link_scheme` placeholder
    (`{scheme}{source_id}`); the engine rewrites them once every id is known."""

    source_id: str
    title: str
    kind: str  # "doc" | "database"
    parent_source_id: str | None = None
    blocks: list[dict[str, Any]] = field(default_factory=list)
    # Populated only when kind == "database".
    db_schema: list[PropSpec] | None = None
    db_rows: list[RowSpec] | None = None


@runtime_checkable
class SourceAdapter(Protocol):
    """What the engine needs from any migration source."""

    # Placeholder scheme for cross-page links, e.g. "notion-page:" / "confluence-page:".
    link_scheme: str
    # Human label shown while the source is being scanned.
    scan_label: str

    async def prepare(self) -> int:
        """Scan the source and return the total number of items (pages +
        databases, excluding database rows) — used to drive the progress bar."""
        ...

    def fetch_items(self) -> AsyncIterator[SourceItem]:
        """Yield every item, parents before children."""
        ...

    async def download_asset(self, ref: str) -> bytes:
        """Fetch the bytes for a media block's `props.url` so the engine can
        re-host it locally."""
        ...
