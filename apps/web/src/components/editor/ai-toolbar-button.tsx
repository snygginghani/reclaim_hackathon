"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useBlockNoteEditor } from "@blocknote/react";
import { Languages, Loader2, Sparkles, Wand2 } from "lucide-react";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { sseStream } from "@/lib/sse";

const ACTIONS = [
  { action: "improve", label: "Improve writing" },
  { action: "fix", label: "Fix spelling & grammar" },
  { action: "shorten", label: "Make shorter" },
  { action: "lengthen", label: "Make longer" },
  { action: "summarize", label: "Summarize" },
] as const;

const TONES = ["professional", "casual", "confident", "friendly", "academic"];
const LANGUAGES = ["Spanish", "French", "German", "Arabic", "Japanese", "Chinese"];

/** Custom formatting-toolbar button: rewrites the selected text with AI and
 * replaces it in place. Streams the result through the Tiptap editor. */
export function AiToolbarButton() {
  const editor = useBlockNoteEditor();
  const params = useParams<{ workspaceId: string }>();
  const [busy, setBusy] = useState(false);

  const run = async (action: string, arg = "") => {
    const text = editor.getSelectedText();
    if (!text.trim()) {
      toast.info("Select some text first");
      return;
    }
    setBusy(true);
    try {
      let out = "";
      for await (const ev of sseStream<{ type: string; text?: string; error?: string }>(
        "/api/ai/rewrite",
        { workspace_id: params.workspaceId, text, action, arg }
      )) {
        if (ev.type === "error") throw new Error(ev.error);
        if (ev.type === "text" && ev.text) out += ev.text;
      }
      if (!out.trim()) throw new Error("No result");
      // Replace the current selection with the rewritten text.
      editor._tiptapEditor.commands.insertContent(out.trim());
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Rewrite failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="flex h-8 items-center gap-1 rounded px-2 text-sm font-medium text-ai transition-colors hover:bg-ai-soft"
          title="Ask AI"
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          AI
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-52">
        <DropdownMenuLabel className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Wand2 className="size-3.5" />
          Rewrite selection
        </DropdownMenuLabel>
        {ACTIONS.map((a) => (
          <DropdownMenuItem key={a.action} onClick={() => run(a.action)}>
            {a.label}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            <Sparkles className="size-4" />
            Change tone
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent>
            {TONES.map((t) => (
              <DropdownMenuItem key={t} className="capitalize" onClick={() => run("tone", t)}>
                {t}
              </DropdownMenuItem>
            ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            <Languages className="size-4" />
            Translate
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent>
            {LANGUAGES.map((l) => (
              <DropdownMenuItem key={l} onClick={() => run("translate", l)}>
                {l}
              </DropdownMenuItem>
            ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
