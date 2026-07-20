"use client";

import { useState } from "react";
import { Check, ExternalLink, Plus } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { CellValue, DbProperty, SelectChoice } from "@/lib/types";
import { useRows } from "@/hooks/use-database";

export const CHOICE_COLORS = [
  "#64748B", "#5E6AD2", "#8B5CF6", "#16A34A", "#D97706", "#DC2626", "#0891B2", "#DB2777",
];

export function choiceById(prop: DbProperty, id: string | undefined): SelectChoice | undefined {
  return prop.options.choices?.find((c) => c.id === id);
}

export function ChoicePill({ choice, className }: { choice: SelectChoice; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 truncate rounded px-1.5 py-0.5 text-xs font-medium text-white",
        className
      )}
      style={{ background: choice.color }}
    >
      {choice.name}
    </span>
  );
}

/** Inline editor for one cell. `onChange(null)` clears the value.
 * `onOptionsChange` lets select editors add new choices to the property. */
export function CellEditor({
  prop,
  value,
  onChange,
  onOptionsChange,
  disabled,
}: {
  prop: DbProperty;
  value: CellValue | undefined;
  onChange: (v: CellValue | null) => void;
  onOptionsChange?: (options: DbProperty["options"]) => void;
  disabled?: boolean;
}) {
  switch (prop.type) {
    case "text":
      return (
        <SeamlessText
          initial={value?.text ?? ""}
          placeholder="Empty"
          disabled={disabled}
          onCommit={(t) => onChange(t.trim() ? { text: t } : null)}
        />
      );
    case "number":
      return (
        <SeamlessText
          initial={value?.number?.toString() ?? ""}
          placeholder="Empty"
          disabled={disabled}
          align="right"
          onCommit={(t) => {
            const n = Number(t);
            onChange(t.trim() === "" || Number.isNaN(n) ? null : { number: n });
          }}
        />
      );
    case "url":
      return (
        <div className="flex min-w-0 items-center gap-1">
          <SeamlessText
            initial={value?.url ?? ""}
            placeholder="Empty"
            disabled={disabled}
            className="text-primary underline-offset-2 hover:underline"
            onCommit={(t) => onChange(t.trim() ? { url: t.trim() } : null)}
          />
          {value?.url && (
            <a
              href={/^https?:\/\//.test(value.url) ? value.url : `https://${value.url}`}
              target="_blank"
              rel="noreferrer noopener"
              aria-label="Open link"
              className="shrink-0 rounded p-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              <ExternalLink className="size-3.5" />
            </a>
          )}
        </div>
      );
    case "checkbox":
      return (
        <input
          type="checkbox"
          checked={value?.checkbox === true}
          disabled={disabled}
          onChange={(e) => onChange({ checkbox: e.target.checked })}
          aria-label={prop.name}
          className="size-4 cursor-pointer accent-primary"
        />
      );
    case "date":
      return (
        <input
          type="date"
          value={value?.date?.start?.slice(0, 10) ?? ""}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value ? { date: { start: e.target.value } } : null)}
          aria-label={prop.name}
          className="w-full cursor-pointer bg-transparent text-sm outline-none [color-scheme:dark] dark:[color-scheme:dark] [.light_&]:[color-scheme:light]"
        />
      );
    case "select":
      return (
        <ChoicePicker
          prop={prop}
          selected={value?.select ? [value.select] : []}
          multi={false}
          disabled={disabled}
          onSelect={(ids) => onChange(ids[0] ? { select: ids[0] } : null)}
          onOptionsChange={onOptionsChange}
        />
      );
    case "multi_select":
      return (
        <ChoicePicker
          prop={prop}
          selected={value?.multi_select ?? []}
          multi
          disabled={disabled}
          onSelect={(ids) => onChange(ids.length ? { multi_select: ids } : null)}
          onOptionsChange={onOptionsChange}
        />
      );
    case "relation":
      return (
        <RelationPicker
          prop={prop}
          selected={value?.relation ?? []}
          disabled={disabled}
          onSelect={(ids) => onChange(ids.length ? { relation: ids } : null)}
        />
      );
  }
}

function SeamlessText({
  initial,
  placeholder,
  onCommit,
  disabled,
  align,
  className,
}: {
  initial: string;
  placeholder: string;
  onCommit: (t: string) => void;
  disabled?: boolean;
  align?: "right";
  className?: string;
}) {
  const [text, setText] = useState(initial);
  return (
    <input
      value={text}
      disabled={disabled}
      placeholder={placeholder}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => text !== initial && onCommit(text)}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") {
          setText(initial);
          (e.target as HTMLInputElement).blur();
        }
      }}
      className={cn(
        "w-full min-w-0 truncate bg-transparent text-sm outline-none placeholder:text-muted-foreground/50",
        align === "right" && "text-right tabular-nums",
        className
      )}
    />
  );
}

