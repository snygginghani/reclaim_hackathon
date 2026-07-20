import type { Page } from "./types";

export interface TreeNode {
  page: Page;
  children: TreeNode[];
}

/** Assemble the flat page list into a sorted tree. Orphans (parent trashed) surface at root. */
export function buildTree(pages: Page[]): TreeNode[] {
  const byId = new Map<string, TreeNode>(pages.map((p) => [p.id, { page: p, children: [] }]));
  const roots: TreeNode[] = [];
  for (const node of byId.values()) {
    const parent = node.page.parent_id ? byId.get(node.page.parent_id) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  const sort = (nodes: TreeNode[]) => {
    nodes.sort((a, b) => a.page.position - b.page.position);
    nodes.forEach((n) => sort(n.children));
  };
  sort(roots);
  return roots;
}

export interface FlatNode {
  page: Page;
  depth: number;
  hasChildren: boolean;
}

/** Depth-first flatten of the *visible* tree (children of collapsed nodes omitted). */
export function flattenVisible(roots: TreeNode[], expanded: Set<string>): FlatNode[] {
  const out: FlatNode[] = [];
  const walk = (nodes: TreeNode[], depth: number) => {
    for (const n of nodes) {
      out.push({ page: n.page, depth, hasChildren: n.children.length > 0 });
      if (n.children.length > 0 && expanded.has(n.page.id)) walk(n.children, depth + 1);
    }
  };
  walk(roots, 0);
  return out;
}

export interface DropProjection {
  parentId: string | null;
  afterId: string | null;
  depth: number;
}

/**
 * dnd-kit sortable-tree projection: given the flat visible list, the indexes the
 * drag would land between, and the horizontal drag offset, decide the new parent
 * and preceding sibling. Dragging right nests deeper, dragging left un-nests.
 */
export function projectDrop(
  flat: FlatNode[],
  activeId: string,
  overIndex: number,
  offsetX: number,
  indentWidth: number
): DropProjection {
  const activeIndex = flat.findIndex((f) => f.page.id === activeId);
  if (activeIndex === -1) return { parentId: null, afterId: null, depth: 0 };

  // The list as it would look with the active row lifted out and re-inserted.
  const without = flat.filter((f) => f.page.id !== activeId);
  const insertAt = Math.min(Math.max(overIndex, 0), without.length);
  const prev = without[insertAt - 1];
  const next = without[insertAt];

  const dragDepth = Math.round(offsetX / indentWidth);
  const projected = (flat[activeIndex]?.depth ?? 0) + dragDepth;
  const maxDepth = prev ? prev.depth + 1 : 0;
  const minDepth = next ? next.depth : 0;
  const depth = Math.min(Math.max(projected, minDepth), maxDepth);

  // Parent: nearest earlier node one level up. After: nearest earlier node at same depth.
  let parentId: string | null = null;
  let afterId: string | null = null;
  for (let i = insertAt - 1; i >= 0; i--) {
    if (without[i].depth === depth - 1) {
      parentId = without[i].page.id;
      break;
    }
    if (without[i].depth < depth - 1) break;
  }
  for (let i = insertAt - 1; i >= 0; i--) {
    if (without[i].depth === depth) {
      const candidateParent = findParentAtDepth(without, i, depth - 1);
      if (candidateParent === parentId) afterId = without[i].page.id;
      break;
    }
    if (without[i].depth < depth) break;
  }
  return { parentId, afterId, depth };
}

function findParentAtDepth(flat: FlatNode[], fromIndex: number, depth: number): string | null {
  if (depth < 0) return null;
  for (let i = fromIndex; i >= 0; i--) {
    if (flat[i].depth === depth) return flat[i].page.id;
  }
  return null;
}
