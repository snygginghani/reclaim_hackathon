"""Async Notion API client + OAuth helpers.

Wraps only what the migration needs: search, block/page/database reads, database
queries, asset download, and the OAuth token exchange/revoke. All list endpoints
are paginated to completion. 429s are retried honoring Retry-After (Notion caps
at ~3 req/s)."""

import asyncio
import base64

import httpx

from ..config import get_settings

API_BASE = "https://api.notion.com/v1"
# Pinned Notion API version — bump deliberately, never float.
NOTION_VERSION = "2022-06-28"

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
_MAX_RETRIES = 5


class NotionError(RuntimeError):
    """A Notion API call failed in a way the migration can't recover from."""


def _basic_auth_header() -> dict[str, str]:
    s = get_settings()
    if not s.notion_client_id or not s.notion_client_secret:
        raise NotionError("Notion integration is not configured on the server.")
    raw = f"{s.notion_client_id}:{s.notion_client_secret}".encode()
    return {"Authorization": f"Basic {base64.b64encode(raw).decode()}"}


async def _request(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
    """One request with 429/5xx retry honoring Retry-After."""
    for attempt in range(_MAX_RETRIES):
        resp = await client.request(method, url, **kwargs)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == _MAX_RETRIES - 1:
                break
            delay = float(resp.headers.get("Retry-After", 1.0))
            await asyncio.sleep(min(delay, 10.0))
            continue
        return resp
    raise NotionError(f"Notion API {method} {url} failed: {resp.status_code} {resp.text[:200]}")


# --- OAuth (client-credential calls, no user token) ---


async def exchange_code(code: str) -> dict:
    """Trade an OAuth `code` for an access token. Returns Notion's token payload
    ({access_token, workspace_name, workspace_id, bot_id, owner, ...})."""
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": get_settings().notion_redirect_uri,
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await _request(
            client, "POST", f"{API_BASE}/oauth/token", json=body, headers=_basic_auth_header()
        )
    if resp.status_code != 200:
        raise NotionError(f"OAuth token exchange failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()


async def revoke_token(token: str) -> None:
    """Revoke an access token so Lore retains no access after migration. Best
    effort — a failure here must not crash the caller (the row is deleted anyway)."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            await _request(
                client, "POST", f"{API_BASE}/oauth/revoke",
                json={"token": token}, headers=_basic_auth_header(),
            )
    except (httpx.HTTPError, NotionError):
        pass


# --- authenticated workspace reads ---


class NotionClient:
    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
        }

    async def _paginate_post(self, path: str, body: dict | None = None) -> list[dict]:
        results: list[dict] = []
        cursor: str | None = None
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=self._headers) as client:
            while True:
                payload = {**(body or {}), "page_size": 100}
                if cursor:
                    payload["start_cursor"] = cursor
                resp = await _request(client, "POST", f"{API_BASE}{path}", json=payload)
                if resp.status_code != 200:
                    raise NotionError(f"{path}: {resp.status_code} {resp.text[:200]}")
                data = resp.json()
                results.extend(data.get("results", []))
                if not data.get("has_more"):
                    return results
                cursor = data.get("next_cursor")

    async def _paginate_get(self, path: str) -> list[dict]:
        results: list[dict] = []
        cursor: str | None = None
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=self._headers) as client:
            while True:
                params: dict = {"page_size": 100}
                if cursor:
                    params["start_cursor"] = cursor
                resp = await _request(client, "GET", f"{API_BASE}{path}", params=params)
                if resp.status_code != 200:
                    raise NotionError(f"{path}: {resp.status_code} {resp.text[:200]}")
                data = resp.json()
                results.extend(data.get("results", []))
                if not data.get("has_more"):
                    return results
                cursor = data.get("next_cursor")

    async def _get(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=self._headers) as client:
            resp = await _request(client, "GET", f"{API_BASE}{path}")
        if resp.status_code != 200:
            raise NotionError(f"{path}: {resp.status_code} {resp.text[:200]}")
        return resp.json()

    async def search(self) -> list[dict]:
        """All pages and databases the integration can see (each result carries
        an `object` field of 'page' or 'database')."""
        return await self._paginate_post("/search")

    async def get_block_children(self, block_id: str) -> list[dict]:
        return await self._paginate_get(f"/blocks/{block_id}/children")

    async def get_page(self, page_id: str) -> dict:
        return await self._get(f"/pages/{page_id}")

    async def retrieve_database(self, database_id: str) -> dict:
        return await self._get(f"/databases/{database_id}")

    async def query_database(self, database_id: str) -> list[dict]:
        return await self._paginate_post(f"/databases/{database_id}/query")

    async def download_asset(self, url: str) -> bytes:
        """Fetch a (temporary, signed) Notion-hosted file so it can be re-hosted
        locally before the signature expires."""
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            raise NotionError(f"asset download failed: {resp.status_code}")
        return resp.content
