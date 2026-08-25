from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Hashable


class TTLCache:
    """In-process LRU+TTL cache — free stand-in for Redis on Render Free."""

    def __init__(self, maxsize: int = 256, ttl_seconds: float = 86400.0):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._data: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires, value = item
            if time.time() > expires:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.time() + self.ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)


geocode_cache = TTLCache(maxsize=256, ttl_seconds=86400)
autocomplete_cache = TTLCache(maxsize=256, ttl_seconds=86400)
