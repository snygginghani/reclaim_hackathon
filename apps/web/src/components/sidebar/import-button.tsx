"use client";

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { FileUp, FolderUp, Import, Loader2 } from "lucide-react";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { importMarkdownFiles } from "@/lib/markdown";

export function ImportButton({ workspaceId }: { workspaceId: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  const handleFiles = async (list: FileList | null) => {
    if (!list || list.length === 0) return;
    setBusy(true);
    try {
      const result = await importMarkdownFiles([...list], workspaceId, null);
      if (result.created === 0) {
        toast.info("No markdown files found to import.");
      } else {
        qc.invalidateQueries({ queryKey: ["pages", workspaceId] });
        toast.success(`Imported ${result.created} page${result.created === 1 ? "" : "s"}`);
        if (result.firstPageId) router.push(`/w/${workspaceId}/p/${result.firstPageId}`);
      }
    } catch {
      toast.error("Import failed partway — some pages may already be in the sidebar.");
      qc.invalidateQueries({ queryKey: ["pages", workspaceId] });
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
      if (folderInput.current) folderInput.current.value = "";
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            disabled={busy}
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Import className="size-4" />}
            {busy ? "Importing…" : "Import"}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" side="top" className="w-56">
          <DropdownMenuItem onClick={() => fileInput.current?.click()}>
            <FileUp className="size-4" />
            Markdown files (.md)
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => folderInput.current?.click()}>
            <FolderUp className="size-4" />
            Folder (vault) of markdown
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <input
        ref={fileInput}
        type="file"
        accept=".md,text/markdown"
        multiple
        hidden
        onChange={(e) => handleFiles(e.target.files)}
      />
      <input
        ref={folderInput}
        type="file"
        hidden
        // Non-standard but universal: lets the user pick a whole folder (e.g. a Reclaim vault).
        {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
        onChange={(e) => handleFiles(e.target.files)}
      />
    </>
  );
}
