"use client";

import { useRouter } from "next/navigation";
import { Check, ChevronsUpDown, Plus, UserPlus } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useWorkspaces } from "@/hooks/use-workspaces";
import { cn } from "@/lib/utils";

export function WorkspaceSwitcher({
  workspaceId,
  onInvite,
}: {
  workspaceId: string;
  onInvite: () => void;
}) {
  const router = useRouter();
  const workspaces = useWorkspaces();
  const current = workspaces.data?.find((w) => w.id === workspaceId);

  const switchTo = (id: string) => {
    window.localStorage.setItem("lore:last-workspace", id);
    router.push(`/w/${id}`);
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="flex h-9 w-full items-center gap-2 rounded-md px-2 text-sm font-semibold transition-colors hover:bg-secondary"
          aria-label="Switch workspace"
        >
          <span className="flex size-5 items-center justify-center rounded bg-primary/10 text-sm">
            {current?.icon ?? current?.name?.[0]?.toUpperCase() ?? "…"}
          </span>
          <span className="min-w-0 flex-1 truncate text-left">{current?.name ?? "Workspace"}</span>
          <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-64" align="start">
        <DropdownMenuLabel className="text-xs text-muted-foreground">
          Workspaces
        </DropdownMenuLabel>
        {(workspaces.data ?? []).map((w) => (
          <DropdownMenuItem key={w.id} onClick={() => switchTo(w.id)}>
            <span className="flex size-5 items-center justify-center rounded bg-primary/10 text-sm">
              {w.icon ?? w.name[0]?.toUpperCase()}
            </span>
            <span className="min-w-0 flex-1 truncate">{w.name}</span>
            <Check className={cn("size-4", w.id !== workspaceId && "invisible")} />
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onInvite}>
          <UserPlus className="size-4" />
          Invite members
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => router.push("/onboarding")}>
          <Plus className="size-4" />
          New workspace
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
