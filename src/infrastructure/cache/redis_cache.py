"""Redis cache implementation.

Implements CacheRepository interface.
Liskov Substitution: Can substitute any CacheRepository implementation.
"""

import json
from typing import Any

from src.domain.interfaces.repositories import CacheRepository


class RedisCache(CacheRepository):
    """Redis-based cache repository.
    
    Provides shared caching across all users (30 QE engineers).
    Prevents duplicate LLM calls for same failures.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        prefix: str = "tfa:",
    ):
        """Initialize Redis connection."""
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._prefix = prefix
        self._client = None
    
    async def _get_client(self):
        """Get or create Redis client (lazy initialization)."""
        if self._client is None:
            try:
                import redis.asyncio as redis
                self._client = redis.Redis(
                    host=self._host,
                    port=self._port,
                    db=self._db,
                    password=self._password,
                    decode_responses=True,
                )
            except ImportError:
                raise ImportError("redis package required. Install with: pip install redis")
        return self._client
    
    def _make_key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self._prefix}{key}"
    
    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        try:
            client = await self._get_client()
            value = await client.get(self._make_key(key))
            if value:
                return json.loads(value)
            return None
        except Exception:
            return None
    
    async def set(self, key: str, value: Any, ttl_seconds: int = 86400) -> bool:
        """Set value in cache with TTL (default 24 hours)."""
        try:
            client = await self._get_client()
            serialized = json.dumps(value, default=str)
            await client.setex(self._make_key(key), ttl_seconds, serialized)
            return True
        except Exception:
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            client = await self._get_client()
            return await client.exists(self._make_key(key)) > 0
        except Exception:
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            client = await self._get_client()
            await client.delete(self._make_key(key))
            return True
        except Exception:
            return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern."""
        try:
            client = await self._get_client()
            full_pattern = self._make_key(pattern)
            keys = []
            async for key in client.scan_iter(match=full_pattern):
                keys.append(key)
            
            if keys:
                await client.delete(*keys)
            return len(keys)
        except Exception:
            return 0
    
    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
    
    async def health_check(self) -> bool:
        """Check if Redis is available."""
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception:
            return False
