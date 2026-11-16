"""HTTP layer: the static page and the search API."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, Response, current_app, jsonify, request

from .exporters import build_filename, to_csv, to_json, utc_now
from .models import SearchResult
from .providers import ProviderBlockedError, ProviderError, SearchProvider

bp = Blueprint("main", __name__)

FORMATS = {
    "json": "application/json; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
}


def _error(message: str, status: int) -> tuple[Response, int]:
    return jsonify(error=message), status


@bp.get("/")
def index():
    return current_app.send_static_file("index.html")


@bp.get("/healthz")
def healthz():
    return {"status": "ok", "provider": current_app.extensions["search_provider"].name}


def _search_cached(provider: SearchProvider, query: str) -> tuple[list[SearchResult], datetime]:
    cache = current_app.extensions["search_cache"]
    key = f"{provider.name}:{query.casefold()}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    value = (provider.search(query), utc_now())
    cache.set(key, value)
    return value


@bp.get("/api/search")
def search():
    query = " ".join(request.args.get("q", "").split())
    fmt = request.args.get("format", "json").lower()
    max_len = current_app.config["MAX_QUERY_LENGTH"]

    if not query:
        return _error("Query must not be empty.", 400)
    if len(query) > max_len:
        return _error(f"Query is too long (max {max_len} characters).", 400)
    if fmt not in FORMATS:
        return _error("Unsupported format. Use 'json' or 'csv'.", 400)

    provider: SearchProvider = current_app.extensions["search_provider"]
    try:
        results, fetched_at = _search_cached(provider, query)
    except ProviderBlockedError as exc:
        current_app.logger.warning("Provider blocked: %s", exc)
        return _error(f"The search provider is temporarily blocking requests: {exc} Please try again later.", 503)
    except ProviderError as exc:
        current_app.logger.error("Provider error: %s", exc)
        return _error(f"Search provider error: {exc}", 502)

    body = to_json(results, query, provider.name, fetched_at) if fmt == "json" else to_csv(results)
    filename = build_filename(query, fmt, fetched_at)
    return Response(
        body,
        mimetype=None,
        content_type=FORMATS[fmt],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
