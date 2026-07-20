"use client";

import Link from "next/link";
import { Database as DatabaseIcon } from "lucide-react";
import { CellEditor } from "./cells";
import { PropertyTypeIcon } from "./table-view";
import { usePatchProperty, usePatchRowValues, useRowContext, useRows } from "@/hooks/use-database";

/** The property strip shown at the top of a row page (like Notion's page properties). */
export function RowProperties({
  rowId,
  workspaceId,
  canEdit,
}: {
  rowId: string;
  workspaceId: string;
  canEdit: boolean;
}) {
  const ctx = useRowContext(rowId);
  const dbId = ctx.data?.page.id ?? "";
  const rows = useRows(dbId, !!dbId);
  const patchValues = usePatchRowValues(dbId);
  const patchProperty = usePatchProperty(dbId);

  if (!ctx.data || !rows.data) return null;
  const row = rows.data.find((r) => r.id === rowId);
  if (!row) return null;

  return (
    <div className="mt-4 flex flex-col gap-1 border-b pb-4">
      <Link
        href={`/w/${workspaceId}/p/${ctx.data.page.id}`}
        className="mb-1 flex w-fit items-center gap-1.5 rounded-md px-1.5 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      >
        <DatabaseIcon className="size-3.5" />
        {ctx.data.page.title || "Untitled database"}
      </Link>
      {ctx.data.properties.map((p) => {
        return (
          <div key={p.id} className="flex min-h-7 items-center gap-2">
            <span className="flex w-36 shrink-0 items-center gap-1.5 text-sm text-muted-foreground">
              <PropertyTypeIcon type={p.type} className="size-3.5" />
              {p.name}
            </span>
            <div className="min-w-0 flex-1">
              <CellEditor
                prop={p}
                value={row.values[p.id]}
                disabled={!canEdit}
                onChange={(v) => patchValues.mutate({ rowId, values: { [p.id]: v } })}
                onOptionsChange={(options) => patchProperty.mutate({ id: p.id, options })}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
