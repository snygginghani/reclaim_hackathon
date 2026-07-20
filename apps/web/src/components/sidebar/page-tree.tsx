"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragMoveEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  ChevronRight,
  FileDown,
  FileText,
  MoreHorizontal,
  Plus,
  Star,
  StarOff,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { Page } from "@/lib/types";
import { buildTree, flattenVisible, projectDrop, type FlatNode } from "@/lib/tree";
import {
  useCreatePage,
  useFavorites,
  useMovePage,
  usePages,
  useRestorePage,
  useToggleFavorite,
  useTrashPage,
} from "@/hooks/use-pages";
import { useUiStore } from "@/stores/ui";

const INDENT = 16;

export function PageTree({ workspaceId }: { workspaceId: string }) {
  const router = useRouter();
  const params = useParams<{ pageId?: string }>();
  const pages = usePages(workspaceId);
  const favorites = useFavorites(workspaceId);
  const createPage = useCreatePage(workspaceId);
  const movePage = useMovePage(workspaceId);
  const expandedMap = useUiStore((s) => s.expanded);
  const setExpanded = useUiStore((s) => s.setExpanded);

  const expanded = useMemo(
    () => new Set(Object.keys(expandedMap).filter((id) => expandedMap[id])),
    [expandedMap]
  );
  const flat = useMemo(
    () => (pages.data ? flattenVisible(buildTree(pages.data), expanded) : []),
    [pages.data, expanded]
  );
  const favoriteIds = useMemo(
    () => new Set((favorites.data ?? []).map((f) => f.page_id)),
    [favorites.data]
  );

  const [activeId, setActiveId] = useState<string | null>(null);
  const [offsetX, setOffsetX] = useState(0);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const projection =
    activeId !== null && overIndex !== null
      ? projectDrop(flat, activeId, overIndex, offsetX, INDENT)
      : null;

  const handleDragStart = (e: DragStartEvent) => setActiveId(String(e.active.id));
  const handleDragMove = (e: DragMoveEvent) => {
    setOffsetX(e.delta.x);
    if (e.over) {
      const idx = flat.findIndex((f) => f.page.id === String(e.over!.id));
      if (idx !== -1) {
        const activeIdx = flat.findIndex((f) => f.page.id === String(e.active.id));
        // Insert position in the "lifted-out" list: dropping below self shifts by one.
        setOverIndex(activeIdx < idx ? idx : idx);
      }
    }
  };
  const handleDragEnd = async (e: DragEndEvent) => {
    const id = String(e.active.id);
    const proj = projection;
    setActiveId(null);
    setOverIndex(null);
    setOffsetX(0);
    if (!proj || !e.over) return;
    if (proj.parentId === id) return;
    if (proj.parentId) setExpanded(proj.parentId, true);
    try {
      await movePage.mutateAsync({ id, parent_id: proj.parentId, after_id: proj.afterId });
    } catch {
      toast.error("Couldn’t move the page");
    }
  };

  const handleNewPage = async (parentId: string | null) => {
    try {
      const page = await createPage.mutateAsync({ parent_id: parentId });
      if (parentId) setExpanded(parentId, true);
      router.push(`/w/${workspaceId}/p/${page.id}`);
    } catch {
      toast.error("Couldn’t create the page");
    }
  };

  const activeNode = activeId ? flat.find((f) => f.page.id === activeId) : null;

  return (
    <div className="flex flex-col gap-0.5">
      {favoriteIds.size > 0 && pages.data && (
        <>
          <SectionLabel>Favorites</SectionLabel>
          {pages.data
            .filter((p) => favoriteIds.has(p.id))
            .map((p) => (
              <PlainRow
                key={`fav-${p.id}`}
                page={p}
                workspaceId={workspaceId}
                active={params.pageId === p.id}
                depth={0}
              />
            ))}
          <div className="h-2" />
        </>
      )}

      <div className="flex items-center justify-between pr-1">
        <SectionLabel>Pages</SectionLabel>
        <button
          onClick={() => handleNewPage(null)}
          aria-label="New page"
          className="flex size-5 items-center justify-center rounded text-muted-foreground opacity-0 transition-opacity hover:bg-secondary hover:text-foreground focus-visible:opacity-100 group-hover/sidebar:opacity-100"
        >
          <Plus className="size-4" />
        </button>
      </div>

      <DndContext
        sensors={sensors}
        onDragStart={handleDragStart}
        onDragMove={handleDragMove}
        onDragEnd={handleDragEnd}
        onDragCancel={() => {
          setActiveId(null);
          setOverIndex(null);
        }}
      >
        <SortableContext
          items={flat.map((f) => f.page.id)}
          strategy={verticalListSortingStrategy}
        >
          {flat.map((node) => (
            <TreeRow
              key={node.page.id}
              node={node}
              workspaceId={workspaceId}
              active={params.pageId === node.page.id}
              favorited={favoriteIds.has(node.page.id)}
              expanded={expanded.has(node.page.id)}
              dropDepth={
                activeId && projection && flat[overIndex ?? -1]?.page.id === node.page.id
                  ? projection.depth
                  : null
              }
              onNewChild={() => handleNewPage(node.page.id)}
            />
          ))}
        </SortableContext>
        <DragOverlay>
          {activeNode && (
            <div className="flex items-center gap-1.5 rounded-md border bg-popover px-2 py-1 text-sm shadow-lg">
              <span className="text-base leading-none">{activeNode.page.icon ?? "📄"}</span>
              {activeNode.page.title || "Untitled"}
            </div>
          )}
        </DragOverlay>
      </DndContext>

      {flat.length === 0 && pages.isSuccess && (
        <button
          onClick={() => handleNewPage(null)}
          className="mx-1 mt-1 rounded-md border border-dashed px-3 py-4 text-center text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
        >
          No pages yet — create your first
        </button>
      )}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/80">
      {children}
    </span>
  );
}

