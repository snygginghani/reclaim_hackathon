"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMe } from "@/hooks/use-auth";
import { useWorkspaces } from "@/hooks/use-workspaces";
import { LoadingScreen } from "@/components/loading-screen";

/** Root router: authed users land in their last (or first) workspace, others sign in. */
export default function Home() {
  const router = useRouter();
  const me = useMe();
  const workspaces = useWorkspaces();

  useEffect(() => {
    if (me.isError) {
      router.replace("/login");
      return;
    }
    if (!workspaces.data) return;
    const lastId =
      typeof window !== "undefined" ? window.localStorage.getItem("lore:last-workspace") : null;
    const target =
      workspaces.data.find((w) => w.id === lastId) ?? workspaces.data[0];
    router.replace(target ? `/w/${target.id}` : "/onboarding");
  }, [me.isError, workspaces.data, router]);

  return <LoadingScreen />;
}