function ChoicePicker({
  prop,
  selected,
  multi,
  onSelect,
  onOptionsChange,
  disabled,
}: {
  prop: DbProperty;
  selected: string[];
  multi: boolean;
  onSelect: (ids: string[]) => void;
  onOptionsChange?: (options: DbProperty["options"]) => void;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState("");
  const choices = prop.options.choices ?? [];
  const filtered = choices.filter((c) => c.name.toLowerCase().includes(query.toLowerCase()));
  const canCreate =
    query.trim() &&
    onOptionsChange &&
    !choices.some((c) => c.name.toLowerCase() === query.trim().toLowerCase());

  const toggle = (id: string) => {
    if (multi) {
      onSelect(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]);
    } else {
      onSelect(selected[0] === id ? [] : [id]);
    }
  };

  const createChoice = () => {
    const name = query.trim();
    if (!name || !onOptionsChange) return;
    const choice: SelectChoice = {
      id: crypto.randomUUID().slice(0, 8),
      name,
      color: CHOICE_COLORS[choices.length % CHOICE_COLORS.length],
    };
    onOptionsChange({ ...prop.options, choices: [...choices, choice] });
    toggle(choice.id);
    setQuery("");
  };

  return (
    <Popover>
      <PopoverTrigger asChild disabled={disabled}>
        <button
          className="flex h-full min-h-6 w-full flex-wrap items-center gap-1 rounded px-0.5 text-left"
          aria-label={prop.name}
        >
          {selected.length === 0 && (
            <span className="text-sm text-muted-foreground/50">Empty</span>
          )}
          {selected.map((id) => {
            const c = choiceById(prop, id);
            return c ? <ChoicePill key={id} choice={c} /> : null;
          })}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-1.5" align="start">
        <Input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && canCreate && createChoice()}
          placeholder={onOptionsChange ? "Find or create…" : "Find…"}
          className="mb-1.5 h-7 text-sm"
        />
        <div className="flex max-h-52 flex-col gap-0.5 overflow-y-auto">
          {filtered.map((c) => (
            <button
              key={c.id}
              onClick={() => toggle(c.id)}
              className="flex items-center gap-2 rounded px-1.5 py-1 text-left hover:bg-secondary"
            >
              <ChoicePill choice={c} />
              <Check
                className={cn(
                  "ml-auto size-3.5 text-muted-foreground",
                  !selected.includes(c.id) && "invisible"
                )}
              />
            </button>
          ))}
          {canCreate && (
            <button
              onClick={createChoice}
              className="flex items-center gap-1.5 rounded px-1.5 py-1 text-left text-sm hover:bg-secondary"
            >
              <Plus className="size-3.5 text-muted-foreground" />
              Create “{query.trim()}”
            </button>
          )}
          {filtered.length === 0 && !canCreate && (
            <p className="px-1.5 py-2 text-center text-xs text-muted-foreground">No options.</p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function RelationPicker({
  prop,
  selected,
  onSelect,
  disabled,
}: {
  prop: DbProperty;
  selected: string[];
  onSelect: (ids: string[]) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const target = prop.options.target;
  const rows = useRows(target ?? "", open && !!target);
  const byId = new Map((rows.data ?? []).map((r) => [r.id, r]));

  const toggle = (id: string) =>
    onSelect(selected.includes(id) ? selected.filter((s) => s !== id) : [...selected, id]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild disabled={disabled || !target}>
        <button
          className="flex h-full min-h-6 w-full flex-wrap items-center gap-1 rounded px-0.5 text-left"
          aria-label={prop.name}
        >
          {selected.length === 0 && (
            <span className="text-sm text-muted-foreground/50">
              {target ? "Empty" : "No target database"}
            </span>
          )}
          {selected.map((id) => (
            <span key={id} className="truncate rounded bg-secondary px-1.5 py-0.5 text-xs">
              {byId.get(id)?.title || "…"}
            </span>
          ))}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-60 p-1.5" align="start">
        <div className="flex max-h-52 flex-col gap-0.5 overflow-y-auto">
          {(rows.data ?? []).map((r) => (
            <button
              key={r.id}
              onClick={() => toggle(r.id)}
              className="flex items-center gap-2 rounded px-1.5 py-1 text-left text-sm hover:bg-secondary"
            >
              <span className="truncate">{r.title || "Untitled"}</span>
              <Check
                className={cn(
                  "ml-auto size-3.5 text-muted-foreground",
                  !selected.includes(r.id) && "invisible"
                )}
              />
            </button>
          ))}
          {rows.isSuccess && rows.data.length === 0 && (
            <p className="px-1.5 py-2 text-center text-xs text-muted-foreground">
              The linked database has no rows yet.
            </p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
