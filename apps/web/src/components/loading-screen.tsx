import { BookOpenText } from "lucide-react";

export function LoadingScreen() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3" role="status">
      <div className="flex size-12 animate-pulse items-center justify-center rounded-xl bg-primary/90 text-primary-foreground">
        <BookOpenText className="size-6" aria-hidden />
      </div>
      <span className="sr-only">Loading Lore</span>
    </div>
  );
}
