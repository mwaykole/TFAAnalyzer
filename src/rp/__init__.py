"""ReportPortal API client and utilities."""

from src.rp.client import ReportPortalClient, AuthenticationError
from src.rp.models import (
    Launch,
    TestItem,
    LogEntry,
    AnalysisResult,
    TestStatus,
    LaunchStatus,
)
from src.rp.component_fetcher import (
    ComponentFetcher,
    Component,
    ComponentFailure,
    LaunchResult,
    fetch_component_logs,
)
from src.rp.test_history import (
    TestHistory,
    fetch_test_history,
)

__all__ = [
    # Client
    "ReportPortalClient",
    "AuthenticationError",
    # Models
    "Launch",
    "TestItem",
    "LogEntry",
    "AnalysisResult",
    "TestStatus",
    "LaunchStatus",
    # Component fetcher
    "ComponentFetcher",
    "Component",
    "ComponentFailure",
    "LaunchResult",
    "fetch_component_logs",
    # Test history
    "TestHistory",
    "fetch_test_history",
]
