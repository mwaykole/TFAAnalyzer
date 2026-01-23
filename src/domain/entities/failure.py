"""Failure entity representing a test failure."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Failure:
    """Domain entity representing a test failure.
    
    Single Responsibility: Only holds failure data and basic validation.
    """
    
    id: str
    test_name: str
    logs: str
    status: str
    launch_id: str
    component: str = ""
    test_code: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Failure ID cannot be empty")
        if not self.test_name:
            raise ValueError("Test name cannot be empty")
    
    @property
    def duration_seconds(self) -> float | None:
        """Calculate test duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    @property
    def cache_key(self) -> str:
        """Generate cache key for this failure."""
        import hashlib
        log_hash = hashlib.md5(self.logs[:1000].encode()).hexdigest()[:12]
        return f"failure:{self.id}:{log_hash}"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "test_name": self.test_name,
            "logs": self.logs,
            "status": self.status,
            "launch_id": self.launch_id,
            "component": self.component,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Failure":
        """Create Failure from dictionary."""
        return cls(
            id=str(data.get("id", "")),
            test_name=data.get("test_name", data.get("name", "")),
            logs=data.get("logs", ""),
            status=data.get("status", "FAILED"),
            launch_id=str(data.get("launch_id", "")),
            component=data.get("component", ""),
            test_code=data.get("test_code", ""),
        )
