import type { Block } from "@blocknote/core";
import { api } from "./api";

export interface Approval {
  tool: string;
  args: Record<string, unknown>;
  preview: { action: string; title: string | null; page_id?: string; summary: string };
}

/** Execute an approved agent proposal through the normal APIs (reusing the
 * frontend markdown→blocks path so the backend never emits BlockNote JSON). */
export async function applyApproval(
  workspaceId: string,
  a: Approval
): Promise<{ pageId?: string }> {
  const { markdownToBlocks } = await import("./markdown");

  if (a.tool === "create_page") {
    const blocks = await markdownToBlocks(String(a.args.content_markdown ?? ""));
    const page = await api<{ id: string }>("/api/pages", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, title: a.args.title ?? "Untitled" }),
    });
    await api(`/api/pages/${page.id}/content`, {
      method: "PUT",
      body: JSON.stringify({ blocks }),
    });
    return { pageId: page.id };
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
