"""Code fetcher interface for fetching test source code.

Dependency Inversion: High-level modules depend on this abstraction,
not concrete implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestCodeInfo:
    """Information about fetched test code."""
    
    test_name: str
    file_path: str
    function_name: str
    source_code: str
    repo: str = ""
    branch: str = ""
    line_start: int | None = None
    line_end: int | None = None
    github_url: str = ""
    
    # Parsed metadata from AST
    decorators: list[str] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    has_timeout: bool = False
    timeout_value: int | None = None
    has_retry: bool = False
    uses_sleep: bool = False
    wait_patterns: list[str] = field(default_factory=list)
    parametrize_args: list[str] = field(default_factory=list)
    
    @property
    def short_code(self) -> str:
        """Get truncated code for display."""
        max_lines = 50
        lines = self.source_code.split('\n')
        if len(lines) > max_lines:
            return '\n'.join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
        return self.source_code
    
    @property
    def is_potentially_flaky(self) -> bool:
        """Check if test has flakiness indicators based on code analysis."""
        indicators = [
            self.uses_sleep,
            self.has_timeout,
            len(self.wait_patterns) > 0,
            any("flaky" in d.lower() for d in self.decorators),
            any("skip" in d.lower() for d in self.decorators),
            any("xfail" in d.lower() for d in self.decorators),
        ]
        return sum(indicators) >= 2
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "test_name": self.test_name,
            "file_path": self.file_path,
            "function_name": self.function_name,
            "source_code": self.short_code,
            "github_url": self.github_url,
            "decorators": self.decorators,
            "fixtures": self.fixtures,
            "has_timeout": self.has_timeout,
            "timeout_value": self.timeout_value,
            "has_retry": self.has_retry,
            "uses_sleep": self.uses_sleep,
            "wait_patterns": self.wait_patterns,
            "is_potentially_flaky": self.is_potentially_flaky,
        }


class CodeFetcher(ABC):
    """Abstract interface for fetching test source code.
    
    Implementations can fetch from:
    - GitHub API (remote)
    - Local filesystem
    - GitLab, Bitbucket, etc.
    """
    
    @abstractmethod
    async def fetch_test_code(self, test_name: str) -> TestCodeInfo | None:
        """Fetch source code for a test.
        
        Args:
            test_name: Full test name (e.g., "test_module::TestClass::test_func")
            
        Returns:
            TestCodeInfo with source code and metadata, or None if not found
        """
        pass
    
    @abstractmethod
    async def build_index(self) -> dict[str, str]:
        """Build index of test files.
        
        Returns:
            Dict mapping test names to file paths
        """
        pass
    
    @abstractmethod
    def get_github_url(self, file_path: str, line: int | None = None) -> str:
        """Generate GitHub URL for a file/line.
        
        Args:
            file_path: Path to file in repo
            line: Optional line number
            
        Returns:
            GitHub URL string
        """
        pass
    
    async def close(self) -> None:
        """Close any open connections."""
        pass
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()
