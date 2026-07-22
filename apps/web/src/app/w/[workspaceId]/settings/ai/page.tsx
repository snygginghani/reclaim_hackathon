"use client";

import { use, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Cloud,
  Cpu,
  Download,
  Gauge,
  HardDrive,
  KeyRound,
  Loader2,
  MemoryStick,
  MonitorSmartphone,
  Send,
  Sparkles,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { sseStream } from "@/lib/sse";
import { cn } from "@/lib/utils";
import {
  useAiSettings,
  useOllamaStatus,
  useOpenRouterCatalog,
  useRecommendations,
  useSaveAiSettings,
  type Fit,
  type HardwareInfo,
  type Recommendations,
} from "@/hooks/use-ai";
import { useWorkspace } from "@/hooks/use-workspaces";

export default function AiSettingsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = use(params);
  const search = useSearchParams();
  const isWizard = search.get("setup") === "1";
  const workspace = useWorkspace(workspaceId);
  const settings = useAiSettings();
  const save = useSaveAiSettings();
  const isOwner = workspace.data?.role === "owner";

  const provider = settings.data?.provider ?? null;

  return (
    <div className="mx-auto w-full max-w-[860px] flex-1 px-6 py-12">
      <header className="mb-8">
        {isWizard && (
          <p className="mb-1 text-sm font-medium text-ai">One last step</p>
        )}
        <h1 className="text-3xl font-bold tracking-tight">
          {isWizard ? "Set up Lore’s AI" : "AI settings"}
        </h1>
        <p className="mt-1 max-w-lg text-sm text-muted-foreground">
          Lore can run on a local model — private, free, on this machine — or through
          OpenRouter with your own key. {!isOwner && "Only workspace owners can change this."}
        </p>
      </header>

      {settings.isPending ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <ProviderCard
              icon={MonitorSmartphone}
              title="Local (Ollama)"
              description="Private and free. Lore picks the best model your hardware can run."
              active={provider === "ollama"}
              disabled={!isOwner}
              onClick={() => save.mutate({ provider: "ollama" })}
            />
            <ProviderCard
              icon={Cloud}
              title="Cloud (OpenRouter)"
              description="Frontier models with your own API key. Pay per use."
              active={provider === "openrouter"}
              disabled={!isOwner}
              onClick={() => save.mutate({ provider: "openrouter" })}
            />
          </div>

          <div className="mt-8 flex flex-col gap-8">
            {provider === "ollama" && (
              <LocalSection isOwner={isOwner} />
            )}
            {provider === "openrouter" && (
              <CloudSection isOwner={isOwner} />
            )}
            {provider && settings.data?.default_model && (
              <TestChat workspaceId={workspaceId} />
            )}
          </div>
        </>
      )}
    </div>
  );
}

function ProviderCard({
  icon: Icon,
  title,
  description,
  active,
  disabled,
  onClick,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={cn(
        "flex flex-col gap-1.5 rounded-xl border p-4 text-left transition-all",
        active
          ? "border-primary bg-accent shadow-sm"
          : "hover:border-primary/40 hover:bg-secondary/50",
        disabled && "cursor-not-allowed opacity-60"
      )}
    >
      <span className="flex items-center gap-2 font-semibold">
        <Icon className={cn("size-4", active ? "text-primary" : "text-muted-foreground")} />
        {title}
        {active && <Check className="ml-auto size-4 text-primary" />}
      </span>
      <span className="text-sm text-muted-foreground">{description}</span>
    </button>
  );
}

/* ---------------- local (Ollama) ---------------- */

