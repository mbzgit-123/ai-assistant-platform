import time
from typing import Any


class InMemoryStore:
    def __init__(self):
        self._store: dict[str, tuple[Any, float | None]] = {}

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        expire_at = time.monotonic() + ttl_seconds if ttl_seconds is not None else None
        self._store[key] = (value, expire_at)

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self._store:
            return default
        value, expire_at = self._store[key]
        if expire_at is not None and time.monotonic() >= expire_at:
            del self._store[key]
            return default
        return value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
