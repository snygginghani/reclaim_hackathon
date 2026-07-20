/** Base URL of the Lore API. All fetches go through `api()` so auth and errors are handled once. */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8300";

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

/** Thin fetch wrapper: JSON in/out, cookies included, silent token refresh, typed errors. */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res = await rawFetch(path, init);
  // Expired access token: refresh once, replay the request. Auth routes are excluded
  // so a failed login/refresh can't loop.
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    if (await tryRefresh()) res = await rawFetch(path, init);
  }
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
