"use client";

import { BlockNoteEditor, type Block } from "@blocknote/core";
import JSZip from "jszip";
import { api } from "./api";
import type { Page } from "./types";

/** Unmounted BlockNote instance used purely for format conversion. */
function headless(): BlockNoteEditor {
  return BlockNoteEditor.create();
}

export async function blocksToMarkdown(blocks: Block[]): Promise<string> {
  if (blocks.length === 0) return "";
  return headless().blocksToMarkdownLossy(blocks);
}

export async function markdownToBlocks(markdown: string): Promise<Block[]> {
  return headless().tryParseMarkdownToBlocks(markdown);
}

// --- export ---

async function pageMarkdown(page: Page): Promise<string> {
  const doc = await api<{ blocks: Block[] }>(`/api/pages/${page.id}/content`);
  const body = await blocksToMarkdown(doc.blocks);
  // The title lives outside the body in Lore; markdown files carry it as an H1
  // (this is also what makes the Reclaim vault format round-trip).
  const title = page.title || "Untitled";
  return `# ${title}\n\n${body}`.trimEnd() + "\n";
}

function safeName(title: string): string {
  return (title || "Untitled").replace(/[\\/:*?"<>|]/g, "-").slice(0, 120);
}

function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Export a page as `<title>.md`; if it has descendants, export a zip mirroring
 * the subtree as folders of markdown files.
 */
export async function exportPage(page: Page, allPages: Page[]): Promise<void> {
  const children = (parent: string) =>
    allPages
      .filter((p) => p.parent_id === parent)
      .sort((a, b) => a.position - b.position);

  if (children(page.id).length === 0) {
    const md = await pageMarkdown(page);
    download(new Blob([md], { type: "text/markdown" }), `${safeName(page.title)}.md`);
    return;
  }

  const zip = new JSZip();
  const walk = async (p: Page, dir: string): Promise<void> => {
    const kids = children(p.id);
    const md = await pageMarkdown(p);
    if (kids.length === 0) {
      zip.file(`${dir}${safeName(p.title)}.md`, md);
    } else {
      // A page with children becomes a folder + an index file of its own content.
      const sub = `${dir}${safeName(p.title)}/`;
      zip.file(`${sub}${safeName(p.title)}.md`, md);
      for (const k of kids) await walk(k, sub);
    }
  };
  await walk(page, "");
  download(await zip.generateAsync({ type: "blob" }), `${safeName(page.title)}.zip`);
}

// --- import ---

export interface ImportResult {
  created: number;
  firstPageId: string | null;
}

interface ImportFile {
  /** Path segments relative to the import root, e.g. ["notes", "ideas.md"]. */
  segments: string[];
  text: string;
}

/**
 * Import markdown files as pages. Folder structure becomes page nesting.
 * A leading `# Heading` that matches the convention becomes the page title
 * (Reclaim vault files always start with one).
 */
export async function importMarkdownFiles(
  files: File[],
  workspaceId: string,
  parentId: string | null
): Promise<ImportResult> {
  const items: ImportFile[] = [];
  for (const f of files) {
    if (!f.name.toLowerCase().endsWith(".md")) continue;
    const rel = (f.webkitRelativePath || f.name).split("/").filter(Boolean);
    // Drop the shared root folder from folder uploads; skip hidden dirs like .reclaim.
    const segments = rel.length > 1 ? rel.slice(1) : rel;
    if (segments.some((s) => s.startsWith("."))) continue;
    items.push({ segments, text: await f.text() });
  }
  if (items.length === 0) return { created: 0, firstPageId: null };

  const dirPageIds = new Map<string, string>(); // "a/b" -> page id
  let created = 0;
  let firstPageId: string | null = null;

  const ensureDir = async (segments: string[]): Promise<string | null> => {
    if (segments.length === 0) return parentId;
    const key = segments.join("/");
    const existing = dirPageIds.get(key);
    if (existing) return existing;
    const parent = await ensureDir(segments.slice(0, -1));
    const page = await api<Page>("/api/pages", {
      method: "POST",
      body: JSON.stringify({
        workspace_id: workspaceId,
        parent_id: parent,
        title: segments.at(-1),
      }),
    });
    dirPageIds.set(key, page.id);
    created++;
    return page.id;
  };

  for (const item of items.sort((a, b) => a.segments.length - b.segments.length)) {
    const dirs = item.segments.slice(0, -1);
    const fileName = item.segments.at(-1)!.replace(/\.md$/i, "");
    const parent = await ensureDir(dirs);

    let blocks = await markdownToBlocks(item.text);
    let title = fileName;
    // Title convention: a document starting with an H1 keeps it as the page title.
    const first = blocks[0];
    if (first?.type === "heading" && (first.props as { level?: number }).level === 1) {
      const text = (first.content as { text?: string }[] | undefined)
        ?.map((c) => c.text ?? "")
        .join("")
        .trim();
      if (text) {
        title = text;
        blocks = blocks.slice(1);
      }
    }

    const page = await api<Page>("/api/pages", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, parent_id: parent, title }),
    });
    if (blocks.length > 0) {
      await api(`/api/pages/${page.id}/content`, {
        method: "PUT",
        body: JSON.stringify({ blocks }),
      });
    }
    created++;
    firstPageId ??= page.id;
  }

  return { created, firstPageId };
}
