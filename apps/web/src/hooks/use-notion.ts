"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface NotionStatus {
  configured: boolean;
  connected: boolean;
  notion_workspace_name: string | null;
}

export function notionStatusKey(workspaceId: string) {
  return ["notion-status", workspaceId] as const;
}

export function useNotionStatus(workspaceId: string) {
  return useQuery({
    queryKey: notionStatusKey(workspaceId),
    queryFn: () =>
      api<NotionStatus>(`/api/notion/status?workspace_id=${workspaceId}`),
  });
}

/** Fetch the Notion OAuth URL, then hand the browser off to Notion's consent screen. */
export function useConnectNotion(workspaceId: string) {
  return useMutation({
    mutationFn: async () => {
      const { url } = await api<{ url: string }>(
        `/api/notion/authorize-url?workspace_id=${workspaceId}`
      );
      window.location.href = url;
    },
  });
}

export function useDisconnectNotion(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<void>(`/api/notion/disconnect?workspace_id=${workspaceId}`, {
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: notionStatusKey(workspaceId) }),
  });
}
