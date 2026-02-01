"""Fetch test history and pass/fail rates from ReportPortal."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.infrastructure.reportportal.client import ReportPortalClient
from src.infrastructure.reportportal.models import Launch, TestItem, TestStatus
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TestExecution:
    """A single test execution."""
    
    launch_id: str
    launch_name: str
    launch_time: datetime | None
    status: str
    item_id: str
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "launch_id": self.launch_id,
            "launch_name": self.launch_name,
            "launch_time": self.launch_time.isoformat() if self.launch_time else None,
            "status": self.status,
            "item_id": self.item_id,
        }


@dataclass
class TestHistory:
    """History of a test across multiple launches."""
    
    test_name: str
    executions: list[TestExecution] = field(default_factory=list)
    
    @property
    def total_runs(self) -> int:
        return len(self.executions)
    
    @property
    def passed_count(self) -> int:
        return sum(1 for e in self.executions if e.status == "PASSED")
    
    @property
    def failed_count(self) -> int:
        return sum(1 for e in self.executions if e.status == "FAILED")
    
    @property
    def skipped_count(self) -> int:
        return sum(1 for e in self.executions if e.status == "SKIPPED")
    
    @property
    def pass_rate(self) -> float:
        """Pass rate as percentage (0-100)."""
        if self.total_runs == 0:
            return 0.0
        return (self.passed_count / self.total_runs) * 100
    
    @property
    def fail_rate(self) -> float:
        """Fail rate as percentage (0-100)."""
        if self.total_runs == 0:
            return 0.0
        return (self.failed_count / self.total_runs) * 100
    
    @property
    def is_flaky(self) -> bool:
        """Check if test is flaky (has both passes and failures)."""
        return self.passed_count > 0 and self.failed_count > 0
    
    @property
    def last_status(self) -> str | None:
        """Get the most recent status."""
        if not self.executions:
            return None
        # Sort by launch time descending
        sorted_execs = sorted(
            self.executions,
            key=lambda e: e.launch_time or datetime.min,
            reverse=True,
        )
        return sorted_execs[0].status
    
    @property
    def consecutive_failures(self) -> int:
        """Count consecutive failures from most recent."""
        sorted_execs = sorted(
            self.executions,
            key=lambda e: e.launch_time or datetime.min,
            reverse=True,
        )
        count = 0
        for e in sorted_execs:
            if e.status == "FAILED":
                count += 1
            else:
                break
        return count
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "test_name": self.test_name,
            "total_runs": self.total_runs,
            "passed": self.passed_count,
            "failed": self.failed_count,
            "skipped": self.skipped_count,
            "pass_rate": round(self.pass_rate, 1),
            "fail_rate": round(self.fail_rate, 1),
            "is_flaky": self.is_flaky,
            "last_status": self.last_status,
            "consecutive_failures": self.consecutive_failures,
            "executions": [e.to_dict() for e in self.executions],
        }
    
    def format_summary(self) -> str:
        """Format a summary line."""
        status_icon = "✓" if self.last_status == "PASSED" else "✗"
        flaky_tag = " [FLAKY]" if self.is_flaky else ""
        return (
            f"{status_icon} {self.test_name[:50]}: "
            f"{self.passed_count}/{self.total_runs} passed "
            f"({self.pass_rate:.0f}%){flaky_tag}"
        )


class TestHistoryFetcher:
    """Fetches test history across launches."""
    
    def __init__(
        self,
        client: ReportPortalClient,
        max_launches: int = 20,
    ):
        self.client = client
        self.max_launches = max_launches
    
    async def get_test_history(
        self,
        test_name: str,
        launch_name_filter: str | None = None,
    ) -> TestHistory:
        """Get history for a specific test.
        
        Args:
            test_name: Name of the test to search for
            launch_name_filter: Optional filter for launch names (substring match)
            
        Returns:
            TestHistory with all executions
        """
        history = TestHistory(test_name=test_name)
        
        # Get recent launches
        launches, _ = await self.client.get_launches(size=self.max_launches)
        
        # Filter launches if specified
        if launch_name_filter:
            launches = [
                l for l in launches
                if launch_name_filter.lower() in l.name.lower()
            ]
        
        # Search for test in each launch
        for launch in launches:
            items, _ = await self.client.get_test_items(launch.id, size=200)
            
            # Find matching test (case-insensitive partial match)
            test_name_lower = test_name.lower()
            for item in items:
                if test_name_lower in item.name.lower():
                    history.executions.append(TestExecution(
                        launch_id=launch.id,
                        launch_name=launch.name,
                        launch_time=launch.start_time,
                        status=item.status,
                        item_id=item.id,
                    ))
                    break  # Only count once per launch
        
        logger.info(
            "fetched_test_history",
            test_name=test_name,
            executions=len(history.executions),
        )
        
        return history
    
    async def get_failed_tests_history(
        self,
        launch_id: str,
        max_history_launches: int | None = None,
    ) -> dict[str, TestHistory]:
        """Get history for all failed tests in a launch.
        
        Args:
            launch_id: Launch to get failed tests from
            max_history_launches: Max launches to search history
            
        Returns:
            Dict mapping test name to TestHistory
        """
        max_launches = max_history_launches or self.max_launches
        
        # Get failed items from target launch
        failed_items, _ = await self.client.get_test_items(
            launch_id, status=TestStatus.FAILED, size=200
        )
        
        # Get launch info
        target_launch = await self.client.get_launch_by_id(launch_id)
        
        # Get recent launches for history
        all_launches, _ = await self.client.get_launches(size=max_launches * 3)
        
        # Filter to similar launches (smoke tests, same type)
        # Extract key parts of launch name
        name_parts = target_launch.name.lower().replace('-', ' ').replace('_', ' ').split()
        key_words = [p for p in name_parts if len(p) > 3 and not p.isdigit()][:3]
        
        similar_launches = []
        for l in all_launches:
            l_name_lower = l.name.lower()
            # Match if any 2 key words match
            matches = sum(1 for kw in key_words if kw in l_name_lower)
            if matches >= 2 or target_launch.name.split()[0].lower() in l_name_lower:
                similar_launches.append(l)
        
        similar_launches = similar_launches[:max_launches]
        
        logger.info(
            "searching_history",
            target_launch=target_launch.name,
            similar_launches=len(similar_launches),
            key_words=key_words,
        )
        
        # Build history for each failed test
        histories: dict[str, TestHistory] = {}
        
        for failed_item in failed_items:
            test_name = failed_item.name
            # Extract core test name (without parameters)
            core_name = test_name.split('[')[0].strip()
            
            history = TestHistory(test_name=test_name)
            
            # Search in similar launches
            for launch in similar_launches:
                items, _ = await self.client.get_test_items(launch.id, size=300)
                
                # Find matching test (by core name)
                for item in items:
                    item_core = item.name.split('[')[0].strip()
                    if item_core == core_name or core_name in item.name:
                        history.executions.append(TestExecution(
                            launch_id=launch.id,
                            launch_name=launch.name,
                            launch_time=launch.start_time,
                            status=item.status,
                            item_id=item.id,
                        ))
                        break
            
            histories[test_name] = history
        
        return histories


async def fetch_test_history(
    url: str,
    project: str,
    username: str,
    password: str,
    launch_id: str,
    max_history: int = 10,
    verify_ssl: bool = False,
) -> dict[str, TestHistory]:
    """Convenience function to fetch history for failed tests.
    
    Args:
        url: ReportPortal URL
        project: Project name
        username: RP username
        password: RP password
        launch_id: Launch ID to analyze
        max_history: Maximum launches to search
        verify_ssl: Whether to verify SSL
        
    Returns:
        Dict of test name to TestHistory
    """
    client = ReportPortalClient(
        url=url,
        project=project,
        username=username,
        password=password,
        verify_ssl=verify_ssl,
    )
    
    async with client:
        fetcher = TestHistoryFetcher(client, max_launches=max_history)
        return await fetcher.get_failed_tests_history(launch_id)


async def fetch_test_history_by_name(
    url: str,
    project: str,
    username: str,
    password: str,
    test_name: str,
    max_history: int = 14,
    verify_ssl: bool = False,
) -> dict[str, Any]:
    """Fetch history for a specific test by name.
    
    Args:
        url: ReportPortal URL
        project: Project name
        username: RP username
        password: RP password
        test_name: Name of the test to search for
        max_history: Maximum launches to search
        verify_ssl: Whether to verify SSL
        
    Returns:
        Dict with pass_rate, is_flaky, and other history info
    """
    client = ReportPortalClient(
        url=url,
        project=project,
        username=username,
        password=password,
        verify_ssl=verify_ssl,
    )
    
    async with client:
        fetcher = TestHistoryFetcher(client, max_launches=max_history)
        history = await fetcher.get_test_history(test_name)
        return history.to_dict()

