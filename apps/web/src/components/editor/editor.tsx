"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import type { Block } from "@blocknote/core";
import "@blocknote/shadcn/style.css";
import { api } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

export type SaveState = "saved" | "saving" | "error";

interface DocumentPayload {
  page_id: string;
  blocks: Block[];
  updated_at: string;
}

const AUTOSAVE_MS = 800;

export function Editor({
  pageId,
  editable,
  onSaveState,
}: {
  pageId: string;
  editable: boolean;
  onSaveState: (s: SaveState) => void;
}) {
  const doc = useQuery({
    queryKey: ["document", pageId],
    queryFn: () => api<DocumentPayload>(`/api/pages/${pageId}/content`),
    staleTime: Infinity, // the editor owns the document while open
  });

  if (doc.isPending) {
    return (
      <div className="mt-6 flex flex-col gap-3" aria-hidden>
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-4/5" />
      </div>
    );
  }
  if (doc.isError) {
    return (
      <p className="mt-6 text-sm text-destructive">
        Couldn’t load this page’s content. Reload to try again.
      </p>
    );
  }
  return (
    <LoadedEditor
      key={pageId}
      pageId={pageId}
      initial={doc.data.blocks}
      editable={editable}
      onSaveState={onSaveState}
    />
  );
}

function LoadedEditor({
  pageId,
  initial,
  editable,
  onSaveState,
}: {
  pageId: string;
  initial: Block[];
  editable: boolean;
  onSaveState: (s: SaveState) => void;
}) {
  const { resolvedTheme } = useTheme();
  const qc = useQueryClient();
  const editor = useCreateBlockNote({
    initialContent: initial.length > 0 ? initial : undefined,
  });

  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const latest = useRef<Block[] | null>(null);
  const saving = useRef(false);

  const flush = async (): Promise<void> => {
    const blocks = latest.current;
    if (blocks === null || saving.current) return;
    saving.current = true;
    latest.current = null;
    try {
      await api(`/api/pages/${pageId}/content`, {
        method: "PUT",
        body: JSON.stringify({ blocks }),
      });
      qc.setQueryData(["document", pageId], (old: DocumentPayload | undefined) =>
        old ? { ...old, blocks } : old
      );
      onSaveState(latest.current === null ? "saved" : "saving");
    } catch {
      latest.current ??= blocks; // keep the unsaved edits for the next attempt
      onSaveState("error");
    } finally {
      saving.current = false;
      // Edits arrived mid-save: save again right away.
      if (latest.current !== null) void flush();
    }
  };

  const handleChange = () => {
    latest.current = editor.document;
    onSaveState("saving");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => void flush(), AUTOSAVE_MS);
  };

  // Flush pending edits when leaving the page or closing the tab.
  useEffect(() => {
    const beforeUnload = () => {
      if (latest.current !== null) {
        // Fire-and-forget; sendBeacon can't set cookies-included JSON PUT, so use fetch keepalive.
        void fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8300"}/api/pages/${pageId}/content`, {
          method: "PUT",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ blocks: latest.current }),
          keepalive: true,
        });
        latest.current = null;
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      clearTimeout(timer.current);
      beforeUnload();
    };
  }, [pageId]);

  return (
    <BlockNoteView
      editor={editor}
      editable={editable}
      theme={resolvedTheme === "dark" ? "dark" : "light"}
      onChange={handleChange}
      className="lore-editor mt-4"
      data-testid="page-editor"
    />
  );
}
