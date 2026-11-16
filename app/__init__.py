"""Flask application factory."""
from __future__ import annotations

import os

from dotenv import find_dotenv, load_dotenv
from flask import Flask

from .cache import TTLCache
from .providers import SearchProvider, get_provider


def create_app(provider: SearchProvider | None = None, cache_ttl: float = 300.0) -> Flask:
    """Build the app. Tests inject a fake `provider`; production reads it from env.

    When no provider is injected, variables from a `.env` file in the current working
    directory are loaded first. Real environment variables win over `.env` values,
    so Docker / Render settings are never overridden.
    Raises ConfigurationError at startup if the configuration is invalid.
    """
    if provider is None:
        load_dotenv(find_dotenv(usecwd=True), override=False)

    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    app.config["JSON_AS_ASCII"] = False
    app.config["MAX_QUERY_LENGTH"] = 200

    provider = provider or get_provider()
    app.extensions["search_provider"] = provider
    app.extensions["search_cache"] = TTLCache(ttl=cache_ttl)
    app.logger.info("Search provider: %s", provider.name)

    from .routes import bp

    app.register_blueprint(bp)
    return app

