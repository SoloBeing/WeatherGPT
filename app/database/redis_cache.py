"""
Redis Cache Client — Point forecast cache + semantic query cache.

Every point query hits Redis first (TTL 1h). Precomputed forecasts
for top 5000 Indian towns are warmed after each GFS cycle.
"""

import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.config import settings

logger = logging.getLogger(__name__)

# Default cache time-to-live: 1 hour (3600 seconds)
DEFAULT_TTL = 3600


class RedisCache:
    """Async Redis cache client with fail-open fallback.

    If Redis is unavailable or disconnected, cache reads return None
    and writes fail silently without raising exceptions, ensuring the
    application continues to serve live weather data uninterrupted.
    """

    def __init__(self, url: Optional[str] = None) -> None:
        self._url = url or settings.REDIS_URL
        self._pool: Optional[aioredis.ConnectionPool] = None
        self._client: Optional[aioredis.Redis] = None
        self._warned_offline = False

    def _get_pool(self) -> aioredis.ConnectionPool:
        if self._pool is None:
            self._pool = aioredis.ConnectionPool.from_url(
                self._url,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                decode_responses=True,
            )
        return self._pool

    def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            pool = self._get_pool()
            self._client = aioredis.Redis(connection_pool=pool)
        return self._client

    async def ping(self) -> bool:
        """Check if Redis connection is alive."""
        try:
            client = self._get_client()
            return bool(await client.ping())
        except Exception as e:
            if not self._warned_offline:
                logger.warning("Redis is unreachable at %s: %s (caching disabled)", self._url, e)
                self._warned_offline = True
            return False

    async def get(self, key: str) -> Optional[str]:
        """Get string value by key."""
        try:
            client = self._get_client()
            return await client.get(key)
        except (RedisError, ConnectionError, OSError) as e:
            if not self._warned_offline:
                logger.warning("Redis GET failed for key '%s': %s", key, e)
                self._warned_offline = True
            return None

    async def set(self, key: str, value: str, ttl: int = DEFAULT_TTL) -> bool:
        """Set string value with TTL in seconds."""
        try:
            client = self._get_client()
            await client.set(key, value, ex=ttl)
            return True
        except (RedisError, ConnectionError, OSError) as e:
            if not self._warned_offline:
                logger.warning("Redis SET failed for key '%s': %s", key, e)
                self._warned_offline = True
            return False

    async def get_json(self, key: str) -> Optional[dict]:
        """Get JSON-deserialized value by key."""
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Corrupt JSON in cache key '%s'", key)
            return None

    async def set_json(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
        """Serialize value to JSON and store with TTL."""
        try:
            if isinstance(value, str):
                serialized = value
            else:
                serialized = json.dumps(value, default=str)
            return await self.set(key, serialized, ttl=ttl)
        except Exception as e:
            logger.error("Failed to serialize cache value for key '%s': %s", key, e)
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        try:
            client = self._get_client()
            await client.delete(key)
            return True
        except (RedisError, ConnectionError, OSError):
            return False

    # -----------------------------------------------------------------------
    # Domain-specific cache helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _make_point_key(prefix: str, lat: float, lon: float, *extras: Any) -> str:
        """Format a standardized cache key rounded to 2 decimal places (~1.1km)."""
        extra_str = ":".join(str(x) for x in extras)
        suffix = f":{extra_str}" if extra_str else ""
        return f"{prefix}:{round(lat, 2):.2f}:{round(lon, 2):.2f}{suffix}"

    async def get_current_weather(self, lat: float, lon: float) -> Optional[str]:
        """Retrieve cached current weather JSON string."""
        key = self._make_point_key("weather:current", lat, lon)
        return await self.get(key)

    async def set_current_weather(
        self, lat: float, lon: float, data_json: str, ttl: int = DEFAULT_TTL
    ) -> bool:
        """Store current weather JSON string."""
        key = self._make_point_key("weather:current", lat, lon)
        return await self.set(key, data_json, ttl=ttl)

    async def get_forecast(self, lat: float, lon: float, days: int) -> Optional[str]:
        """Retrieve cached forecast JSON string."""
        key = self._make_point_key("weather:forecast", lat, lon, days)
        return await self.get(key)

    async def mget(self, keys: list[str]) -> list[Optional[str]]:
        """Get multiple string values in a single network round-trip."""
        if not keys:
            return []
        try:
            client = self._get_client()
            return await client.mget(keys)
        except (RedisError, ConnectionError, OSError) as e:
            if not self._warned_offline:
                logger.warning("Redis MGET failed: %s", e)
                self._warned_offline = True
            return [None] * len(keys)

    async def set_many(self, items: list[tuple[str, str, int]]) -> bool:
        """Set multiple key-value pairs with individual TTLs using a pipeline.

        Args:
            items: List of (key, value_str, ttl_seconds) tuples.
        """
        if not items:
            return True
        try:
            client = self._get_client()
            async with client.pipeline(transaction=False) as pipe:
                for key, val, ttl in items:
                    pipe.set(key, val, ex=ttl)
                await pipe.execute()
            return True
        except (RedisError, ConnectionError, OSError) as e:
            if not self._warned_offline:
                logger.warning("Redis batch SET failed (%d items): %s", len(items), e)
                self._warned_offline = True
            return False

    async def set_forecast(
        self, lat: float, lon: float, days: int, data_json: str, ttl: int = DEFAULT_TTL
    ) -> bool:
        """Store forecast JSON string."""
        key = self._make_point_key("weather:forecast", lat, lon, days)
        return await self.set(key, data_json, ttl=ttl)

    async def set_forecasts_batch(
        self,
        items: list[tuple[float, float, int, str, int]],
    ) -> bool:
        """Store multiple location forecasts in a single pipelined operation.

        Args:
            items: List of (lat, lon, days, data_json, ttl) tuples.
        """
        pipeline_items = [
            (self._make_point_key("weather:forecast", lat, lon, days), data_json, ttl)
            for lat, lon, days, data_json, ttl in items
        ]
        return await self.set_many(pipeline_items)

    async def close(self) -> None:
        """Close underlying Redis client and connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None


# Shared singleton instance
cache = RedisCache()
