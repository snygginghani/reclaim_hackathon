"use client";

import { useEffect, useRef } from "react";
import { useTheme } from "next-themes";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import type { Block } from "@blocknote/core";
import "@blocknote/shadcn/style.css";
import { api, API_URL } from "@/lib/api";
import {
  getCollabSession,
  releaseCollabSession,
  retainCollabSession,
} from "@/lib/collab-session";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/hooks/use-auth";

export type SaveState = "saved" | "saving" | "error";

/** A collaborator visible on this page (from Yjs awareness). */
export interface PresenceUser {
  clientId: number;
  name: string;
  color: string;
}

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
  onPresence,
}: {
  pageId: string;
  editable: boolean;
  onSaveState: (s: SaveState) => void;
  onPresence?: (users: PresenceUser[]) => void;
}) {
  const doc = useQuery({
    queryKey: ["document", pageId],
    queryFn: () => api<DocumentPayload>(`/api/pages/${pageId}/content`),
    staleTime: Infinity, // the collaborative session owns the document while open
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
    <CollabEditor
      key={pageId}
      pageId={pageId}
      snapshot={doc.data.blocks}
      editable={editable}
      onSaveState={onSaveState}
      onPresence={onPresence}
    />
  );
}

function CollabEditor({
  pageId,
  snapshot,
  editable,
  onSaveState,
  onPresence,
}: {
  pageId: string;
  snapshot: Block[];
  editable: boolean;
  onSaveState: (s: SaveState) => void;
  onPresence?: (users: PresenceUser[]) => void;
}) {
  const { resolvedTheme } = useTheme();
  const qc = useQueryClient();
  const me = useMe();

  // Shared session, refcounted in the effect so StrictMode's unmount/remount
  // cycle can't destroy a socket the surviving mount still uses.
  const collab = getCollabSession(pageId);
  useEffect(() => {
    retainCollabSession(pageId);
    return () => releaseCollabSession(pageId);
  }, [pageId]);

  const editor = useCreateBlockNote(
    {
      collaboration: {
        provider: collab.provider,
        fragment: collab.fragment,
        user: {
          name: me.data?.name ?? "Someone",
          color: `hsl(${me.data?.avatar_hue ?? 220} 70% 50%)`,
        },
      },
    },
    [collab]
  );

  // --- one-time seeding of legacy/imported pages into the Y.Doc ---
  const seedTried = useRef(false);
  useEffect(() => {
    const trySeed = async (synced: boolean) => {
      if (!synced || seedTried.current) return;
      seedTried.current = true;
      if (collab.fragment.length > 0 || snapshot.length === 0 || !editable) return;
      try {
        const { granted } = await api<{ granted: boolean }>(
          `/api/pages/${pageId}/collab-seed`,
          { method: "POST" }
        );
        // The server grants exactly one seeder — the deterministic-seed lesson
        // from Reclaim v1, enforced centrally instead of via fixed clientIDs.
        if (granted && collab.fragment.length === 0) {
          editor.replaceBlocks(editor.document, snapshot);
        }
      } catch {
        // Seeding is best-effort; the page just starts empty until an editor types.
      }
    };
    collab.provider.on("sync", trySeed);
    if (collab.provider.synced) void trySeed(true);
    return () => collab.provider.off("sync", trySeed);
  }, [collab, editor, pageId, snapshot, editable]);

  // --- presence (live avatars) ---
  useEffect(() => {
    if (!onPresence) return;
    const awareness = collab.provider.awareness;
    const emit = () => {
      const users: PresenceUser[] = [];
      awareness.getStates().forEach((state, clientId) => {
        const u = state.user as { name?: string; color?: string } | undefined;
        if (u?.name) users.push({ clientId, name: u.name, color: u.color ?? "#888" });
      });
      onPresence(users);
    };
    awareness.on("change", emit);
    emit();
    return () => {
      awareness.off("change", emit);
      onPresence([]);
    };
  }, [collab, onPresence]);

  // --- read-model autosave (documents.blocks stays fresh for export/search/RAG) ---
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
      if (latest.current !== null) void flush(); // edits arrived mid-save
    }
  };

  const handleChange = () => {
    if (!editable) return;
    latest.current = editor.document;
    onSaveState("saving");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => void flush(), AUTOSAVE_MS);
  };

  useEffect(() => {
    const beforeUnload = () => {
      if (latest.current !== null) {
        void fetch(`${API_URL}/api/pages/${pageId}/content`, {
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
