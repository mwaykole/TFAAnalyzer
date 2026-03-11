"""Async ReportPortal API client for version 5.x with OAuth support."""

import asyncio
import ssl
from typing import Any

import aiohttp
from aiohttp import BasicAuth, ClientTimeout

from src.infrastructure.reportportal.models import (
    Launch,
    LaunchStatus,
    LogEntry,
    PagedResponse,
    TestItem,
    TestStatus,
)
from src.utils.logging import get_logger
from src.utils.retry import RetryConfig, async_retry

logger = get_logger(__name__)

DEFECT_MAP = {
    "Product Bug": "pb001",
    "Test Automation Issue": "ab001",
    "Infrastructure Issue": "si001",
    "Flaky Test": "ab_1kbn5su3gqpdt",  # Intermittent Script Issue
    "Intermittent Failure": "ab_1kbn5su3gqpdt",  # Same as Flaky
    "No Defect": "nd001",
    "To Investigate": "ti001",
}


class OAuthTokenManager:
    """Manages OAuth token acquisition and refresh for ReportPortal 5.x."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self._access_token: str | None = None
        self._token_type: str = "bearer"

    async def get_token(self, session: aiohttp.ClientSession) -> str:
        """Get OAuth access token, fetching new one if needed."""
        if not self._access_token:
            await self._fetch_token(session)
        return self._access_token

    async def _fetch_token(self, session: aiohttp.ClientSession) -> None:
        """Fetch new OAuth token from ReportPortal."""
        oauth_url = f"{self.base_url}/uat/sso/oauth/token"
        
        auth = BasicAuth("ui", "uiman")
        
        data = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
        }

        logger.debug("fetching_oauth_token", url=oauth_url, username=self.username)

        try:
            async with session.post(
                oauth_url,
                data=data,
                auth=auth,
            ) as response:
                if response.status == 200:
                    token_data = await response.json()
                    self._access_token = token_data.get("access_token")
                    self._token_type = token_data.get("token_type", "bearer")
                    logger.info("oauth_token_obtained", token_type=self._token_type)
                else:
                    error_text = await response.text()
                    logger.error(
                        "oauth_token_failed",
                        status=response.status,
                        error=error_text[:500],
                    )
                    raise AuthenticationError(
                        f"Failed to get OAuth token: {response.status} - {error_text[:200]}"
                    )
        except aiohttp.ClientError as e:
            logger.error("oauth_request_failed", error=str(e))
            raise AuthenticationError(f"OAuth request failed: {e}") from e

    def get_auth_header(self) -> dict[str, str]:
        """Get authorization header with current token."""
        if not self._access_token:
            raise AuthenticationError("No access token available")
        return {"Authorization": f"Bearer {self._access_token}"}

    def invalidate(self) -> None:
        """Invalidate current token to force refresh."""
        self._access_token = None


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class ReportPortalClient:
    """Async client for ReportPortal 5.x API.

    Provides methods to interact with ReportPortal API including:
    - Fetching launches
    - Fetching test items (with filtering)
    - Fetching logs for test items
    - Posting comments to test items
    - Updating defect types
    
    Supports OAuth authentication with username/password for ReportPortal 5.x.
    Compatible with ReportPortal 5.x (tested with 5.11.1).
    """

    def __init__(
        self,
        url: str,
        project: str,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        verify_ssl: bool = True,
        timeout: float = 30.0,
        max_concurrent: int = 5,
        retry_config: RetryConfig | None = None,
    ):
        """Initialize ReportPortal client.

        Args:
            url: ReportPortal server URL (without trailing slash)
            project: Project name
            token: API bearer token (optional if username/password provided)
            username: ReportPortal username for OAuth (optional if token provided)
            password: ReportPortal password for OAuth (optional if token provided)
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
            max_concurrent: Maximum concurrent requests
            retry_config: Retry configuration for failed requests
        """
        self.url = url.rstrip("/")
        self.project = project
        self.token = token
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = ClientTimeout(total=timeout)
        self.retry_config = retry_config or RetryConfig()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._session: aiohttp.ClientSession | None = None
        self._oauth_manager: OAuthTokenManager | None = None

        if not token and not (username and password):
            raise ValueError(
                "Either 'token' or both 'username' and 'password' must be provided"
            )

        if username and password and not token:
            self._oauth_manager = OAuthTokenManager(
                base_url=self.url,
                username=username,
                password=password,
                verify_ssl=verify_ssl,
            )

    @property
    def base_url(self) -> str:
        """Get base API URL for the project."""
        return f"{self.url}/api/v1/{self.project}"

    def _get_base_headers(self) -> dict[str, str]:
        """Get base request headers without auth."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _get_auth_headers(self) -> dict[str, str]:
        """Get headers with authentication."""
        headers = self._get_base_headers()
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif self._oauth_manager and self._session:
            token = await self._oauth_manager.get_token(self._session)
            headers["Authorization"] = f"Bearer {token}"
        
        return headers

    async def __aenter__(self) -> "ReportPortalClient":
        """Enter async context manager."""
        if not self.verify_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)
        else:
            connector = aiohttp.TCPConnector()
        
        self._session = aiohttp.ClientSession(
            timeout=self.timeout,
            connector=connector,
        )
        
        if self._oauth_manager:
            await self._oauth_manager.get_token(self._session)
            logger.info("oauth_authenticated", username=self.username)
        
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        if self._session:
            await self._session.close()
            self._session = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure session is available."""
        if not self._session:
            raise RuntimeError(
                "Client not initialized. Use 'async with client:' context manager."
            )
        return self._session

    @async_retry()
    async def _get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make GET request to ReportPortal API.

        Args:
            endpoint: API endpoint (relative to base_url)
            params: Query parameters

        Returns:
            JSON response as dictionary
        """
        session = self._ensure_session()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = await self._get_auth_headers()

        async with self._semaphore:
            logger.debug("api_request", method="GET", url=url, params=params)
            async with session.get(url, params=params, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
                logger.debug("api_response", status=response.status, url=url)
                return data

    @async_retry()
    async def _post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make POST request to ReportPortal API.

        Args:
            endpoint: API endpoint (relative to base_url)
            data: Request body

        Returns:
            JSON response as dictionary
        """
        session = self._ensure_session()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = await self._get_auth_headers()

        async with self._semaphore:
            logger.debug("api_request", method="POST", url=url)
            async with session.post(url, json=data, headers=headers) as response:
                response.raise_for_status()
                result = await response.json()
                logger.debug("api_response", status=response.status, url=url)
                return result

    @async_retry()
    async def _put(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make PUT request to ReportPortal API.

        Args:
            endpoint: API endpoint (relative to base_url)
            data: Request body

        Returns:
            JSON response as dictionary
        """
        session = self._ensure_session()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = await self._get_auth_headers()

        async with self._semaphore:
            logger.debug("api_request", method="PUT", url=url)
            async with session.put(url, json=data, headers=headers) as response:
                response.raise_for_status()
                result = await response.json()
                logger.debug("api_response", status=response.status, url=url)
                return result

    async def get_launches(
        self,
        status: LaunchStatus | None = None,
        page: int = 0,
        size: int = 50,
        filter_id: int | None = None,
    ) -> tuple[list[Launch], PagedResponse]:
        """Fetch launches from ReportPortal.

        Args:
            status: Filter by launch status
            page: Page number (0-based)
            size: Page size
            filter_id: ReportPortal filter ID to use

        Returns:
            Tuple of (launches list, paged response metadata)
        """
        params: dict[str, Any] = {
            "page.page": page + 1,
            "page.size": size,
            "page.sort": "startTime,desc",
        }
        if status:
            params["filter.eq.status"] = status.value
        if filter_id:
            params["filterId"] = filter_id

        response = await self._get("launch", params=params)
        paged = PagedResponse(**response)

        launches = []
        for item in paged.content:
            item["launch_id"] = item.get("id", item.get("launchId", ""))
            launches.append(Launch(**item))
        
        logger.info(
            "fetched_launches",
            count=len(launches),
            total=paged.total_elements,
            page=paged.current_page,
            filter_id=filter_id,
        )
        return launches, paged

    async def get_latest_launch(
        self,
        status: LaunchStatus | None = None,
    ) -> Launch | None:
        """Get the most recent launch.

        Args:
            status: Filter by launch status

        Returns:
            Latest launch or None if no launches found
        """
        launches, _ = await self.get_launches(status=status, page=0, size=1)
        return launches[0] if launches else None

    async def get_launch_by_id(self, launch_id: str) -> Launch:
        """Fetch a specific launch by ID.

        Args:
            launch_id: Launch ID

        Returns:
            Launch entity
        """
        response = await self._get(f"launch/{launch_id}")
        return Launch(**response)

    async def get_test_items(
        self,
        launch_id: str,
        status: TestStatus | None = None,
        page: int = 0,
        size: int = 100,
    ) -> tuple[list[TestItem], PagedResponse]:
        """Fetch test items for a launch.

        Args:
            launch_id: Parent launch ID
            status: Filter by test status
            page: Page number (0-based)
            size: Page size

        Returns:
            Tuple of (test items list, paged response metadata)
        """
        params: dict[str, Any] = {
            "filter.eq.launchId": launch_id,
            "page.page": page + 1,
            "page.size": size,
            "page.sort": "startTime,asc",
        }
        if status:
            params["filter.eq.status"] = status.value

        response = await self._get("item", params=params)
        paged = PagedResponse(**response)

        items = []
        for item in paged.content:
            item["launch_id"] = item.get("launchId", launch_id)
            item["parent_id"] = item.get("parentId", item.get("parent_id"))
            item["has_logs"] = item.get("hasLogs", item.get("has_logs", False))
            item["has_stats"] = item.get("hasStats", item.get("has_stats", False))
            item["path_names"] = item.get("pathNames", item.get("path_names"))
            items.append(TestItem(**item))
        
        logger.info(
            "fetched_test_items",
            launch_id=launch_id,
            count=len(items),
            total=paged.total_elements,
            status_filter=status.value if status else None,
        )
        return items, paged

    async def get_all_failed_items(
        self,
        launch_id: str,
        page_size: int = 100,
    ) -> list[TestItem]:
        """Fetch all failed test items for a launch (handles pagination).

        Args:
            launch_id: Parent launch ID
            page_size: Items per page

        Returns:
            List of all failed test items
        """
        all_items: list[TestItem] = []
        page = 0

        while True:
            items, paged = await self.get_test_items(
                launch_id=launch_id,
                status=TestStatus.FAILED,
                page=page,
                size=page_size,
            )
            all_items.extend(items)

            if page >= paged.total_pages - 1:
                break
            page += 1

        logger.info(
            "fetched_all_failed_items",
            launch_id=launch_id,
            total_failed=len(all_items),
        )
        return all_items

    async def get_logs(
        self,
        item_id: str,
        page: int = 0,
        size: int = 300,
    ) -> tuple[list[LogEntry], PagedResponse]:
        """Fetch logs for a test item.

        Args:
            item_id: Test item ID
            page: Page number (0-based)
            size: Page size

        Returns:
            Tuple of (log entries list, paged response metadata)
        """
        params: dict[str, Any] = {
            "filter.eq.item": item_id,
            "page.page": page + 1,
            "page.size": size,
            "page.sort": "logTime,asc",
        }

        response = await self._get("log", params=params)
        paged = PagedResponse(**response)

        logs = []
        for log in paged.content:
            log["item_id"] = log.get("itemId", item_id)
            log["launch_id"] = log.get("launchId", log.get("launch_id", ""))
            log["binary_content"] = log.get("binaryContent", log.get("binary_content"))
            logs.append(LogEntry(**log))
        
        logger.debug(
            "fetched_logs",
            item_id=item_id,
            count=len(logs),
            total=paged.total_elements,
        )
        return logs, paged

    async def get_all_logs(
        self,
        item_id: str,
        page_size: int = 300,
    ) -> list[LogEntry]:
        """Fetch all logs for a test item (handles pagination).

        Args:
            item_id: Test item ID
            page_size: Logs per page

        Returns:
            List of all log entries
        """
        all_logs: list[LogEntry] = []
        page = 0

        while True:
            logs, paged = await self.get_logs(
                item_id=item_id,
                page=page,
                size=page_size,
            )
            all_logs.extend(logs)

            if page >= paged.total_pages - 1:
                break
            page += 1

        return all_logs

    async def get_nested_step_logs(
        self,
        parent_item_id: str,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch child test items (nested steps) and their logs.

        ReportPortal stores test steps as child items. This fetches
        them with their logs to provide step-level failure context.

        Args:
            parent_item_id: Parent test item ID
            page_size: Items per page

        Returns:
            List of dicts with step name, status, and logs
        """
        steps: list[dict[str, Any]] = []
        try:
            params: dict[str, Any] = {
                "filter.eq.parentId": parent_item_id,
                "page.page": 1,
                "page.size": page_size,
                "page.sort": "startTime,asc",
            }
            response = await self._get("item", params=params)
            paged = PagedResponse(**response)

            for item in paged.content:
                item_id = str(item.get("id", ""))
                step_name = item.get("name", "")
                step_status = item.get("status", "")

                step_logs = ""
                if item.get("hasLogs", False):
                    logs, _ = await self.get_logs(item_id, page=0, size=50)
                    step_logs = "\n".join(
                        f"[{log.level}] {log.message}" for log in logs
                    )

                steps.append({
                    "name": step_name,
                    "status": step_status,
                    "logs": step_logs,
                    "id": item_id,
                })

            logger.debug(
                "fetched_nested_steps",
                parent_id=parent_item_id,
                step_count=len(steps),
            )
        except Exception as e:
            logger.debug("nested_steps_fetch_failed", error=str(e))

        return steps

    async def post_comment(
        self,
        item_id: str,
        comment: str,
    ) -> dict[str, Any]:
        """Post a comment to a test item.

        Args:
            item_id: Test item ID
            comment: Comment text (supports markdown)

        Returns:
            API response
        """
        data = {
            "issue": {
                "comment": comment,
            }
        }

        result = await self._put(f"item/{item_id}/update", data=data)
        logger.info("posted_comment", item_id=item_id)
        return result

    async def update_defect_type(
        self,
        item_id: str,
        defect_type_locator: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Update defect type for a test item.

        Args:
            item_id: Test item ID
            defect_type_locator: Defect type locator (e.g., "pb001" for Product Bug)
            comment: Optional comment to add

        Returns:
            API response
        """
        # ReportPortal 5.x uses bulk update endpoint with issues array
        issue_data: dict[str, Any] = {
            "issueType": defect_type_locator,
        }
        if comment:
            issue_data["comment"] = comment

        data = {
            "issues": [
                {
                    "testItemId": int(item_id),
                    "issue": issue_data,
                }
            ]
        }

        result = await self._put("item", data=data)
        logger.info(
            "updated_defect_type",
            item_id=item_id,
            defect_type=defect_type_locator,
        )
        return result

    async def bulk_update_items(
        self,
        updates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Bulk update multiple test items.

        Args:
            updates: List of update payloads with item IDs

        Returns:
            API response
        """
        result = await self._put("item", data={"issues": updates})
        logger.info("bulk_updated_items", count=len(updates))
        return result