function LocalSection({ isOwner }: { isOwner: boolean }) {
  const recs = useRecommendations();
  const ollama = useOllamaStatus();
  const settings = useAiSettings();
  const save = useSaveAiSettings();

  if (recs.isPending) return <Skeleton className="h-64 w-full" />;
  if (recs.isError) {
    return <p className="text-sm text-destructive">Couldn’t inspect this machine’s hardware.</p>;
  }
  const { hardware, budget, recommendations, ladder } = recs.data;
  const installed = new Set(ollama.data?.models ?? []);

  return (
    <section className="flex flex-col gap-5">
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Detected on this machine
          </h2>
          <span
            className={cn(
              "flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium",
              ollama.data?.running
                ? "bg-success/15 text-success"
                : "bg-muted-foreground/10 text-muted-foreground"
            )}
          >
            <span
              className={cn(
                "size-1.5 rounded-full",
                ollama.data?.running ? "animate-pulse bg-success" : "bg-muted-foreground"
              )}
            />
            {ollama.data?.running ? "Ollama connected" : "Ollama offline"}
          </span>
        </div>
        <HardwarePanel hardware={hardware} budget={budget} />
        {!ollama.data?.running && (
          <p className="mt-3 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
            Your hardware is detected, but Ollama isn’t running yet. Install it from{" "}
            <a
              href="https://ollama.com/download"
              target="_blank"
              rel="noreferrer noopener"
              className="font-medium text-primary hover:underline"
            >
              ollama.com/download
            </a>{" "}
            — Lore reconnects automatically, then you can install a model in one click.
          </p>
        )}
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Recommended for you
        </h2>
        <div className="grid gap-3 md:grid-cols-3">
          {recommendations.map((r, i) => (
            <div
              key={r.model.tag}
              className={cn(
                "flex flex-col gap-2 rounded-xl border p-4",
                i === 0 && "border-primary/50 bg-accent/60"
              )}
            >
              <div className="flex items-center gap-1.5">
                {i === 0 && <Sparkles className="size-4 text-primary" />}
                <span className="font-semibold">{r.model.label}</span>
                <FitBadge fit={r.fit} />
              </div>
              <p className="flex-1 text-xs leading-relaxed text-muted-foreground">{r.reasoning}</p>
              <InstallButton
                tag={r.model.tag}
                diskGb={r.model.disk_gb}
                installed={installed.has(r.model.tag)}
                canInstall={isOwner && !!ollama.data?.running}
                isDefault={settings.data?.default_model === r.model.tag}
                onUse={() =>
                  save.mutate(
                    i === 0 || r.model.params_b > 4
                      ? { default_model: r.model.tag }
                      : { fast_model: r.model.tag }
                  )
                }
              />
            </div>
          ))}
          {recommendations.length === 0 && (
            <p className="col-span-3 rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
              This machine is too constrained for a local model — use the cloud provider instead.
            </p>
          )}
        </div>
      </div>

      <ModelPicker
        ladder={ladder}
        installedModels={[...installed]}
        gpuBudget={budget.gpu_gb}
        cpuBudget={budget.cpu_gb}
        isOwner={isOwner}
        ollamaRunning={!!ollama.data?.running}
      />
    </section>
  );
}

function Meter({
  value,
  max,
  tone = "primary",
}: {
  value: number;
  max: number;
  tone?: "primary" | "ai" | "muted";
}) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  const bar = { primary: "bg-primary", ai: "bg-ai", muted: "bg-muted-foreground/50" }[tone];
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
      <div className={cn("h-full rounded-full transition-all", bar)} style={{ width: `${pct}%` }} />
    </div>
  );
}

function SpecRow({
  icon: Icon,
  label,
  value,
  children,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  children?: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1.5 px-3.5 py-3">
      <div className="flex items-center gap-2">
        <Icon className={cn("size-4 shrink-0", accent ? "text-primary" : "text-muted-foreground")} />
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </span>
        <span className="ml-auto text-right text-xs tabular-nums text-muted-foreground">{value}</span>
      </div>
      <span className="truncate text-sm font-medium">{children}</span>
    </div>
  );
}

