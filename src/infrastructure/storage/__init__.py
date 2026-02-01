"""Storage module for TFA historical data.

This module provides persistent storage for:
- Analysis history
- Metrics tracking
- Cached results
"""

from src.infrastructure.storage.sqlite_store import AnalysisStore, get_store

__all__ = ["AnalysisStore", "get_store"]
