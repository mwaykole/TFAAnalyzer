"""Log Parser interface following Single Responsibility Principle."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedLogs:
    """Result of parsing logs."""
    
    error_type: str = ""
    error_message: str = ""
    stack_trace: str = ""
    patterns_found: list[str] = field(default_factory=list)
    has_timeout: bool = False
    has_assertion_error: bool = False
    has_connection_error: bool = False
    has_resource_error: bool = False
    key_indicators: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace[:500] if self.stack_trace else "",
            "patterns_found": self.patterns_found,
            "has_timeout": self.has_timeout,
            "has_assertion_error": self.has_assertion_error,
            "has_connection_error": self.has_connection_error,
            "has_resource_error": self.has_resource_error,
        }


class LogParser(ABC):
    """Interface for log parsing.
    
    Single Responsibility: Only parses logs, no classification logic.
    """
    
    @abstractmethod
    def parse(self, logs: str) -> ParsedLogs:
        """Parse logs and extract structured information."""
        pass
    
    @abstractmethod
    def extract_error_signature(self, logs: str) -> str:
        """Extract unique error signature for deduplication."""
        pass
