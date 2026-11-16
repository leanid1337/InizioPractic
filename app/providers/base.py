"""Provider interface and shared errors."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import SearchResult


class ProviderError(Exception):
    """Generic provider failure (bad response, upstream error)."""


class ProviderBlockedError(ProviderError):
    """Upstream refused to serve results (CAPTCHA, HTTP 429, consent wall...)."""


class SearchProvider(ABC):
    """Anything that turns a query into the organic results of Google page 1."""

    name: str = "base"

    @abstractmethod
    def search(self, query: str) -> list[SearchResult]:
        """Return organic results, positions 1..N."""
