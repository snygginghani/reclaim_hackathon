"use client";

import { use, useState } from "react";
import { Bot, Check, Loader2, Pencil, Plus, RefreshCw, Trash2, User } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAddMemory,
  useDeleteMemory,
  useEditMemory,
  useMemories,
  useReindex,
  type MemoryItem,
} from "@/hooks/use-assistant";

export default function MemoryPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = use(params);
  const memories = useMemories(workspaceId);
  const addMemory = useAddMemory(workspaceId);
  const reindex = useReindex(workspaceId);
  const [draft, setDraft] = useState("");

  const add = async () => {
    if (!draft.trim()) return;
    try {
      await addMemory.mutateAsync({ content: draft.trim() });
      setDraft("");
    } catch {
      toast.error("Couldn’t save that memory");
    }
  };

  return (
    <div className="mx-auto w-full max-w-[720px] flex-1 px-6 py-12">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Lore’s memory</h1>
        <p className="mt-1 max-w-lg text-sm text-muted-foreground">
          Facts Lore remembers about you and your work, woven into every chat. Everything here is
          yours to edit or delete — Lore adds to it automatically as you talk.
        </p>
      </header>

      <div className="mb-6 flex gap-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="Add something Lore should remember…"
        />
        <Button onClick={add} disabled={!draft.trim() || addMemory.isPending}>
          <Plus className="size-4" />
          Add
        </Button>
      </div>

      {memories.isPending ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : memories.data && memories.data.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {memories.data.map((m) => (
            <MemoryRow key={m.id} memory={m} workspaceId={workspaceId} />
          ))}
        </ul>
      ) : (
        <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          Nothing remembered yet. Chat with Lore, or add a fact above.
        </div>
      )}

      <div className="mt-10 border-t pt-6">
        <h2 className="text-sm font-semibold">Search index</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Lore indexes your pages so it can cite them. New edits are indexed automatically; reindex
          if answers seem to miss older content.
        </p>
        <Button
          variant="outline"
          className="mt-3"
          disabled={reindex.isPending}
          onClick={async () => {
            try {
              const r = await reindex.mutateAsync();
              toast.success(`Reindexed — ${r.chunks} passages searchable`);
            } catch {
              toast.error("Reindex failed");
            }
          }}
        >
          {reindex.isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RefreshCw className="size-4" />
          )}
          Reindex workspace
        </Button>
      </div>
    </div>
  );
}

function MemoryRow({ memory, workspaceId }: { memory: MemoryItem; workspaceId: string }) {
  const editMemory = useEditMemory(workspaceId);
  const deleteMemory = useDeleteMemory(workspaceId);
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(memory.content);

  return (
    <li className="group flex items-center gap-3 rounded-xl border bg-card px-3 py-2.5">
      <span
        className="flex size-6 shrink-0 items-center justify-center rounded-full"
        title={memory.source === "auto" ? "Remembered by Lore" : "Added by you"}
      >
        {memory.source === "auto" ? (
          <Bot className="size-4 text-ai" />
        ) : (
          <User className="size-4 text-muted-foreground" />
        )}
      </span>
      {editing ? (
        <Input
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              editMemory.mutate({ id: memory.id, content: value, kind: memory.kind });
              setEditing(false);
            }
            if (e.key === "Escape") {
              setValue(memory.content);
              setEditing(false);
            }
          }}
          className="h-8"
        />
      ) : (
        <span className="min-w-0 flex-1 text-sm">{memory.content}</span>
      )}
      <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        {editing ? (
          <button
            onClick={() => {
              editMemory.mutate({ id: memory.id, content: value, kind: memory.kind });
              setEditing(false);
            }}
            aria-label="Save"
            className="flex size-7 items-center justify-center rounded-md text-success hover:bg-secondary"
          >
            <Check className="size-4" />
          </button>
        ) : (
          <button
            onClick={() => setEditing(true)}
            aria-label="Edit"
            className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <Pencil className="size-3.5" />
          </button>
        )}
        <button
          onClick={() => deleteMemory.mutate(memory.id)}
          aria-label="Forget"
          className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-destructive"
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>
    </li>
  );
}
