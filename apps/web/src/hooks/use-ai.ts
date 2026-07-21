"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface GpuInfo {
  vendor: string;
  name: string;
  vram_gb: number | null;
}

export interface HardwareInfo {
  os: string;
  cpu: string;
  cores: number;
  ram_total_gb: number;
  ram_available_gb: number;
  disk_free_gb: number;
  gpus: GpuInfo[];
}

export interface CandidateModel {
  tag: string;
  label: string;
  params_b: number;
  quality: number;
  disk_gb: number;
  note: string;
}

export interface Fit {
  footprint_gb: number;
  fits_gpu: boolean;
  fits_cpu: boolean;
  fits_disk: boolean;
  speed: "fast" | "ok" | "slow" | "no";
}

export interface Recommendations {
  hardware: HardwareInfo;
  budget: { gpu_gb: number | null; cpu_gb: number; gpu_name: string | null };
  recommendations: { model: CandidateModel; fit: Fit; reasoning: string }[];
  ladder: { model: CandidateModel; fit: Fit }[];
}

export interface AiSettings {
  provider: "ollama" | "openrouter" | null;
  default_model: string | null;
  fast_model: string | null;
  has_openrouter_key: boolean;
}

export interface CatalogModel {
  id: string;
  name: string;
  context_length: number | null;
  prompt_price: string | null;
  completion_price: string | null;
  featured: boolean;
}

export interface Catalog {
  featured: { label: string; id: string }[];
  models: CatalogModel[];
}

export function useAiSettings(workspaceId: string) {
  return useQuery({
    queryKey: ["ai-settings", workspaceId],
    queryFn: () => api<AiSettings>(`/api/ai/settings?workspace_id=${workspaceId}`),
  });
}

export function useSaveAiSettings(workspaceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      provider?: "ollama" | "openrouter";
      default_model?: string;
      fast_model?: string;
      openrouter_key?: string;
    }) =>
      api<AiSettings>(`/api/ai/settings?workspace_id=${workspaceId}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => qc.setQueryData(["ai-settings", workspaceId], data),
  });
}

export function useRecommendations() {
  return useQuery({
    queryKey: ["ai-recommendations"],
    queryFn: () => api<Recommendations>("/api/ai/recommendations"),
    staleTime: 60_000,
  });
}

export function useOllamaStatus() {
  return useQuery({
    queryKey: ["ollama-status"],
    queryFn: () => api<{ running: boolean; models: string[] }>("/api/ai/ollama/status"),
    refetchInterval: 15_000,
  });
}

export function useOpenRouterCatalog(enabled: boolean) {
  return useQuery({
    queryKey: ["openrouter-catalog"],
    queryFn: () => api<Catalog>("/api/ai/openrouter/models"),
    enabled,
    staleTime: 10 * 60_000,
  });
}
