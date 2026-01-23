"""GitHub code fetcher implementation.

Implements the CodeFetcher interface for fetching test code from GitHub.
"""

import os
import re
from pathlib import Path

import aiohttp

from src.domain.interfaces.code_fetcher import CodeFetcher, TestCodeInfo
from src.utils.logging import get_logger

logger = get_logger(__name__)


class GitHubCodeFetcher(CodeFetcher):
    """Fetches test source code from GitHub repositories.
    
    Implements CodeFetcher interface for GitHub.
    Supports mapping pytest test names to source files and extracting
    relevant test functions.
    """
    
    GITHUB_API_BASE = "https://api.github.com"
    GITHUB_RAW_BASE = "https://raw.githubusercontent.com"
    
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
        self._file_index: dict[str, str] = {}
        self._test_parser: "TestParser | None" = None
    
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
    
    async def build_index(self) -> dict[str, str]:
        """Build an index of test files in the repository."""
        if self._file_index:
            return self._file_index
        
        logger.info("building_github_file_index", repo=self.repo, test_dir=self.test_dir)
        
        session = await self._get_session()
        url = f"{self.GITHUB_API_BASE}/repos/{self.repo}/git/trees/{self.branch}?recursive=1"
        
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.error("github_tree_fetch_failed", status=resp.status)
                    return {}
                
                data = await resp.json()
                
                test_files = []
                for item in data.get("tree", []):
                    if item["type"] == "blob":
                        path = item["path"]
                        if self._is_test_file(path):
                            test_files.append(path)
                
                logger.info("found_test_files", count=len(test_files))
                
                # Index first 50 files to avoid rate limits
                for file_path in test_files[:50]:
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
        
        if filename.startswith("test_") or filename.endswith("_test.py"):
            return True
        
        if self.test_dir and self.test_dir in path:
            return True
        
        return False
    
    def _extract_test_functions(self, content: str) -> list[str]:
        """Extract test function names from Python source code."""
        pattern = r"(?:async\s+)?def\s+(test_\w+)\s*\("
        return re.findall(pattern, content)
    
    async def _fetch_file_content(self, file_path: str) -> str | None:
        """Fetch raw file content from GitHub."""
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
                cache_file.write_text(content)
                return content
                
        except Exception as e:
            logger.error("file_fetch_failed", path=file_path, error=str(e))
            return None
    
    async def fetch_test_code(self, test_name: str) -> TestCodeInfo | None:
        """Fetch source code for a specific test."""
        base_name = self._extract_base_test_name(test_name)
        
        if not self._file_index:
            await self.build_index()
        
        file_path = self._file_index.get(base_name)
        
        if not file_path:
            for func_name, path in self._file_index.items():
                if base_name in func_name or func_name in base_name:
                    file_path = path
                    break
        
        if not file_path:
            logger.warning("test_not_found_in_index", test_name=test_name)
            return await self._search_for_test(test_name)
        
        content = await self._fetch_file_content(file_path)
        if not content:
            return None
        
        function_code, line_start, line_end = self._extract_function(content, base_name)
        
        if not function_code:
            function_code = content
        
        github_url = self.get_github_url(file_path, line_start)
        
        # Parse for metadata
        test_info = TestCodeInfo(
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
        
        # Enhance with AST parsing
        self._enhance_with_parser(test_info, function_code)
        
        return test_info
    
    def _enhance_with_parser(self, test_info: TestCodeInfo, source: str) -> None:
        """Enhance test info with AST parsing metadata."""
        try:
            from src.infrastructure.code_fetcher.test_parser import TestParser
            
            if self._test_parser is None:
                self._test_parser = TestParser()
            
            parsed_tests = self._test_parser.parse_source(source, test_info.file_path)
            for parsed in parsed_tests:
                if parsed.name == test_info.function_name or test_info.function_name in parsed.name:
                    test_info.decorators = parsed.decorators
                    test_info.fixtures = parsed.fixtures
                    test_info.has_timeout = parsed.has_timeout
                    test_info.timeout_value = parsed.timeout_value
                    test_info.has_retry = parsed.has_retry
                    test_info.uses_sleep = parsed.uses_sleep
                    test_info.wait_patterns = parsed.waits_for
                    test_info.parametrize_args = parsed.parametrize_args
                    break
        except Exception as e:
            logger.debug("parser_enhancement_failed", error=str(e))
    
    async def _search_for_test(self, test_name: str) -> TestCodeInfo | None:
        """Search for a test using GitHub code search API."""
        base_name = self._extract_base_test_name(test_name)
        session = await self._get_session()
        
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
                
                file_path = items[0]["path"]
                content = await self._fetch_file_content(file_path)
                
                if content:
                    function_code, line_start, line_end = self._extract_function(content, base_name)
                    
                    test_info = TestCodeInfo(
                        test_name=test_name,
                        file_path=file_path,
                        function_name=base_name,
                        source_code=function_code or content,
                        repo=self.repo,
                        branch=self.branch,
                        line_start=line_start,
                        line_end=line_end,
                        github_url=self.get_github_url(file_path, line_start),
                    )
                    
                    self._enhance_with_parser(test_info, function_code or content)
                    return test_info
                
                return None
                
        except Exception as e:
            logger.error("test_search_failed", error=str(e))
            return None
    
    def get_github_url(self, file_path: str, line: int | None = None) -> str:
        """Generate GitHub URL for a file/line."""
        url = f"https://github.com/{self.repo}/blob/{self.branch}/{file_path}"
        if line:
            url += f"#L{line}"
        return url
    
    def _extract_base_test_name(self, test_name: str) -> str:
        """Extract base test name without pytest parameters."""
        if "[" in test_name:
            test_name = test_name.split("[")[0]
        if "::" in test_name:
            test_name = test_name.split("::")[-1]
        return test_name.strip()
    
    def _extract_function(
        self,
        content: str,
        function_name: str,
    ) -> tuple[str | None, int | None, int | None]:
        """Extract a specific function from Python source code."""
        lines = content.split("\n")
        pattern = rf"(?:async\s+)?def\s+{re.escape(function_name)}\s*\("
        func_start = None
        
        for i, line in enumerate(lines):
            if re.search(pattern, line):
                func_start = i
                break
        
        if func_start is None:
            return None, None, None
        
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
        
        # Include decorators
        decorator_start = func_start
        for i in range(func_start - 1, -1, -1):
            line = lines[i].strip()
            if line.startswith("@"):
                decorator_start = i
            elif line and not line.startswith("#"):
                break
        
        function_code = "\n".join(lines[decorator_start:func_end])
        return function_code, decorator_start + 1, func_end
