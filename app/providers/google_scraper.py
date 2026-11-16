"""Direct Google scraping: fetching (impure) is separated from parsing (pure)."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from ..models import SearchResult
from .base import ProviderBlockedError, ProviderError, SearchProvider

GOOGLE_URL = "https://www.google.com/search"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",
}

# Blocks that are NOT organic results. They are removed from the tree before
# result extraction, so anything nested inside them can never leak through.
NON_ORGANIC_SELECTORS = [
    # ads
    "#tads", "#tadsb", "#bottomads", "[data-text-ad]", ".uEierd",
    # featured snippet / answer boxes
    "block-component", ".xpdopen", ".ifM9O", ".kp-wholepage", "[data-attrid^='wa:']",
    # people also ask
    ".related-question-pair", "[data-initq]", ".cUnQKe",
    # maps / local pack
    ".VkpGBb", "[data-local-attribute]", "#lu_map",
    # videos, top stories, carousels
    "g-scrolling-carousel", "g-section-with-header", "video-voyager", "[data-vid]",
    # right-hand knowledge panel, related searches
    "#rhs", "#bres", "#botstuff",
]

SNIPPET_SELECTORS = [".VwiC3b", "[data-sncf='1']", "[style*='-webkit-line-clamp']", ".IsZvec", ".s3v9rd"]

BLOCK_MARKERS = (
    'id="captcha-form"',
    "g-recaptcha",
    "/sorry/index",
    "unusual traffic from your computer network",
    "neobvyklý provoz",
)
JS_WALL_MARKERS = ("/httpservice/retry/enablejs",)
CONSENT_MARKERS = ("consent.google.", 'action="https://consent.google')

_WS = re.compile(r"\s+")


def _text(el: Tag | None) -> str:
    return _WS.sub(" ", el.get_text()).strip() if el else ""


def _clean_href(href: str) -> str | None:
    """Return the absolute destination URL, unwrapping Google's /url?q= links."""
    if href.startswith("/url?"):
        target = parse_qs(urlparse(href).query).get("q", [""])[0]
        href = target
    parsed = urlparse(href)
    if parsed.scheme not in ("http", "https"):
        return None
    host = parsed.netloc.lower()
    if host.endswith("google.com") or host.startswith("google.") or ".google." in host:
        return None
    return href


def _container(a: Tag) -> Tag:
    """The result block an anchor belongs to (div.g / div.MjjYud), or a near ancestor."""
    for parent in a.parents:
        classes = parent.get("class") or []
        if "g" in classes or "MjjYud" in classes:
            return parent
    return a.parent or a


def _detect_block(html: str) -> None:
    low = html.lower()
    if any(m in low for m in JS_WALL_MARKERS):
        raise ProviderBlockedError(
            "Google served its 'enable JavaScript' wall instead of results (non-browser client detected)."
        )
    if any(m.lower() in low for m in BLOCK_MARKERS):
        raise ProviderBlockedError("Google returned a CAPTCHA / bot-detection page.")
    if any(m in low for m in CONSENT_MARKERS) and 'id="rso"' not in low:
        raise ProviderBlockedError("Google returned a cookie-consent page instead of results.")


def parse_html(html: str) -> list[SearchResult]:
    """Pure function: Google SERP HTML -> organic results (positions 1..N).

    Raises ProviderBlockedError if the HTML is a CAPTCHA / bot-check page.
    """
    if not html or not html.strip():
        return []
    _detect_block(html)

    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one("#rso") or soup.select_one("#search") or soup.body or soup
    for sel in NON_ORGANIC_SELECTORS:
        for el in root.select(sel):
            el.decompose()

    results: list[SearchResult] = []
    seen: set[str] = set()
    for h3 in root.find_all("h3"):
        a = h3.find_parent("a", href=True)
        if a is None:
            continue
        url = _clean_href(a["href"])
        if not url or url in seen:
            continue
        title = _text(h3)
        if not title:
            continue
        seen.add(url)

        box = _container(a)
        cite = box.find("cite")
        displayed = _text(cite) or urlparse(url).netloc
        snippet_el = None
        for sel in SNIPPET_SELECTORS:
            snippet_el = box.select_one(sel)
            if snippet_el is not None:
                break
        results.append(
            SearchResult(
                position=len(results) + 1,
                title=title,
                url=url,
                snippet=_text(snippet_el),
                displayed_url=displayed,
            )
        )
    return results


class GoogleScraperProvider(SearchProvider):
    name = "scraper"

    def __init__(
        self,
        session: requests.Session | None = None,
        hl: str = "cs",
        gl: str = "cz",
        timeout: float = 10.0,
    ) -> None:
        self.session = session or requests.Session()
        self.hl, self.gl, self.timeout = hl, gl, timeout

    def fetch(self, query: str) -> str:
        params = {"q": query, "hl": self.hl, "gl": self.gl, "num": 10, "pws": 0}
        # SOCS cookie skips the EU cookie-consent interstitial.
        cookies = {"SOCS": "CAESHAgBEhJnd3NfMjAyNDAxMDEtMF9SQzEaAmNzIAEaBgiA_LyuBg", "CONSENT": "YES+"}
        try:
            resp = self.session.get(
                GOOGLE_URL, params=params, headers=DEFAULT_HEADERS, cookies=cookies, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise ProviderError(f"Network error while contacting Google: {exc}") from exc
        if resp.status_code == 429 or "/sorry/" in resp.url:
            raise ProviderBlockedError("Google rate-limited this server (HTTP 429 / CAPTCHA).")
        if resp.status_code >= 400:
            raise ProviderError(f"Google responded with HTTP {resp.status_code}.")
        return resp.text

    def search(self, query: str) -> list[SearchResult]:
        return parse_html(self.fetch(query))
