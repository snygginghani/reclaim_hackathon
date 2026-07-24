"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BookOpen, Brain, FileArchive, Menu, PanelLeftClose, PanelLeftOpen, Plug, Search, Shapes, Sparkles, Trash2, X } from "lucide-react";
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

/**
 * `null` until measured. Defaulting to `false` meant a narrow viewport rendered
 * the desktop sidebar on the first paint and tore it down once the effect ran —
 * the sidebar visibly flashed in and vanished. Callers render nothing until this
 * resolves, which costs one frame on desktop and removes the flash.
 */
function useIsMobile() {
  const [mobile, setMobile] = useState<boolean | null>(null);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const update = () => setMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return mobile;
}

export function Sidebar({ workspaceId }: { workspaceId: string }) {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const setCollapsed = useUiStore((s) => s.setSidebarCollapsed);
  const [trashOpen, setTrashOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const isMobile = useIsMobile();

  const inner = (variant: "desktop" | "mobile", widthClass: string) => (
    <SidebarInner
      workspaceId={workspaceId}
      widthClass={widthClass}
      variant={variant}
      onClose={() => (variant === "mobile" ? setMobileOpen(false) : setCollapsed(true))}
      onTrash={() => setTrashOpen(true)}
      onInvite={() => setInviteOpen(true)}
    />
  );

  const dialogs = (
    <>
      <TrashDialog workspaceId={workspaceId} open={trashOpen} onOpenChange={setTrashOpen} />
      <InviteDialog workspaceId={workspaceId} open={inviteOpen} onOpenChange={setInviteOpen} />
    </>
  );

  if (isMobile === null) return null; // avoid painting the wrong variant first

  if (isMobile) {
    return (
      <>
        {!mobileOpen && (
          <button
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
            className="fixed left-3 top-3 z-30 flex size-9 items-center justify-center rounded-md border bg-card text-muted-foreground shadow-sm"
          >
            <Menu className="size-5" />
          </button>
        )}
        <AnimatePresence>
          {mobileOpen && (
            <>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                onClick={() => setMobileOpen(false)}
                className="fixed inset-0 z-40 bg-black/50"
                aria-hidden
              />
              <motion.aside
                initial={{ x: "-100%" }}
                animate={{ x: 0 }}
                exit={{ x: "-100%" }}
                transition={{ duration: 0.24, ease: EASE }}
                // A tap on any navigating link inside the drawer dismisses it.
                onClick={(e) => {
                  if ((e.target as HTMLElement).closest("a")) setMobileOpen(false);
                }}
                className="group/sidebar fixed inset-y-0 left-0 z-50 flex h-dvh w-[280px] flex-col border-r bg-sidebar text-sidebar-foreground shadow-xl"
              >
                {inner("mobile", "w-full")}
              </motion.aside>
            </>
          )}
        </AnimatePresence>
        {dialogs}
      </>
    );
  }

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
            {inner("desktop", "w-[260px]")}
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

      {dialogs}
    </>
  );
}

function SidebarInner({
  workspaceId,
  widthClass,
  variant,
  onClose,
  onTrash,
  onInvite,
}: {
  workspaceId: string;
  widthClass: string;
  variant: "desktop" | "mobile";
  onClose: () => void;
  onTrash: () => void;
  onInvite: () => void;
}) {
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);

  return (
    <>
      <div className={`flex ${widthClass} shrink-0 items-center gap-1 p-2`}>
        <div className="min-w-0 flex-1">
          <WorkspaceSwitcher workspaceId={workspaceId} onInvite={onInvite} />
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={onClose}
              aria-label={variant === "mobile" ? "Close menu" : "Collapse sidebar"}
              className={`flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-opacity hover:bg-secondary hover:text-foreground ${
                variant === "mobile"
                  ? ""
                  : "opacity-0 group-hover/sidebar:opacity-100 focus-visible:opacity-100"
              }`}
            >
              {variant === "mobile" ? (
                <X className="size-4" />
              ) : (
                <PanelLeftClose className="size-4" />
              )}
            </button>
          </TooltipTrigger>
          {variant === "desktop" && (
            <TooltipContent side="right">
              Collapse <kbd className="ml-1 font-mono text-[10px]">⌘\</kbd>
            </TooltipContent>
          )}
        </Tooltip>
      </div>

      <div className={`${widthClass} px-2`}>
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

      <ScrollArea className={`min-h-0 ${widthClass} flex-1 px-2 py-1`}>
        <PageTree workspaceId={workspaceId} />
      </ScrollArea>

      <div className={`${widthClass} border-t p-2`}>
        <Link
          href={`/w/${workspaceId}/settings/ai`}
          className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <Sparkles className="size-4" />
          AI settings
        </Link>
        <Link
          href={`/w/${workspaceId}/settings/memory`}
          className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <Brain className="size-4" />
          Lore’s memory
        </Link>
        <ImportButton workspaceId={workspaceId} />
        <Link
          href={`/w/${workspaceId}/settings/notion`}
          className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <Plug className="size-4" />
          Migrate from Notion
        </Link>
        <Link
          href={`/w/${workspaceId}/settings/confluence`}
          className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <BookOpen className="size-4" />
          Migrate from Confluence
        </Link>
        <Link
          href={`/w/${workspaceId}/settings/obsidian`}
          className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <FileArchive className="size-4" />
          Migrate from Obsidian
        </Link>
        <Link
          href={`/w/${workspaceId}/settings/affine`}
          className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <Shapes className="size-4" />
          Migrate from AFFiNE
        </Link>
        <button
          onClick={onTrash}
          className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <Trash2 className="size-4" />
          Trash
        </button>
        <UserMenu />
      </div>
    </>
  );
}
