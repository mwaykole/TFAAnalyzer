"""AST-based test code parser for extracting test metadata.

Parses Python test files to extract:
1. Test decorators (pytest marks, parametrize, etc.)
2. Fixtures used by tests
3. Imports and dependencies
4. Timeout and retry configurations
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedTest:
    """Parsed test function with metadata."""
    
    name: str
    file_path: str
    line_number: int
    decorators: list[str] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    has_timeout: bool = False
    timeout_value: int | None = None
    has_retry: bool = False
    retry_count: int | None = None
    waits_for: list[str] = field(default_factory=list)
    uses_sleep: bool = False
    parametrize_args: list[str] = field(default_factory=list)
    docstring: str = ""
    
    @property
    def is_potentially_flaky(self) -> bool:
        """Check if test has flakiness indicators."""
        indicators = [
            self.uses_sleep,
            self.has_timeout,
            len(self.waits_for) > 0,
            "flaky" in " ".join(self.decorators).lower(),
            "skip" in " ".join(self.decorators).lower(),
        ]
        return sum(indicators) >= 2


class TestParser:
    """AST-based parser for Python test files.
    
    Extracts metadata from test functions including decorators,
    fixtures, and patterns that might indicate flakiness.
    """
    
    # Patterns that indicate waiting/polling
    WAIT_PATTERNS = [
        r"wait_for_\w+",
        r"poll_until\w*",
        r"wait_until\w*",
        r"TimeoutSampler",
        r"retry\s*\(",
        r"time\.sleep",
    ]
    
    def __init__(self):
        """Initialize the parser."""
        self._wait_patterns = [re.compile(p, re.IGNORECASE) for p in self.WAIT_PATTERNS]
    
    def parse_file(self, file_path: Path | str) -> list[ParsedTest]:
        """Parse a test file and extract all test functions.
        
        Args:
            file_path: Path to Python test file
            
        Returns:
            List of ParsedTest objects
        """
        file_path = Path(file_path)
        if not file_path.exists():
            logger.warning("file_not_found", path=str(file_path))
            return []
        
        try:
            source = file_path.read_text()
            return self.parse_source(source, str(file_path))
        except Exception as e:
            logger.error("parse_file_error", path=str(file_path), error=str(e))
            return []
    
    def parse_source(self, source: str, file_path: str = "<string>") -> list[ParsedTest]:
        """Parse source code and extract test functions.
        
        Args:
            source: Python source code
            file_path: Path for reference
            
        Returns:
            List of ParsedTest objects
        """
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            logger.error("syntax_error", file=file_path, error=str(e))
            return []
        
        # Extract module-level imports
        imports = self._extract_imports(tree)
        
        tests = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                parsed = self._parse_function(node, file_path, source, imports)
                tests.append(parsed)
        
        logger.debug("parsed_tests", file=file_path, count=len(tests))
        return tests
    
    def _extract_imports(self, tree: ast.Module) -> list[str]:
        """Extract import statements from module."""
        imports = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}")
        return imports
    
    def _parse_function(
        self,
        node: ast.FunctionDef,
        file_path: str,
        source: str,
        module_imports: list[str],
    ) -> ParsedTest:
        """Parse a single test function."""
        parsed = ParsedTest(
            name=node.name,
            file_path=file_path,
            line_number=node.lineno,
            imports=module_imports.copy(),
        )
        
        # Extract docstring
        parsed.docstring = ast.get_docstring(node) or ""
        
        # Extract decorators
        for decorator in node.decorator_list:
            dec_str = self._decorator_to_string(decorator)
            parsed.decorators.append(dec_str)
            
            # Check for specific decorators
            if "timeout" in dec_str.lower():
                parsed.has_timeout = True
                # Try to extract timeout value
                if isinstance(decorator, ast.Call):
                    for arg in decorator.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)):
                            parsed.timeout_value = int(arg.value)
                            break
            
            if "retry" in dec_str.lower() or "flaky" in dec_str.lower():
                parsed.has_retry = True
            
            if "parametrize" in dec_str.lower():
                # Extract parametrize argument names
                if isinstance(decorator, ast.Call) and decorator.args:
                    first_arg = decorator.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                        parsed.parametrize_args = [
                            a.strip() for a in first_arg.value.split(",")
                        ]
        
        # Extract fixtures from function arguments
        for arg in node.args.args:
            if arg.arg not in ("self", "cls"):
                parsed.fixtures.append(arg.arg)
        
        # Analyze function body for patterns
        self._analyze_body(node, parsed, source)
        
        return parsed
    
    def _decorator_to_string(self, decorator: ast.expr) -> str:
        """Convert decorator AST node to string representation."""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Attribute):
            parts = []
            node = decorator
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                parts.append(node.id)
            return ".".join(reversed(parts))
        elif isinstance(decorator, ast.Call):
            func_str = self._decorator_to_string(decorator.func)
            return f"{func_str}(...)"
        return str(decorator)
    
    def _analyze_body(
        self,
        node: ast.FunctionDef,
        parsed: ParsedTest,
        source: str,
    ) -> None:
        """Analyze function body for patterns."""
        # Get source lines for this function
        start_line = node.lineno - 1
        end_line = node.end_lineno or start_line + 1
        lines = source.split("\n")[start_line:end_line]
        func_source = "\n".join(lines)
        
        # Check for sleep usage
        if "sleep(" in func_source or "time.sleep" in func_source:
            parsed.uses_sleep = True
        
        # Check for wait patterns
        for pattern in self._wait_patterns:
            matches = pattern.findall(func_source)
            if matches:
                parsed.waits_for.extend(matches)
        
        # Look for specific method calls
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func_name = self._get_call_name(child)
                if func_name:
                    if "timeout" in func_name.lower():
                        parsed.has_timeout = True
                    if "retry" in func_name.lower():
                        parsed.has_retry = True
                    if any(w in func_name.lower() for w in ["wait", "poll", "sampler"]):
                        parsed.waits_for.append(func_name)
    
    def _get_call_name(self, call: ast.Call) -> str | None:
        """Get the name of a function call."""
        if isinstance(call.func, ast.Name):
            return call.func.id
        elif isinstance(call.func, ast.Attribute):
            return call.func.attr
        return None
    
    def find_test(self, tests: list[ParsedTest], test_name: str) -> ParsedTest | None:
        """Find a test by name (supports partial matching).
        
        Args:
            tests: List of parsed tests
            test_name: Name to search for
            
        Returns:
            Matching ParsedTest or None
        """
        # Extract just the function name if full path given
        func_name = test_name.split("::")[-1] if "::" in test_name else test_name
        func_name = func_name.split("[")[0]  # Remove parametrize suffix
        
        # Exact match first
        for t in tests:
            if t.name == func_name:
                return t
        
        # Partial match
        for t in tests:
            if func_name in t.name or t.name in func_name:
                return t
        
        return None
    
    def get_test_metadata(self, test: ParsedTest) -> dict[str, Any]:
        """Get metadata dict for a parsed test.
        
        Args:
            test: ParsedTest object
            
        Returns:
            Dict with test metadata
        """
        return {
            "name": test.name,
            "file": test.file_path,
            "line": test.line_number,
            "decorators": test.decorators,
            "fixtures": test.fixtures,
            "has_timeout": test.has_timeout,
            "timeout_value": test.timeout_value,
            "has_retry": test.has_retry,
            "uses_sleep": test.uses_sleep,
            "wait_patterns": test.waits_for,
            "is_potentially_flaky": test.is_potentially_flaky,
            "parametrize_args": test.parametrize_args,
        }
