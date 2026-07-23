"use client";

import { use, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, Plug, ShieldCheck, Unplug } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { sseStream } from "@/lib/sse";
import {
  notionStatusKey,
  useConnectNotion,
  useDisconnectNotion,
  useNotionStatus,
} from "@/hooks/use-notion";

type ImportEvent =
  | { type: "progress"; stage: string; done: number; total: number; label: string }
  | { type: "imported"; pages: number; page_ids: string[] }
  | { type: "done"; pages: number; revoked: boolean }
  | { type: "error"; error: string };

const ERROR_MESSAGES: Record<string, string> = {
  invalid_state: "That connection link expired. Please try connecting again.",
  forbidden: "You don’t have permission to connect Notion for this workspace.",
  exchange_failed: "Notion rejected the connection. Please try again.",
  no_token: "Notion didn’t return an access token. Please try again.",
};

export default function NotionSettingsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = use(params);
  const search = useSearchParams();
  const qc = useQueryClient();
  const status = useNotionStatus(workspaceId);
  const connect = useConnectNotion(workspaceId);
  const disconnect = useDisconnectNotion(workspaceId);

  const [migrating, setMigrating] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number; label: string } | null>(
    null
  );
  const [finished, setFinished] = useState<number | null>(null);
  // Surface OAuth callback outcomes exactly once.
  const handledCallback = useRef(false);

  useEffect(() => {
    if (handledCallback.current) return;
    if (search.get("connected")) {
      handledCallback.current = true;
      toast.success("Notion connected");
      qc.invalidateQueries({ queryKey: notionStatusKey(workspaceId) });
    }
    const err = search.get("notion_error");
    if (err) {
      handledCallback.current = true;
      toast.error(ERROR_MESSAGES[err] ?? "Couldn’t connect to Notion");
    }
  }, [search, qc, workspaceId]);

  const startMigration = async () => {
    setMigrating(true);
    setFinished(null);
    setProgress({ done: 0, total: 0, label: "Starting…" });
    const toastId = toast.loading("Migrating from Notion…");
    try {
      for await (const ev of sseStream<ImportEvent>("/api/notion/import", { workspace_id: workspaceId })) {
        if (ev.type === "progress") {
          setProgress({ done: ev.done, total: ev.total, label: ev.label });
        } else if (ev.type === "error") {
          throw new Error(ev.error);
        } else if (ev.type === "done") {
          setFinished(ev.pages);
          toast.success(
            `Migration complete — ${ev.pages} page${ev.pages === 1 ? "" : "s"} imported. Lore no longer has access to your Notion.`,
            { id: toastId }
          );
        }
      }
      qc.invalidateQueries({ queryKey: ["pages", workspaceId] });
      qc.invalidateQueries({ queryKey: notionStatusKey(workspaceId) });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Migration failed", { id: toastId });
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
        <h1 className="text-3xl font-bold tracking-tight">Migrate from Notion</h1>
        <p className="mt-1 max-w-lg text-sm text-muted-foreground">
          Bring your Notion pages and databases into Lore in one pass. Lore connects to Notion only
          for the migration, then automatically revokes its access — nothing keeps reaching back
          into your Notion afterward.
        </p>
      </header>

      {status.isPending ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : !status.data?.configured ? (
        <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          Notion migration isn’t configured on this server yet. An administrator needs to set the
          Notion integration credentials (<code>LORE_NOTION_CLIENT_ID</code> /{" "}
          <code>LORE_NOTION_CLIENT_SECRET</code>).
        </div>
      ) : finished !== null ? (
        <div className="rounded-xl border bg-card p-8 text-center">
          <CheckCircle2 className="mx-auto size-8 text-success" />
          <h2 className="mt-3 text-lg font-semibold">
            Imported {finished} page{finished === 1 ? "" : "s"}
          </h2>
          <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
            Your Notion content is now in the sidebar. Lore has disconnected and no longer has
            access to your Notion workspace.
          </p>
        </div>
      ) : !status.data?.connected ? (
        <div className="rounded-xl border bg-card p-8">
          <div className="flex items-start gap-4">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-secondary">
              <Plug className="size-5" />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-lg font-semibold">Connect your Notion</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                You’ll approve access on Notion and choose which pages to share. Read-only — Lore
                never writes to Notion.
              </p>
              <Button className="mt-4" disabled={connect.isPending} onClick={() => connect.mutate()}>
                {connect.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Plug className="size-4" />
                )}
                Connect Notion
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border bg-card p-8">
          <div className="flex items-center gap-2 text-sm text-success">
            <ShieldCheck className="size-4" />
            Connected{status.data.notion_workspace_name ? ` to ${status.data.notion_workspace_name}` : ""}
          </div>

          {migrating ? (
            <div className="mt-6">
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
              <p className="mt-3 text-sm text-muted-foreground">
                Start the migration to import your pages and databases. This can take a few minutes
                for a large workspace.
              </p>
              <div className="mt-4 flex items-center gap-2">
                <Button onClick={startMigration}>
                  <Plug className="size-4" />
                  Start migration
                </Button>
                <Button
                  variant="outline"
                  disabled={disconnect.isPending}
                  onClick={async () => {
                    try {
                      await disconnect.mutateAsync();
                      toast.success("Disconnected from Notion");
                    } catch {
                      toast.error("Couldn’t disconnect");
                    }
                  }}
                >
                  <Unplug className="size-4" />
                  Disconnect
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
