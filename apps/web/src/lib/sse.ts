import { authedFetch } from "./api";

async function ensureOk(res: Response): Promise<void> {
  if (res.ok && res.body) return;
  let detail = res.statusText;
  try {
    const parsed = await res.json();
    if (typeof parsed.detail === "string") detail = parsed.detail;
  } catch {
    // keep statusText
  }
  throw new Error(detail);
}

/** Read an SSE Response body, yielding each `data:` JSON payload. */
async function* readSse<T>(res: Response): AsyncGenerator<T> {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      try {
        yield JSON.parse(trimmed.slice(5).trim()) as T;
      } catch {
        // partial or malformed frame; skip
      }
    }
  }
}

/**
 * POST JSON to an SSE endpoint and yield each `data:` JSON payload.
 *
 * Goes through `authedFetch` so an expired access token is refreshed and the
 * request replayed, exactly as for JSON calls. Streaming used to bypass that and
 * every AI feature is SSE, so the assistant failed with "Not authenticated" once
 * the 15-minute token lapsed while the rest of the app silently recovered.
 */
export async function* sseStream<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal
): AsyncGenerator<T> {
  const res = await authedFetch(path, {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
  await ensureOk(res);
  yield* readSse<T>(res);
}

/** POST a multipart form (e.g. a file upload) to an SSE endpoint and yield each
 * `data:` JSON payload. Same auth/refresh treatment as `sseStream`. */
export async function* sseUpload<T>(
  path: string,
  form: FormData,
  signal?: AbortSignal
): AsyncGenerator<T> {
  const res = await authedFetch(path, {
    method: "POST",
    body: form,
    signal,
  });
  await ensureOk(res);
  yield* readSse<T>(res);
}
