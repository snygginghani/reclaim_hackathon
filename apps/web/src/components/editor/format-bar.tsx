"use client";

import { useCallback, useRef, useState } from "react";
import { useActiveStyles, useEditorSelectionChange } from "@blocknote/react";
import type { BlockNoteEditor } from "@blocknote/core";
import { TextSelection } from "prosemirror-state";
import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  CheckSquare,
  ChevronDown,
  Italic,
  List,
  ListOrdered,
  Quote,
  Strikethrough,
  Type,
  Underline,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

/**
 * Always-visible formatting controls.
 *
 * BlockNote ships these actions in a toolbar that only appears once text is
 * selected, so nobody discovered that headings, alignment and checklists exist.
 * This bar exposes the common ones permanently and delegates to the same editor
 * API rather than reimplementing any formatting behaviour.
 */

/** The app uses BlockNote's default schema, so the default generics apply. */
type AnyEditor = BlockNoteEditor;

interface BlockShape {
  type: string;
  props?: Record<string, unknown>;
}

/** Minimal structural view of the ProseMirror instance we need to reach. */
interface PmView {
  state: {
    doc: { content: { size: number } };
    selection: { from: number; to: number };
    tr: { setSelection: (s: unknown) => unknown };
  };
  dispatch: (tr: unknown) => void;
  focus: () => void;
}

const BLOCK_TYPES = [
  { label: "Text", type: "paragraph", icon: Type },
  { label: "Heading 1", type: "heading", level: 1, icon: Type },
  { label: "Heading 2", type: "heading", level: 2, icon: Type },
  { label: "Heading 3", type: "heading", level: 3, icon: Type },
  { label: "Bulleted list", type: "bulletListItem", icon: List },
  { label: "Numbered list", type: "numberedListItem", icon: ListOrdered },
  { label: "Checklist", type: "checkListItem", icon: CheckSquare },
  { label: "Quote", type: "quote", icon: Quote },
] as const;

const ALIGNMENTS = [
  { value: "left", label: "Align left", icon: AlignLeft },
  { value: "center", label: "Align centre", icon: AlignCenter },
  { value: "right", label: "Align right", icon: AlignRight },
] as const;

function currentLabel(block: BlockShape | null): string {
  if (!block) return "Text";
  const level = block.props?.level;
  const match = BLOCK_TYPES.find(
    (b) => b.type === block.type && ("level" in b ? b.level === level : true)
  );
  return match?.label ?? "Text";
}

export function FormatBar({ editor, editable }: { editor: AnyEditor; editable: boolean }) {
  const styles = useActiveStyles(editor) as Record<string, unknown>;
  const [block, setBlock] = useState<BlockShape | null>(null);
  // Pressing a control moves focus out of the editor and collapses its
  // selection before the click handler runs, so the formatting would land on
  // nothing. Remember the last real selection and put it back before acting —
  // more reliable than trying to stop the browser from moving focus at all.
  const saved = useRef<{ from: number; to: number } | null>(null);

  const view = useCallback((): PmView | null => {
    const tt = (editor as unknown as { _tiptapEditor?: { view?: PmView } })._tiptapEditor;
    return tt?.view ?? null;
  }, [editor]);

  const sync = useCallback(() => {
    const v = view();
    if (v) saved.current = { from: v.state.selection.from, to: v.state.selection.to };
    try {
      setBlock(editor.getTextCursorPosition().block as unknown as BlockShape);
    } catch {
      setBlock(null); // no cursor in the document yet
    }
  }, [editor, view]);
  useEditorSelectionChange(sync, editor);

  const restore = useCallback(() => {
    const v = view();
    const s = saved.current;
    if (!v || !s) return;
    const max = v.state.doc.content.size;
    const from = Math.min(s.from, max);
    const to = Math.min(s.to, max);
    v.dispatch(v.state.tr.setSelection(TextSelection.create(v.state.doc as never, from, to)));
    v.focus();
  }, [view]);

  if (!editable) return null;

  const applyBlockType = (item: (typeof BLOCK_TYPES)[number]) => {
    restore();
    editor.updateBlock(editor.getTextCursorPosition().block, {
      type: item.type,
      props: "level" in item ? { level: item.level } : {},
    } as never);
    sync();
  };

  const applyAlignment = (value: string) => {
    restore();
    editor.updateBlock(editor.getTextCursorPosition().block, {
      props: { textAlignment: value },
    } as never);
    sync();
  };

  const toggle = (style: string) => {
    restore();
    editor.toggleStyles({ [style]: true } as never);
  };

  const alignment = (block?.props?.textAlignment as string) ?? "left";

  return (
    <div
      role="toolbar"
      aria-label="Formatting"
      className="sticky top-12 z-10 -mx-1 mb-1 flex flex-wrap items-center gap-0.5 rounded-lg border bg-background/85 px-1 py-1 backdrop-blur-sm"
    >
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            aria-label={`Block type: ${currentLabel(block)}`}
            className="flex h-7 min-w-28 items-center gap-1 rounded-md px-2 text-xs font-medium text-foreground transition-colors hover:bg-secondary"
          >
            {currentLabel(block)}
            <ChevronDown className="ml-auto size-3.5 text-muted-foreground" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          {BLOCK_TYPES.map((item, i) => (
            <div key={item.label}>
              {i === 4 && <DropdownMenuSeparator />}
              <DropdownMenuItem onClick={() => applyBlockType(item)}>
                <item.icon className="size-4" />
                {item.label}
              </DropdownMenuItem>
            </div>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      <Divider />

      <BarButton label="Bold" shortcut="Ctrl+B" active={!!styles.bold} onClick={() => toggle("bold")}>
        <Bold className="size-4" />
      </BarButton>
      <BarButton
        label="Italic"
        shortcut="Ctrl+I"
        active={!!styles.italic}
        onClick={() => toggle("italic")}
      >
        <Italic className="size-4" />
      </BarButton>
      <BarButton
        label="Underline"
        shortcut="Ctrl+U"
        active={!!styles.underline}
        onClick={() => toggle("underline")}
      >
        <Underline className="size-4" />
      </BarButton>
      <BarButton label="Strikethrough" active={!!styles.strike} onClick={() => toggle("strike")}>
        <Strikethrough className="size-4" />
      </BarButton>

      <Divider />

      {ALIGNMENTS.map((a) => (
        <BarButton
          key={a.value}
          label={a.label}
          active={alignment === a.value}
          onClick={() => applyAlignment(a.value)}
        >
          <a.icon className="size-4" />
        </BarButton>
      ))}
    </div>
  );
}

function Divider() {
  return <span aria-hidden className="mx-0.5 h-4 w-px shrink-0 bg-border" />;
}

function BarButton({
  label,
  shortcut,
  active,
  onClick,
  children,
}: {
  label: string;
  shortcut?: string;
  active?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    // Plain button with `title` rather than a Radix Tooltip: the tooltip trigger
    // handles pointer events itself, which interfered with the editor selection.
    <button
      onClick={onClick}
      aria-label={label}
      aria-pressed={!!active}
      title={shortcut ? `${label} (${shortcut})` : label}
      className={cn(
        "flex size-7 shrink-0 items-center justify-center rounded-md transition-colors",
        active
          ? "bg-secondary text-foreground"
          : "text-muted-foreground hover:bg-secondary hover:text-foreground"
      )}
    >
      {children}
    </button>
  );
}
