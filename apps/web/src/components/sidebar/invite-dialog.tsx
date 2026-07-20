"use client";

import { useState } from "react";
import { Check, Copy, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCreateInvite, useMembers } from "@/hooks/use-workspaces";
import { UserAvatar } from "./user-menu";
import { cn } from "@/lib/utils";

export function InviteDialog({
  workspaceId,
  open,
  onOpenChange,
}: {
  workspaceId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const members = useMembers(workspaceId);
  const createInvite = useCreateInvite(workspaceId);
  const [role, setRole] = useState<"editor" | "viewer">("editor");
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const generate = async () => {
    try {
      const invite = await createInvite.mutateAsync({ role });
      setLink(`${window.location.origin}/join/${invite.id}`);
      setCopied(false);
    } catch {
      setLink(null);
    }
  };

  const copy = async () => {
    if (!link) return;
    await navigator.clipboard.writeText(link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(v: boolean) => {
        onOpenChange(v);
        if (!v) setLink(null);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Invite to workspace</DialogTitle>
          <DialogDescription>
            Anyone with the link can join with the role you choose.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="flex gap-1" role="radiogroup" aria-label="Invite role">
            {(["editor", "viewer"] as const).map((r) => (
              <button
                key={r}
                role="radio"
                aria-checked={role === r}
                onClick={() => {
                  setRole(r);
                  setLink(null);
                }}
                className={cn(
                  "flex-1 rounded-md border px-3 py-2 text-sm capitalize transition-colors",
                  role === r
                    ? "border-primary bg-accent font-medium text-accent-foreground"
                    : "text-muted-foreground hover:bg-secondary"
                )}
              >
                {r}
                <span className="mt-0.5 block text-xs font-normal text-muted-foreground">
                  {r === "editor" ? "Can edit pages" : "Read-only access"}
                </span>
              </button>
            ))}
          </div>

          {link ? (
            <div className="flex gap-2">
              <Input readOnly value={link} aria-label="Invite link" onFocus={(e) => e.target.select()} />
              <Button variant="outline" size="icon" onClick={copy} aria-label="Copy invite link">
                {copied ? <Check className="size-4 text-success" /> : <Copy className="size-4" />}
              </Button>
            </div>
          ) : (
            <Button onClick={generate} disabled={createInvite.isPending}>
              {createInvite.isPending && <Loader2 className="size-4 animate-spin" />}
              Generate invite link
            </Button>
          )}

          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Members
            </h3>
            <ul className="flex flex-col gap-1.5">
              {(members.data ?? []).map((m) => (
                <li key={m.user_id} className="flex items-center gap-2 text-sm">
                  <UserAvatar name={m.name} hue={m.avatar_hue} />
                  <span className="min-w-0 flex-1 truncate">{m.name}</span>
                  <span className="text-xs capitalize text-muted-foreground">{m.role}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
