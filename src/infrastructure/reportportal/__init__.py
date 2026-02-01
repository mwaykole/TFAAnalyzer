"""ReportPortal infrastructure adapters.

This module contains all ReportPortal API interactions:
- Client for API communication
- Component fetcher for getting failure logs
- Test history for historical data
- Models for data structures
"""

from src.infrastructure.reportportal.client import ReportPortalClient, DEFECT_MAP
from src.infrastructure.reportportal.models import Launch, TestItem, TestStatus
from src.infrastructure.reportportal.component_fetcher import fetch_component_logs
from src.infrastructure.reportportal.test_history import (
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
