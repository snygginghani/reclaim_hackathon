# Handoff: fix the agent's document creation (headings + checklists)

## Project context (read this first)

**Lore** is a local-first, Notion-class collaborative workspace with an integrated
AI layer (RAG + agent + memory). Monorepo at repo root:

- `apps/web` — Next.js 16 (App Router, TS, Tailwind v4, shadcn/ui), BlockNote editor, Yjs, TanStack Query, Zustand.
- `apps/api` — FastAPI, SQLAlchemy 2 async, Postgres 16 + pgvector, fastembed, Ollama/OpenRouter provider layer.
- `docs/architecture.md` — full system map. `docs/decisions.md` — the "why" for every non-obvious call. Read both.

**Run it** (from repo root): `./scripts/dev.sh` — starts db + api:8300 + web:3000.
Demo login: `demo@example.com` / `demo-password-1`. Backend tests:
`(cd apps/api && uv run pytest)` (67 passing).

**uvicorn gotcha (important):** `uvicorn --reload` orphans stale workers when only
the wrapper process is killed, leaving the old code serving the port. `scripts/dev.sh`
handles this — Ctrl-C tears down each service's whole process group. If you started
uvicorn by hand instead, clean up with `pkill -f 'uvicorn lore_api.main:app'` before
re-running. See decision 2.1.

**AI requires a configured model** (Ollama or an OpenRouter key) via Settings → AI
in the app. Chat/agent/generation do nothing without one; the rest of the app works regardless.

## How the agent works today (Phase 8)

- Backend loop: `apps/api/lore_api/routers/agent.py` (`POST /api/ai/agent`, SSE).
  It runs **read** tools inline (search/read/list) and **proposes** writes as
  `approval` SSE events — it never mutates the workspace itself.
- Tool registry: `apps/api/lore_api/ai/tools.py`. Write tools:
  `create_page(title, content_markdown)`, `append_to_page(page_id, content_markdown)`,
  `create_database(title, columns)`. `write_preview()` builds the approval card text.
- Frontend: `apps/web/src/components/assistant/ask-lore-panel.tsx` (Agent mode renders
  approval cards). On **Approve**, `apps/web/src/lib/agent-apply.ts` executes the action
  via existing APIs, converting `content_markdown` → BlockNote blocks with
  `markdownToBlocks` from `apps/web/src/lib/markdown.ts`, then `POST /api/pages` +
  `PUT /api/pages/{id}/content`.

So the pipeline is sound: create_page already carries markdown, and headings (`#`)
convert correctly.

## THE BUG (what to fix)

The user asked the agent to create a document (e.g. a gym workout with sets as a
**checklist**). Headings work, but **checklists render as plain bullets, not real
checkboxes**.

**Confirmed root cause:** BlockNote's `tryParseMarkdownToBlocks` (used by
`markdownToBlocks`) does **not** support GFM task lists. There is no `gfm` /
`taskList` handling in `@blocknote/core`'s markdown importer (grep found only the
`checkListItem` block type, never a task-list parser). So `- [ ] Set 1` becomes a
`bulletListItem` with literal text `[ ] Set 1` — no checkbox. (Note: the parser
also needs a DOM, so it only runs in the browser — can't unit-test it in plain Node.)

Secondary issue: the model isn't **told** it can/should use headings + checklists,
so even with working conversion it may not emit them.

## The fix (3 parts)

### 1. Convert GFM task lists → checkListItem (the actual bug)
In `apps/web/src/lib/markdown.ts`, post-process the output of `markdownToBlocks` so
any `bulletListItem` whose first text run starts with `[ ] `, `[x] `, or `[X] `
becomes a `checkListItem` with the right `checked` prop and the prefix stripped.
Do it recursively (blocks have `children`). This fixes the agent AND the notebook
generators AND markdown import in one place, since all three call `markdownToBlocks`.

Sketch:
```ts
function taskListify(blocks: Block[]): Block[] {
  for (const b of blocks) {
    if (b.type === "bulletListItem") {
      const first = (b.content as { text?: string }[])?.[0];
      const m = first?.text?.match(/^\[( |x|X)\]\s+/);
      if (m) {
        (b as { type: string }).type = "checkListItem";
        (b.props as { checked?: boolean }).checked = m[1].toLowerCase() === "x";
        first!.text = first!.text!.slice(m[0].length);
      }
    }
    if (Array.isArray(b.children)) taskListify(b.children as Block[]);
  }
  return blocks;
}
// return taskListify(await headless().tryParseMarkdownToBlocks(markdown));
```
Verify checkListItem's exact block shape against BlockNote (`props.checked: boolean`)
before shipping — create one in the editor and inspect `editor.document`.

### 2. Tell the model it can build rich documents
In `apps/api/lore_api/ai/tools.py`, expand the `create_page` / `append_to_page`
tool descriptions: "content_markdown supports markdown — use `#`/`##` headings,
`- [ ] item` checklists (great for tasks/sets/steps), `-` bullets, `1.` numbered
lists, and **bold**." In `apps/api/lore_api/routers/agent.py` `SYSTEM`, add a line
encouraging structured documents (headings + checklists) when the user asks for a
plan, workout, checklist, or steps.

### 3. Verify end-to-end
- **Unit-test the conversion** in isolation (the one part testable without a browser
  or model): factor `taskListify` into a pure function and test it on parsed-block
  fixtures. Add to `apps/api`? No — it's TS; add a small vitest or a node script
  that feeds representative block JSON through `taskListify` (not through the
  DOM-dependent parser).
- **Live test** (needs a configured model): in Agent mode ask "create a Leg Day
  workout page with a checklist of sets", approve the proposal, open the page,
  confirm real checkboxes render and toggle + persist.

## Constraints / notes
- Keep writes proposal-only (human approves). Don't auto-execute.
- `markdownToBlocks` is the shared conversion seam — fix it there, not in agent-apply.
- After frontend edits: `cd apps/web; npx tsc --noEmit && npx eslint src` must stay clean.
- Don't hardcode model ids; AI features are gated on the user's configured provider.
