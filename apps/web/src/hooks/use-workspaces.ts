"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Invite, InvitePreview, Member, Workspace } from "@/lib/types";

export function useWorkspaces() {
  return useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api<Workspace[]>("/api/workspaces"),
  });
}

export function useWorkspace(id: string) {
  return useQuery({
    queryKey: ["workspaces", id],
    queryFn: () => api<Workspace>(`/api/workspaces/${id}`),
  });
}

export function useCreateWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; icon?: string | null }) =>
      api<Workspace>("/api/workspaces", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workspaces"] }),
  });
}

export function useMembers(workspaceId: string) {
  return useQuery({
    queryKey: ["workspaces", workspaceId, "members"],
    queryFn: () => api<Member[]>(`/api/workspaces/${workspaceId}/members`),
  });
}

export function useCreateInvite(workspaceId: string) {
  return useMutation({
    mutationFn: (body: { role: "editor" | "viewer" }) =>
      api<Invite>(`/api/workspaces/${workspaceId}/invites`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export function useInvitePreview(inviteId: string) {
  return useQuery({
    queryKey: ["invites", inviteId],
    queryFn: () => api<InvitePreview>(`/api/workspaces/invites/${inviteId}`),
    retry: false,
  });
}

export function useAcceptInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (inviteId: string) =>
      api<Workspace>(`/api/workspaces/invites/${inviteId}/accept`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workspaces"] }),
  });
}
