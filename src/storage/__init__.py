"""Storage module - DEPRECATED.

This module is deprecated. Please import from:
    src.infrastructure.storage

This file exists for backward compatibility only.
"""

import warnings

warnings.warn(
    "src.storage is deprecated. Use src.infrastructure.storage instead.",
    DeprecationWarning,
    stacklevel=2,
)# Re-export from new location
from src.infrastructure.storage import AnalysisStore, get_store__all__ = ["AnalysisStore", "get_store"]