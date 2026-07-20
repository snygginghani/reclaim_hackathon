"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiState {
  /** Expanded page ids in the sidebar tree, across workspaces. */
  expanded: Record<string, boolean>;
  toggleExpanded: (pageId: string) => void;
  setExpanded: (pageId: string, value: boolean) => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (v: boolean) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      expanded: {},
      toggleExpanded: (pageId) =>
        set((s) => ({ expanded: { ...s.expanded, [pageId]: !s.expanded[pageId] } })),
      setExpanded: (pageId, value) =>
        set((s) => ({ expanded: { ...s.expanded, [pageId]: value } })),
      sidebarCollapsed: false,
      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
    }),
    { name: "lore:ui" }
  )
);
