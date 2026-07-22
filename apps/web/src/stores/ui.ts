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
  paletteOpen: boolean;
  setPaletteOpen: (v: boolean) => void;
  assistantOpen: boolean;
  setAssistantOpen: (v: boolean) => void;
  /**
   * How agent write proposals are handled. "ask" shows an approval card for
   * every change; "auto" applies them as they arrive. Writes always execute
   * client-side, so this stays a client preference — the server keeps proposing
   * either way and never mutates the workspace itself.
   */
  agentWrites: "ask" | "auto";
  setAgentWrites: (v: "ask" | "auto") => void;
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
      paletteOpen: false,
      setPaletteOpen: (v) => set({ paletteOpen: v }),
      assistantOpen: false,
      setAssistantOpen: (v) => set({ assistantOpen: v }),
      agentWrites: "ask", // safe default: nothing changes without a click
      setAgentWrites: (v) => set({ agentWrites: v }),
    }),
    {
      name: "lore:ui",
      partialize: (s) => ({
        expanded: s.expanded,
        sidebarCollapsed: s.sidebarCollapsed,
        assistantOpen: s.assistantOpen,
        agentWrites: s.agentWrites,
      }),
    }
  )
);
