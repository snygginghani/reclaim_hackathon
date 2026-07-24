"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface ConfluenceStatus {
  configured: boolean;
  connected: boolean;
  site_name: string | null;
}

export function confluenceStatusKey(workspaceId: string) {
  return ["confluence-status", workspaceId] as const;
}

export function useConfluenceStatus(workspaceId: string) {
  return useQuery({
    queryKey: confluenceStatusKey(workspaceId),
    queryFn: () =>
      api<ConfluenceStatus>(`/api/confluence/status?workspace_id=${workspaceId}`),
  });
}

/** Fetch the Atlassian OAuth URL, then hand the browser off to the consent screen. */
export function useConnectConfluence(workspaceId: string) {
  return useMutation({
    mutationFn: async () => {
      const { url } = await api<{ url: string }>(
        `/api/confluence/authorize-url?workspace_id=${workspaceId}`
      );
      window.location.href = url;
    },
  });
}

export function useDisconnectConfluence(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<void>(`/api/confluence/disconnect?workspace_id=${workspaceId}`, {
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: confluenceStatusKey(workspaceId) }),
  });
}
