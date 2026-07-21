"use client";

import { use, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Sidebar } from "@/components/sidebar/sidebar";
import { CommandPalette } from "@/components/command-palette";
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

  // ⌘\ / Ctrl+\ toggles the sidebar.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "\\" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        const s = useUiStore.getState();
        s.setSidebarCollapsed(!s.sidebarCollapsed);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (me.isPending) return <LoadingScreen />;
  if (me.isError) return null;

  return (
    <div className="flex min-h-dvh">
      <Sidebar workspaceId={workspaceId} />
      <main className="flex min-w-0 flex-1 flex-col">{children}</main>
      <CommandPalette workspaceId={workspaceId} />
    </div>
  );
}
