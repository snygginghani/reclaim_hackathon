# Contributing

Lore was built by a couple of people over about two weeks. It is a small
project, and it has no issue templates, no PR checklist, no commit message
convention, and no CI gate waiting to reject you. That is not an oversight —
there isn't enough project here to justify the ceremony.

So do whatever you're comfortable with. Open an issue that's one sentence. Open
a PR that fixes a typo. Ask a question in an issue instead of filing it as a
bug. If you're unsure whether something is worth reporting, it is.

## The parts that actually help

Not rules, just the things that save a round trip:

- **Say how to hit it.** What you did, what happened, what you expected. A stack
  trace or the `[api]` / `[web]` log line beats a description of the log line.
- **Run it before you push it.** Not exhaustively — just enough to know the thing
  you changed does what you think.
- **One idea per PR.** Easier to read, easier to revert. A PR that fixes a bug
  and also renames forty variables is two PRs.

Anything past that is optional. Draft PRs are fine. Force-pushing your own
branch is fine. Changing your mind and closing it is fine.

## Running it

Full setup is in [`docs/setup.md`](docs/setup.md). Short version, once the
first-time install is done:

```bash
./scripts/dev.sh
```

Tests, neither of which is enforced anywhere:

```bash
(cd apps/api && uv run pytest)
(cd apps/web && npx tsc --noEmit && npx eslint src)
```

If something fails for reasons that clearly predate your change, say so in the
PR and carry on. Don't feel obliged to fix it on the way past.

## Finding your way around

[`docs/architecture.md`](docs/architecture.md) is the system map, and
[`docs/decisions.md`](docs/decisions.md) is the "why" behind the non-obvious
calls — worth a look before changing something that seems oddly built, since
the reason may already be written down.

## License

Lore is [MIT licensed](LICENSE). Contributions land under the same terms.
