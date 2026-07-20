"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { AlertCircle, Check, FileText, Loader2, Smile, Star } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { EmojiPicker } from "@/components/emoji-picker";
import { useFavorites, usePage, usePages, useToggleFavorite, useUpdatePage } from "@/hooks/use-pages";
import { useWorkspace } from "@/hooks/use-workspaces";
import { cn } from "@/lib/utils";
import type { Page } from "@/lib/types";
import type { SaveState } from "@/components/editor/editor";

// The editor is heavy (ProseMirror); load it client-side only, after the shell paints.
const Editor = dynamic(
  () => import("@/components/editor/editor").then((m) => m.Editor),
  { ssr: false }
);

export default function PageView({
  params,
}: {
  params: Promise<{ workspaceId: string; pageId: string }>;
}) {
  const { workspaceId, pageId } = use(params);
  const page = usePage(pageId);
  const pages = usePages(workspaceId);
  const workspace = useWorkspace(workspaceId);
  const favorites = useFavorites(workspaceId);
  const updatePage = useUpdatePage(workspaceId);
  const toggleFavorite = useToggleFavorite(workspaceId);
  const [saveState, setSaveState] = useState<SaveState>("saved");

  const favorited = (favorites.data ?? []).some((f) => f.page_id === pageId);
  const canEdit = workspace.data?.role !== "viewer";

  // Breadcrumbs from the flat page list.
  const crumbs: Page[] = [];
  if (pages.data && page.data) {
    let cursor: Page | undefined = page.data;
    while (cursor?.parent_id) {
      const parent = pages.data.find((p) => p.id === cursor!.parent_id);
      if (!parent) break;
      crumbs.unshift(parent);
      cursor = parent;
    }
  }

  if (page.isError) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
        <FileText className="size-8 text-muted-foreground" />
        <h1 className="text-lg font-semibold">This page doesn’t exist</h1>
        <p className="text-sm text-muted-foreground">
          It may have been deleted, or the link is wrong.
        </p>
        <Link href={`/w/${workspaceId}`} className="mt-2 text-sm font-medium text-primary hover:underline">
          Back to workspace
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="sticky top-0 z-10 flex h-12 items-center gap-1 border-b bg-background/80 px-4 backdrop-blur-sm">
        <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1 pl-8 text-sm md:pl-0">
          {crumbs.map((c) => (
            <span key={c.id} className="flex min-w-0 items-center gap-1">
              <Link
                href={`/w/${workspaceId}/p/${c.id}`}
                className="max-w-40 truncate rounded px-1.5 py-0.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                {c.icon ? `${c.icon} ` : ""}
                {c.title || "Untitled"}
              </Link>
              <span className="text-muted-foreground/50">/</span>
            </span>
          ))}
          <span className="max-w-48 truncate px-1.5 py-0.5 font-medium">
            {page.data ? (
              <>
                {page.data.icon ? `${page.data.icon} ` : ""}
                {page.data.title || "Untitled"}
              </>
            ) : (
              <Skeleton className="h-4 w-24" />
            )}
          </span>
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <SaveChip state={saveState} />
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => toggleFavorite.mutate({ pageId, favorited })}
                aria-label={favorited ? "Remove from favorites" : "Add to favorites"}
                aria-pressed={favorited}
                className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <Star className={cn("size-4", favorited && "fill-warning text-warning")} />
              </button>
            </TooltipTrigger>
            <TooltipContent>{favorited ? "Unfavorite" : "Favorite"}</TooltipContent>
          </Tooltip>
        </div>
      </header>

      <div className="mx-auto w-full max-w-[720px] flex-1 px-6 pb-32">
        {page.data ? (
          <PageHeader
            key={page.data.id}
            page={page.data}
            onUpdate={(patch) => updatePage.mutate({ id: pageId, ...patch })}
          />
        ) : (
          <div className="pt-16">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="mt-6 h-4 w-full" />
            <Skeleton className="mt-2 h-4 w-5/6" />
          </div>
        )}

        {page.data && (
          <Editor pageId={pageId} editable={canEdit} onSaveState={setSaveState} />
        )}
      </div>
    </div>
  );
}

function SaveChip({ state }: { state: SaveState }) {
  return (
    <span
      role="status"
      className={cn(
        "flex items-center gap-1 rounded px-1.5 py-0.5 text-xs transition-colors",
        state === "error" ? "text-destructive" : "text-muted-foreground"
      )}
    >
      {state === "saving" ? (
        <>
          <Loader2 className="size-3 animate-spin" aria-hidden /> Saving…
        </>
      ) : state === "error" ? (
        <>
          <AlertCircle className="size-3" aria-hidden /> Couldn’t save
        </>
      ) : (
        <>
          <Check className="size-3" aria-hidden /> Saved
        </>
      )}
    </span>
  );
}

function PageHeader({
  page,
  onUpdate,
}: {
  page: Page;
  onUpdate: (patch: { title?: string; icon?: string }) => void;
}) {
  const [title, setTitle] = useState(page.title);
  const debounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const titleRef = useRef<HTMLTextAreaElement>(null);

  // The parent keys this component by page.id, so navigation remounts it with fresh state.

  useEffect(() => {
    const el = titleRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    }
  }, [title]);

  const changeTitle = (value: string) => {
    setTitle(value);
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => onUpdate({ title: value }), 400);
  };

  return (
    <div className="pt-16">
      <div className="group/header">
        <div className="mb-2 flex h-8 items-center gap-2">
          <EmojiPicker
            value={page.icon}
            onSelect={(emoji) => onUpdate({ icon: emoji ?? "" })}
          >
            {page.icon ? (
              <button
                aria-label="Change page icon"
                className="flex size-12 items-center justify-center rounded-lg text-5xl transition-colors hover:bg-secondary"
              >
                {page.icon}
              </button>
            ) : (
              <button
                aria-label="Add page icon"
                className="flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted-foreground opacity-0 transition-opacity hover:bg-secondary focus-visible:opacity-100 group-hover/header:opacity-100"
              >
                <Smile className="size-4" />
                Add icon
              </button>
            )}
          </EmojiPicker>
        </div>
        <textarea
          ref={titleRef}
          value={title}
          onChange={(e) => changeTitle(e.target.value.replace(/\n/g, ""))}
          placeholder="Untitled"
          aria-label="Page title"
          rows={1}
          className="w-full resize-none overflow-hidden bg-transparent text-4xl font-bold tracking-tight outline-none placeholder:text-muted-foreground/40"
        />
      </div>
    </div>
  );
}