function HardwarePanel({
  hardware,
  budget,
}: {
  hardware: HardwareInfo;
  budget: { gpu_gb: number | null; cpu_gb: number; gpu_name: string | null };
}) {
  const usedRam = hardware.ram_total_gb - hardware.ram_available_gb;
  return (
    <div className="grid gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-2">
      <div className="bg-card">
        <SpecRow
          icon={Cpu}
          label="Processor"
          value={`${hardware.cores_physical}C · ${hardware.cores_logical}T`}
        >
          {hardware.cpu}
        </SpecRow>
      </div>
      <div className="bg-card">
        <SpecRow
          icon={MemoryStick}
          label="Memory"
          value={`${hardware.ram_available_gb} / ${hardware.ram_total_gb} GB free`}
        >
          <span className="text-muted-foreground">System RAM</span>
        </SpecRow>
        <div className="px-3.5 pb-3">
          <Meter value={usedRam} max={hardware.ram_total_gb} tone="muted" />
        </div>
      </div>

      {hardware.gpus.length > 0 ? (
        hardware.gpus.map((g) => (
          <div key={g.name} className="bg-card">
            <SpecRow
              icon={Gauge}
              label={g.kind === "integrated" ? "Integrated GPU" : "Graphics"}
              value={g.vram_gb ? `${g.vram_gb} GB VRAM` : "VRAM unknown"}
              accent={!!g.vram_gb && g.kind === "discrete"}
            >
              {g.name}
            </SpecRow>
            {g.vram_gb ? (
              <div className="px-3.5 pb-3">
                <Meter value={g.vram_gb - (budget.gpu_gb ?? 0)} max={g.vram_gb} tone="primary" />
              </div>
            ) : null}
          </div>
        ))
      ) : (
        <div className="bg-card">
          <SpecRow icon={Gauge} label="Graphics" value="CPU only">
            <span className="text-muted-foreground">No dedicated GPU detected</span>
          </SpecRow>
        </div>
      )}

      <div className="bg-card">
        <SpecRow
          icon={HardDrive}
          label="Storage"
          value={`${hardware.disk_free_gb} GB free`}
        >
          <span className="text-muted-foreground">Available for models</span>
        </SpecRow>
      </div>
    </div>
  );
}

function FitBadge({ fit }: { fit: Fit }) {
  const map = {
    fast: { label: "GPU · fast", cls: "bg-success/15 text-success" },
    ok: { label: "CPU · ok", cls: "bg-warning/15 text-warning" },
    slow: { label: "CPU · slow", cls: "bg-warning/15 text-warning" },
    no: { label: "won’t fit", cls: "bg-destructive/15 text-destructive" },
  } as const;
  const m = map[fit.speed];
  return (
    <span className={cn("ml-auto rounded px-1.5 py-0.5 text-[10px] font-semibold", m.cls)}>
      {m.label}
    </span>
  );
}

