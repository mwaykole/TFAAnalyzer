"""Code fetcher module - DEPRECATED.

This module is deprecated. Please import from:
    src.infrastructure.code_fetcher

This file exists for backward compatibility only.
"""

import warnings

warnings.warn(
    "src.code_fetcher is deprecated. Use src.infrastructure.code_fetcher instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new location
from src.infrastructure.code_fetcher import (
    GitHubCodeFetcher,
    LocalCodeFetcher,
    TestParser,
)

# Provide alias for backward compatibility
TestCodeInfo = None  # Import from infrastructure if needed

__all__ = [
    "GitHubCodeFetcher",
    "LocalCodeFetcher",
    "TestParser",
]
