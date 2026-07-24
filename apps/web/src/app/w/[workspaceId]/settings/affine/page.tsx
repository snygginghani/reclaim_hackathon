"use client";

import { use, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileArchive, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { sseUpload } from "@/lib/sse";

type ImportEvent =
  | { type: "progress"; stage: string; done: number; total: number; label: string }
  | { type: "imported"; pages: number; page_ids: string[] }
  | { type: "done"; pages: number }
  | { type: "error"; error: string };

export default function AffineSettingsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = use(params);
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [migrating, setMigrating] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number; label: string } | null>(
    null
  );
  const [finished, setFinished] = useState<number | null>(null);

  const startMigration = async () => {
    if (!file) return;
    setMigrating(true);
    setFinished(null);
    setProgress({ done: 0, total: 0, label: "Starting…" });
    const toastId = toast.loading("Importing your AFFiNE workspace…");
    const form = new FormData();
    form.append("workspace_id", workspaceId);
    form.append("file", file);
    try {
      for await (const ev of sseUpload<ImportEvent>("/api/affine/import", form)) {
        if (ev.type === "progress") {
          setProgress({ done: ev.done, total: ev.total, label: ev.label });
        } else if (ev.type === "error") {
          throw new Error(ev.error);
        } else if (ev.type === "done") {
          setFinished(ev.pages);
          toast.success(
            `Import complete — ${ev.pages} page${ev.pages === 1 ? "" : "s"} added from your workspace.`,
            { id: toastId }
          );
        }
      }
      qc.invalidateQueries({ queryKey: ["pages", workspaceId] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Import failed", { id: toastId });
    } finally {
      setMigrating(false);
      setProgress(null);
    }
  };

  const pct =
    progress && progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : null;

  return (
    <div className="mx-auto w-full max-w-[720px] flex-1 px-6 py-12">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Migrate from AFFiNE</h1>
        <p className="mt-1 max-w-lg text-sm text-muted-foreground">
          In AFFiNE, export your workspace as a <code>.affine</code> file and upload it here. Your
          pages become native Lore documents — text, headings, lists, to-dos, code, images, and
          links — with cross-page links rewired. Nothing leaves your machine except this one upload.
        </p>
      </header>

      {finished !== null ? (
        <div className="rounded-xl border bg-card p-8 text-center">
          <CheckCircle2 className="mx-auto size-8 text-success" />
          <h2 className="mt-3 text-lg font-semibold">
            Imported {finished} page{finished === 1 ? "" : "s"}
          </h2>
          <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
            Your AFFiNE pages are now in the sidebar. (The edgeless whiteboard canvas isn’t imported.)
          </p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => {
              setFinished(null);
              setFile(null);
            }}
          >
            Import another workspace
          </Button>
        </div>
      ) : (
        <div className="rounded-xl border bg-card p-8">
          {migrating ? (
            <div>
              <div className="mb-2 flex items-center justify-between text-sm text-muted-foreground">
                <span className="truncate pr-3">{progress?.label ?? "Working…"}</span>
                <span className="shrink-0 tabular-nums">
                  {pct !== null ? `${pct}%` : `${progress?.done ?? 0}`}
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full rounded-full bg-primary transition-all"
                  style={{ width: pct !== null ? `${pct}%` : "15%" }}
                />
              </div>
            </div>
          ) : (
            <>
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="flex w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-10 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
              >
                {file ? (
                  <>
                    <FileArchive className="size-6" />
                    <span className="font-medium text-foreground">{file.name}</span>
                    <span>Click to choose a different file</span>
                  </>
                ) : (
                  <>
                    <Upload className="size-6" />
                    <span>Choose your .affine file</span>
                  </>
                )}
              </button>
              <input
                ref={inputRef}
                type="file"
                accept=".affine"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <div className="mt-4">
                <Button disabled={!file} onClick={startMigration}>
                  <Upload className="size-4" />
                  Start import
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
