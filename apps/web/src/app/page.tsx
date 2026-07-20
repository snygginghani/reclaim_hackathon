"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { BookOpenText, CircleCheck, CircleDashed, CircleX } from "lucide-react";
import { api } from "@/lib/api";

interface Health {
  status: string;
  db: boolean;
  pgvector: boolean;
}

/**
 * Phase-0 status page: proves web ↔ api ↔ db connectivity.
 * Replaced by the real workspace shell in Phase 1.
 */
export default function Home() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<Health>("/api/health"),
    refetchInterval: 5000,
  });

  const items = [
    { label: "API", ok: health.isSuccess },
    { label: "Postgres", ok: health.data?.db === true },
    { label: "pgvector", ok: health.data?.pgvector === true },
  ];

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-10 p-8">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="flex flex-col items-center gap-4 text-center"
      >
        <div className="flex size-14 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
          <BookOpenText className="size-7" aria-hidden />
        </div>
        <h1 className="text-4xl font-bold tracking-tight">Lore</h1>
        <p className="max-w-sm text-muted-foreground">
          Your second brain, with a memory. The workspace is under construction — this page checks
          that every part of the stack is alive.
        </p>
      </motion.div>

      <ul className="flex gap-3" aria-label="Stack status">
        {items.map((item, i) => (
          <motion.li
            key={item.label}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 + i * 0.03, duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="flex items-center gap-2 rounded-lg border bg-card px-4 py-2 text-sm font-medium shadow-xs"
          >
            {health.isPending ? (
              <CircleDashed className="size-4 animate-spin text-muted-foreground" aria-hidden />
            ) : item.ok ? (
              <CircleCheck className="size-4 text-success" aria-hidden />
            ) : (
              <CircleX className="size-4 text-destructive" aria-hidden />
            )}
            {item.label}
            <span className="sr-only">
              {health.isPending ? "checking" : item.ok ? "connected" : "unreachable"}
            </span>
          </motion.li>
        ))}
      </ul>
    </main>
  );
}