function TreeRow({
  node,
  workspaceId,
  active,
  favorited,
  expanded,
  dropDepth,
  onNewChild,
}: {
  node: FlatNode;
  workspaceId: string;
  active: boolean;
  favorited: boolean;
  expanded: boolean;
  dropDepth: number | null;
  onNewChild: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: node.page.id,
  });

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), transition }}
      className={cn(isDragging && "opacity-40")}
    >
      {dropDepth !== null && (
        <div
          className="pointer-events-none h-0.5 rounded bg-primary"
          style={{ marginLeft: dropDepth * INDENT + 8 }}
        />
      )}
      <Row
        page={node.page}
        workspaceId={workspaceId}
        active={active}
        favorited={favorited}
        depth={node.depth}
        hasChildren={node.hasChildren}
        expanded={expanded}
        onNewChild={onNewChild}
        // Drag starts only from the row's label area — never from the action
        // buttons, so menus/chevrons stay plain clicks. Only the listeners are
        // spread: sortable's aria attributes would override the link's role.
        dragHandleProps={listeners}
      />
    </div>
  );
}

/** Favorites entries: same row, no drag/expand. */
function PlainRow({
  page,
  workspaceId,
  active,
  depth,
}: {
  page: Page;
  workspaceId: string;
  active: boolean;
  depth: number;
}) {
  return (
    <Row
      page={page}
      workspaceId={workspaceId}
      active={active}
      favorited
      depth={depth}
      hasChildren={false}
      expanded={false}
    />
  );
}

function Row({
  page,
  workspaceId,
  active,
  favorited,
  depth,
  hasChildren,
  expanded,
  onNewChild,
  dragHandleProps,
}: {
  page: Page;
  workspaceId: string;
  active: boolean;
  favorited: boolean;
  depth: number;
  hasChildren: boolean;
  expanded: boolean;
  onNewChild?: () => void;
  dragHandleProps?: React.HTMLAttributes<HTMLElement>;
}) {
  const router = useRouter();
  const toggleExpanded = useUiStore((s) => s.toggleExpanded);
  const trashPage = useTrashPage(workspaceId);
  const restorePage = useRestorePage(workspaceId);
  const toggleFavorite = useToggleFavorite(workspaceId);
  const [menuOpen, setMenuOpen] = useState(false);

  const handleTrash = async () => {
    try {
      await trashPage.mutateAsync(page.id);
      toast("Moved to trash", {
        action: {
          label: "Undo",
          onClick: () =>
            restorePage.mutate(page.id, {
              onError: () => toast.error("Couldn’t restore the page"),
            }),
        },
      });
      if (active) router.push(`/w/${workspaceId}`);
    } catch {
      toast.error("Couldn’t delete the page");
    }
  };

  return (
    <div
      className={cn(
        "group/row relative flex h-7 items-center gap-1 rounded-md pr-1 text-sm transition-colors",
        active
          ? "bg-accent font-medium text-accent-foreground"
          : "text-muted-foreground hover:bg-secondary hover:text-foreground",
        menuOpen && "bg-secondary text-foreground"
      )}
      style={{ paddingLeft: depth * INDENT + 4 }}
    >
      <button
        onClick={(e) => {
          e.stopPropagation();
          toggleExpanded(page.id);
        }}
        aria-label={expanded ? "Collapse" : "Expand"}
        aria-expanded={expanded}
        tabIndex={hasChildren ? 0 : -1}
        className={cn(
          "flex size-5 shrink-0 items-center justify-center rounded transition-transform hover:bg-border/60",
          !hasChildren && "invisible",
          expanded && "rotate-90"
        )}
      >
        <ChevronRight className="size-3.5" />
      </button>

      <Link
        href={`/w/${workspaceId}/p/${page.id}`}
        className="flex min-w-0 flex-1 items-center gap-1.5 py-1 focus-visible:outline-none"
        aria-current={active ? "page" : undefined}
        {...dragHandleProps}
      >
        {page.icon ? (
          <span className="text-base leading-none">{page.icon}</span>
        ) : (
          <FileText className="size-4 shrink-0" />
        )}
        <span className="truncate">{page.title || "Untitled"}</span>
      </Link>

      <div
        className={cn(
          "flex items-center gap-0.5 opacity-0 transition-opacity group-hover/row:opacity-100 focus-within:opacity-100",
          menuOpen && "opacity-100"
        )}
      >
        {onNewChild && (
          <button
            onClick={onNewChild}
            aria-label="Add sub-page"
            className="flex size-5 items-center justify-center rounded text-muted-foreground hover:bg-border/60 hover:text-foreground"
          >
            <Plus className="size-3.5" />
          </button>
        )}
        <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
          <DropdownMenuTrigger asChild>
            <button
              aria-label="Page options"
              className="flex size-5 items-center justify-center rounded text-muted-foreground hover:bg-border/60 hover:text-foreground"
            >
              <MoreHorizontal className="size-3.5" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="right">
            <DropdownMenuItem
              onClick={() => toggleFavorite.mutate({ pageId: page.id, favorited })}
            >
              {favorited ? <StarOff className="size-4" /> : <Star className="size-4" />}
              {favorited ? "Remove from favorites" : "Add to favorites"}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={async () => {
                const { exportPage } = await import("@/lib/markdown");
                const { api } = await import("@/lib/api");
                try {
                  const all = await api<Page[]>(`/api/pages?workspace_id=${workspaceId}`);
                  await exportPage(page, all);
                } catch {
                  toast.error("Export failed");
                }
              }}
            >
              <FileDown className="size-4" />
              Export markdown
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={handleTrash}>
              <Trash2 className="size-4" />
              Move to trash
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
