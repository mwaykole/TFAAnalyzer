"""Notifier interface for sending analysis notifications.

Dependency Inversion: High-level modules depend on this abstraction.
Open/Closed: Add new notification channels without modifying existing code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class AnalysisSummary:
    """Summary of analysis results for notification."""
    
    launch_name: str
    launch_id: str
    component: str
    total_failures: int
    product_bugs: int
    automation_issues: int
    infrastructure_issues: int
    flaky_tests: int
    critical_bugs: list[dict[str, Any]]
    rp_url: str = ""
    
    @property
    def has_critical_issues(self) -> bool:
        """Check if there are critical issues to highlight."""
        return self.product_bugs > 0 or len(self.critical_bugs) > 0
    
    @property
    def overall_status(self) -> str:
        """Get overall status for notification."""
        if self.product_bugs > 0:
            return "critical"
        elif self.automation_issues > 0:
            return "warning"
        else:
            return "success"
    
    @classmethod
    def from_results(
        cls,
        launch_name: str,
        launch_id: str,
        component: str,
        results: list[dict[str, Any]],
        rp_url: str = "",
    ) -> "AnalysisSummary":
        """Create summary from analysis results."""
        product_bugs = sum(1 for r in results if r.get("classification") == "Product Bug")
        automation_issues = sum(1 for r in results if r.get("classification") == "Test Automation Issue")
        infrastructure_issues = sum(1 for r in results if r.get("classification") == "Infrastructure Issue")
        flaky_tests = sum(1 for r in results if "Flaky" in r.get("classification", "") or "Intermittent" in r.get("classification", ""))
        
        critical_bugs = [
            r for r in results
            if r.get("classification") == "Product Bug"
            and r.get("severity") in ("CRITICAL", "HIGH")
        ]
        
        return cls(
            launch_name=launch_name,
            launch_id=launch_id,
            component=component,
            total_failures=len(results),
            product_bugs=product_bugs,
            automation_issues=automation_issues,
            infrastructure_issues=infrastructure_issues,
            flaky_tests=flaky_tests,
            critical_bugs=critical_bugs,
            rp_url=rp_url,
        )


class Notifier(ABC):
    """Abstract interface for sending notifications.
    
    Implementations can send to:
    - Slack
    - Microsoft Teams
    - Email
    - Discord, etc.
    """
    
    @abstractmethod
    async def send_summary(self, summary: AnalysisSummary) -> bool:
        """Send analysis summary notification.
        
        Args:
            summary: AnalysisSummary with results data
            
        Returns:
            True if notification sent successfully
        """
        pass
    
    @abstractmethod
    async def send_message(self, text: str) -> bool:
        """Send a simple text message.
        
        Args:
            text: Message text
            
        Returns:
            True if sent successfully
        """
        pass
    
    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Get the notification channel name (e.g., 'slack', 'teams')."""
        pass
