"use client";

import { use, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar } from "@/components/sidebar/sidebar";
import { CommandPalette } from "@/components/command-palette";
import { AskLorePanel } from "@/components/assistant/ask-lore-panel";
import { AssistantToggle } from "@/components/assistant/assistant-toggle";
import { LoadingScreen } from "@/components/loading-screen";
import { useMe } from "@/hooks/use-auth";
import { useUiStore } from "@/stores/ui";

export default function WorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = use(params);
  const me = useMe();
  const router = useRouter();
  const pathname = usePathname();

  // Auth guard: unauthenticated users go to login and come back here after.
  useEffect(() => {
    if (me.isError) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [me.isError, router, pathname]);

  // Remember the workspace for the root redirect.
  useEffect(() => {
    window.localStorage.setItem("lore:last-workspace", workspaceId);
  }, [workspaceId]);

  // ⌘\ toggles the sidebar; ⌘J toggles Ask Lore.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key === "\\") {
        e.preventDefault();
        const s = useUiStore.getState();
        s.setSidebarCollapsed(!s.sidebarCollapsed);
      } else if (e.key.toLowerCase() === "j") {
        e.preventDefault();
        const s = useUiStore.getState();
        s.setAssistantOpen(!s.assistantOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (me.isPending) return <LoadingScreen />;
  if (me.isError) return null;

  // The shell is pinned to the viewport (h-dvh + overflow-hidden) so only <main>
  // scrolls. Under min-h-dvh the document grew with the page content and the
  // whole window scrolled, dragging both fixed-height sidebars out of view.
  return (
    <div className="flex h-dvh overflow-hidden">
      <Sidebar workspaceId={workspaceId} />
      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">{children}</main>
      <AskLorePanel workspaceId={workspaceId} />
      <AssistantToggle />
      <CommandPalette workspaceId={workspaceId} />
    </div>
  );
}
