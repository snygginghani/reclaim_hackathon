"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Favorite, Page } from "@/lib/types";

const pagesKey = (workspaceId: string) => ["pages", workspaceId] as const;
const trashKey = (workspaceId: string) => ["pages", workspaceId, "trash"] as const;
const favKey = (workspaceId: string) => ["favorites", workspaceId] as const;

export function usePages(workspaceId: string) {
  return useQuery({
    queryKey: pagesKey(workspaceId),
    queryFn: () => api<Page[]>(`/api/pages?workspace_id=${workspaceId}`),
  });
}

export function useTrashedPages(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: trashKey(workspaceId),
    queryFn: () => api<Page[]>(`/api/pages?workspace_id=${workspaceId}&trashed=true`),
    enabled,
  });
}

export function usePage(pageId: string) {
  return useQuery({
    queryKey: ["page", pageId],
    queryFn: () => api<Page>(`/api/pages/${pageId}`),
  });
}

export function useFavorites(workspaceId: string) {
  return useQuery({
    queryKey: favKey(workspaceId),
    queryFn: () => api<Favorite[]>(`/api/pages/favorites/mine?workspace_id=${workspaceId}`),
  });
}

function useInvalidatePages(workspaceId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: pagesKey(workspaceId) });
    qc.invalidateQueries({ queryKey: trashKey(workspaceId) });
    qc.invalidateQueries({ queryKey: favKey(workspaceId) });
  };
}

export function useCreatePage(workspaceId: string) {
  const invalidate = useInvalidatePages(workspaceId);
  return useMutation({
    mutationFn: (body: { parent_id?: string | null; title?: string }) =>
      api<Page>("/api/pages", {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, ...body }),
      }),
    onSuccess: invalidate,
  });
}

export function useUpdatePage(workspaceId: string) {
  const qc = useQueryClient();
  const invalidate = useInvalidatePages(workspaceId);
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; title?: string; icon?: string }) =>
      api<Page>(`/api/pages/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    // Optimistic title/icon: the tree and the open page reflect keystrokes instantly.
    onMutate: async ({ id, ...body }) => {
      await qc.cancelQueries({ queryKey: pagesKey(workspaceId) });
      const prev = qc.getQueryData<Page[]>(pagesKey(workspaceId));
      if (prev) {
        qc.setQueryData(
          pagesKey(workspaceId),
          prev.map((p) => (p.id === id ? { ...p, ...body, icon: body.icon ?? p.icon } : p))
        );
      }
      const prevPage = qc.getQueryData<Page>(["page", id]);
      if (prevPage) qc.setQueryData(["page", id], { ...prevPage, ...body, icon: body.icon ?? prevPage.icon });
      return { prev, prevPage, id };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(pagesKey(workspaceId), ctx.prev);
      if (ctx?.prevPage) qc.setQueryData(["page", ctx.id], ctx.prevPage);
    },
    onSettled: (_d, _e, { id }) => {
      invalidate();
      qc.invalidateQueries({ queryKey: ["page", id] });
    },
  });
}

export function useMovePage(workspaceId: string) {
  const invalidate = useInvalidatePages(workspaceId);
  return useMutation({
    mutationFn: ({
      id,
      parent_id,
      after_id,
    }: {
      id: string;
      parent_id: string | null;
      after_id: string | null;
    }) =>
      api<Page>(`/api/pages/${id}/move`, {
        method: "POST",
        body: JSON.stringify({ parent_id, after_id }),
      }),
    onSettled: invalidate,
  });
}

export function useTrashPage(workspaceId: string) {
  const invalidate = useInvalidatePages(workspaceId);
  return useMutation({
    mutationFn: (id: string) => api<Page>(`/api/pages/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export function useRestorePage(workspaceId: string) {
  const invalidate = useInvalidatePages(workspaceId);
  return useMutation({
    mutationFn: (id: string) => api<Page>(`/api/pages/${id}/restore`, { method: "POST" }),
    onSuccess: invalidate,
  });
}

export function useHardDeletePage(workspaceId: string) {
  const invalidate = useInvalidatePages(workspaceId);
  return useMutation({
    mutationFn: (id: string) => api<void>(`/api/pages/${id}/permanent`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export function useToggleFavorite(workspaceId: string) {
  const invalidate = useInvalidatePages(workspaceId);
  return useMutation({
    mutationFn: async ({ pageId, favorited }: { pageId: string; favorited: boolean }) => {
      if (favorited) await api<void>(`/api/pages/${pageId}/favorite`, { method: "DELETE" });
      else await api<Favorite>(`/api/pages/${pageId}/favorite`, { method: "PUT" });
    },
    onSuccess: invalidate,
  });
}
