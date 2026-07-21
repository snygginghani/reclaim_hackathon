"use client";

import { Fragment } from "react";
import type { Citation } from "@/hooks/use-assistant";

/** Renders an assistant answer, turning [n] markers into clickable citation
 * chips that jump to the source block. Plain text with preserved whitespace —
 * chat answers are short and don't need full markdown. */
export function Answer({
  content,
  citations,
  onCite,
}: {
  content: string;
  citations: Citation[];
  onCite: (c: Citation) => void;
}) {
  const parts = content.split(/(\[\d+\])/g);
  return (
    <div className="whitespace-pre-wrap text-sm leading-relaxed">
      {parts.map((part, i) => {
        const m = part.match(/^\[(\d+)\]$/);
        if (m) {
          const n = Number(m[1]);
          const cite = citations.find((c) => c.n === n);
          if (cite) {
            return (
              <button
                key={i}
                onClick={() => onCite(cite)}
                title={`${cite.page_title}${cite.heading ? ` › ${cite.heading}` : ""}`}
                className="mx-0.5 inline-flex size-4 -translate-y-0.5 items-center justify-center rounded bg-ai/15 align-middle text-[10px] font-semibold text-ai transition-colors hover:bg-ai/30"
              >
                {n}
              </button>
            );
          }
        }
        return <Fragment key={i}>{part}</Fragment>;
      })}
    </div>
  );
}

/** Distinct source cards under an answer (deduped by page). */
export function SourceList({
  citations,
  onCite,
}: {
  citations: Citation[];
  onCite: (c: Citation) => void;
}) {
  if (citations.length === 0) return null;
  return (
    <div className="mt-2 flex flex-col gap-1">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Sources
      </span>
      {citations.map((c) => (
        <button
          key={c.n}
          onClick={() => onCite(c)}
          className="group flex items-start gap-1.5 rounded-md border bg-card px-2 py-1.5 text-left transition-colors hover:border-ai/40 hover:bg-ai-soft"
        >
          <span className="mt-px flex size-4 shrink-0 items-center justify-center rounded bg-ai/15 text-[10px] font-semibold text-ai">
            {c.n}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-xs font-medium">
              {c.page_title}
              {c.heading ? <span className="text-muted-foreground"> › {c.heading}</span> : null}
            </span>
            <span className="line-clamp-2 text-[11px] text-muted-foreground">{c.snippet}</span>
          </span>
        </button>
      ))}
    </div>
  );
}
