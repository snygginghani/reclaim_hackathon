import { cn } from "@/lib/utils";

/**
 * The Lore brand mark: a rounded hexagon enclosing a hexagram (Star of David /
 * d20 silhouette) with a serif "L" at its heart. Monochrome — inherits
 * `currentColor`, so it reads correctly in both light and dark themes.
 *
 * `variant="badge"` wraps it in the app's rounded-square lockup used on the
 * auth, loading, and join surfaces.
 */
export function LoreMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("size-6", className)}
      role="img"
      aria-label="Lore"
    >
      {/* Outer rounded hexagon */}
      <path
        d="M50 6 L88.1 28 L88.1 72 L50 94 L11.9 72 L11.9 28 Z"
        stroke="currentColor"
        strokeWidth={5}
        strokeLinejoin="round"
      />
      {/* Hexagram — two interlocking triangles */}
      <path
        d="M50 17 L21.42 66.5 L78.58 66.5 Z"
        stroke="currentColor"
        strokeWidth={4.25}
        strokeLinejoin="round"
      />
      <path
        d="M50 83 L78.58 33.5 L21.42 33.5 Z"
        stroke="currentColor"
        strokeWidth={4.25}
        strokeLinejoin="round"
      />
      {/* Serif L */}
      <path
        d="M36 34 H54 V38 H49 V61 H64 V66 H36 V61 H41 V38 H36 Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function LoreBadge({
  className,
  markClassName,
}: {
  className?: string;
  markClassName?: string;
}) {
  return (
    <div
      className={cn(
        "flex size-12 items-center justify-center rounded-xl border border-border/60 bg-card text-foreground shadow-sm",
        className
      )}
    >
      <LoreMark className={cn("size-7", markClassName)} />
    </div>
  );
}
