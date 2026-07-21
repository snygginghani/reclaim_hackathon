"use client";

import { LoreMark } from "@/components/lore-mark";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useUiStore } from "@/stores/ui";

/** Floating button that opens Ask Lore. Hidden while the panel is open. */
export function AssistantToggle() {
  const open = useUiStore((s) => s.assistantOpen);
  const setOpen = useUiStore((s) => s.setAssistantOpen);
  if (open) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={() => setOpen(true)}
          aria-label="Ask Lore"
          className="fixed bottom-5 right-5 z-30 flex size-12 items-center justify-center rounded-full border border-ai/30 bg-card text-ai shadow-lg transition-all hover:scale-105 hover:border-ai/60"
        >
          <LoreMark className="size-6" />
        </button>
      </TooltipTrigger>
      <TooltipContent side="left">
        Ask Lore <kbd className="ml-1 font-mono text-[10px]">⌘J</kbd>
      </TooltipContent>
    </Tooltip>
  );
}
