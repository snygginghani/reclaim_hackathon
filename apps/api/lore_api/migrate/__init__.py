"""Source-agnostic migration core.

`engine.py` walks a `SourceAdapter` and writes Lore pages/documents/databases,
re-hosts assets, and resolves cross-page links/relations. Each source (Notion,
Confluence, …) is a thin adapter under `adapters/` that yields normalized
`SourceItem`s; the engine owns all DB plumbing so adapters never touch the DB."""