function InstallButton({
  tag,
  diskGb,
  installed,
  canInstall,
  isDefault,
  onUse,
}: {
  tag: string;
  diskGb: number;
  installed: boolean;
  canInstall: boolean;
  isDefault: boolean;
  onUse: () => void;
}) {
  const qc = useQueryClient();
  const [progress, setProgress] = useState<number | null>(null);

  const pull = async () => {
    setProgress(0);
    try {
      for await (const event of sseStream<{
        status?: string;
        total?: number;
        completed?: number;
        error?: string;
        done?: boolean;
      }>("/api/ai/ollama/pull", { model: tag })) {
        if (event.error) throw new Error(event.error);
        if (event.total && event.completed !== undefined) {
          setProgress(Math.round((event.completed / event.total) * 100));
        }
        if (event.done) break;
      }
      toast.success(`${tag} installed`);
      qc.invalidateQueries({ queryKey: ["ollama-status"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Download failed");
    } finally {
      setProgress(null);
    }
  };

  if (isDefault) {
    return (
      <span className="flex items-center gap-1 text-xs font-medium text-primary">
        <Check className="size-3.5" /> In use as default
      </span>
    );
  }
  if (installed) {
    return (
      <Button size="sm" variant="outline" onClick={onUse} className="h-7 w-fit text-xs">
        Use this model
      </Button>
    );
  }
  if (progress !== null) {
    return (
      <div className="flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="text-[10px] tabular-nums text-muted-foreground">{progress}%</span>
      </div>
    );
  }
  return (
    <Button
      size="sm"
      variant="outline"
      disabled={!canInstall}
      onClick={pull}
      className="h-7 w-fit text-xs"
    >
      <Download className="size-3.5" />
      Install ({diskGb} GB)
    </Button>
  );
}

function ModelPicker({
  ladder,
  installedModels,
  gpuBudget,
  cpuBudget,
  isOwner,
  ollamaRunning,
}: {
  ladder: Recommendations["ladder"];
  installedModels: string[];
  gpuBudget: number | null;
  cpuBudget: number;
  isOwner: boolean;
  ollamaRunning: boolean;
}) {
  const settings = useAiSettings();
  const save = useSaveAiSettings();
  const budget = gpuBudget ?? cpuBudget;

  return (
    <div>
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
        All models · will it fit? ({budget} GB budget)
      </h2>
      <div className="overflow-hidden rounded-xl border">
        {ladder.map(({ model, fit }) => {
          const pct = Math.min(100, Math.round((fit.footprint_gb / budget) * 100));
          const installed = installedModels.includes(model.tag);
          return (
            <div
              key={model.tag}
              className="flex items-center gap-3 border-b px-3 py-2 text-sm last:border-b-0"
            >
              <span className="w-44 shrink-0 truncate font-medium">{model.label}</span>
              <div className="hidden h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-secondary sm:block">
                <div
                  className={cn(
                    "h-full rounded-full",
                    fit.speed === "no"
                      ? "bg-destructive"
                      : fit.speed === "fast"
                        ? "bg-success"
                        : "bg-warning"
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="w-16 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
                {fit.footprint_gb} GB
              </span>
              <FitBadge fit={fit} />
              <div className="w-28 shrink-0 text-right">
                {settings.data?.default_model === model.tag ? (
                  <span className="text-xs font-medium text-primary">default</span>
                ) : settings.data?.fast_model === model.tag ? (
                  <span className="text-xs font-medium text-ai">background</span>
                ) : installed ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={!isOwner}
                    onClick={() => save.mutate({ default_model: model.tag })}
                    className="h-6 px-2 text-xs"
                  >
                    Use
                  </Button>
                ) : (
                  <InstallMini
                    tag={model.tag}
                    disabled={!isOwner || !ollamaRunning || fit.speed === "no"}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function InstallMini({ tag, disabled }: { tag: string; disabled: boolean }) {
  const qc = useQueryClient();
  const [progress, setProgress] = useState<number | null>(null);
  const run = async () => {
    setProgress(0);
    try {
      for await (const e of sseStream<{
        total?: number;
        completed?: number;
        error?: string;
        done?: boolean;
      }>("/api/ai/ollama/pull", { model: tag })) {
        if (e.error) throw new Error(e.error);
        if (e.total && e.completed !== undefined)
          setProgress(Math.round((e.completed / e.total) * 100));
        if (e.done) break;
      }
      toast.success(`${tag} installed`);
      qc.invalidateQueries({ queryKey: ["ollama-status"] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Download failed");
    } finally {
      setProgress(null);
    }
  };
  if (progress !== null)
    return <span className="text-xs tabular-nums text-muted-foreground">{progress}%</span>;
  return (
    <Button size="sm" variant="ghost" disabled={disabled} onClick={run} className="h-6 px-2 text-xs">
      <Download className="size-3" />
      Get
    </Button>
  );
}

/* ---------------- cloud (OpenRouter) ---------------- */

function CloudSection({ isOwner }: { isOwner: boolean }) {
  const settings = useAiSettings();
  const save = useSaveAiSettings();
  const catalog = useOpenRouterCatalog(true);
  const [key, setKey] = useState("");
  const [filter, setFilter] = useState("");

  const hasKey = settings.data?.has_openrouter_key;

  const saveKey = async () => {
    try {
      await save.mutateAsync({ openrouter_key: key.trim() });
      setKey("");
      toast.success("Key saved and validated");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn’t save the key");
    }
  };

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const models = catalog.data?.models ?? [];
    return (q ? models.filter((m) => m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q)) : models).slice(0, 30);
  }, [catalog.data, filter]);

  return (
    <section className="flex flex-col gap-5">
      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          API key
        </h2>
        <div className="flex gap-2">
          <div className="relative min-w-0 flex-1">
            <KeyRound className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="password"
              value={key}
              disabled={!isOwner}
              onChange={(e) => setKey(e.target.value)}
              placeholder={hasKey ? "•••••••• (a key is saved — paste to replace)" : "sk-or-…"}
              className="pl-8"
              autoComplete="off"
            />
          </div>
          <Button onClick={saveKey} disabled={!isOwner || !key.trim() || save.isPending}>
            {save.isPending && <Loader2 className="size-4 animate-spin" />}
            {hasKey ? "Replace key" : "Save key"}
          </Button>
        </div>
        <p className="mt-1.5 text-xs text-muted-foreground">
          Validated live with OpenRouter, encrypted at rest, never sent back to the browser.
        </p>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Featured models
        </h2>
        {catalog.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : catalog.isError ? (
          <p className="text-sm text-destructive">Couldn’t load the OpenRouter catalog.</p>
        ) : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {catalog.data.featured.map((f) => {
              const model = catalog.data.models.find((m) => m.id === f.id);
              const isDefault = settings.data?.default_model === f.id;
              return (
                <button
                  key={f.id}
                  disabled={!isOwner}
                  onClick={() => save.mutate({ default_model: f.id })}
                  className={cn(
                    "flex flex-col gap-1 rounded-xl border p-3 text-left transition-all",
                    isDefault
                      ? "border-primary bg-accent shadow-sm"
                      : "hover:border-primary/40 hover:bg-secondary/50"
                  )}
                >
                  <span className="flex items-center gap-1.5 text-sm font-semibold">
                    {f.label}
                    {isDefault && <Check className="ml-auto size-4 text-primary" />}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {model?.context_length
                      ? `${Math.round(model.context_length / 1000)}k context`
                      : ""}
                    {model?.prompt_price
                      ? ` · $${(Number(model.prompt_price) * 1e6).toFixed(2)}/M in`
                      : ""}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div>
        <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          <Zap className="size-3.5" />
          Background model (autocomplete, tagging)
        </h2>
        <Input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search the catalog…"
          className="mb-2 max-w-sm"
        />
        <div className="max-h-56 overflow-y-auto rounded-xl border">
          {filtered.map((m) => (
            <button
              key={m.id}
              disabled={!isOwner}
              onClick={() =>
                settings.data?.fast_model === m.id
                  ? save.mutate({ default_model: m.id })
                  : save.mutate({ fast_model: m.id })
              }
              className="flex w-full items-center gap-2 border-b px-3 py-1.5 text-left text-sm last:border-b-0 hover:bg-secondary/60"
            >
              <span className="min-w-0 flex-1 truncate">{m.name}</span>
              {settings.data?.fast_model === m.id && (
                <span className="text-xs font-medium text-ai">background</span>
              )}
              {settings.data?.default_model === m.id && (
                <span className="text-xs font-medium text-primary">default</span>
              )}
              <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                {m.prompt_price ? `$${(Number(m.prompt_price) * 1e6).toFixed(2)}/M` : "—"}
              </span>
            </button>
          ))}
          {filtered.length === 0 && (
            <p className="p-4 text-center text-sm text-muted-foreground">No matches.</p>
          )}
        </div>
      </div>
    </section>
  );
}

/* ---------------- test chat ---------------- */

function TestChat({ workspaceId }: { workspaceId: string }) {
  const [prompt, setPrompt] = useState("");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const run = async () => {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setReply("");
    abortRef.current = new AbortController();
    try {
      for await (const event of sseStream<{ type: string; text?: string; error?: string }>(
        "/api/ai/chat/test",
        { workspace_id: workspaceId, prompt },
        abortRef.current.signal
      )) {
        if (event.type === "error") throw new Error(event.error);
        if (event.type === "text" && event.text) setReply((r) => r + event.text);
        if (event.type === "done") break;
      }
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) {
        toast.error(e instanceof Error ? e.message : "The model didn’t answer");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
        Try it
      </h2>
      <div className="rounded-xl border p-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run();
          }}
          className="flex gap-2"
        >
          <Input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Say hello to your model…"
            disabled={busy}
          />
          <Button type="submit" disabled={busy || !prompt.trim()} aria-label="Send test prompt">
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          </Button>
        </form>
        {(reply || busy) && (
          <div className="mt-3 whitespace-pre-wrap rounded-lg bg-secondary/60 p-3 text-sm">
            {reply}
            {busy && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-ai" />}
          </div>
        )}
      </div>
    </section>
  );
}
