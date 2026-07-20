"use client";

import { useRouter } from "next/navigation";
import { FileText, Plus } from "lucide-react";
import { ChoicePill, choiceById } from "./cells";
import type { Database, DbRow } from "@/lib/types";
import { useCreateRow } from "@/hooks/use-database";

/** Compact list: title first, then a short inline summary of the row's values. */
export function ListView({
  database,
  rows,
  workspaceId,
  canEdit,
}: {
  database: Database;
  rows: DbRow[];
  workspaceId: string;
  canEdit: boolean;
}) {
  const router = useRouter();
  const createRow = useCreateRow(database.page.id);

  return (
    <div className="flex flex-col">
      {rows.map((row) => (
        <button
          key={row.id}
          onClick={() => router.push(`/w/${workspaceId}/p/${row.id}`)}
          className="flex items-center gap-2 border-b border-border/60 px-2 py-2 text-left transition-colors hover:bg-secondary/50"
        >
          {row.icon ? (
            <span className="text-base leading-none">{row.icon}</span>
          ) : (
            <FileText className="size-4 shrink-0 text-muted-foreground" />
          )}
          <span className="min-w-0 flex-1 truncate text-sm font-medium">
            {row.title || "Untitled"}
          </span>
          <span className="flex shrink-0 items-center gap-1.5">
            {database.properties.slice(0, 4).map((p) => {
              const v = row.values[p.id];
              if (!v) return null;
              if (p.type === "select" && v.select) {
                const c = choiceById(p, v.select);
                return c ? <ChoicePill key={p.id} choice={c} /> : null;
              }
              if (p.type === "multi_select" && v.multi_select?.length) {
                return v.multi_select.slice(0, 2).map((id) => {
                  const c = choiceById(p, id);
                  return c ? <ChoicePill key={`${p.id}-${id}`} choice={c} /> : null;
                });
              }
              if (p.type === "date" && v.date?.start) {
                return (
                  <span key={p.id} className="text-xs tabular-nums text-muted-foreground">
                    {v.date.start.slice(0, 10)}
                  </span>
                );
              }
              if (p.type === "checkbox") {
                return (
                  <span key={p.id} className="text-xs text-muted-foreground">
                    {v.checkbox ? "✓" : ""}
                  </span>
                );
              }
              if (p.type === "number" && v.number !== undefined) {
                return (
                  <span key={p.id} className="text-xs tabular-nums text-muted-foreground">
                    {v.number}
                  </span>
                );
              }
              return null;
            })}
          </span>
        </button>
      ))}
      {canEdit && (
        <button
          onClick={() => createRow.mutate({})}
          className="flex items-center gap-1.5 rounded-md px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <Plus className="size-4" />
          New row
        </button>
      )}
      {rows.length === 0 && !canEdit && (
        <p className="px-2 py-6 text-center text-sm text-muted-foreground">No rows yet.</p>
      )}
    </div>
  );
}
