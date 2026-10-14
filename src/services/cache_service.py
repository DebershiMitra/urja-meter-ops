"""In-memory TTL Caching Service with Stale-While-Revalidate support."""
import asyncio
import logging
import time
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

logger = logging.getLogger("urja.cache")
T = TypeVar("T")


class CacheItem(Generic[T]):
    def __init__(self, value: T, ttl_seconds: float):
        self.value = value
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl_seconds

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class CacheService:
    """Thread-safe In-Memory Cache supporting TTL and Stale-While-Revalidate (SWR).
    
    Freshness & Invalidation Strategy:
    - Master meter and hierarchy dataset TTL: 3600 seconds (matches upstream session).
    - Live energy timeseries TTL: 300 seconds (5 minutes).
    - If data is stale but upstream is down or slow, serves stale data gracefully
      rather than failing with a 502 error to client consumers.
    """

    def __init__(self):
        self._store: Dict[str, CacheItem[Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Returns cached item if present and not expired."""
        async with self._lock:
            item = self._store.get(key)
            if item and not item.is_expired:
                return item.value
            return None

    async def get_with_staleness(self, key: str) -> tuple[Optional[Any], bool]:
        """Returns (value, is_stale). Returns None if not cached at all."""
        async with self._lock:
            item = self._store.get(key)
            if not item:
                return None, True
            return item.value, item.is_expired

    async def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        """Stores a value with a specified TTL."""
        async with self._lock:
            self._store[key] = CacheItem(value, ttl_seconds)

    async def invalidate(self, key: Optional[str] = None) -> None:
        """Invalidates a specific key or purges the entire cache if key is None."""
        async with self._lock:
            if key is None:
                self._store.clear()
                logger.info("Purged entire in-memory cache.")
            elif key in self._store:
                del self._store[key]
                logger.info("Invalidated cache key '%s'.", key)

    async def get_or_set(
        self,
        key: str,
        producer: Callable[[], Any],
        ttl_seconds: float,
    ) -> Any:
        """Retrieves item from cache, or invokes producer to compute and cache it."""
        val, is_stale = await self.get_with_staleness(key)
        if val is not None and not is_stale:
            return val

        try:
            # Produce fresh data
            new_val = await producer() if asyncio.iscoroutinefunction(producer) else producer()
            await self.set(key, new_val, ttl_seconds)
            return new_val
        except Exception as e:
            # If fresh generation failed and we have a stale value, return stale
            if val is not None:
                logger.warning(
                    "Producer failed for key '%s' (%s). Serving stale cached value.",
                    key,
                    str(e),
                )
                return val
            raise
