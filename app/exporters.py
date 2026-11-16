"""Serialise search results into machine-readable formats (JSON, CSV)."""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Iterable

from .models import FIELDS, SearchResult

UTF8_BOM = "﻿"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_json(
    results: Iterable[SearchResult],
    query: str,
    provider: str,
    timestamp: datetime | None = None,
) -> str:
    """Return a JSON document with metadata and the results array."""
    ts = (timestamp or utc_now()).astimezone(timezone.utc)
    items = [r.to_dict() for r in results]
    payload = {
        "query": query,
        "timestamp": ts.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "provider": provider,
        "count": len(items),
        "results": items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def to_csv(results: Iterable[SearchResult]) -> str:
    """Return CSV text prefixed with a UTF-8 BOM so Excel detects the encoding."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\r\n")
    writer.writeheader()
    for r in results:
        writer.writerow(r.to_dict())
    return UTF8_BOM + buf.getvalue()


def slugify(text: str, max_len: int = 40) -> str:
    """ASCII slug for filenames: 'Kávovar Praha!' -> 'kavovar-praha'."""
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug[:max_len].strip("-") or "query"


def build_filename(query: str, ext: str, when: datetime | None = None) -> str:
    date = (when or utc_now()).strftime("%Y-%m-%d")
    return f"results_{slugify(query)}_{date}.{ext}"
