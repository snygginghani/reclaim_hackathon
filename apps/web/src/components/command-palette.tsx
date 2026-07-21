"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import { FileText, Home, Moon, Plus, Sun, Table2 } from "lucide-react";
import { toast } from "sonner";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { api } from "@/lib/api";
import type { Page } from "@/lib/types";
import { useCreatePage, usePages } from "@/hooks/use-pages";
import { useCreateDatabase } from "@/hooks/use-database";
import { useUiStore } from "@/stores/ui";

interface SearchHit {
  page_id: string;
  title: string;
  icon: string | null;
  kind: Page["kind"];
  parent_id: string | null;
  snippet: string | null;
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

/** Snippet with [[match]] markers -> text with highlighted `<mark>` runs. */
function Snippet({ text }: { text: string }) {
  const parts = text.split(/\[\[|\]\]/g);
  return (
    <span className="truncate text-xs text-muted-foreground">
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="rounded-sm bg-warning/25 px-0.5 text-foreground">
            {part}
          </mark>
        ) : (
          part
        )
      )}
    </span>
  );
}

export function CommandPalette({ workspaceId }: { workspaceId: string }) {
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const open = useUiStore((s) => s.paletteOpen);
  const setOpen = useUiStore((s) => s.setPaletteOpen);
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounced(query, 150);

  const pages = usePages(workspaceId);
  const createPage = useCreatePage(workspaceId);
  const createDatabase = useCreateDatabase();

  // ⌘K / Ctrl+K toggles; the store lets the sidebar button open it too.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen(!useUiStore.getState().paletteOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  const handleOpenChange = (v: boolean) => {
    setOpen(v);
    if (!v) setQuery("");
  };

  const search = useQuery({
    queryKey: ["search", workspaceId, debouncedQuery],
    queryFn: () =>
      api<SearchHit[]>(
        `/api/search?workspace_id=${workspaceId}&q=${encodeURIComponent(debouncedQuery)}`
      ),
    enabled: open && debouncedQuery.trim().length > 0,
    placeholderData: (prev) => prev, // keep results while the next query loads
  });

  // Instant local title matches ahead of the server round-trip.
  const localHits = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !pages.data) return [];
    return pages.data.filter((p) => p.title.toLowerCase().includes(q)).slice(0, 5);
  }, [query, pages.data]);

  const serverHits = useMemo(() => {
    const seen = new Set(localHits.map((p) => p.id));
    return (search.data ?? []).filter((h) => !seen.has(h.page_id));
  }, [search.data, localHits]);

  const recent = useMemo(
    () =>
      (pages.data ?? [])
        .slice()
        .sort((a, b) => +new Date(b.updated_at) - +new Date(a.updated_at))
        .slice(0, 6),
    [pages.data]
  );

  const go = (pageId: string) => {
    setOpen(false);
    router.push(`/w/${workspaceId}/p/${pageId}`);
  };

  const showResults = query.trim().length > 0;

  return (
    <CommandDialog
      open={open}
      onOpenChange={handleOpenChange}
      title="Search and commands"
      description="Search pages or run a quick action"
    >
      <Command shouldFilter={false}>
        <CommandInput
        value={query}
        onValueChange={setQuery}
        placeholder="Search pages, or type a command…"
      />
      <CommandList>
        <CommandEmpty>
          {search.isFetching ? "Searching…" : "No results. Try different words."}
        </CommandEmpty>

        {showResults && (localHits.length > 0 || serverHits.length > 0) && (
          <CommandGroup heading="Pages">
            {localHits.map((p) => (
              <CommandItem key={p.id} value={`local-${p.id}`} onSelect={() => go(p.id)}>
                <PageGlyph icon={p.icon} kind={p.kind} />
                <span className="truncate">{p.title || "Untitled"}</span>
              </CommandItem>
            ))}
            {serverHits.map((h) => (
              <CommandItem key={h.page_id} value={`hit-${h.page_id}`} onSelect={() => go(h.page_id)}>
                <PageGlyph icon={h.icon} kind={h.kind} />
                <span className="flex min-w-0 flex-col">
                  <span className="truncate">{h.title || "Untitled"}</span>
                  {h.snippet && <Snippet text={h.snippet} />}
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {!showResults && recent.length > 0 && (
          <CommandGroup heading="Recent">
            {recent.map((p) => (
              <CommandItem key={p.id} value={`recent-${p.id}`} onSelect={() => go(p.id)}>
                <PageGlyph icon={p.icon} kind={p.kind} />
                <span className="truncate">{p.title || "Untitled"}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        <CommandSeparator />
        <CommandGroup heading="Actions">
          <CommandItem
            value="action-new-page"
            onSelect={async () => {
              setOpen(false);
              try {
                const page = await createPage.mutateAsync({});
                router.push(`/w/${workspaceId}/p/${page.id}`);
              } catch {
                toast.error("Couldn’t create the page");
              }
            }}
          >
            <Plus className="size-4" />
            New page
          </CommandItem>
          <CommandItem
            value="action-new-database"
            onSelect={async () => {
              setOpen(false);
              try {
                const d = await createDatabase.mutateAsync({ workspace_id: workspaceId });
                router.push(`/w/${workspaceId}/p/${d.page.id}`);
              } catch {
                toast.error("Couldn’t create the database");
              }
            }}
          >
            <Table2 className="size-4" />
            New database
          </CommandItem>
          <CommandItem
            value="action-home"
            onSelect={() => {
              setOpen(false);
              router.push(`/w/${workspaceId}`);
            }}
          >
            <Home className="size-4" />
            Workspace home
          </CommandItem>
          <CommandItem
            value="action-theme"
            onSelect={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          >
            {resolvedTheme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            Switch to {resolvedTheme === "dark" ? "light" : "dark"} theme
          </CommandItem>
        </CommandGroup>
      </CommandList>
      </Command>
    </CommandDialog>
  );
}

function PageGlyph({ icon, kind }: { icon: string | null; kind: Page["kind"] }) {
  if (icon) return <span className="text-base leading-none">{icon}</span>;
  if (kind === "database") return <Table2 className="size-4 text-muted-foreground" />;
  return <FileText className="size-4 text-muted-foreground" />;
}
