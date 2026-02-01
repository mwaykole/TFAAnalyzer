"""ReportPortal repository implementation.

Implements FailureRepository and HistoryRepository interfaces.
Liskov Substitution: Can substitute any FailureRepository implementation.
"""

import re
from typing import Any

from src.domain.entities.failure import Failure
from src.domain.entities.rca import RCA
from src.domain.interfaces.repositories import FailureRepository, HistoryRepository
from src.infrastructure.reportportal.client import ReportPortalClient


AI_COMMENT_PREFIX = "🤖 AI:"


class RPRepository(FailureRepository, HistoryRepository):
    """ReportPortal repository for failures and history.
    
    Implements both FailureRepository and HistoryRepository interfaces.
    Uses composition with existing ReportPortalClient.
    """
    
    def __init__(
        self,
        url: str,
        project: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
    ):
        """Initialize with RP connection details."""
        self._client = ReportPortalClient(
            url=url,
            project=project,
            username=username,
            password=password,
            verify_ssl=verify_ssl,
        )
        self._url = url
        self._project = project
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._client.__aexit__(exc_type, exc_val, exc_tb)
    
    async def get_failure(self, test_id: str, launch_id: str) -> Failure | None:
        """Get failure by test ID and launch ID."""
        try:
            item = await self._client.get_test_item(test_id)
            if not item:
                return None
            
            logs = await self._client.get_item_logs(test_id)
            combined_logs = "\n".join(
                log.get("message", "") for log in logs if log.get("level") == "ERROR"
            )
            
            return Failure(
                id=str(item.get("id", test_id)),
                test_name=item.get("name", ""),
                logs=combined_logs,
                status=item.get("status", "FAILED"),
                launch_id=launch_id,
                component=self._extract_component(item),
            )
        except Exception:
            return None
    
    async def get_failures_by_component(
        self, launch_id: str, component: str
    ) -> list[Failure]:
        """Get all failures for a component in a launch."""
        from src.infrastructure.reportportal.component_fetcher import fetch_component_logs
        
        result = await fetch_component_logs(
            url=self._url,
            project=self._project,
            username=self._client.username,
            password=self._client.password,
            launch_id=launch_id,
            component_name=component,
            verify_ssl=self._client.verify_ssl,
        )
        
        failures = []
        target_component = result.get_component(component)
        
        if target_component and target_component.failures:
            for f in target_component.failures:
                failures.append(Failure(
                    id=str(f.test_item.id),
                    test_name=f.test_item.name or "",
                    logs=f.combined_logs,
                    status="FAILED",
                    launch_id=launch_id,
                    component=component,
                ))
        
        return failures
    
    async def get_failure_logs(self, test_id: str) -> str:
        """Get logs for a specific test."""
        logs = await self._client.get_item_logs(test_id)
        return "\n".join(
            log.get("message", "") for log in logs if log.get("level") == "ERROR"
        )
    
    async def save_classification(
        self, test_id: str, rca: RCA, comment: str
    ) -> bool:
        """Save classification result back to ReportPortal."""
        try:
            defect_type = rca.classification.category.defect_type_code
            await self._client.update_defect_type(test_id, defect_type, comment)
            return True
        except Exception:
            return False
    
    async def has_ai_classification(self, test_id: str) -> bool:
        """Check if test already has AI classification."""
        try:
            item = await self._client.get_test_item(test_id)
            if not item:
                return False
            
            issue = item.get("issue", {})
            comment = issue.get("comment", "") or ""
            
            return AI_COMMENT_PREFIX in comment
        except Exception:
            return False
    
    async def get_existing_classification(self, test_id: str) -> RCA | None:
        """Get existing AI classification from ReportPortal."""
        try:
            item = await self._client.get_test_item(test_id)
            if not item:
                return None
            
            issue = item.get("issue", {})
            comment = issue.get("comment", "") or ""
            
            if AI_COMMENT_PREFIX not in comment:
                return None
            
            return self._parse_ai_comment(comment)
        except Exception:
            return None
    
    def _parse_ai_comment(self, comment: str) -> RCA | None:
        """Parse AI comment back to RCA."""
        from src.domain.entities.classification import Classification, FailureCategory, Severity
        
        category_match = re.search(r"AI Classification:\s*([^\n]+)", comment)
        confidence_match = re.search(r"Confidence:\s*(\d+)%", comment)
        severity_match = re.search(r"Severity:\s*[^\s]*\s*(\w+)", comment)
        root_cause_match = re.search(r"### Root Cause\n(.+?)(?=\n###|\Z)", comment, re.DOTALL)
        reasoning_match = re.search(r"### Why This Classification\n(.+?)(?=\n###|\Z)", comment, re.DOTALL)
        
        if not category_match:
            return None
        
        classification = Classification(
            category=FailureCategory.from_string(category_match.group(1).strip()),
            confidence=int(confidence_match.group(1)) / 100 if confidence_match else 0.8,
            severity=Severity(severity_match.group(1).upper()) if severity_match else Severity.MEDIUM,
            reasoning=reasoning_match.group(1).strip() if reasoning_match else "",
        )
        
        return RCA(
            classification=classification,
            root_cause=root_cause_match.group(1).strip() if root_cause_match else "",
            evidence_summary="Retrieved from ReportPortal",
        )
    
    async def get_test_history(
        self, test_name: str, days: int = 14
    ) -> dict[str, Any]:
        """Get historical pass/fail data for a test."""
        from src.infrastructure.reportportal.test_history import fetch_test_history_by_name
        
        try:
            history = await fetch_test_history_by_name(
                url=self._url,
                project=self._project,
                username=self._client.username,
                password=self._client.password,
                test_name=test_name,
                max_history=days,
                verify_ssl=self._client.verify_ssl,
            )
            return history or {}
        except Exception:
            return {}
    
    async def get_pass_rate(self, test_name: str, launches: int = 15) -> float:
        """Get pass rate for a test over recent launches."""
        history = await self.get_test_history(test_name, launches)
        return history.get("pass_rate", 1.0)
    
    async def is_known_flaky(self, test_name: str) -> bool:
        """Check if test is marked as flaky."""
        pass_rate = await self.get_pass_rate(test_name)
        return 0.2 <= pass_rate <= 0.8
    
    async def save_analysis(
        self,
        test_name: str,
        launch_id: str,
        component: str,
        rca: RCA,
    ) -> int:
        """Save analysis result to history (via RP comment)."""
        return 0
    
    def _extract_component(self, item: dict) -> str:
        """Extract component from test item path."""
        path = item.get("path", "") or ""
        parts = path.split("/")
        return parts[1] if len(parts) > 1 else ""
