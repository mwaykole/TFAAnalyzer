"""Fetch test failures by component from ReportPortal."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.infrastructure.reportportal.client import ReportPortalClient
from src.infrastructure.reportportal.models import Launch, LogEntry, TestItem, TestStatus
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ComponentFailure:
    """A failed test with its logs within a component."""
    
    test_item: TestItem
    logs: list[LogEntry] = field(default_factory=list)
    
    @property
    def combined_logs(self) -> str:
        """Get all logs combined as a single string."""
        if not self.logs:
            return "(No logs available)"
        log_lines = []
        for log in self.logs:
            timestamp = log.time.strftime("%Y-%m-%d %H:%M:%S") if log.time else "N/A"
            log_lines.append(f"[{timestamp}] [{log.level}] {log.message}")
        return "\n".join(log_lines)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.test_item.id,
            "name": self.test_item.name,
            "status": self.test_item.status,
            "type": self.test_item.type,
            "log_count": len(self.logs),
            "logs": self.combined_logs,
        }


@dataclass
class Component:
    """A component (suite) with its test failures."""
    
    name: str
    item: TestItem
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    failures: list[ComponentFailure] = field(default_factory=list)
    
    @property
    def status(self) -> str:
        return self.item.status
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "id": self.item.id,
            "status": self.status,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "failures": [f.to_dict() for f in self.failures],
        }


@dataclass
class LaunchResult:
    """Complete launch result with components and failures."""
    
    launch: Launch
    components: list[Component] = field(default_factory=list)
    
    @property
    def launch_name(self) -> str:
        return self.launch.name
    
    @property
    def launch_id(self) -> str:
        return self.launch.id
    
    @property
    def start_time(self) -> datetime | None:
        return self.launch.start_time
    
    @property
    def status(self) -> str:
        return self.launch.status
    
    @property
    def component_names(self) -> list[str]:
        """Get list of all component names."""
        return [c.name for c in self.components]
    
    @property
    def failed_components(self) -> list[Component]:
        """Get only failed components."""
        return [c for c in self.components if c.status == "FAILED"]
    
    def get_component(self, name: str) -> Component | None:
        """Get a specific component by name.

        Matching order: exact (case-insensitive) → normalized
        (underscores/hyphens treated as spaces) → substring containment.
        """
        name_lower = name.lower()
        for c in self.components:
            if c.name.lower() == name_lower:
                return c

        def _normalize(s: str) -> str:
            return s.lower().replace("_", " ").replace("-", " ").strip()

        name_norm = _normalize(name)
        for c in self.components:
            if _normalize(c.name) == name_norm:
                return c

        for c in self.components:
            if name_norm in _normalize(c.name) or _normalize(c.name) in name_norm:
                return c

        return None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "launch_name": self.launch_name,
            "launch_id": self.launch_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "status": self.status,
            "component_count": len(self.components),
            "failed_component_count": len(self.failed_components),
            "components": [c.to_dict() for c in self.components],
        }


class ComponentFetcher:
    """Fetches test failures organized by component."""
    
    def __init__(
        self,
        client: ReportPortalClient,
        max_logs_per_item: int = 50,
    ):
        self.client = client
        self.max_logs_per_item = max_logs_per_item
    
    async def get_launch_components(
        self,
        launch_id: str,
    ) -> LaunchResult:
        """Get all components (top-level items) for a launch.
        
        Args:
            launch_id: ReportPortal launch ID
            
        Returns:
            LaunchResult with all components
        """
        # Get launch info
        launch = await self.client.get_launch_by_id(launch_id)
        
        # Get all items for this launch
        all_items, _ = await self.client.get_test_items(launch_id, size=500)
        
        # Find top-level items (components) - items without parent
        top_level = [item for item in all_items if not item.parent_id]
        
        components = []
        for item in top_level:
            # Count child items by status
            children = [i for i in all_items if i.parent_id == item.id]
            
            component = Component(
                name=item.name,
                item=item,
                total_tests=len(children) + 1,  # Include self
                passed=sum(1 for c in children if c.status == "PASSED"),
                failed=sum(1 for c in children if c.status == "FAILED"),
                skipped=sum(1 for c in children if c.status == "SKIPPED"),
            )
            components.append(component)
        
        logger.info(
            "fetched_components",
            launch_id=launch_id,
            component_count=len(components),
        )
        
        return LaunchResult(launch=launch, components=components)
    
    async def get_component_failures(
        self,
        launch_id: str,
        component_name: str,
    ) -> tuple[Launch, Component]:
        """Get failures for a specific component with logs.
        
        Args:
            launch_id: ReportPortal launch ID
            component_name: Name of the component (e.g., 'model_server')
            
        Returns:
            Tuple of (launch, component with failures and logs)
        """
        launch_result = await self.get_launch_components(launch_id)
        
        component = launch_result.get_component(component_name)
        component_id = component.item.id if component else None
        
        # Get ALL failed items for this launch
        all_failed, _ = await self.client.get_test_items(
            launch_id, status=TestStatus.FAILED, size=500
        )
        
        # Filter failures that belong to this component
        component_failures = []
        component_name_lower = component_name.lower()
        name_normalized = component_name_lower.replace("_", " ").replace("-", " ")
        
        for item in all_failed:
            matched = False
            
            # Check if direct parent is the component
            if component_id and item.parent_id == component_id:
                matched = True
            
            # Check if item name contains component name
            if not matched and item.name:
                item_lower = item.name.lower()
                item_norm = item_lower.replace("_", " ").replace("-", " ")
                if component_name_lower in item_lower or name_normalized in item_norm:
                    matched = True
            
            # Check path for component name
            if not matched and item.path_names:
                path_str = str(item.path_names).lower()
                path_norm = path_str.replace("_", " ").replace("-", " ")
                if component_name_lower in path_str or name_normalized in path_norm:
                    matched = True
            
            if matched:
                component_failures.append(item)
        
        if not component_failures:
            available = ", ".join(launch_result.component_names[:20])
            raise ValueError(
                f"No failures matching '{component_name}' found. "
                f"Top-level components: {available}"
            )
        
        if not component:
            from src.infrastructure.reportportal.models import TestItem
            virtual_item = TestItem(
                id="virtual",
                name=component_name,
                type="SUITE",
                status="FAILED",
            )
            component = Component(item=virtual_item, status="FAILED", children=[])
        
        # Fetch logs for component failures only
        failures_with_logs = []
        for item in component_failures:
            logs, _ = await self.client.get_logs(item.id, size=self.max_logs_per_item)
            if logs:
                failures_with_logs.append(ComponentFailure(test_item=item, logs=logs))
        
        component.failures = failures_with_logs
        
        logger.info(
            "fetched_component_failures",
            launch_id=launch_id,
            component=component_name,
            failure_count=len(failures_with_logs),
            total_failed=len(all_failed),
        )
        
        return launch_result.launch, component
    
    async def get_component_failures_silent(
        self,
        launch_id: str,
        component_name: str,
        max_failures: int = 50,
    ) -> tuple[Launch, Component] | None:
        """Get failures for a specific component only, returns None if not found.
        
        Searches for failures that match the component name in:
        - Top-level component name
        - Test item path/name containing the component name
        
        Args:
            launch_id: ReportPortal launch ID
            component_name: Name of the component (e.g., 'Model_server')
            max_failures: Maximum number of failures to fetch logs for
            
        Returns:
            Tuple of (Launch, Component) or None if no matching failures found
        """
        launch_result = await self.get_launch_components(launch_id)
        
        # Try to find top-level component first
        component = launch_result.get_component(component_name)
        component_id = component.item.id if component else None
        
        # Get ALL failed items
        all_failed, _ = await self.client.get_test_items(
            launch_id, status=TestStatus.FAILED, size=500
        )
        
        if not all_failed:
            return None
        
        # Filter failures that match the component (case-insensitive)
        component_failures = []
        component_name_lower = component_name.lower()
        
        for item in all_failed:
            matched = False
            
            # Check if parent is the component
            if component_id and item.parent_id == component_id:
                matched = True
            
            # Check item name for component
            if not matched and item.name:
                if component_name_lower in item.name.lower():
                    matched = True
            
            # Check path for component name
            if not matched and item.path_names:
                path_str = str(item.path_names).lower()
                if component_name_lower in path_str:
                    matched = True
            
            if matched:
                component_failures.append(item)
        
        if not component_failures:
            return None
        
        # Limit failures to fetch logs for (to avoid timeouts)
        component_failures = component_failures[:max_failures]
        
        # Fetch logs only for component failures
        failures_with_logs = []
        for item in component_failures:
            logs, _ = await self.client.get_logs(item.id, size=self.max_logs_per_item)
            if logs:
                failures_with_logs.append(ComponentFailure(test_item=item, logs=logs))
        
        if not failures_with_logs:
            return None
        
        # Create or use existing component
        if not component:
            # Create a virtual component for these failures
            from src.infrastructure.reportportal.models import TestItem
            virtual_item = TestItem(
                id="virtual",
                name=component_name,
                type="SUITE",
                status="FAILED",
            )
            component = Component(item=virtual_item, status="FAILED", children=[])
            
        component.failures = failures_with_logs
        return launch_result.launch, component
    
    async def get_all_component_failures(
        self,
        launch_id: str,
        only_with_logs: bool = True,
    ) -> LaunchResult:
        """Get all failures for all components with logs.
        
        Args:
            launch_id: ReportPortal launch ID
            only_with_logs: Only include failures that have logs
            
        Returns:
            LaunchResult with all components and their failures
        """
        launch_result = await self.get_launch_components(launch_id)
        
        # Get all failed items
        failed_items, _ = await self.client.get_test_items(
            launch_id, status=TestStatus.FAILED, size=500
        )
        
        # Fetch logs for ALL failed items first
        failures_with_logs = []
        for item in failed_items:
            logs, _ = await self.client.get_logs(item.id, size=self.max_logs_per_item)
            if not only_with_logs or logs:
                failures_with_logs.append(ComponentFailure(test_item=item, logs=logs))
        
        # Assign failures to components (or create a catch-all component)
        component_map = {c.item.id: c for c in launch_result.components}
        
        for failure in failures_with_logs:
            # Check if this failure IS a component
            if failure.test_item.id in component_map:
                component_map[failure.test_item.id].failures.append(failure)
            # Check if parent is a component  
            elif failure.test_item.parent_id in component_map:
                component_map[failure.test_item.parent_id].failures.append(failure)
            # Otherwise assign to first failed component or create misc
            else:
                for comp in launch_result.components:
                    if comp.status == "FAILED":
                        comp.failures.append(failure)
                        break
        
        return launch_result


async def fetch_component_logs(
    url: str,
    project: str,
    username: str,
    password: str,
    launch_id: str,
    component_name: str | None = None,
    verify_ssl: bool = False,
) -> LaunchResult:
    """Convenience function to fetch component failures with logs.
    
    Args:
        url: ReportPortal URL
        project: Project name
        username: RP username
        password: RP password
        launch_id: Launch ID to analyze
        component_name: Specific component or None for all
        verify_ssl: Whether to verify SSL
        
    Returns:
        LaunchResult with components and failures
    """
    client = ReportPortalClient(
        url=url,
        project=project,
        username=username,
        password=password,
        verify_ssl=verify_ssl,
    )
    
    async with client:
        fetcher = ComponentFetcher(client)
        
        if component_name:
            launch, component = await fetcher.get_component_failures(
                launch_id, component_name
            )
            return LaunchResult(launch=launch, components=[component])
        else:
            return await fetcher.get_all_component_failures(launch_id)



