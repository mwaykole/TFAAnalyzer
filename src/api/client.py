"""API client for connecting to centralized TFA server.

Used by CLI when --server flag is provided.
"""

import aiohttp
from typing import Any


class TFAClient:
    """Client for TFA API server.
    
    Enables CLI to use centralized server for:
    - Shared cache (avoid duplicate LLM calls)
    - Centralized configuration
    - Team-wide analytics
    """
    
    def __init__(self, server_url: str, timeout: int = 120):
        """Initialize TFA API client.
        
        Args:
            server_url: Base URL of TFA server (e.g., https://tfa.internal)
            timeout: Request timeout in seconds
        """
        self._server_url = server_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
    
    async def analyze(
        self,
        launch_id: str,
        component: str,
        test_id: str | None = None,
        push_to_rp: bool = False,
        use_cache: bool = True,
        use_llm: bool = True,
        provider: str = "claude-cli",
    ) -> dict[str, Any]:
        """Analyze test failures via API server.
        
        Args:
            launch_id: ReportPortal launch ID
            component: Component to analyze
            test_id: Specific test ID (optional)
            push_to_rp: Push results to ReportPortal
            use_cache: Use cached results
            use_llm: Use LLM for complex cases
            provider: LLM provider to use
            
        Returns:
            Analysis response from server
        """
        url = f"{self._server_url}/api/v1/analyze"
        payload = {
            "launch_id": launch_id,
            "component": component,
            "test_id": test_id,
            "push_to_rp": push_to_rp,
            "use_cache": use_cache,
            "use_llm": use_llm,
            "provider": provider,
        }
        
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error = await response.text()
                    raise RuntimeError(f"API error ({response.status}): {error}")
                return await response.json()
    
    async def investigate(
        self,
        launch_id: str,
        component: str,
        test_id: str | None = None,
        push_to_rp: bool = False,
        verify_tests: bool = False,
        provider: str = "claude-cli",
    ) -> dict[str, Any]:
        """Deep RCA investigation via API server.
        
        Args:
            launch_id: ReportPortal launch ID
            component: Component to investigate
            test_id: Specific test ID (optional)
            push_to_rp: Push results to ReportPortal
            verify_tests: Re-run tests for verification
            provider: LLM provider to use
            
        Returns:
            Investigation response from server
        """
        url = f"{self._server_url}/api/v1/investigate"
        payload = {
            "launch_id": launch_id,
            "component": component,
            "test_id": test_id,
            "push_to_rp": push_to_rp,
            "verify_tests": verify_tests,
            "provider": provider,
        }
        
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error = await response.text()
                    raise RuntimeError(f"API error ({response.status}): {error}")
                return await response.json()
    
    async def health_check(self) -> dict[str, Any]:
        """Check server health.
        
        Returns:
            Health status response
        """
        url = f"{self._server_url}/health"
        
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise RuntimeError(f"Server unhealthy: {response.status}")
                return await response.json()
    
    async def is_available(self) -> bool:
        """Check if server is available.
        
        Returns:
            True if server is reachable
        """
        try:
            await self.health_check()
            return True
        except Exception:
            return False
