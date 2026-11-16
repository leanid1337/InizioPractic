"""Tiny in-memory TTL cache.

The UI shows a table and then offers JSON/CSV downloads of the same query.
Caching for a few minutes means one upstream call per query instead of three,
which saves API credits and lowers the chance of being rate-limited by Google.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable


class TTLCache:
    def __init__(self, ttl: float = 300.0, max_items: int = 256, clock: Callable[[], float] = time.monotonic):
        self.ttl, self.max_items, self._clock = ttl, max_items, clock
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires, value = item
            if self._clock() >= expires:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        if self.ttl <= 0:
            return
        with self._lock:
            if len(self._data) >= self.max_items:
                oldest = min(self._data, key=lambda k: self._data[k][0])
                del self._data[oldest]
            self._data[key] = (self._clock() + self.ttl, value)
