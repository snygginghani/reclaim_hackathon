"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  CellValue,
  Database,
  DbProperty,
  DbRow,
  DbView,
  Page,
  PropertyType,
  ViewConfig,
  ViewType,
} from "@/lib/types";

const dbKey = (id: string) => ["database", id] as const;
const rowsKey = (id: string) => ["database", id, "rows"] as const;

export function useDatabase(pageId: string, enabled = true) {
  return useQuery({
    queryKey: dbKey(pageId),
    queryFn: () => api<Database>(`/api/databases/${pageId}`),
    enabled,
  });
}

export function useRows(pageId: string, enabled = true) {
  return useQuery({
    queryKey: rowsKey(pageId),
    queryFn: () => api<DbRow[]>(`/api/databases/${pageId}/rows`),
    enabled,
  });
}

export function useRowContext(rowId: string, enabled = true) {
  return useQuery({
    queryKey: ["row-context", rowId],
    queryFn: () => api<Database>(`/api/databases/rows/${rowId}/context`),
    enabled,
  });
}

export function useCreateDatabase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { workspace_id: string; parent_id?: string | null; title?: string }) =>
      api<Database>("/api/databases", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (_d, vars) =>
      qc.invalidateQueries({ queryKey: ["pages", vars.workspace_id] }),
  });
}

export function useCreateProperty(pageId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; type: PropertyType; options?: DbProperty["options"] }) =>
      api<DbProperty>(`/api/databases/${pageId}/properties`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: dbKey(pageId) }),
  });
}

export function usePatchProperty(pageId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string;
      name?: string;
      type?: PropertyType;
      options?: DbProperty["options"];
      position?: number;
    }) =>
      api<DbProperty>(`/api/databases/${pageId}/properties/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: dbKey(pageId) }),
  });
}

export function useDeleteProperty(pageId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<void>(`/api/databases/${pageId}/properties/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: dbKey(pageId) }),
  });
}

export function useCreateView(pageId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; type: ViewType }) =>
      api<DbView>(`/api/databases/${pageId}/views`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: dbKey(pageId) }),
  });
}

export function usePatchView(pageId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; config?: ViewConfig }) =>
      api<DbView>(`/api/databases/${pageId}/views/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    // Optimistic: filter/sort tweaks feel instant.
    onMutate: async ({ id, config }) => {
      if (!config) return {};
      await qc.cancelQueries({ queryKey: dbKey(pageId) });
      const prev = qc.getQueryData<Database>(dbKey(pageId));
      if (prev) {
        qc.setQueryData(dbKey(pageId), {
          ...prev,
          views: prev.views.map((v) => (v.id === id ? { ...v, config } : v)),
        });
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(dbKey(pageId), ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: dbKey(pageId) }),
  });
}

export function useDeleteView(pageId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<void>(`/api/databases/${pageId}/views/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: dbKey(pageId) }),
  });
}

export function useCreateRow(pageId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { title?: string; values?: Record<string, CellValue> }) =>
      api<DbRow>(`/api/databases/${pageId}/rows`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: rowsKey(pageId) }),
  });
}

export function usePatchRowValues(pageId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ rowId, values }: { rowId: string; values: Record<string, CellValue | null> }) =>
      api<DbRow>(`/api/databases/${pageId}/rows/${rowId}/values`, {
        method: "PATCH",
        body: JSON.stringify({ values }),
      }),
    // Optimistic cell edits.
    onMutate: async ({ rowId, values }) => {
      await qc.cancelQueries({ queryKey: rowsKey(pageId) });
      const prev = qc.getQueryData<DbRow[]>(rowsKey(pageId));
      if (prev) {
        qc.setQueryData(
          rowsKey(pageId),
          prev.map((r) => {
            if (r.id !== rowId) return r;
            const next = { ...r.values };
            for (const [k, v] of Object.entries(values)) {
              if (v === null) delete next[k];
              else next[k] = v;
            }
            return { ...r, values: next };
          })
        );
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(rowsKey(pageId), ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: rowsKey(pageId) }),
  });
}

export function useRenameRow(pageId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ rowId, title }: { rowId: string; title: string }) =>
      api<Page>(`/api/pages/${rowId}`, { method: "PATCH", body: JSON.stringify({ title }) }),
    onMutate: async ({ rowId, title }) => {
      await qc.cancelQueries({ queryKey: rowsKey(pageId) });
      const prev = qc.getQueryData<DbRow[]>(rowsKey(pageId));
      if (prev) {
        qc.setQueryData(
          rowsKey(pageId),
          prev.map((r) => (r.id === rowId ? { ...r, title } : r))
        );
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(rowsKey(pageId), ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: rowsKey(pageId) }),
  });
}

export function useDeleteRow(pageId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rowId: string) =>
      api<void>(`/api/databases/${pageId}/rows/${rowId}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: rowsKey(pageId) }),
  });
}
