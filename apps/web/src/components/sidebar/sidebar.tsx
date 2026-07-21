"use client";

import { useState } from "react";
import { PanelLeftClose, PanelLeftOpen, Search, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { WorkspaceSwitcher } from "./workspace-switcher";
import { PageTree } from "./page-tree";
import { UserMenu } from "./user-menu";
import { TrashDialog } from "./trash-dialog";
import { InviteDialog } from "./invite-dialog";
import { ImportButton } from "./import-button";
import { useUiStore } from "@/stores/ui";

const EASE = [0.16, 1, 0.3, 1] as const;

export function Sidebar({ workspaceId }: { workspaceId: string }) {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const setCollapsed = useUiStore((s) => s.setSidebarCollapsed);
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const [trashOpen, setTrashOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);

  return (
    <>
      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 260, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: EASE }}
            className="group/sidebar relative z-20 flex h-dvh shrink-0 flex-col overflow-hidden border-r bg-sidebar text-sidebar-foreground"
          >
            <div className="flex w-[260px] shrink-0 items-center gap-1 p-2">
              <div className="min-w-0 flex-1">
                <WorkspaceSwitcher workspaceId={workspaceId} onInvite={() => setInviteOpen(true)} />
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setCollapsed(true)}
                    aria-label="Collapse sidebar"
                    className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity hover:bg-secondary hover:text-foreground group-hover/sidebar:opacity-100"
                  >
                    <PanelLeftClose className="size-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">
                  Collapse <kbd className="ml-1 font-mono text-[10px]">⌘\</kbd>
                </TooltipContent>
              </Tooltip>
            </div>

            <div className="w-[260px] px-2">
              <button
                onClick={() => setPaletteOpen(true)}
                className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                aria-label="Search"
              >
                <Search className="size-4" />
                Search
                <kbd className="ml-auto rounded border bg-secondary px-1 font-mono text-[10px] text-muted-foreground">
                  ⌘K
                </kbd>
              </button>
            </div>

            <ScrollArea className="min-h-0 w-[260px] flex-1 px-2 py-1">
              <PageTree workspaceId={workspaceId} />
            </ScrollArea>

            <div className="w-[260px] border-t p-2">
              <Link
                href={`/w/${workspaceId}/settings/ai`}
                className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <Sparkles className="size-4" />
                AI settings
              </Link>
              <ImportButton workspaceId={workspaceId} />
              <button
                onClick={() => setTrashOpen(true)}
                className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              >
                <Trash2 className="size-4" />
                Trash
              </button>
              <UserMenu />
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {collapsed && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={() => setCollapsed(false)}
              aria-label="Open sidebar"
              className="fixed left-3 top-3 z-30 flex size-8 items-center justify-center rounded-md border bg-card text-muted-foreground shadow-sm transition-colors hover:text-foreground"
            >
              <PanelLeftOpen className="size-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">Open sidebar</TooltipContent>
        </Tooltip>
      )}

      <TrashDialog workspaceId={workspaceId} open={trashOpen} onOpenChange={setTrashOpen} />
      <InviteDialog workspaceId={workspaceId} open={inviteOpen} onOpenChange={setInviteOpen} />
    </>
  );
}
