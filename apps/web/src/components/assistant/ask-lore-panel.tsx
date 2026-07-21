"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  BookText,
  Check,
  ChevronDown,
  Database,
  FilePlus2,
  FileText,
  History,
  Loader2,
  MessageSquare,
  Plus,
  Search,
  Send,
  Sparkles,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { LoreMark } from "@/components/lore-mark";
import { Answer, SourceList } from "./answer";
import { applyApproval, type Approval } from "@/lib/agent-apply";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { sseStream } from "@/lib/sse";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  useConversations,
  useDeleteConversation,
  type ChatMessage,
  type Citation,
} from "@/hooks/use-assistant";
import { useUiStore } from "@/stores/ui";
import { useHighlight } from "@/stores/highlight";

const EASE = [0.16, 1, 0.3, 1] as const;

type StreamEvent =
  | { type: "conversation"; id: string }
  | { type: "sources"; sources: Citation[] }
  | { type: "text"; text: string }
  | { type: "tool"; name: string; args: Record<string, unknown> }
  | { type: "approval"; tool: string; args: Record<string, unknown>; preview: Approval["preview"] }
  | { type: "error"; error: string }
  | { type: "done"; citations?: Citation[] };

type ApprovalState = Approval & {
  status: "pending" | "applying" | "applied" | "rejected";
};

type PanelMessage = ChatMessage & {
  tools?: string[];
  approvals?: ApprovalState[];
};

const GENERATORS = [
  { kind: "summary", label: "Summary" },
  { kind: "study_guide", label: "Study guide" },
  { kind: "faq", label: "FAQ" },
  { kind: "outline", label: "Outline" },
] as const;

