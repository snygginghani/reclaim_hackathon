"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { BookOpenText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useMe } from "@/hooks/use-auth";
import { useAcceptInvite, useInvitePreview } from "@/hooks/use-workspaces";
import { LoadingScreen } from "@/components/loading-screen";

export default function JoinPage({ params }: { params: Promise<{ inviteId: string }> }) {
  const { inviteId } = use(params);
  const router = useRouter();
  const me = useMe();
  const preview = useInvitePreview(inviteId);
  const accept = useAcceptInvite();

  if (preview.isPending) return <LoadingScreen />;

  if (preview.isError) {
    return (
      <Shell>
        <h1 className="text-xl font-semibold">This invite is no longer valid</h1>
        <p className="text-sm text-muted-foreground">
          Ask for a fresh link, or sign in to your own workspaces.
        </p>
        <Button variant="outline" onClick={() => router.push("/")}>
          Go to Lore
        </Button>
      </Shell>
    );
  }

  const join = async () => {
    const ws = await accept.mutateAsync(inviteId);
    window.localStorage.setItem("lore:last-workspace", ws.id);
    router.replace(`/w/${ws.id}`);
  };

  return (
    <Shell>
      <div className="text-4xl">{preview.data.workspace_icon ?? "🧠"}</div>
      <h1 className="text-xl font-semibold">
        Join “{preview.data.workspace_name}” as {preview.data.role}
      </h1>
      {me.data ? (
        <Button onClick={join} disabled={accept.isPending}>
          {accept.isPending && <Loader2 className="size-4 animate-spin" />}
          Join workspace
        </Button>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">Sign in or create an account to join.</p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => router.push(`/login?next=${encodeURIComponent(`/join/${inviteId}`)}`)}
            >
              Sign in
            </Button>
            <Button
              onClick={() => router.push(`/register?next=${encodeURIComponent(`/join/${inviteId}`)}`)}
            >
              Create account
            </Button>
          </div>
        </>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        className="flex w-full max-w-sm flex-col items-center gap-4 text-center"
      >
        <div className="mb-2 flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <BookOpenText className="size-5" aria-hidden />
        </div>
        {children}
      </motion.div>
    </main>
  );
}
