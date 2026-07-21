"use client";

import { create } from "zustand";

/** Cross-component request to jump to and flash a source block (citation click). */
interface HighlightState {
  pageId: string | null;
  blockId: string | null;
  request: (pageId: string, blockId: string) => void;
  clear: () => void;
}

export const useHighlight = create<HighlightState>((set) => ({
  pageId: null,
  blockId: null,
  request: (pageId, blockId) => set({ pageId, blockId }),
  clear: () => set({ pageId: null, blockId: null }),
}));
