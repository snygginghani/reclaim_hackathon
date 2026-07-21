# Lore design system — "Calm Precision"

Source of truth for every visual decision in `apps/web`. Generated with the `ui-ux-pro-max` skill
(persisted raw output in `design-system/lore/MASTER.md`), then synthesized by hand — see decision 0.6.

## Brand mark

The Lore mark is a rounded hexagon enclosing a hexagram (Star of David / d20 silhouette) with a
serif **L** at its centre — stark, monochrome, faintly occult. It lives in
`apps/web/src/components/lore-mark.tsx` as `<LoreMark>`, drawn in `currentColor` so it inverts
cleanly between themes (white-on-dark, dark-on-light). Used on the auth, loading, and join
surfaces in `text-foreground` — no indigo container; the mark stands alone. The browser favicon
(`apps/web/src/app/icon.svg`) pins the original white-on-black lockup so it reads on any tab bar.

## Direction

Notion-calm surfaces in light mode, Linear-grade depth in dark mode. The product is a text-dense,
keyboard-first tool: **content is the interface**. Chrome recedes; type, spacing, and a single
indigo accent do the talking. Translucency/blur is allowed ONLY on transient overlays (command
palette, modals, toasts) — never on persistent surfaces like the sidebar or editor.

## Color tokens

Semantic tokens only — components never use raw hex. Defined as CSS variables in `globals.css`,
mapped through Tailwind/shadcn. Light and dark are designed together; contrast verified per mode.

| Token           | Light                | Dark                  | Notes |
|-----------------|----------------------|-----------------------|-------|
| `--background`  | `#F8FAFC`            | `#0B0B0E`             | App canvas (dark: near-black, never pure #000) |
| `--surface`     | `#FFFFFF`            | `#131318`             | Cards, sidebar, panels |
| `--surface-2`   | `#F1F5F9`            | `#1B1B22`             | Hover fills, wells, code blocks |
| `--foreground`  | `#1E293B`            | `#EDEDEF`             | Primary text (≥ 7:1 on background) |
| `--muted-fg`    | `#64748B`            | `#8A8F98`             | Secondary text (≥ 4.5:1) |
| `--faint-fg`    | `#94A3B8`            | `#5C616B`             | Tertiary/disabled text (≥ 3:1) |
| `--border`      | `#E2E8F0`            | `rgba(255,255,255,.08)` | Hairlines everywhere in dark |
| `--primary`     | `#5E6AD2`            | `#5E6AD2`             | Brand indigo — buttons, active nav, focus |
| `--primary-hover` | `#6E79D6`          | `#6E79D6`             | |
| `--on-primary`  | `#FFFFFF`            | `#FFFFFF`             | |
| `--accent-soft` | `#EEF0FB`            | `rgba(94,106,210,.15)` | Selected rows, active sidebar item |
| `--destructive` | `#DC2626`            | `#F87171`             | Always paired with icon/text, never color-only |
| `--success`     | `#16A34A`            | `#4ADE80`             | |
| `--warning`     | `#D97706`            | `#FBBF24`             | |
| `--ring`        | `#5E6AD2`            | `#7C87E0`             | 2px focus rings, always visible |
| `--ai`          | `#8B5CF6`            | `#A78BFA`             | Lore-assistant identity: chat accents, ghost text, AI badges |

Rules: dark mode is desaturated-lifted, not inverted. `--ai` violet distinguishes assistant
surfaces from user content at a glance. Scrims: `rgba(0,0,0,.5)` both modes.

## Typography

- **UI + headings + body:** Plus Jakarta Sans (via `next/font`, self-hosted, `display: swap`).
- **Code / kbd:** JetBrains Mono.
- Scale (px): 12 label · 13 secondary · 15 body (editor: 16) · 18 h3 · 22 h2 · 28 h1 · 36 page-title.
- Weights: 400 body, 500 labels/nav, 600 headings, 700 page titles. Line-height 1.6 body, 1.25 headings.
- Tabular figures for dates, counts, and database number cells.

## Space, radius, elevation

- Spacing: 4px scale (4/8/12/16/24/32/48/64). Sidebar width 260px; editor column `max-w-[720px]` centered.
- Radius: `--radius-sm` 6px (inputs, menu items) · `--radius` 8px (buttons, cards) · `--radius-lg` 12px (modals, palette).
- Elevation: light mode = layered soft shadows (`0 1px 2px rgba(0,0,0,.04)` cards → `0 16px 48px rgba(0,0,0,.12)` modals);
  dark mode = hairline borders + slightly lighter surface instead of shadows. One scale, no ad-hoc values.

## Motion

- Token: `--ease: cubic-bezier(0.16, 1, 0.3, 1)` (expo-out). Micro-interactions 150–200ms; overlays 250ms in, ~170ms out (exit ≈ 70% of enter).
- Springs (Framer Motion) only for drag physics (blocks, kanban cards): `stiffness 500, damping 40`.
- Stagger list entrances 30ms/item, max 8 items. Never animate width/height/top/left — transform+opacity only.
- Every animation honors `prefers-reduced-motion` (global MotionConfig).
- Purpose test: motion must explain cause→effect (where did this come from, where did it go) or it's cut.

## Interaction constants

- Focus: 2px `--ring` ring with 2px offset, on every interactive element, both modes. Never removed.
- Hover states: background shift to `--surface-2` at 150ms; press: scale 0.98 on buttons/cards.
- Hit targets ≥ 32px pointer / 44px touch. `cursor-pointer` on all clickables.
- Icons: **Lucide only**, 16px in dense UI, 20px elsewhere, `stroke-width 1.75`, never emoji.
- Kbd hints everywhere discoverable: menu rows, palette items, tooltips (`⌘K` style, JetBrains Mono 11px).

## Voice

UI copy is calm and specific ("Saved just now", "3 peers editing"). The assistant is **Lore**:
first person, concise, always cites. Empty states teach one action, never scold.
