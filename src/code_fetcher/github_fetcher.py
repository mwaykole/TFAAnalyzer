"""Fetch test source code from GitHub repositories.

This module provides functionality to:
1. Map test names to file paths in GitHub repos
2. Fetch test source code for analysis
3. Cache fetched code to reduce API calls
"""

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import aiohttp

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TestCodeInfo:
    """Information about fetched test code."""
    
    test_name: str
    file_path: str
    function_name: str
    source_code: str
    repo: str
    branch: str
    line_start: int | None = None
    line_end: int | None = None
    github_url: str = ""
    
    @property
    def short_code(self) -> str:
        """Get truncated code for display."""
        max_lines = 50
        lines = self.source_code.split('\n')
        if len(lines) > max_lines:
            return '\n'.join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
        return self.source_code


class GitHubCodeFetcher:
    """Fetches test source code from GitHub repositories.
    
    Supports mapping pytest test names to source files and extracting
    relevant test functions.
    """
    
    GITHUB_API_BASE = "https://api.github.com"
    GITHUB_RAW_BASE = "https://raw.githubusercontent.com"
    
    # Common test file patterns for pytest
    TEST_FILE_PATTERNS = [
        r"test_[\w]+\.py",
        r"[\w]+_test\.py",
        r"tests?/.*\.py",
    ]
    
    def __init__(
        self,
        repo: str,
        branch: str = "main",
        token: str | None = None,
        test_dir: str = "tests",
        cache_dir: Path | None = None,
    ):
        """Initialize GitHub code fetcher.
        
        Args:
            repo: GitHub repository (owner/repo format, e.g., "redhat/ods-ci")
            branch: Branch to fetch from (default: main)
            token: GitHub personal access token (optional, for private repos)
            test_dir: Directory containing tests (default: tests)
            cache_dir: Directory to cache fetched files
        """
        self.repo = repo
        self.branch = branch
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.test_dir = test_dir
        self.cache_dir = cache_dir or Path(".code_cache")
        self.cache_dir.mkdir(exist_ok=True)
        
        self._session: aiohttp.ClientSession | None = None
        self._file_index: dict[str, str] = {}  # test_name -> file_path mapping
    
    @property
    def headers(self) -> dict[str, str]:
        """Get headers for GitHub API requests."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TFA-CodeFetcher",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session
    
    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()
    
    async def build_file_index(self) -> dict[str, str]:
        """Build an index of test files in the repository.
        
        Returns:
            Dict mapping test function names to file paths
        """
        if self._file_index:
            return self._file_index
        
        logger.info("building_file_index", repo=self.repo, test_dir=self.test_dir)
        
        session = await self._get_session()
        
        # Use GitHub's search API or tree API to find test files
        url = f"{self.GITHUB_API_BASE}/repos/{self.repo}/git/trees/{self.branch}?recursive=1"
        
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.error("github_tree_fetch_failed", status=resp.status)
                    return {}
                
                data = await resp.json()
                
                # Find all test files
                test_files = []
                for item in data.get("tree", []):
                    if item["type"] == "blob":
                        path = item["path"]
                        if self._is_test_file(path):
                            test_files.append(path)
                
                logger.info("found_test_files", count=len(test_files))
                
                # For each test file, extract test function names
                for file_path in test_files[:50]:  # Limit to avoid rate limits
                    content = await self._fetch_file_content(file_path)
                    if content:
                        functions = self._extract_test_functions(content)
                        for func_name in functions:
                            self._file_index[func_name] = file_path
                
                return self._file_index
                
        except Exception as e:
            logger.error("file_index_build_failed", error=str(e))
            return {}
    
    def _is_test_file(self, path: str) -> bool:
        """Check if a file path is a test file."""
        if not path.endswith(".py"):
            return False
        
        filename = Path(path).name
        
        # Check common patterns
        if filename.startswith("test_") or filename.endswith("_test.py"):
            return True
        
        # Check if in test directory
        if self.test_dir and self.test_dir in path:
            return True
        
        return False
    
    def _extract_test_functions(self, content: str) -> list[str]:
        """Extract test function names from Python source code."""
        functions = []
        
        # Match def test_xxx(...) or async def test_xxx(...)
        pattern = r"(?:async\s+)?def\s+(test_\w+)\s*\("
        matches = re.findall(pattern, content)
        functions.extend(matches)
        
        return functions
    
    async def _fetch_file_content(self, file_path: str) -> str | None:
        """Fetch raw file content from GitHub."""
        # Check cache first
        cache_file = self.cache_dir / file_path.replace("/", "_")
        if cache_file.exists():
            return cache_file.read_text()
        
        session = await self._get_session()
        url = f"{self.GITHUB_RAW_BASE}/{self.repo}/{self.branch}/{file_path}"
        
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                
                content = await resp.text()
                
                # Cache the content
                cache_file.write_text(content)
                
                return content
                
        except Exception as e:
            logger.error("file_fetch_failed", path=file_path, error=str(e))
            return None
    
    async def get_test_code(self, test_name: str) -> TestCodeInfo | None:
        """Fetch source code for a specific test.
        
        Args:
            test_name: Test name (e.g., "test_kueue_inference_service_raw")
            
        Returns:
            TestCodeInfo with source code, or None if not found
        """
        # Extract base test name (without parameters)
        base_name = self._extract_base_test_name(test_name)
        
        # Build index if needed
        if not self._file_index:
            await self.build_file_index()
        
        # Look up file path
        file_path = self._file_index.get(base_name)
        
        if not file_path:
            # Try searching by partial match
            for func_name, path in self._file_index.items():
                if base_name in func_name or func_name in base_name:
                    file_path = path
                    break
        
        if not file_path:
            logger.warning("test_not_found_in_index", test_name=test_name)
            return await self._search_for_test(test_name)
        
        # Fetch the file content
        content = await self._fetch_file_content(file_path)
        if not content:
            return None
        
        # Extract the specific test function
        function_code, line_start, line_end = self._extract_function(content, base_name)
        
        if not function_code:
            # Return the whole file if function extraction fails
            function_code = content
        
        github_url = f"https://github.com/{self.repo}/blob/{self.branch}/{file_path}"
        if line_start:
            github_url += f"#L{line_start}-L{line_end}"
        
        return TestCodeInfo(
            test_name=test_name,
            file_path=file_path,
            function_name=base_name,
            source_code=function_code,
            repo=self.repo,
            branch=self.branch,
            line_start=line_start,
            line_end=line_end,
            github_url=github_url,
        )
    
    async def _search_for_test(self, test_name: str) -> TestCodeInfo | None:
        """Search for a test using GitHub code search API."""
        base_name = self._extract_base_test_name(test_name)
        session = await self._get_session()
        
        # Search for the function definition
        query = f"def {base_name} repo:{self.repo} language:python"
        url = f"{self.GITHUB_API_BASE}/search/code?q={query}"
        
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning("github_search_failed", status=resp.status)
                    return None
                
                data = await resp.json()
                items = data.get("items", [])
                
                if not items:
                    return None
                
                # Get the first matching file
                file_path = items[0]["path"]
                content = await self._fetch_file_content(file_path)
                
                if content:
                    function_code, line_start, line_end = self._extract_function(content, base_name)
                    
                    return TestCodeInfo(
                        test_name=test_name,
                        file_path=file_path,
                        function_name=base_name,
                        source_code=function_code or content,
                        repo=self.repo,
                        branch=self.branch,
                        line_start=line_start,
                        line_end=line_end,
                        github_url=f"https://github.com/{self.repo}/blob/{self.branch}/{file_path}",
                    )
                
                return None
                
        except Exception as e:
            logger.error("test_search_failed", error=str(e))
            return None
    
    def _extract_base_test_name(self, test_name: str) -> str:
        """Extract base test name without pytest parameters."""
        # Remove parameters: test_foo[param1-param2] -> test_foo
        if "[" in test_name:
            test_name = test_name.split("[")[0]
        
        # Remove module prefix if present: module::test_foo -> test_foo
        if "::" in test_name:
            test_name = test_name.split("::")[-1]
        
        return test_name.strip()
    
    def _extract_function(
        self,
        content: str,
        function_name: str,
    ) -> tuple[str | None, int | None, int | None]:
        """Extract a specific function from Python source code.
        
        Returns:
            Tuple of (function_code, line_start, line_end)
        """
        lines = content.split("\n")
        
        # Find the function definition
        pattern = rf"(?:async\s+)?def\s+{re.escape(function_name)}\s*\("
        func_start = None
        
        for i, line in enumerate(lines):
            if re.search(pattern, line):
                func_start = i
                break
        
        if func_start is None:
            return None, None, None
        
        # Find the function end (next def at same or lower indentation, or end of file)
        base_indent = len(lines[func_start]) - len(lines[func_start].lstrip())
        func_end = len(lines)
        
        for i in range(func_start + 1, len(lines)):
            line = lines[i]
            stripped = line.lstrip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue
            
            current_indent = len(line) - len(stripped)
            
            # Check if we've reached a new function/class at same or lower indentation
            if current_indent <= base_indent and (
                stripped.startswith("def ") or 
                stripped.startswith("async def ") or
                stripped.startswith("class ")
            ):
                func_end = i
                break
        
        # Include decorator lines before the function
        decorator_start = func_start
        for i in range(func_start - 1, -1, -1):
            line = lines[i].strip()
            if line.startswith("@"):
                decorator_start = i
            elif line and not line.startswith("#"):
                break
        
        function_code = "\n".join(lines[decorator_start:func_end])
        
        return function_code, decorator_start + 1, func_end  # 1-indexed lines


class LocalCodeFetcher:
    """Fetches test source code from a local directory.
    
    Useful when you have a local clone of the test repository.
    """
    
    # Directories to exclude from indexing
    EXCLUDE_DIRS = {
        '.venv', 'venv', '.git', '__pycache__', 'node_modules',
        '.tox', '.nox', 'build', 'dist', '.eggs', '*.egg-info',
        'site-packages', '.mypy_cache', '.pytest_cache',
    }
    
    def __init__(self, base_path: Path | str):
        """Initialize local code fetcher.
        
        Args:
            base_path: Path to the root of the test repository
        """
        self.base_path = Path(base_path)
        self._file_index: dict[str, Path] = {}
    
    def _should_exclude(self, path: Path) -> bool:
        """Check if a path should be excluded from indexing."""
        parts = path.parts
        for part in parts:
            if part in self.EXCLUDE_DIRS:
                return True
            if part.endswith('.egg-info'):
                return True
        return False
    
    def build_file_index(self) -> dict[str, Path]:
        """Build an index of test files in the local directory."""
        if self._file_index:
            return self._file_index
        
        for py_file in self.base_path.rglob("*.py"):
            # Skip excluded directories
            if self._should_exclude(py_file):
                continue
            
            if py_file.name.startswith("test_") or py_file.name.endswith("_test.py"):
                try:
                    content = py_file.read_text()
                    functions = self._extract_test_functions(content)
                    for func_name in functions:
                        self._file_index[func_name] = py_file
                except Exception:
                    pass  # Skip files that can't be read
        
        return self._file_index
    
    def _extract_test_functions(self, content: str) -> list[str]:
        """Extract test function names from Python source code."""
        pattern = r"(?:async\s+)?def\s+(test_\w+)\s*\("
        return re.findall(pattern, content)
    
    def get_test_code(self, test_name: str) -> TestCodeInfo | None:
        """Get source code for a specific test."""
        base_name = test_name.split("[")[0].split("::")[-1].strip()
        
        if not self._file_index:
            self.build_file_index()
        
        file_path = self._file_index.get(base_name)
        if not file_path:
            for func_name, path in self._file_index.items():
                if base_name in func_name or func_name in base_name:
                    file_path = path
                    break
        
        if not file_path or not file_path.exists():
            return None
        
        content = file_path.read_text()
        
        # Extract the specific function
        lines = content.split("\n")
        pattern = rf"(?:async\s+)?def\s+{re.escape(base_name)}\s*\("
        
        func_start = None
        for i, line in enumerate(lines):
            if re.search(pattern, line):
                func_start = i
                break
        
        if func_start is None:
            return TestCodeInfo(
                test_name=test_name,
                file_path=str(file_path.relative_to(self.base_path)),
                function_name=base_name,
                source_code=content,
                repo="local",
                branch="local",
            )
        
        # Find function end
        base_indent = len(lines[func_start]) - len(lines[func_start].lstrip())
        func_end = len(lines)
        
        for i in range(func_start + 1, len(lines)):
            line = lines[i]
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            current_indent = len(line) - len(stripped)
            if current_indent <= base_indent and (
                stripped.startswith("def ") or 
                stripped.startswith("async def ") or
                stripped.startswith("class ")
            ):
                func_end = i
                break
        
        function_code = "\n".join(lines[func_start:func_end])
        
        return TestCodeInfo(
            test_name=test_name,
            file_path=str(file_path.relative_to(self.base_path)),
            function_name=base_name,
            source_code=function_code,
            repo="local",
            branch="local",
            line_start=func_start + 1,
            line_end=func_end,
        )
