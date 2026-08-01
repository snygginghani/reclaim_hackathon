# Lore — the workspace for knowledge that stays yours

Real-time collaborative pages and databases where every AI answer cites the block
it came from, your machine is the only machine, and you decide which model — if
any — ever reads your notes.

```bash
./scripts/dev.sh
```

Runs the whole stack — Postgres, API, web — at **localhost:3000**.
First-time install: [`docs/setup.md`](docs/setup.md).

---

## Citation is the product

Ask Lore anything and every claim points back at the exact source block, one click
away. No summary you have to take on faith, no confident paragraph with nothing
underneath it. Retrieval is hybrid — full-text and semantic — so the citation is
the answer's origin, not a plausible match found afterward.

## Sovereignty is the default

Lore runs on your hardware, against your Postgres. Pick a local model through
Ollama, sized to your machine by a built-in calculator, or bring your own
OpenRouter key. Embeddings always run locally, whatever you choose. The importers
hand back their own keys when they're done — Notion's token is revoked outright,
and Confluence never requests offline access, so its token expires on its own and
is deleted after the import. Nothing keeps reaching back into accounts you already
migrated away from. The code is [MIT licensed](LICENSE) — fork it, run it, keep it.

## Memory is structural

The assistant accumulates durable facts about your projects, your context, and
your history, and carries them across sessions — that is what the name means. In
Agent mode it proposes edits to your workspace and waits; nothing changes until
you approve them.

---

## Built for

People whose notes are the work: researchers, students, engineering teams, and
anyone who has watched a knowledge base become a subscription to someone else's
server. If shipping your documents to a third-party model isn't acceptable, Lore
is designed for you.

## Bring what you already wrote

One **Migrate** menu imports from **Notion** and **Confluence** over OAuth,
**Obsidian** from a vault upload, and **AFFiNE** from a `.affine` snapshot — all
converted to native Lore pages and databases, not attachments.

---

Setup, architecture, and the reasoning behind the design live in [`docs/`](docs/) —
[setup](docs/setup.md) · [architecture](docs/architecture.md) · [decisions](docs/decisions.md).
