"use client";

import { useMemo, useState } from "react";
import {
  ArrowUpDown,
  Calendar as CalendarIcon,
  Columns3,
  LayoutList,
  ListFilter,
  Plus,
  Settings2,
  Table2,
  Trash2,
  X,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { TableView } from "./table-view";
import { BoardView } from "./board-view";
import { ListView } from "./list-view";
import { CalendarView } from "./calendar-view";
import { applyView, FILTER_OPS } from "@/lib/database-query";
import type { DbProperty, DbView, ViewFilter, ViewSort, ViewType } from "@/lib/types";
import {
  useCreateView,
  useDatabase,
  useDeleteView,
  usePatchView,
  useRows,
} from "@/hooks/use-database";
import { cn } from "@/lib/utils";

const VIEW_ICONS: Record<ViewType, React.ElementType> = {
  table: Table2,
  board: Columns3,
  list: LayoutList,
  calendar: CalendarIcon,
};

export function DatabasePage({
  pageId,
  workspaceId,
  canEdit,
}: {
  pageId: string;
  workspaceId: string;
  canEdit: boolean;
}) {
  const database = useDatabase(pageId);
  const rows = useRows(pageId);
  const createView = useCreateView(pageId);
  const deleteView = useDeleteView(pageId);
  const patchView = usePatchView(pageId);
  const [activeViewId, setActiveViewId] = useState<string | null>(null);

  const views = database.data?.views ?? [];
  const activeView = views.find((v) => v.id === activeViewId) ?? views[0];

  const visibleRows = useMemo(() => {
    if (!database.data || !rows.data || !activeView) return [];
    return applyView(
      rows.data,
      database.data.properties,
      activeView.config.filters,
      activeView.config.sorts
    );
  }, [database.data, rows.data, activeView]);

  if (database.isPending || rows.isPending) {
    return (
      <div className="mt-6 flex flex-col gap-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (database.isError || rows.isError || !activeView) {
    return (
      <p className="mt-6 text-sm text-destructive">
        Couldn’t load this database. Reload to try again.
      </p>
    );
  }
  const db = database.data;

  const setConfig = (patch: Partial<DbView["config"]>) =>
    patchView.mutate({ id: activeView.id, config: { ...activeView.config, ...patch } });

  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center gap-1 border-b pb-1">
        {views.map((v) => {
          const Icon = VIEW_ICONS[v.type];
          const active = v.id === activeView.id;
          return (
            <button
              key={v.id}
              onClick={() => setActiveViewId(v.id)}
              aria-current={active ? "true" : undefined}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-2 py-1 text-sm transition-colors",
                active
                  ? "bg-secondary font-medium text-foreground"
                  : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
              )}
            >
              <Icon className="size-3.5" />
              {v.name}
            </button>
          );
        })}
        {canEdit && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                aria-label="Add view"
                className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
              >
                <Plus className="size-4" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              {(Object.keys(VIEW_ICONS) as ViewType[]).map((t) => {
                const Icon = VIEW_ICONS[t];
                return (
                  <DropdownMenuItem
                    key={t}
                    onClick={async () => {
                      const v = await createView.mutateAsync({
                        name: t[0].toUpperCase() + t.slice(1),
                        type: t,
                      });
                      setActiveViewId(v.id);
                    }}
                  >
                    <Icon className="size-4" />
                    <span className="capitalize">{t}</span>
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        <div className="ml-auto flex items-center gap-1">
          <FilterButton
            properties={db.properties}
            filters={activeView.config.filters ?? []}
            onChange={(filters) => setConfig({ filters })}
            disabled={!canEdit}
          />
          <SortButton
            properties={db.properties}
            sorts={activeView.config.sorts ?? []}
            onChange={(sorts) => setConfig({ sorts })}
            disabled={!canEdit}
          />
          {canEdit && (
            <ViewOptions
              view={activeView}
              properties={db.properties}
              onConfig={setConfig}
              onDelete={
                views.length > 1
                  ? () => {
                      deleteView.mutate(activeView.id);
                      setActiveViewId(null);
                    }
                  : undefined
              }
            />
          )}
        </div>
      </div>

      <div className="mt-3">
        {activeView.type === "table" && (
          <TableView database={db} rows={visibleRows} workspaceId={workspaceId} canEdit={canEdit} />
        )}
        {activeView.type === "board" && (
          <BoardView
            database={db}
            rows={visibleRows}
            groupBy={
              activeView.config.group_by ??
              db.properties.find((p) => p.type === "select")?.id ??
              ""
            }
            workspaceId={workspaceId}
            canEdit={canEdit}
          />
        )}
        {activeView.type === "list" && (
          <ListView database={db} rows={visibleRows} workspaceId={workspaceId} canEdit={canEdit} />
        )}
        {activeView.type === "calendar" && (
          <CalendarView
            database={db}
            rows={visibleRows}
            dateProp={
              activeView.config.date_prop ??
              db.properties.find((p) => p.type === "date")?.id ??
              ""
            }
            workspaceId={workspaceId}
            canEdit={canEdit}
          />
        )}
      </div>
    </div>
  );
}

function FilterButton({
  properties,
  filters,
  onChange,
  disabled,
}: {
  properties: DbProperty[];
  filters: ViewFilter[];
  onChange: (f: ViewFilter[]) => void;
  disabled?: boolean;
}) {
  const filterable = [
    { id: "title", name: "Name", type: "text" as const, position: 0, options: {} },
    ...properties,
  ];
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          className={cn(
            "flex items-center gap-1 rounded-md px-2 py-1 text-sm transition-colors hover:bg-secondary",
            filters.length > 0 ? "text-primary" : "text-muted-foreground hover:text-foreground"
          )}
        >
          <ListFilter className="size-3.5" />
          Filter
          {filters.length > 0 && <span className="tabular-nums">({filters.length})</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-2" align="end">
        <div className="flex flex-col gap-2">
          {filters.map((f, i) => {
            const prop = filterable.find((p) => p.id === f.prop);
            const ops = prop ? FILTER_OPS[prop.type] : [];
            const opMeta = ops.find((o) => o.op === f.op);
            return (
              <div key={i} className="flex items-center gap-1.5">
                <select
                  value={f.prop}
                  disabled={disabled}
                  onChange={(e) => {
                    const nextProp = filterable.find((p) => p.id === e.target.value)!;
                    const next = [...filters];
                    next[i] = { prop: nextProp.id, op: FILTER_OPS[nextProp.type][0].op };
                    onChange(next);
                  }}
                  className="h-7 w-24 rounded-md border bg-transparent px-1 text-xs"
                >
                  {filterable.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <select
                  value={f.op}
                  disabled={disabled}
                  onChange={(e) => {
                    const next = [...filters];
                    next[i] = { ...f, op: e.target.value };
                    onChange(next);
                  }}
                  className="h-7 w-28 rounded-md border bg-transparent px-1 text-xs"
                >
                  {ops.map((o) => (
                    <option key={o.op} value={o.op}>
                      {o.label}
                    </option>
                  ))}
                </select>
                {opMeta?.needsValue &&
                  (prop && (prop.type === "select" || prop.type === "multi_select") ? (
                    <select
                      value={String(f.value ?? "")}
                      disabled={disabled}
                      onChange={(e) => {
                        const next = [...filters];
                        next[i] = { ...f, value: e.target.value };
                        onChange(next);
                      }}
                      className="h-7 min-w-0 flex-1 rounded-md border bg-transparent px-1 text-xs"
                    >
                      <option value="">—</option>
                      {(prop.options.choices ?? []).map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <Input
                      value={String(f.value ?? "")}
                      disabled={disabled}
                      type={prop?.type === "date" ? "date" : "text"}
                      onChange={(e) => {
                        const next = [...filters];
                        next[i] = { ...f, value: e.target.value };
                        onChange(next);
                      }}
                      className="h-7 min-w-0 flex-1 px-1.5 text-xs"
                    />
                  ))}
                <button
                  onClick={() => onChange(filters.filter((_, j) => j !== i))}
                  disabled={disabled}
                  aria-label="Remove filter"
                  className="shrink-0 rounded p-1 text-muted-foreground hover:text-destructive"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            );
          })}
          <button
            disabled={disabled}
            onClick={() => onChange([...filters, { prop: "title", op: "contains", value: "" }])}
            className="flex items-center gap-1 rounded-md px-1.5 py-1 text-left text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <Plus className="size-3.5" />
            Add filter
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function SortButton({
  properties,
  sorts,
  onChange,
  disabled,
}: {
  properties: DbProperty[];
  sorts: ViewSort[];
  onChange: (s: ViewSort[]) => void;
  disabled?: boolean;
}) {
  const sortable = [{ id: "title", name: "Name" }, ...properties];
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          className={cn(
            "flex items-center gap-1 rounded-md px-2 py-1 text-sm transition-colors hover:bg-secondary",
            sorts.length > 0 ? "text-primary" : "text-muted-foreground hover:text-foreground"
          )}
        >
          <ArrowUpDown className="size-3.5" />
          Sort
          {sorts.length > 0 && <span className="tabular-nums">({sorts.length})</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-2" align="end">
        <div className="flex flex-col gap-2">
          {sorts.map((s, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <select
                value={s.prop}
                disabled={disabled}
                onChange={(e) => {
                  const next = [...sorts];
                  next[i] = { ...s, prop: e.target.value };
                  onChange(next);
                }}
                className="h-7 min-w-0 flex-1 rounded-md border bg-transparent px-1 text-xs"
              >
                {sortable.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <select
                value={s.dir}
                disabled={disabled}
                onChange={(e) => {
                  const next = [...sorts];
                  next[i] = { ...s, dir: e.target.value as "asc" | "desc" };
                  onChange(next);
                }}
                className="h-7 w-28 rounded-md border bg-transparent px-1 text-xs"
              >
                <option value="asc">Ascending</option>
                <option value="desc">Descending</option>
              </select>
              <button
                onClick={() => onChange(sorts.filter((_, j) => j !== i))}
                disabled={disabled}
                aria-label="Remove sort"
                className="shrink-0 rounded p-1 text-muted-foreground hover:text-destructive"
              >
                <X className="size-3.5" />
              </button>
            </div>
          ))}
          <button
            disabled={disabled}
            onClick={() => onChange([...sorts, { prop: "title", dir: "asc" }])}
            className="flex items-center gap-1 rounded-md px-1.5 py-1 text-left text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <Plus className="size-3.5" />
            Add sort
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function ViewOptions({
  view,
  properties,
  onConfig,
  onDelete,
}: {
  view: DbView;
  properties: DbProperty[];
  onConfig: (patch: Partial<DbView["config"]>) => void;
  onDelete?: () => void;
}) {
  const selects = properties.filter((p) => p.type === "select" || p.type === "multi_select");
  const dates = properties.filter((p) => p.type === "date");
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          aria-label="View options"
          className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <Settings2 className="size-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {view.type === "board" && (
          <>
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Group by
            </DropdownMenuLabel>
            {selects.map((p) => (
              <DropdownMenuItem
                key={p.id}
                onClick={() => onConfig({ group_by: p.id })}
                className={cn(view.config.group_by === p.id && "bg-accent text-accent-foreground")}
              >
                {p.name}
              </DropdownMenuItem>
            ))}
            {selects.length === 0 && (
              <p className="px-2 py-1.5 text-xs text-muted-foreground">
                Add a select property first.
              </p>
            )}
          </>
        )}
        {view.type === "calendar" && (
          <>
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Calendar by
            </DropdownMenuLabel>
            {dates.map((p) => (
              <DropdownMenuItem
                key={p.id}
                onClick={() => onConfig({ date_prop: p.id })}
                className={cn(view.config.date_prop === p.id && "bg-accent text-accent-foreground")}
              >
                {p.name}
              </DropdownMenuItem>
            ))}
            {dates.length === 0 && (
              <p className="px-2 py-1.5 text-xs text-muted-foreground">
                Add a date property first.
              </p>
            )}
          </>
        )}
        {onDelete && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={onDelete}>
              <Trash2 className="size-4" />
              Delete view
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
