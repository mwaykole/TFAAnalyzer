"""Local filesystem code fetcher implementation.

Implements the CodeFetcher interface for local test repositories.
"""

import re
from pathlib import Path

from src.domain.interfaces.code_fetcher import CodeFetcher, TestCodeInfo
from src.utils.logging import get_logger

logger = get_logger(__name__)


class LocalCodeFetcher(CodeFetcher):
    """Fetches test source code from a local directory.
    
    Implements CodeFetcher interface for local filesystems.
    Useful when you have a local clone of the test repository.
    """
    
    EXCLUDE_DIRS = {
        '.venv', 'venv', '.git', '__pycache__', 'node_modules',
        '.tox', '.nox', 'build', 'dist', '.eggs',
        'site-packages', '.mypy_cache', '.pytest_cache',
    }
    
    def __init__(self, base_path: Path | str, github_repo: str = "", github_branch: str = "main"):
        """Initialize local code fetcher.
        
        Args:
            base_path: Path to the root of the test repository
            github_repo: Optional GitHub repo for generating URLs (owner/repo format)
            github_branch: Branch name for GitHub URLs
        """
        self.base_path = Path(base_path)
        self.github_repo = github_repo
        self.github_branch = github_branch
        self._file_index: dict[str, Path] = {}
        self._test_parser: "TestParser | None" = None
    
    def _should_exclude(self, path: Path) -> bool:
        """Check if a path should be excluded from indexing."""
        for part in path.parts:
            if part in self.EXCLUDE_DIRS:
                return True
            if part.endswith('.egg-info'):
                return True
        return False
    
    async def build_index(self) -> dict[str, str]:
        """Build an index of test files in the local directory."""
        if self._file_index:
            return {k: str(v) for k, v in self._file_index.items()}
        
        logger.info("building_local_file_index", path=str(self.base_path))
        
        for py_file in self.base_path.rglob("*.py"):
            if self._should_exclude(py_file):
                continue
            
            if py_file.name.startswith("test_") or py_file.name.endswith("_test.py"):
                try:
                    content = py_file.read_text()
                    functions = self._extract_test_functions(content)
                    for func_name in functions:
                        self._file_index[func_name] = py_file
                except Exception:
                    pass
        
        logger.info("indexed_tests", count=len(self._file_index))
        return {k: str(v) for k, v in self._file_index.items()}
    
    def _extract_test_functions(self, content: str) -> list[str]:
        """Extract test function names from Python source code."""
        pattern = r"(?:async\s+)?def\s+(test_\w+)\s*\("
        return re.findall(pattern, content)
    
    async def fetch_test_code(self, test_name: str) -> TestCodeInfo | None:
        """Get source code for a specific test."""
        base_name = test_name.split("[")[0].split("::")[-1].strip()
        
        if not self._file_index:
            await self.build_index()
        
        file_path = self._file_index.get(base_name)
        if not file_path:
            for func_name, path in self._file_index.items():
                if base_name in func_name or func_name in base_name:
                    file_path = path
                    break
        
        if not file_path or not file_path.exists():
            logger.warning("test_not_found_locally", test_name=test_name)
            return None
        
        content = file_path.read_text()
        function_code, line_start, line_end = self._extract_function(content, base_name)
        
        rel_path = str(file_path.relative_to(self.base_path))
        github_url = self.get_github_url(rel_path, line_start) if self.github_repo else ""
        
        test_info = TestCodeInfo(
            test_name=test_name,
            file_path=rel_path,
            function_name=base_name,
            source_code=function_code or content,
            repo=self.github_repo or "local",
            branch=self.github_branch if self.github_repo else "local",
            line_start=line_start,
            line_end=line_end,
            github_url=github_url,
        )
        
        # Enhance with AST parsing
        self._enhance_with_parser(test_info, function_code or content)
        
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
    
    def get_github_url(self, file_path: str, line: int | None = None) -> str:
        """Generate GitHub URL for a file/line."""
        if not self.github_repo:
            return ""
        url = f"https://github.com/{self.github_repo}/blob/{self.github_branch}/{file_path}"
        if line:
            url += f"#L{line}"
        return url
    
    def _extract_function(
        self,
        content: str,
        function_name: str,
    ) -> tuple[str | None, int | None, int | None]:
        """Extract a specific function from Python source code.
        
        Delegates to shared utility to avoid code duplication.
        """
        from src.infrastructure.code_fetcher.utils import extract_function_from_source
        return extract_function_from_source(content, function_name, include_decorators=True)
