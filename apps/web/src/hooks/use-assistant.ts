"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface Citation {
  n: number;
  page_id: string;
  page_title: string;
  heading: string | null;
  block_ids: string[];
  snippet: string;
}

export interface ChatMessage {
  id?: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
}

export interface Conversation {
  id: string;
  title: string;
  updated_at: string;
}

export interface MemoryItem {
  id: string;
  content: string;
  kind: "fact" | "preference" | "project";
  source: "auto" | "manual";
  created_at: string;
}

export function useConversations(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: ["conversations", workspaceId],
    queryFn: () => api<Conversation[]>(`/api/ai/conversations?workspace_id=${workspaceId}`),
    enabled,
  });
}

export function useConversationMessages(conversationId: string | null) {
  return useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: () => api<ChatMessage[]>(`/api/ai/conversations/${conversationId}`),
    enabled: !!conversationId,
  });
}

export function useDeleteConversation(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<void>(`/api/ai/conversations/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations", workspaceId] }),
  });
}

export function useMemories(workspaceId: string, enabled = true) {
  return useQuery({
    queryKey: ["memories", workspaceId],
    queryFn: () => api<MemoryItem[]>(`/api/ai/memory?workspace_id=${workspaceId}`),
    enabled,
  });
}

export function useAddMemory(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { content: string; kind?: string }) =>
      api<MemoryItem>(`/api/ai/memory?workspace_id=${workspaceId}`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memories", workspaceId] }),
  });
}

export function useEditMemory(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; content: string; kind: string }) =>
      api<MemoryItem>(`/api/ai/memory/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memories", workspaceId] }),
  });
}

export function useDeleteMemory(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/api/ai/memory/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memories", workspaceId] }),
  });
}

export function useReindex(workspaceId: string) {
  return useMutation({
    mutationFn: () =>
      api<{ chunks: number }>(`/api/ai/reindex?workspace_id=${workspaceId}`, { method: "POST" }),
  });
}
