import { authedFetch } from "./api";

/**
 * POST to an SSE endpoint and yield each `data:` JSON payload.
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
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      const parsed = await res.json();
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      // keep statusText
    }
    throw new Error(detail);
  }
  const reader = res.body.getReader();
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
