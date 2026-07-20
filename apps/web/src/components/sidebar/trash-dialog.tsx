"use client";

import { useState } from "react";
import { FileText, RotateCcw, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useHardDeletePage, useRestorePage, useTrashedPages } from "@/hooks/use-pages";
import type { Page } from "@/lib/types";

export function TrashDialog({
  workspaceId,
  open,
  onOpenChange,
}: {
  workspaceId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const trashed = useTrashedPages(workspaceId, open);
  const restore = useRestorePage(workspaceId);
  const hardDelete = useHardDeletePage(workspaceId);
  const [confirming, setConfirming] = useState<Page | null>(null);

  // Only show subtree roots: restoring/deleting a root carries its children.
  const ids = new Set((trashed.data ?? []).map((p) => p.id));
  const roots = (trashed.data ?? []).filter((p) => !p.parent_id || !ids.has(p.parent_id));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Trash</DialogTitle>
          <DialogDescription>
            Pages here can be restored, or deleted forever with their sub-pages.
          </DialogDescription>
        </DialogHeader>

        {confirming ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm">
              Delete <span className="font-semibold">{confirming.title || "Untitled"}</span> and
              all of its sub-pages forever? This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setConfirming(null)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={async () => {
                  try {
                    await hardDelete.mutateAsync(confirming.id);
                    toast.success("Deleted forever");
                  } catch {
                    toast.error("Couldn’t delete the page");
                  }
                  setConfirming(null);
                }}
              >
                <Trash2 className="size-4" />
                Delete forever
              </Button>
            </div>
          </div>
        ) : (
          <ScrollArea className="max-h-80">
            <ul className="flex flex-col gap-0.5">
              {roots.map((p) => (
                <li
                  key={p.id}
                  className="group flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-secondary"
                >
                  {p.icon ? (
                    <span className="text-base leading-none">{p.icon}</span>
                  ) : (
                    <FileText className="size-4 text-muted-foreground" />
                  )}
                  <span className="min-w-0 flex-1 truncate">{p.title || "Untitled"}</span>
                  <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7"
                      aria-label={`Restore ${p.title || "Untitled"}`}
                      onClick={async () => {
                        try {
                          await restore.mutateAsync(p.id);
                          toast.success("Page restored");
                        } catch {
                          toast.error("Couldn’t restore the page");
                        }
                      }}
                    >
                      <RotateCcw className="size-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7 text-destructive hover:text-destructive"
                      aria-label={`Delete ${p.title || "Untitled"} forever`}
                      onClick={() => setConfirming(p)}
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                </li>
              ))}
              {roots.length === 0 && (
                <li className="py-10 text-center text-sm text-muted-foreground">
                  Trash is empty.
                </li>
              )}
            </ul>
          </ScrollArea>
        )}
      </DialogContent>
    </Dialog>
  );
}
