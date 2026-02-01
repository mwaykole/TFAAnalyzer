"""ReportPortal module - DEPRECATED.

This module is deprecated. Please import from:
    src.infrastructure.reportportal

This file exists for backward compatibility only.
"""

import warnings

# Emit deprecation warning on first import
warnings.warn(
    "src.rp is deprecated. Use src.infrastructure.reportportal instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from new location for compatibility
from src.infrastructure.reportportal import (
    ReportPortalClient,
    DEFECT_MAP,
    Launch,
    TestItem,
    TestStatus,
    fetch_component_logs,
    TestHistoryFetcher,
    TestHistory,
    TestExecution,
    fetch_test_history,
    fetch_test_history_by_name,
)

__all__ = [
    "ReportPortalClient",
    "DEFECT_MAP",
    "Launch",
    "TestItem",
    "TestStatus",
    "fetch_component_logs",
    "TestHistoryFetcher",
    "TestHistory",
    "TestExecution",
    "fetch_test_history",
    "fetch_test_history_by_name",
]
