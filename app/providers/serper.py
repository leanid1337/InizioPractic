"""Serper.dev SERP API provider (production default)."""
from __future__ import annotations

from urllib.parse import urlparse

import requests

from ..models import SearchResult
from .base import ProviderBlockedError, ProviderError, SearchProvider

SERPER_URL = "https://google.serper.dev/search"


def displayed_url_from(link: str) -> str:
    """Mimic Google's breadcrumb style: 'https://www.alza.cz › kavovary'."""
    p = urlparse(link)
    parts = [seg for seg in p.path.split("/") if seg]
    base = f"{p.scheme}://{p.netloc}" if p.scheme else p.netloc
    return " › ".join([base, *parts[:2]])


def map_organic(payload: dict) -> list[SearchResult]:
    """Pure mapping of Serper's JSON 'organic' array to SearchResult objects."""
    results: list[SearchResult] = []
    for item in payload.get("organic") or []:
        link = item.get("link")
        title = (item.get("title") or "").strip()
        if not link or not title:
            continue
        results.append(
            SearchResult(
                position=len(results) + 1,
                title=title,
                url=link,
                snippet=(item.get("snippet") or "").strip(),
                displayed_url=displayed_url_from(link),
            )
        )
    return results


class SerperProvider(SearchProvider):
    name = "serper"

    def __init__(
        self,
        api_key: str,
        hl: str = "cs",
        gl: str = "cz",
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.hl, self.gl, self.timeout = hl, gl, timeout
        self.session = session or requests.Session()

    def search(self, query: str) -> list[SearchResult]:
        if not self.api_key:
            raise ProviderError("SERPER_API_KEY is not configured on the server.")
        try:
            resp = self.session.post(
                SERPER_URL,
                json={"q": query, "hl": self.hl, "gl": self.gl, "num": 10},
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"Network error while contacting Serper: {exc}") from exc
        if resp.status_code == 429:
            raise ProviderBlockedError("Serper API rate limit or quota exceeded.")
        if resp.status_code in (401, 403):
            raise ProviderError("Serper API rejected the API key.")
        if resp.status_code >= 400:
            raise ProviderError(f"Serper API error: HTTP {resp.status_code}.")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ProviderError("Serper API returned invalid JSON.") from exc
        return map_organic(payload)