export function AskLorePanel({ workspaceId }: { workspaceId: string }) {
  const open = useUiStore((s) => s.assistantOpen);
  const setOpen = useUiStore((s) => s.setAssistantOpen);
  const router = useRouter();
  const pathname = usePathname();
  const qc = useQueryClient();
  const requestHighlight = useHighlight((s) => s.request);

  const currentPageId = pathname.match(/\/p\/([0-9a-f-]{8,})/)?.[1] ?? null;

  const [messages, setMessages] = useState<PanelMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"ask" | "agent">("ask");
  const [scope, setScope] = useState<"workspace" | "page">("workspace");
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [streamSources, setStreamSources] = useState<Citation[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const conversations = useConversations(workspaceId, open && showHistory);
  const deleteConversation = useDeleteConversation(workspaceId);

  // Without an open page, workspace scope is the only sensible choice (derived,
  // so we never fight the toggle in an effect).
  const effectiveScope: "workspace" | "page" = currentPageId ? scope : "workspace";

  // Autoscroll to the latest content.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streamText]);

  const onCite = (c: Citation) => {
    if (c.block_ids[0]) requestHighlight(c.page_id, c.block_ids[0]);
    router.push(`/w/${workspaceId}/p/${c.page_id}`);
  };

  const newChat = () => {
    abortRef.current?.abort();
    setMessages([]);
    setConversationId(null);
    setStreamText("");
    setStreaming(false);
  };

  const loadConversation = async (id: string) => {
    setShowHistory(false);
    const msgs = await api<ChatMessage[]>(`/api/ai/conversations/${id}`);
    setMessages(msgs);
    setConversationId(id);
  };

  const send = async (text: string) => {
    if (!text.trim() || streaming) return;
    setMessages((m) => [...m, { role: "user", content: text, citations: [] }]);
    setInput("");
    setStreaming(true);
    setStreamText("");
    setStreamSources([]);
    abortRef.current = new AbortController();
    try {
      if (mode === "agent") await runAgent(text);
      else await runAsk(text);
    } finally {
      setStreaming(false);
      setStreamText("");
      setStreamSources([]);
    }
  };

  const runAsk = async (text: string) => {
    const scopeBody =
      effectiveScope === "page" && currentPageId
        ? { type: "page", page_ids: [currentPageId] }
        : { type: "workspace" };
    let acc = "";
    let used: Citation[] = [];
    try {
      for await (const ev of sseStream<StreamEvent>(
        "/api/ai/chat",
        { workspace_id: workspaceId, message: text, scope: scopeBody, conversation_id: conversationId },
        abortRef.current!.signal
      )) {
        if (ev.type === "conversation") setConversationId(ev.id);
        else if (ev.type === "sources") setStreamSources(ev.sources);
        else if (ev.type === "text") {
          acc += ev.text;
          setStreamText(acc);
        } else if (ev.type === "error") throw new Error(ev.error);
        else if (ev.type === "done") used = ev.citations ?? [];
      }
      setMessages((m) => [...m, { role: "assistant", content: acc, citations: used }]);
      qc.invalidateQueries({ queryKey: ["conversations", workspaceId] });
    } catch (e) {
      appendError(e);
    }
  };

  const runAgent = async (text: string) => {
    let acc = "";
    const tools: string[] = [];
    const approvals: ApprovalState[] = [];
    try {
      for await (const ev of sseStream<StreamEvent>(
        "/api/ai/agent",
        { workspace_id: workspaceId, message: text },
        abortRef.current!.signal
      )) {
        if (ev.type === "text") {
          acc += ev.text;
          setStreamText(acc);
        } else if (ev.type === "tool") {
          tools.push(ev.name);
        } else if (ev.type === "approval") {
          approvals.push({ tool: ev.tool, args: ev.args, preview: ev.preview, status: "pending" });
        } else if (ev.type === "error") throw new Error(ev.error);
      }
      setMessages((m) => [
        ...m,
        { role: "assistant", content: acc, citations: [], tools, approvals },
      ]);
    } catch (e) {
      appendError(e);
    }
  };

  const appendError = (e: unknown) => {
    if (e instanceof DOMException && e.name === "AbortError") return;
    const msg = e instanceof Error ? e.message : "The assistant didn’t respond";
    setMessages((m) => [...m, { role: "assistant", content: `⚠️ ${msg}`, citations: [] }]);
  };

  const decideApproval = async (msgIndex: number, apprIndex: number, approve: boolean) => {
    const setStatus = (status: ApprovalState["status"]) =>
      setMessages((m) =>
        m.map((msg, i) => {
          if (i !== msgIndex || !msg.approvals) return msg;
          const next = msg.approvals.map((a, j) => (j === apprIndex ? { ...a, status } : a));
          return { ...msg, approvals: next };
        })
      );
    if (!approve) {
      setStatus("rejected");
      return;
    }
    const approval = messages[msgIndex]?.approvals?.[apprIndex];
    if (!approval) return;
    setStatus("applying");
    try {
      const { pageId } = await applyApproval(workspaceId, approval);
      setStatus("applied");
      qc.invalidateQueries({ queryKey: ["pages", workspaceId] });
      toast.success(`${approval.preview.action} done`);
      if (pageId) router.push(`/w/${workspaceId}/p/${pageId}`);
    } catch {
      setStatus("pending");
      toast.error("Couldn’t apply that change");
    }
  };

  const generate = async (kind: string, label: string) => {
    const scopeBody =
      effectiveScope === "page" && currentPageId
        ? { type: "page", page_ids: [currentPageId] }
        : { type: "workspace" };
    const toastId = toast.loading(`Generating ${label.toLowerCase()}…`);
    try {
      let md = "";
      for await (const ev of sseStream<StreamEvent>("/api/ai/generate", {
        workspace_id: workspaceId,
        kind,
        scope: scopeBody,
      })) {
        if (ev.type === "text") md += ev.text;
        else if (ev.type === "error") throw new Error(ev.error);
      }
      if (!md.trim()) throw new Error("Nothing was generated");
      const { markdownToBlocks } = await import("@/lib/markdown");
      const blocks = await markdownToBlocks(md.replace(/\[\d+\]/g, "")); // drop citation markers for the page
      const page = await api<{ id: string }>("/api/pages", {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, title: label }),
      });
      await api(`/api/pages/${page.id}/content`, {
        method: "PUT",
        body: JSON.stringify({ blocks }),
      });
      qc.invalidateQueries({ queryKey: ["pages", workspaceId] });
      toast.success(`Created “${label}”`, { id: toastId });
      router.push(`/w/${workspaceId}/p/${page.id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Generation failed", { id: toastId });
    }
  };

  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.aside
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 400, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ duration: 0.22, ease: EASE }}
          className="relative z-20 flex h-dvh shrink-0 flex-col overflow-hidden border-l bg-sidebar"
        >
          <div className="flex w-[400px] flex-1 flex-col overflow-hidden">
            {/* header */}
            <div className="flex items-center gap-2 border-b p-3">
              <LoreMark className="size-5 text-ai" />
              <span className="font-semibold">Ask Lore</span>
              <div className="ml-auto flex items-center gap-0.5">
                <IconBtn label="New chat" onClick={newChat}>
                  <Plus className="size-4" />
                </IconBtn>
                <IconBtn label="History" onClick={() => setShowHistory((v) => !v)} active={showHistory}>
                  <History className="size-4" />
                </IconBtn>
                <IconBtn label="Close" onClick={() => setOpen(false)}>
                  <X className="size-4" />
                </IconBtn>
              </div>
            </div>

            {/* mode + scope */}
            <div className="flex items-center gap-2 border-b px-3 py-2">
              <div className="flex rounded-lg bg-secondary p-0.5">
                <ModeBtn active={mode === "ask"} onClick={() => setMode("ask")} icon={MessageSquare}>
                  Ask
                </ModeBtn>
                <ModeBtn active={mode === "agent"} onClick={() => setMode("agent")} icon={Wand2}>
                  Agent
                </ModeBtn>
              </div>
              {mode === "ask" && (
                <div className="ml-auto flex items-center gap-1">
                  <ScopePill
                    active={effectiveScope === "workspace"}
                    onClick={() => setScope("workspace")}
                  >
                    Workspace
                  </ScopePill>
                  <ScopePill
                    active={effectiveScope === "page"}
                    disabled={!currentPageId}
                    onClick={() => currentPageId && setScope("page")}
                  >
                    This page
                  </ScopePill>
                </div>
              )}
              {mode === "agent" && (
                <span className="ml-auto text-xs text-muted-foreground">Proposes edits you approve</span>
              )}
            </div>

            {showHistory ? (
              <ScrollArea className="flex-1">
                <div className="flex flex-col gap-1 p-2">
                  <span className="px-2 py-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Recent chats
                  </span>
                  {(conversations.data ?? []).map((c) => (
                    <div
                      key={c.id}
                      className="group flex items-center gap-1 rounded-md px-2 py-1.5 text-sm hover:bg-secondary"
                    >
                      <button
                        onClick={() => loadConversation(c.id)}
                        className="min-w-0 flex-1 truncate text-left"
                      >
                        {c.title}
                      </button>
                      <button
                        onClick={() => deleteConversation.mutate(c.id)}
                        aria-label="Delete chat"
                        className="rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  ))}
                  {conversations.isSuccess && conversations.data.length === 0 && (
                    <p className="px-2 py-6 text-center text-sm text-muted-foreground">
                      No chats yet.
                    </p>
                  )}
                </div>
              </ScrollArea>
            ) : (
              <div ref={scrollRef} className="flex-1 overflow-y-auto p-3">
                {messages.length === 0 && !streaming ? (
                  <EmptyState onAsk={send} onGenerate={generate} />
                ) : (
                  <div className="flex flex-col gap-4">
                    {messages.map((m, i) => (
                      <MessageBubble
                        key={i}
                        message={m}
                        onCite={onCite}
                        onDecide={(ai, approve) => decideApproval(i, ai, approve)}
                      />
                    ))}
                    {streaming && (
                      <div className="flex flex-col gap-1">
                        {streamText ? (
                          <Answer content={streamText} citations={streamSources} onCite={onCite} />
                        ) : (
                          <span className="flex items-center gap-2 text-sm text-muted-foreground">
                            <Loader2 className="size-3.5 animate-spin" /> Searching your workspace…
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* input */}
            <div className="border-t p-3">
              <div className="flex items-end gap-2 rounded-xl border bg-card p-1.5 focus-within:border-ai/50">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send(input);
                    }
                  }}
                  rows={1}
                  placeholder={mode === "agent" ? "Tell Lore what to do…" : "Ask about your workspace…"}
                  className="max-h-32 min-h-8 flex-1 resize-none bg-transparent px-2 py-1 text-sm outline-none"
                />
                {streaming ? (
                  <button
                    onClick={() => abortRef.current?.abort()}
                    aria-label="Stop"
                    className="flex size-8 items-center justify-center rounded-lg bg-secondary text-foreground"
                  >
                    <span className="size-2.5 rounded-sm bg-foreground" />
                  </button>
                ) : (
                  <button
                    onClick={() => void send(input)}
                    disabled={!input.trim()}
                    aria-label="Send"
                    className="flex size-8 items-center justify-center rounded-lg bg-ai text-white transition-opacity disabled:opacity-40"
                  >
                    <Send className="size-4" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function MessageBubble({
  message,
  onCite,
  onDecide,
}: {
  message: PanelMessage;
  onCite: (c: Citation) => void;
  onDecide: (approvalIndex: number, approve: boolean) => void;
}) {
  if (message.role === "user") {
    return (
      <div className="ml-6 self-end rounded-xl rounded-br-sm bg-primary px-3 py-2 text-sm text-primary-foreground">
        {message.content}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {message.tools && message.tools.length > 0 && <ToolChips tools={message.tools} />}
      {message.content.trim() && (
        <Answer content={message.content} citations={message.citations} onCite={onCite} />
      )}
      <SourceList citations={message.citations} onCite={onCite} />
      {message.approvals?.map((a, i) => (
        <ApprovalCard key={i} approval={a} onDecide={(approve) => onDecide(i, approve)} />
      ))}
    </div>
  );
}

const TOOL_LABELS: Record<string, string> = {
  search_workspace: "Searched the workspace",
  read_page: "Read a page",
  list_pages: "Listed pages",
};

function ToolChips({ tools }: { tools: string[] }) {
  return (
    <div className="flex flex-wrap gap-1">
      {tools.map((t, i) => (
        <span
          key={i}
          className="flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground"
        >
          <Search className="size-3" />
          {TOOL_LABELS[t] ?? t}
        </span>
      ))}
    </div>
  );
}

const APPROVAL_ICON: Record<string, React.ElementType> = {
  create_page: FilePlus2,
  append_to_page: FileText,
  create_database: Database,
};

function ApprovalCard({
  approval,
  onDecide,
}: {
  approval: ApprovalState;
  onDecide: (approve: boolean) => void;
}) {
  const Icon = APPROVAL_ICON[approval.tool] ?? Wand2;
  return (
    <div
      className={cn(
        "rounded-xl border p-3 transition-colors",
        approval.status === "applied" && "border-success/40 bg-success/5",
        approval.status === "rejected" && "border-border bg-muted/30 opacity-60",
        approval.status === "pending" && "border-ai/30 bg-ai-soft"
      )}
    >
      <div className="flex items-center gap-2">
        <Icon className="size-4 shrink-0 text-ai" />
        <span className="text-sm font-medium">
          {approval.preview.action}
          {approval.preview.title ? `: ${approval.preview.title}` : ""}
        </span>
      </div>
      {approval.preview.summary && (
        <p className="mt-1.5 max-h-32 overflow-y-auto whitespace-pre-wrap rounded-md bg-background/60 p-2 text-xs text-muted-foreground">
          {approval.preview.summary}
        </p>
      )}
      {approval.status === "pending" && (
        <div className="mt-2.5 flex gap-2">
          <button
            onClick={() => onDecide(true)}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-ai px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
          >
            <Check className="size-4" />
            Approve
          </button>
          <button
            onClick={() => onDecide(false)}
            className="flex items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-secondary"
          >
            Reject
          </button>
        </div>
      )}
      {approval.status === "applying" && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" /> Applying…
        </p>
      )}
      {approval.status === "applied" && (
        <p className="mt-2 flex items-center gap-1.5 text-xs font-medium text-success">
          <Check className="size-3.5" /> Applied
        </p>
      )}
      {approval.status === "rejected" && (
        <p className="mt-2 text-xs text-muted-foreground">Rejected</p>
      )}
    </div>
  );
}

function ModeBtn({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
        active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
      )}
    >
      <Icon className="size-3.5" />
      {children}
    </button>
  );
}

function EmptyState({
  onAsk,
  onGenerate,
}: {
  onAsk: (t: string) => void;
  onGenerate: (kind: string, label: string) => void;
}) {
  const suggestions = [
    "Summarize what's in this workspace",
    "What are the open questions across my notes?",
    "What did I decide about the roadmap?",
  ];
  return (
    <div className="flex h-full flex-col items-center justify-center gap-5 px-2 text-center">
      <div className="flex flex-col items-center gap-2">
        <LoreMark className="size-9 text-ai" />
        <p className="max-w-[16rem] text-sm text-muted-foreground">
          Ask anything about your workspace. Every answer cites the exact source.
        </p>
      </div>
      <div className="flex w-full flex-col gap-1.5">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onAsk(s)}
            className="rounded-lg border bg-card px-3 py-2 text-left text-sm transition-colors hover:border-ai/40 hover:bg-ai-soft"
          >
            {s}
          </button>
        ))}
      </div>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground">
            <BookText className="size-4" />
            Generate a document
            <ChevronDown className="size-3.5" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="center">
          <DropdownMenuLabel className="text-xs text-muted-foreground">
            From your sources
          </DropdownMenuLabel>
          {GENERATORS.map((g) => (
            <DropdownMenuItem key={g.kind} onClick={() => onGenerate(g.kind, g.label)}>
              <FileText className="size-4" />
              {g.label}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled className="text-xs text-muted-foreground">
            <Sparkles className="size-3.5" />
            Each becomes a new page
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

function ScopePill({
  active,
  disabled,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
        active ? "bg-ai/15 text-ai" : "text-muted-foreground hover:bg-secondary",
        disabled && "cursor-not-allowed opacity-40"
      )}
    >
      {children}
    </button>
  );
}

function IconBtn({
  label,
  onClick,
  active,
  children,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className={cn(
        "flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
        active && "bg-secondary text-foreground"
      )}
    >
      {children}
    </button>
  );
}
