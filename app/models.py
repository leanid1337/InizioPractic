"""Domain model shared by all providers and exporters."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SearchResult:
    """One organic Google search result."""

    position: int
    title: str
    url: str
    snippet: str
    displayed_url: str

    def to_dict(self) -> dict:
        return asdict(self)


FIELDS: tuple[str, ...] = ("position", "title", "url", "snippet", "displayed_url")
