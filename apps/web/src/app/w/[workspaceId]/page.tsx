"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { FileText, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/hooks/use-auth";
import { useCreatePage, usePages } from "@/hooks/use-pages";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Working late";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function WorkspaceHome({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = use(params);
  const router = useRouter();
  const me = useMe();
  const pages = usePages(workspaceId);
  const createPage = useCreatePage(workspaceId);

  const recent = (pages.data ?? [])
    .slice()
    .sort((a, b) => +new Date(b.updated_at) - +new Date(a.updated_at))
    .slice(0, 8);

  const newPage = async () => {
    try {
      const page = await createPage.mutateAsync({});
      router.push(`/w/${workspaceId}/p/${page.id}`);
    } catch {
      toast.error("Couldn’t create the page");
    }
  };

  return (
    <div className="mx-auto w-full max-w-[720px] flex-1 px-6 py-16">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      >
        <h1 className="text-3xl font-bold tracking-tight">
          {greeting()}
          {me.data ? `, ${me.data.name.split(" ")[0]}` : ""}.
        </h1>

        <section className="mt-10">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Recently updated
          </h2>

          {pages.isPending ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-24 rounded-lg" />
              ))}
            </div>
          ) : recent.length > 0 ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {recent.map((p, i) => (
                <motion.button
                  key={p.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03, duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                  onClick={() => router.push(`/w/${workspaceId}/p/${p.id}`)}
                  className="group flex h-24 flex-col justify-between rounded-lg border bg-card p-3 text-left shadow-xs transition-all hover:-translate-y-0.5 hover:shadow-sm"
                >
                  <span className="text-xl">
                    {p.icon ?? <FileText className="size-5 text-muted-foreground" />}
                  </span>
                  <span className="line-clamp-2 text-sm font-medium">
                    {p.title || "Untitled"}
                  </span>
                </motion.button>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed p-8">
              <p className="text-sm text-muted-foreground">
                This workspace is empty. Create your first page — meeting notes, a project plan,
                anything.
              </p>
              <Button onClick={newPage} disabled={createPage.isPending}>
                <Plus className="size-4" />
                New page
              </Button>
            </div>
          )}
        </section>
      </motion.div>
    </div>
  );
}
