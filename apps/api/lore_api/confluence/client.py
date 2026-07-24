"""Async Confluence Cloud client + Atlassian OAuth 2.0 (3LO) helpers.

Wraps only what the migration needs: the OAuth code exchange, resolving the site
`cloudId`, listing spaces/pages (with ADF bodies) and attachments, and downloading
attachment bytes. All list endpoints paginate to completion via `_links.next`.
429s/5xx are retried honoring Retry-After.

No token revoke exists in Atlassian 3LO; instead we never request `offline_access`
(so the access token self-expires) and delete the stored token after import."""

from __future__ import annotations

import asyncio
import json

import httpx

from ..config import get_settings

AUTH_BASE = "https://auth.atlassian.com"
ACCESSIBLE_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
# Read-only scopes; deliberately NO offline_access (we don't want a refresh token).
OAUTH_SCOPES = "read:confluence-content.all read:confluence-space.summary read:confluence-content.summary"

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
_MAX_RETRIES = 5


class ConfluenceError(RuntimeError):
    """A Confluence/Atlassian API call failed in a way the migration can't recover from."""


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
    raise ConfluenceError(f"Confluence API {method} {url} failed: {resp.status_code} {resp.text[:200]}")


# --- OAuth (no user token yet) ---


async def exchange_code(code: str) -> dict:
    """Trade an OAuth `code` for an access token. Returns Atlassian's token payload
    ({access_token, expires_in, scope, ...}); no refresh token without offline_access."""
    s = get_settings()
    body = {
        "grant_type": "authorization_code",
        "client_id": s.confluence_client_id,
        "client_secret": s.confluence_client_secret,
        "code": code,
        "redirect_uri": s.confluence_redirect_uri,
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await _request(client, "POST", f"{AUTH_BASE}/oauth/token", json=body)
    if resp.status_code != 200:
        raise ConfluenceError(f"OAuth token exchange failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()


async def resolve_site(token: str) -> tuple[str, str] | None:
    """Return (cloud_id, site_name) for the first Confluence site this token can
    access, or None if it can't reach any."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await _request(
            client, "GET", ACCESSIBLE_RESOURCES_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
    if resp.status_code != 200:
        raise ConfluenceError(f"accessible-resources failed: {resp.status_code} {resp.text[:200]}")
    for site in resp.json():
        scopes = " ".join(site.get("scopes", []))
        if "confluence" in scopes or "confluence" in (site.get("url") or ""):
            return site["id"], site.get("name") or site.get("url") or "Confluence"
    resources = resp.json()
    if resources:  # fall back to the first resource if we can't positively identify one
        return resources[0]["id"], resources[0].get("name") or "Confluence"
    return None


# --- authenticated reads ---


class ConfluenceClient:
    def __init__(self, token: str, cloud_id: str) -> None:
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self._site_base = f"https://api.atlassian.com/ex/confluence/{cloud_id}"
        self._api = f"{self._site_base}/wiki/api/v2"

    async def _paginate(self, path: str, params: dict | None = None) -> list[dict]:
        """GET a v2 collection to completion, following `_links.next` cursors."""
        results: list[dict] = []
        url: str | None = f"{self._api}{path}"
        first_params = {**(params or {}), "limit": 100}
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=self._headers) as client:
            while url:
                resp = await _request(client, "GET", url, params=first_params)
                first_params = None  # cursor is baked into `next`
                if resp.status_code != 200:
                    raise ConfluenceError(f"{path}: {resp.status_code} {resp.text[:200]}")
                data = resp.json()
                results.extend(data.get("results", []))
                nxt = (data.get("_links") or {}).get("next")
                url = f"{self._site_base}{nxt}" if nxt else None
        return results

    async def list_spaces(self) -> list[dict]:
        return await self._paginate("/spaces")

    async def list_pages(self, space_id: str) -> list[dict]:
        """All pages in a space, each with its ADF body and `parentId`."""
        return await self._paginate(
            f"/spaces/{space_id}/pages", {"body-format": "atlas_doc_format"}
        )

    async def list_attachments(self, page_id: str) -> list[dict]:
        return await self._paginate(f"/pages/{page_id}/attachments")

    async def download_attachment(self, download_link: str) -> bytes:
        """Fetch attachment bytes. `download_link` is the v2 attachment
        `downloadLink` (relative to the site's /wiki context) or an absolute URL."""
        if download_link.startswith("http"):
            url = download_link
        elif download_link.startswith("/wiki"):
            url = f"{self._site_base}{download_link}"
        else:
            url = f"{self._site_base}/wiki{download_link}"
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=self._headers,
                                     follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            raise ConfluenceError(f"attachment download failed: {resp.status_code}")
        return resp.content


def parse_adf(body: dict | None) -> dict:
    """Pull the ADF document out of a v2 page `body` field. The atlas_doc_format
    value is a JSON string."""
    raw = ((body or {}).get("atlas_doc_format") or {}).get("value")
    if not raw:
        return {"type": "doc", "content": []}
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return {"type": "doc", "content": []}
