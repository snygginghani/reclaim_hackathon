"use client";

import { useRouter } from "next/navigation";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useState } from "react";
import { Plus } from "lucide-react";
import { ChoicePill } from "./cells";
import type { Database, DbRow, SelectChoice } from "@/lib/types";
import { useCreateRow, usePatchRowValues } from "@/hooks/use-database";
import { cn } from "@/lib/utils";

const NO_STATUS = "__none__";

/** Kanban grouped by a select property (view.config.group_by). */
export function BoardView({
  database,
  rows,
  groupBy,
  workspaceId,
  canEdit,
}: {
  database: Database;
  rows: DbRow[];
  groupBy: string;
  workspaceId: string;
  canEdit: boolean;
}) {
  const dbId = database.page.id;
  const router = useRouter();
  const patchValues = usePatchRowValues(dbId);
  const createRow = useCreateRow(dbId);
  const [activeRow, setActiveRow] = useState<DbRow | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const prop = database.properties.find((p) => p.id === groupBy);
  if (!prop || (prop.type !== "select" && prop.type !== "multi_select")) {
    return (
      <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        Pick a select property to group by in the view options.
      </p>
    );
  }

  const choices = prop.options.choices ?? [];
  const columns: { id: string; choice: SelectChoice | null; rows: DbRow[] }[] = [
    ...choices.map((c) => ({
      id: c.id,
      choice: c,
      rows: rows.filter((r) => r.values[prop.id]?.select === c.id),
    })),
    {
      id: NO_STATUS,
      choice: null,
      rows: rows.filter((r) => !r.values[prop.id]?.select),
    },
  ];

  const handleDragEnd = (e: DragEndEvent) => {
    setActiveRow(null);
    if (!e.over) return;
    const rowId = String(e.active.id);
    const columnId = String(e.over.id);
    const value = columnId === NO_STATUS ? null : { select: columnId };
    patchValues.mutate({ rowId, values: { [prop.id]: value } });
  };

  return (
    <DndContext
      sensors={sensors}
      onDragStart={(e: DragStartEvent) =>
        setActiveRow(rows.find((r) => r.id === String(e.active.id)) ?? null)
      }
      onDragEnd={handleDragEnd}
      onDragCancel={() => setActiveRow(null)}
    >
      <div className="flex gap-3 overflow-x-auto pb-3">
        {columns.map((col) => (
          <BoardColumn
            key={col.id}
            columnId={col.id}
            choice={col.choice}
            rows={col.rows}
            canEdit={canEdit}
            onOpen={(rowId) => router.push(`/w/${workspaceId}/p/${rowId}`)}
            onAdd={() =>
              createRow.mutate({
                values: col.id === NO_STATUS ? {} : { [prop.id]: { select: col.id } },
              })
            }
          />
        ))}
      </div>
      <DragOverlay>
        {activeRow && (
          <div className="w-56 rounded-lg border bg-popover p-2.5 text-sm font-medium shadow-lg">
            {activeRow.title || "Untitled"}
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}

function BoardColumn({
  columnId,
  choice,
  rows,
  canEdit,
  onOpen,
  onAdd,
}: {
  columnId: string;
  choice: SelectChoice | null;
  rows: DbRow[];
  canEdit: boolean;
  onOpen: (rowId: string) => void;
  onAdd: () => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: columnId });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex w-60 shrink-0 flex-col gap-1.5 rounded-lg bg-secondary/50 p-2 transition-colors",
        isOver && "bg-accent"
      )}
    >
      <div className="flex items-center gap-1.5 px-1 py-0.5">
        {choice ? (
          <ChoicePill choice={choice} />
        ) : (
          <span className="text-xs font-medium text-muted-foreground">No status</span>
        )}
        <span className="text-xs tabular-nums text-muted-foreground">{rows.length}</span>
      </div>
      {rows.map((row) => (
        <BoardCard key={row.id} row={row} canDrag={canEdit} onOpen={() => onOpen(row.id)} />
      ))}
      {canEdit && (
        <button
          onClick={onAdd}
          className="flex items-center gap-1 rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-background/60 hover:text-foreground"
        >
          <Plus className="size-3.5" />
          New
        </button>
      )}
    </div>
  );
}

function BoardCard({
  row,
  canDrag,
  onOpen,
}: {
  row: DbRow;
  canDrag: boolean;
  onOpen: () => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: row.id,
    disabled: !canDrag,
  });
  return (
    <button
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      onClick={onOpen}
      className={cn(
        "rounded-lg border bg-card p-2.5 text-left text-sm font-medium shadow-xs transition-shadow hover:shadow-sm",
        isDragging && "opacity-40"
      )}
    >
      {row.icon && <span className="mr-1">{row.icon}</span>}
      {row.title || "Untitled"}
    </button>
  );
}
