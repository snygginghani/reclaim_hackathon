"use client";

import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import { API_URL } from "./api";

const WS_URL = API_URL.replace(/^http/, "ws") + "/api/collab";

export interface CollabSession {
  ydoc: Y.Doc;
  provider: WebsocketProvider;
  fragment: Y.XmlFragment;
}

interface Entry {
  session: CollabSession;
  refs: number;
  teardown: ReturnType<typeof setTimeout> | null;
}

/**
 * One live collab session per page, shared across mounts. React StrictMode (and
 * fast route flips) unmount/remount instantly, so destroying the provider in a
 * cleanup would hand the remount a dead socket. Contract instead:
 *
 * - `getCollabSession` is render-safe: it creates or returns the session without
 *   refcounting. A freshly created session starts a grace timer so a discarded
 *   render can't leak it forever.
 * - `retainCollabSession` / `releaseCollabSession` are effect-safe and symmetric;
 *   the last release schedules a deferred destroy that a quick re-retain cancels.
 */
const sessions = new Map<string, Entry>();

const TEARDOWN_DELAY_MS = 2000;

function scheduleTeardown(pageId: string, entry: Entry): void {
  if (entry.teardown) clearTimeout(entry.teardown);
  entry.teardown = setTimeout(() => {
    const current = sessions.get(pageId);
    if (!current || current.refs > 0) return;
    sessions.delete(pageId);
    current.session.provider.destroy();
    current.session.ydoc.destroy();
  }, TEARDOWN_DELAY_MS);
}

export function getCollabSession(pageId: string): CollabSession {
  let entry = sessions.get(pageId);
  if (!entry) {
    const ydoc = new Y.Doc();
    const provider = new WebsocketProvider(WS_URL, pageId, ydoc, { connect: true });
    entry = {
      session: { ydoc, provider, fragment: ydoc.getXmlFragment("document-store") },
      refs: 0,
      teardown: null,
    };
    sessions.set(pageId, entry);
    scheduleTeardown(pageId, entry); // grace period until someone retains
    if (process.env.NODE_ENV === "development") {
      (window as unknown as Record<string, unknown>).__loreCollabSessions = sessions;
    }
  }
  return entry.session;
}

export function retainCollabSession(pageId: string): void {
  const entry = sessions.get(pageId);
  if (!entry) return;
  entry.refs++;
  if (entry.teardown) {
    clearTimeout(entry.teardown);
    entry.teardown = null;
  }
}

export function releaseCollabSession(pageId: string): void {
  const entry = sessions.get(pageId);
  if (!entry) return;
  entry.refs = Math.max(0, entry.refs - 1);
  if (entry.refs === 0) scheduleTeardown(pageId, entry);
}
