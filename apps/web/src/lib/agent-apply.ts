import type { Block } from "@blocknote/core";
import { api } from "./api";

export interface Approval {
  tool: string;
  args: Record<string, unknown>;
  preview: { action: string; title: string | null; page_id?: string; summary: string };
}

/**
 * Models like to open the body with an H1 repeating the page title. In Lore the
 * title lives outside the document, so that renders as a duplicate heading —
 * drop it when it matches.
 */
function stripDuplicateTitle(markdown: string, title: string): string {
  const norm = (s: string) => s.replace(/[^\p{L}\p{N}]+/gu, "").toLowerCase();
  const match = markdown.match(/^\s*#\s+(.+?)\s*(?:\n|$)/);
  if (!match || !norm(title) || norm(match[1]) !== norm(title)) return markdown;
  return markdown.slice(match[0].length).replace(/^\s*\n/, "");
}

/** Execute an approved agent proposal through the normal APIs (reusing the
 * frontend markdown→blocks path so the backend never emits BlockNote JSON). */
export async function applyApproval(
  workspaceId: string,
  a: Approval
): Promise<{ pageId?: string }> {
  const { markdownToBlocks } = await import("./markdown");

  if (a.tool === "create_page") {
    const title = String(a.args.title ?? "Untitled");
    const blocks = await markdownToBlocks(
      stripDuplicateTitle(String(a.args.content_markdown ?? ""), title)
    );
    const page = await api<{ id: string }>("/api/pages", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, title }),
    });
    await api(`/api/pages/${page.id}/content`, {
      method: "PUT",
      body: JSON.stringify({ blocks }),
    });
    return { pageId: page.id };
  }

  if (a.tool === "update_page") {
    const pageId = String(a.args.page_id);
    const newTitle = a.args.title ? String(a.args.title) : null;
    // Fall back to the page's existing title so the H1 strip still applies on a
    // plain rewrite (no rename).
    const title =
      newTitle ?? (await api<{ title: string }>(`/api/pages/${pageId}`)).title ?? "";
    const blocks = await markdownToBlocks(
      stripDuplicateTitle(String(a.args.content_markdown ?? ""), title)
    );
    if (newTitle) {
      await api(`/api/pages/${pageId}`, {
        method: "PATCH",
        body: JSON.stringify({ title: newTitle }),
      });
    }
    await api(`/api/pages/${pageId}/content`, {
      method: "PUT",
      body: JSON.stringify({ blocks }),
    });
    return { pageId };
  }

  if (a.tool === "append_to_page") {
    const pageId = String(a.args.page_id);
    const doc = await api<{ blocks: Block[] }>(`/api/pages/${pageId}/content`);
    const added = await markdownToBlocks(String(a.args.content_markdown ?? ""));
    await api(`/api/pages/${pageId}/content`, {
      method: "PUT",
      body: JSON.stringify({ blocks: [...doc.blocks, ...added] }),
    });
    return { pageId };
  }

  if (a.tool === "rename_page") {
    const pageId = String(a.args.page_id);
    await api(`/api/pages/${pageId}`, {
      method: "PATCH",
      body: JSON.stringify({ title: String(a.args.title ?? "Untitled") }),
    });
    return { pageId };
  }

  if (a.tool === "trash_pages") {
    const ids = Array.isArray(a.args.page_ids) ? (a.args.page_ids as string[]) : [];
    // Soft delete — the same endpoint the sidebar uses, so these land in Trash
    // and stay restorable.
    for (const id of ids) {
      await api(`/api/pages/${id}`, { method: "DELETE" });
    }
    return {};
  }

  if (a.tool === "create_database") {
    const db = await api<{ page: { id: string } }>("/api/databases", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, title: a.args.title ?? "Untitled" }),
    });
    const columns = Array.isArray(a.args.columns) ? (a.args.columns as string[]) : [];
    for (const name of columns) {
      await api(`/api/databases/${db.page.id}/properties`, {
        method: "POST",
        body: JSON.stringify({ name: String(name), type: "text" }),
      });
    }
    return { pageId: db.page.id };
  }

  throw new Error("Unknown action");
}
