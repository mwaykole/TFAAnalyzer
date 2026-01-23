"""In-memory cache implementation for fallback/testing.

Implements CacheRepository interface.
Liskov Substitution: Can substitute any CacheRepository implementation.
"""

import time
from typing import Any

from src.domain.interfaces.repositories import CacheRepository


class MemoryCache(CacheRepository):
    """In-memory cache repository.
    
    Used as fallback when Redis is not available.
    Also useful for testing.
    
    Note: Not shared across processes/users - use Redis for production.
    """
    
    def __init__(self, default_ttl: int = 86400):
        """Initialize in-memory cache."""
        self._cache: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl
    
    async def get(self, key: str) -> Any | None:
        """Get value from cache if not expired."""
        if key not in self._cache:
            return None
        
        value, expiry = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            return None
        
        return value
    
    async def set(self, key: str, value: Any, ttl_seconds: int = 86400) -> bool:
        """Set value in cache with TTL."""
        expiry = time.time() + ttl_seconds
        self._cache[key] = (value, expiry)
        return True
    
    async def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return await self.get(key) is not None
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern (simple prefix match)."""
        import fnmatch
        
        keys_to_delete = [
            k for k in self._cache.keys()
            if fnmatch.fnmatch(k, pattern)
        ]
        
        for key in keys_to_delete:
            del self._cache[key]
        
        return len(keys_to_delete)
    
    async def clear_all(self) -> int:
        """Clear all entries (for testing)."""
        count = len(self._cache)
        self._cache.clear()
        return count
    
    def size(self) -> int:
        """Get number of entries in cache."""
        return len(self._cache)
