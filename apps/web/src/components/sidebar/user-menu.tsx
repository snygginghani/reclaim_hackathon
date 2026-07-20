"use client";

import { useTheme } from "next-themes";
import { LogOut, Monitor, Moon, Sun } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLogout, useMe } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";

export function UserAvatar({ name, hue, size = 24 }: { name: string; hue: number; size?: number }) {
  return (
    <span
      aria-hidden
      className="flex shrink-0 select-none items-center justify-center rounded-full font-semibold text-white"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.45,
        background: `oklch(0.55 0.15 ${hue})`,
      }}
    >
      {name
        .split(" ")
        .slice(0, 2)
        .map((p) => p[0]?.toUpperCase())
        .join("")}
    </span>
  );
}

export function UserMenu() {
  const me = useMe();
  const logout = useLogout();
  const { theme, setTheme } = useTheme();

  if (!me.data) return null;
  const themes = [
    { id: "light", label: "Light", icon: Sun },
    { id: "dark", label: "Dark", icon: Moon },
    { id: "system", label: "System", icon: Monitor },
  ] as const;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="flex h-10 w-full items-center gap-2 rounded-md px-2 text-sm transition-colors hover:bg-secondary"
          aria-label="Account menu"
        >
          <UserAvatar name={me.data.name} hue={me.data.avatar_hue} />
          <span className="min-w-0 flex-1 truncate text-left font-medium">{me.data.name}</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-56" align="start" side="top">
        <DropdownMenuLabel>
          <p className="text-sm font-medium">{me.data.name}</p>
          <p className="text-xs font-normal text-muted-foreground">{me.data.email}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs text-muted-foreground">Theme</DropdownMenuLabel>
        <div className="flex gap-1 px-2 pb-2" role="radiogroup" aria-label="Theme">
          {themes.map((t) => (
            <button
              key={t.id}
              role="radio"
              aria-checked={theme === t.id}
              onClick={() => setTheme(t.id)}
              className={cn(
                "flex flex-1 flex-col items-center gap-1 rounded-md border px-2 py-1.5 text-xs transition-colors",
                theme === t.id
                  ? "border-primary bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-secondary"
              )}
            >
              <t.icon className="size-3.5" />
              {t.label}
            </button>
          ))}
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => logout.mutate()}>
          <LogOut className="size-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
