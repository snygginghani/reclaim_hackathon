"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowUpRight,
  Calendar,
  CheckSquare,
  ChevronDown,
  Hash,
  Link2,
  List,
  Plus,
  Tag,
  Text,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { CellEditor } from "./cells";
import type { Database, DbProperty, DbRow, PropertyType } from "@/lib/types";
import {
  useCreateProperty,
  useCreateRow,
  useDeleteProperty,
  useDeleteRow,
  usePatchProperty,
  usePatchRowValues,
  useRenameRow,
} from "@/hooks/use-database";
import { cn } from "@/lib/utils";

export const PROPERTY_TYPE_META: { type: PropertyType; label: string; icon: React.ElementType }[] = [
  { type: "text", label: "Text", icon: Text },
  { type: "number", label: "Number", icon: Hash },
  { type: "select", label: "Select", icon: ChevronDown },
  { type: "multi_select", label: "Multi-select", icon: List },
  { type: "date", label: "Date", icon: Calendar },
  { type: "checkbox", label: "Checkbox", icon: CheckSquare },
  { type: "url", label: "URL", icon: Link2 },
  { type: "relation", label: "Relation", icon: Tag },
];

export function PropertyTypeIcon({
  type,
  className,
}: {
  type: PropertyType;
  className?: string;
}) {
  const Icon = PROPERTY_TYPE_META.find((m) => m.type === type)?.icon ?? Text;
  return <Icon className={className} />;
}

export function TableView({
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
  const dbId = database.page.id;
  const router = useRouter();
  const createRow = useCreateRow(dbId);
  const patchValues = usePatchRowValues(dbId);
  const renameRow = useRenameRow(dbId);
  const deleteRow = useDeleteRow(dbId);
  const patchProperty = usePatchProperty(dbId);

  const properties = database.properties;

  return (
    <div className="overflow-x-auto pb-2">
      <table className="w-full min-w-[560px] border-collapse text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="w-[280px] min-w-[200px] px-2 py-1.5 font-medium">Name</th>
            {properties.map((p) => (
              <PropertyHeader key={p.id} database={database} prop={p} canEdit={canEdit} />
            ))}
            {canEdit && (
              <th className="w-9 px-1 py-1.5">
                <AddPropertyButton database={database} />
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="group/tr border-b border-border/60 hover:bg-secondary/40">
              <td className="px-2 py-1">
                <div className="flex items-center gap-1">
                  <TitleCell
                    row={row}
                    disabled={!canEdit}
                    onCommit={(title) => renameRow.mutate({ rowId: row.id, title })}
                  />
                  <button
                    onClick={() => router.push(`/w/${workspaceId}/p/${row.id}`)}
                    aria-label={`Open ${row.title || "Untitled"} as page`}
                    className="flex shrink-0 items-center gap-0.5 rounded border bg-card px-1 py-0.5 text-[10px] font-medium text-muted-foreground opacity-0 shadow-xs transition-opacity hover:text-foreground group-hover/tr:opacity-100"
                  >
                    <ArrowUpRight className="size-3" />
                    Open
                  </button>
                  {canEdit && (
                    <button
                      onClick={async () => {
                        try {
                          await deleteRow.mutateAsync(row.id);
                        } catch {
                          toast.error("Couldn’t delete the row");
                        }
                      }}
                      aria-label={`Delete ${row.title || "Untitled"}`}
                      className="flex shrink-0 rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover/tr:opacity-100"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  )}
                </div>
              </td>
              {properties.map((p) => (
                <td key={p.id} className="border-l border-border/40 px-2 py-1 align-middle">
                  <CellEditor
                    prop={p}
                    value={row.values[p.id]}
                    disabled={!canEdit}
                    onChange={(v) => patchValues.mutate({ rowId: row.id, values: { [p.id]: v } })}
                    onOptionsChange={(options) => patchProperty.mutate({ id: p.id, options })}
                  />
                </td>
              ))}
              {canEdit && <td className="border-l border-border/40" />}
            </tr>
          ))}
        </tbody>
      </table>

      {canEdit && (
        <button
          onClick={() => createRow.mutate({})}
          className="mt-1 flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
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

function TitleCell({
  row,
  onCommit,
  disabled,
}: {
  row: DbRow;
  onCommit: (title: string) => void;
  disabled?: boolean;
}) {
  const [title, setTitle] = useState(row.title);
  return (
    <input
      value={title}
      disabled={disabled}
      placeholder="Untitled"
      onChange={(e) => setTitle(e.target.value)}
      onBlur={() => title !== row.title && onCommit(title)}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      className="w-full min-w-0 truncate bg-transparent font-medium outline-none placeholder:text-muted-foreground/50"
    />
  );
}

function PropertyHeader({
  database,
  prop,
  canEdit,
}: {
  database: Database;
  prop: DbProperty;
  canEdit: boolean;
}) {
  const patchProperty = usePatchProperty(database.page.id);
  const deleteProperty = useDeleteProperty(database.page.id);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(prop.name);

  return (
    <th className="min-w-[140px] border-l border-border/40 px-2 py-1.5 font-medium">
      {renaming ? (
        <Input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => {
            setRenaming(false);
            if (name.trim() && name !== prop.name) patchProperty.mutate({ id: prop.id, name });
          }}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          className="h-6 px-1 text-xs"
        />
      ) : (
        <DropdownMenu>
          <DropdownMenuTrigger asChild disabled={!canEdit}>
            <button className="flex items-center gap-1.5 rounded px-1 py-0.5 hover:bg-secondary">
              <PropertyTypeIcon type={prop.type} className="size-3.5" />
              {prop.name}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-48">
            <DropdownMenuItem onClick={() => setRenaming(true)}>Rename</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs text-muted-foreground">Type</DropdownMenuLabel>
            {PROPERTY_TYPE_META.map((m) => (
              <DropdownMenuItem
                key={m.type}
                onClick={() => patchProperty.mutate({ id: prop.id, type: m.type })}
                className={cn(prop.type === m.type && "bg-accent text-accent-foreground")}
              >
                <m.icon className="size-4" />
                {m.label}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant="destructive"
              onClick={() => deleteProperty.mutate(prop.id)}
            >
              <Trash2 className="size-4" />
              Delete property
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </th>
  );
}

export function AddPropertyButton({ database }: { database: Database }) {
  const createProperty = useCreateProperty(database.page.id);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          aria-label="Add property"
          className="flex size-6 items-center justify-center rounded text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <Plus className="size-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuLabel className="text-xs text-muted-foreground">
          New property
        </DropdownMenuLabel>
        {PROPERTY_TYPE_META.map((m) => (
          <DropdownMenuItem
            key={m.type}
            onClick={() =>
              createProperty.mutate({
                name: m.label,
                type: m.type,
                options: m.type === "select" || m.type === "multi_select" ? { choices: [] } : {},
              })
            }
          >
            <m.icon className="size-4" />
            {m.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
