"use client";

import Link from "next/link";
import { BookOpen, ChevronRight, FileArchive, Import, Plug, Shapes } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const SOURCES = [
  { slug: "notion", label: "Notion", icon: Plug },
  { slug: "confluence", label: "Confluence", icon: BookOpen },
  { slug: "obsidian", label: "Obsidian", icon: FileArchive },
  { slug: "affine", label: "AFFiNE", icon: Shapes },
] as const;

export function MigrateMenu({ workspaceId }: { workspaceId: string }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground data-[state=open]:bg-secondary data-[state=open]:text-foreground"
          aria-label="Migrate from another app"
        >
          <Import className="size-4" />
          <span className="flex-1 text-left">Migrate</span>
          <ChevronRight className="size-3.5 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-52" align="start" side="right">
        <DropdownMenuLabel className="text-xs text-muted-foreground">Import from</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {SOURCES.map((s) => (
          <DropdownMenuItem key={s.slug} asChild>
            <Link href={`/w/${workspaceId}/settings/${s.slug}`}>
              <s.icon className="size-4" />
              {s.label}
            </Link>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
