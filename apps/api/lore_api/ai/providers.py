"""One chat interface over two runtimes: Ollama (local) and OpenRouter (cloud).
Streaming and tool calls are normalized to a small event vocabulary so every
consumer (assistant, agent, autocomplete) is provider-agnostic."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, TypedDict

import httpx

OLLAMA_URL = "http://localhost:11434"
OPENROUTER_URL = "https://openrouter.ai/api/v1"


class ChatMessage(TypedDict, total=False):
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_calls: list[dict]
    tool_call_id: str
    name: str


class StreamEvent(TypedDict, total=False):
    type: str  # "text" | "tool_call" | "usage" | "error"
    text: str
    tool_call: dict  # {id, name, arguments(dict)}
    usage: dict  # {input_tokens, output_tokens}
    error: str


class LLMProvider(ABC):
    @abstractmethod
    def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]: ...


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = OLLAMA_URL):
        self.base_url = base_url.rstrip("/")

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }
        if tools:
            payload["tools"] = tools
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10)) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/api/chat", json=payload
                ) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode(errors="replace")[:300]
                        yield {"type": "error", "error": f"Ollama {resp.status_code}: {body}"}
                        return
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        for event in parse_ollama_chunk(line):
                            yield event
        except httpx.HTTPError as e:
            yield {"type": "error", "error": f"Can’t reach Ollama at {self.base_url}: {e}"}


def parse_ollama_chunk(line: str) -> list[StreamEvent]:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return []
    events: list[StreamEvent] = []
    msg = data.get("message") or {}
    if msg.get("content"):
        events.append({"type": "text", "text": msg["content"]})
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        events.append(
            {
                "type": "tool_call",
                "tool_call": {"id": tc.get("id") or fn.get("name", ""), "name": fn.get("name", ""), "arguments": args or {}},
            }
        )
    if data.get("done"):
        events.append(
            {
                "type": "usage",
                "usage": {
                    "input_tokens": data.get("prompt_eval_count", 0),
                    "output_tokens": data.get("eval_count", 0),
                },
            }
        )
    return events


class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "usage": {"include": True},
        }
        if tools:
            payload["tools"] = tools
        if max_tokens:
            payload["max_tokens"] = max_tokens
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "Lore",
        }
        # Streamed tool-call deltas arrive fragmented; accumulate per index.
        pending_tools: dict[int, dict] = {}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15)) as client:
                async with client.stream(
                    "POST", f"{OPENROUTER_URL}/chat/completions", json=payload, headers=headers
                ) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode(errors="replace")[:300]
                        yield {"type": "error", "error": f"OpenRouter {resp.status_code}: {body}"}
                        return
                    async for line in resp.aiter_lines():
                        for event in parse_openrouter_line(line, pending_tools):
                            yield event
        except httpx.HTTPError as e:
            yield {"type": "error", "error": f"OpenRouter request failed: {e}"}
        for tool in flush_pending_tools(pending_tools):
            yield tool


def parse_openrouter_line(line: str, pending: dict[int, dict]) -> list[StreamEvent]:
    line = line.strip()
    if not line.startswith("data:"):
        return []
    data = line[5:].strip()
    if data == "[DONE]":
        return flush_pending_tools(pending)
    try:
        chunk = json.loads(data)
    except json.JSONDecodeError:
        return []
    events: list[StreamEvent] = []
    for choice in chunk.get("choices") or []:
        delta = choice.get("delta") or {}
        if delta.get("content"):
            events.append({"type": "text", "text": delta["content"]})
        for tc in delta.get("tool_calls") or []:
            idx = tc.get("index", 0)
            slot = pending.setdefault(idx, {"id": "", "name": "", "arguments": ""})
            if tc.get("id"):
                slot["id"] = tc["id"]
            fn = tc.get("function") or {}
            if fn.get("name"):
                slot["name"] = fn["name"]
            if fn.get("arguments"):
                slot["arguments"] += fn["arguments"]
    if chunk.get("usage"):
        events.append(
            {
                "type": "usage",
                "usage": {
                    "input_tokens": chunk["usage"].get("prompt_tokens", 0),
                    "output_tokens": chunk["usage"].get("completion_tokens", 0),
                },
            }
        )
    return events


def flush_pending_tools(pending: dict[int, dict]) -> list[StreamEvent]:
    events: list[StreamEvent] = []
    for idx in sorted(pending):
        slot = pending[idx]
        try:
            args = json.loads(slot["arguments"]) if slot["arguments"] else {}
        except json.JSONDecodeError:
            args = {}
        events.append(
            {
                "type": "tool_call",
                "tool_call": {"id": slot["id"] or slot["name"], "name": slot["name"], "arguments": args},
            }
        )
    pending.clear()
    return events
