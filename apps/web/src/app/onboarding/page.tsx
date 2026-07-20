"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, Smile } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmojiPicker } from "@/components/emoji-picker";
import { useCreateWorkspace } from "@/hooks/use-workspaces";
import { useMe } from "@/hooks/use-auth";

export default function OnboardingPage() {
  const router = useRouter();
  const me = useMe();
  const createWorkspace = useCreateWorkspace();
  const [name, setName] = useState("");
  const [icon, setIcon] = useState<string | null>("🧠");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    try {
      const ws = await createWorkspace.mutateAsync({ name: name.trim(), icon });
      window.localStorage.setItem("lore:last-workspace", ws.id);
      router.replace(`/w/${ws.id}`);
    } catch {
      setError("Could not create the workspace. Please try again.");
    }
  };

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-sm"
      >
        <h1 className="text-2xl font-bold tracking-tight">
          {me.data ? `Welcome, ${me.data.name.split(" ")[0]}.` : "Welcome."}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          A workspace holds your pages, databases, and Lore’s memory. Name your first one.
        </p>

        <form onSubmit={submit} className="mt-8 flex flex-col gap-4">
          <div className="flex gap-2">
            <EmojiPicker value={icon} onSelect={setIcon}>
              <Button
                type="button"
                variant="outline"
                size="icon"
                aria-label="Choose workspace icon"
                className="shrink-0 text-lg"
              >
                {icon ?? <Smile className="size-4 text-muted-foreground" />}
              </Button>
            </EmojiPicker>
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Personal, Acme Inc, Thesis"
              aria-label="Workspace name"
              maxLength={120}
            />
          </div>

          {error && (
            <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          <Button type="submit" disabled={!name.trim() || createWorkspace.isPending}>
            {createWorkspace.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
            Create workspace
          </Button>
        </form>
      </motion.div>
    </main>
  );
}
