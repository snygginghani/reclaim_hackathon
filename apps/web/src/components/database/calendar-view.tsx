"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import type { Database, DbRow } from "@/lib/types";
import { useCreateRow } from "@/hooks/use-database";
import { cn } from "@/lib/utils";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function isoDay(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

/** Month grid over a date property (view.config.date_prop). */
export function CalendarView({
  database,
  rows,
  dateProp,
  workspaceId,
  canEdit,
}: {
  database: Database;
  rows: DbRow[];
  dateProp: string;
  workspaceId: string;
  canEdit: boolean;
}) {
  const router = useRouter();
  const createRow = useCreateRow(database.page.id);
  const [cursor, setCursor] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  const prop = database.properties.find((p) => p.id === dateProp);
  if (!prop || prop.type !== "date") {
    return (
      <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        Pick a date property for the calendar in the view options.
      </p>
    );
  }

  const byDay = new Map<string, DbRow[]>();
  for (const row of rows) {
    const start = row.values[prop.id]?.date?.start?.slice(0, 10);
    if (!start) continue;
    byDay.set(start, [...(byDay.get(start) ?? []), row]);
  }

  // Build a Monday-first 6-week grid around the cursor month.
  const first = new Date(cursor);
  const offset = (first.getDay() + 6) % 7;
  const gridStart = new Date(first);
  gridStart.setDate(first.getDate() - offset);
  const days = Array.from({ length: 42 }, (_, i) => {
    const d = new Date(gridStart);
    d.setDate(gridStart.getDate() + i);
    return d;
  });
  const today = isoDay(new Date());
  const monthLabel = cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" });

  return (
    <div>
      <div className="mb-2 flex items-center gap-1">
        <h3 className="mr-auto text-sm font-semibold">{monthLabel}</h3>
        <button
          onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}
          aria-label="Previous month"
          className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <ChevronLeft className="size-4" />
        </button>
        <button
          onClick={() => {
            const now = new Date();
            setCursor(new Date(now.getFullYear(), now.getMonth(), 1));
          }}
          className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          Today
        </button>
        <button
          onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}
          aria-label="Next month"
          className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <ChevronRight className="size-4" />
        </button>
      </div>

      <div className="grid grid-cols-7 overflow-hidden rounded-lg border">
        {WEEKDAYS.map((d) => (
          <div
            key={d}
            className="border-b bg-secondary/50 px-2 py-1 text-center text-[11px] font-medium text-muted-foreground"
          >
            {d}
          </div>
        ))}
        {days.map((d, i) => {
          const iso = isoDay(d);
          const inMonth = d.getMonth() === cursor.getMonth();
          const dayRows = byDay.get(iso) ?? [];
          return (
            <div
              key={iso}
              className={cn(
                "group/day min-h-24 border-border/60 p-1",
                i % 7 !== 0 && "border-l",
                i >= 7 && "border-t",
                !inMonth && "bg-secondary/30"
              )}
            >
              <div className="flex items-center justify-between px-1">
                <span
                  className={cn(
                    "text-[11px] tabular-nums",
                    inMonth ? "text-muted-foreground" : "text-muted-foreground/40",
                    iso === today &&
                      "flex size-5 items-center justify-center rounded-full bg-primary font-semibold text-primary-foreground"
                  )}
                >
                  {d.getDate()}
                </span>
                {canEdit && (
                  <button
                    onClick={() =>
                      createRow.mutate({ values: { [prop.id]: { date: { start: iso } } } })
                    }
                    aria-label={`Add row on ${iso}`}
                    className="rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:bg-secondary group-hover/day:opacity-100"
                  >
                    <Plus className="size-3" />
                  </button>
                )}
              </div>
              <div className="mt-0.5 flex flex-col gap-0.5">
                {dayRows.slice(0, 3).map((row) => (
                  <button
                    key={row.id}
                    onClick={() => router.push(`/w/${workspaceId}/p/${row.id}`)}
                    className="truncate rounded bg-accent px-1 py-0.5 text-left text-[11px] font-medium text-accent-foreground hover:brightness-110"
                  >
                    {row.icon ? `${row.icon} ` : ""}
                    {row.title || "Untitled"}
                  </button>
                ))}
                {dayRows.length > 3 && (
                  <span className="px-1 text-[10px] text-muted-foreground">
                    +{dayRows.length - 3} more
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
