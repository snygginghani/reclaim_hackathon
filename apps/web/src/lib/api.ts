/** Base URL of the Lore API. All fetches go through `api()` so auth and errors are handled once.
 * Defaults to the API on the same host that served this page (LAN-friendly, no per-network
 * config); set NEXT_PUBLIC_API_URL to override when the API lives on a different host. */
function resolveApiUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") return `http://${window.location.hostname}:8300`;
  return "http://localhost:8300";
}

export const API_URL = resolveApiUrl();

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
  }
}

async function rawFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
}

let refreshInFlight: Promise<boolean> | null = null;

/** One shared refresh attempt at a time; concurrent 401s all await the same call. */
async function tryRefresh(): Promise<boolean> {
  refreshInFlight ??= rawFetch("/api/auth/refresh", { method: "POST" })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

/**
 * Fetch with the shared auth behaviour: cookies included, and one silent refresh
 * + replay on an expired access token. Returns the raw Response so streaming
 * callers (SSE) get the same treatment as JSON ones — the assistant used to skip
 * this and died with "Not authenticated" 15 minutes after login.
 */
export async function authedFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await rawFetch(path, init);
  // Auth routes are excluded so a failed login/refresh can't loop.
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    if (await tryRefresh()) return rawFetch(path, init);
  }
  return res;
}

/** Thin fetch wrapper: JSON in/out, cookies included, silent token refresh, typed errors. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await authedFetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      // FastAPI validation errors: [{loc: [...], msg: "..."}, ...] — surface the first one.
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        const first = body.detail[0];
        const field = Array.isArray(first.loc) ? String(first.loc.at(-1)) : "";
        detail = field && field !== "body" ? `${field}: ${first.msg}` : String(first.msg);
      }
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
