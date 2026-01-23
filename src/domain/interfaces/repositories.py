"""Repository interfaces following Dependency Inversion Principle.

High-level modules should not depend on low-level modules.
Both should depend on abstractions.
"""

from abc import ABC, abstractmethod
from typing import Any

from src.domain.entities.failure import Failure
from src.domain.entities.rca import RCA


class FailureRepository(ABC):
    """Interface for failure data access.
    
    Liskov Substitution: Any implementation can substitute this interface.
    """
    
    @abstractmethod
    async def get_failure(self, test_id: str, launch_id: str) -> Failure | None:
        """Get failure by test ID and launch ID."""
        pass
    
    @abstractmethod
    async def get_failures_by_component(
        self, launch_id: str, component: str
    ) -> list[Failure]:
        """Get all failures for a component in a launch."""
        pass
    
    @abstractmethod
    async def get_failure_logs(self, test_id: str) -> str:
        """Get logs for a specific test."""
        pass
    
    @abstractmethod
    async def save_classification(
        self, test_id: str, rca: RCA, comment: str
    ) -> bool:
        """Save classification result back to repository."""
        pass
    
    @abstractmethod
    async def has_ai_classification(self, test_id: str) -> bool:
        """Check if test already has AI classification."""
        pass


class CacheRepository(ABC):
    """Interface for caching layer.
    
    Interface Segregation: Only cache-specific methods.
    """
    
    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: int = 86400) -> bool:
        """Set value in cache with TTL (default 24 hours)."""
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        pass
    
    @abstractmethod
    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern."""
        pass


class HistoryRepository(ABC):
    """Interface for historical data access.
    
    Interface Segregation: Only history-specific methods.
    """
    
    @abstractmethod
    async def get_test_history(
        self, test_name: str, days: int = 14
    ) -> dict[str, Any]:
        """Get historical pass/fail data for a test."""
        pass
    
    @abstractmethod
    async def get_pass_rate(self, test_name: str, launches: int = 15) -> float:
        """Get pass rate for a test over recent launches."""
        pass
    
    @abstractmethod
    async def is_known_flaky(self, test_name: str) -> bool:
        """Check if test is marked as flaky."""
        pass
    
    @abstractmethod
    async def save_analysis(
        self,
        test_name: str,
        launch_id: str,
        component: str,
        rca: RCA,
    ) -> int:
        """Save analysis result to history."""
        pass
