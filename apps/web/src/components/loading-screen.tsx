import { LoreMark } from "./lore-mark";

export function LoadingScreen() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3" role="status">
      <LoreMark className="size-12 animate-pulse text-foreground" />
      <span className="sr-only">Loading Lore</span>
    </div>
  );
}
