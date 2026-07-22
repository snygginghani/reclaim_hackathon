"use client";

import { Fragment } from "react";
import { cn } from "@/lib/utils";
import type { Citation } from "@/hooks/use-assistant";

/**
 * Inline spans within one line: bold, italic, inline code, and [n] citation
 * chips. Deliberately a small hand-rolled pass rather than a markdown library —
 * answers only ever use these four, and citations have to interleave with them.
 */
function InlineRuns({
  text,
  citations,
  onCite,
}: {
  text: string;
  citations: Citation[];
  onCite: (c: Citation) => void;
}) {
  const tokens = text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\n]+\*|\[\d+\])/g);
  return (
    <>
      {tokens.map((tok, i) => {
        if (!tok) return null;
        const cite = tok.match(/^\[(\d+)\]$/);
        if (cite) {
          const found = citations.find((c) => c.n === Number(cite[1]));
          if (found) {
            return (
              <button
                key={i}
                onClick={() => onCite(found)}
                title={`${found.page_title}${found.heading ? ` › ${found.heading}` : ""}`}
                className="mx-0.5 inline-flex size-4 -translate-y-0.5 items-center justify-center rounded bg-ai/15 align-middle text-[10px] font-semibold text-ai transition-colors hover:bg-ai/30"
              >
                {cite[1]}
              </button>
            );
          }
        }
        if (tok.startsWith("**") && tok.endsWith("**") && tok.length > 4) {
          return (
            <strong key={i} className="font-semibold text-foreground">
              {tok.slice(2, -2)}
            </strong>
          );
        }
        if (tok.startsWith("`") && tok.endsWith("`") && tok.length > 2) {
          return (
            <code
              key={i}
              className="rounded bg-secondary px-1 py-0.5 font-mono text-[0.85em] text-foreground"
            >
              {tok.slice(1, -1)}
            </code>
          );
        }
        if (tok.startsWith("*") && tok.endsWith("*") && tok.length > 2) {
          return (
            <em key={i} className="italic">
              {tok.slice(1, -1)}
            </em>
          );
        }
        return <Fragment key={i}>{tok}</Fragment>;
      })}
    </>
  );
}

/**
 * Renders an assistant answer. Answers arrive as markdown, so headings, lists,
 * bold and code are given real typography instead of being shown as literal
 * `**` and `##`; [n] markers become chips that jump to the cited block.
 */
export function Answer({
  content,
  citations,
  onCite,
}: {
  content: string;
  citations: Citation[];
  onCite: (c: Citation) => void;
}) {
  const lines = content.split("\n");
  return (
    <div className="flex flex-col gap-1 text-sm leading-relaxed">
      {lines.map((line, i) => {
        const inline = <InlineRuns text={line} citations={citations} onCite={onCite} />;

        const heading = line.match(/^(#{1,4})\s+(.*)$/);
        if (heading) {
          const level = heading[1].length;
          return (
            <p
              key={i}
              className={cn(
                "mt-2 font-semibold text-foreground first:mt-0",
                level <= 2 ? "text-[15px]" : "text-sm"
              )}
            >
              <InlineRuns text={heading[2]} citations={citations} onCite={onCite} />
            </p>
          );
        }

        const task = line.match(/^\s*[-*+]\s+\[([ xX])\]\s+(.*)$/);
        if (task) {
          return (
            <span key={i} className="flex items-start gap-1.5 pl-1">
              <span
                aria-hidden
                className={cn(
                  "mt-[3px] flex size-3.5 shrink-0 items-center justify-center rounded-[4px] border text-[9px]",
                  task[1] === " " ? "border-muted-foreground/40" : "border-ai bg-ai text-white"
                )}
              >
                {task[1] === " " ? "" : "✓"}
              </span>
              <span className="min-w-0">
                <InlineRuns text={task[2]} citations={citations} onCite={onCite} />
              </span>
            </span>
          );
        }

        const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
        if (bullet) {
          return (
            <span key={i} className="flex items-start gap-1.5 pl-1">
              <span aria-hidden className="mt-[7px] size-1 shrink-0 rounded-full bg-muted-foreground" />
              <span className="min-w-0">
                <InlineRuns text={bullet[1]} citations={citations} onCite={onCite} />
              </span>
            </span>
          );
        }

        const numbered = line.match(/^\s*(\d+)[.)]\s+(.*)$/);
        if (numbered) {
          return (
            <span key={i} className="flex items-start gap-1.5 pl-1">
              <span aria-hidden className="shrink-0 text-muted-foreground">
                {numbered[1]}.
              </span>
              <span className="min-w-0">
                <InlineRuns text={numbered[2]} citations={citations} onCite={onCite} />
              </span>
            </span>
          );
        }

        const quote = line.match(/^>\s?(.*)$/);
        if (quote) {
          return (
            <span key={i} className="border-l-2 border-ai/40 pl-2 text-muted-foreground">
              <InlineRuns text={quote[1]} citations={citations} onCite={onCite} />
            </span>
          );
        }

        // Blank lines become spacing, not empty paragraphs.
        if (!line.trim()) return <span key={i} className="h-1" />;
        return <span key={i}>{inline}</span>;
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
