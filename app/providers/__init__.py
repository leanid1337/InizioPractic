"""Search providers and the factory that picks one from the environment."""
from __future__ import annotations

import os
from typing import Mapping

from .base import ProviderBlockedError, ProviderError, SearchProvider
from .google_scraper import GoogleScraperProvider
from .serper import SerperProvider

__all__ = [
    "ConfigurationError",
    "ProviderBlockedError",
    "ProviderError",
    "SearchProvider",
    "GoogleScraperProvider",
    "SerperProvider",
    "get_provider",
]


class ConfigurationError(ValueError):
    """Invalid provider configuration; raised at startup so the app fails fast."""


def get_provider(env: Mapping[str, str] | None = None) -> SearchProvider:
    """SEARCH_PROVIDER=scraper|serper; default: serper if SERPER_API_KEY is set, else scraper."""
    env = os.environ if env is None else env
    key = env.get("SERPER_API_KEY", "").strip()
    choice = env.get("SEARCH_PROVIDER", "").strip().lower() or ("serper" if key else "scraper")
    hl, gl = env.get("SEARCH_HL", "cs"), env.get("SEARCH_GL", "cz")
    if choice == "serper":
        if not key:
            raise ConfigurationError(
                "SEARCH_PROVIDER=serper but SERPER_API_KEY is not set. "
                "Add it to the environment or .env, or set SEARCH_PROVIDER=scraper."
            )
        return SerperProvider(api_key=key, hl=hl, gl=gl)
    if choice == "scraper":
        return GoogleScraperProvider(hl=hl, gl=gl)
    raise ConfigurationError(f"Unknown SEARCH_PROVIDER: {choice!r} (use 'scraper' or 'serper').")
