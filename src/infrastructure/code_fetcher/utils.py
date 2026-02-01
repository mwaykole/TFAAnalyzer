"""Shared utilities for code fetcher adapters.

This module contains shared helper functions to avoid code duplication
across different code fetcher adapter implementations.
"""

import re


def extract_function_from_source(
    content: str,
    function_name: str,
    include_decorators: bool = True,
) -> tuple[str | None, int | None, int | None]:
    """Extract a specific function from Python source code.
    
    Args:
        content: Python source code content
        function_name: Name of the function to extract
        include_decorators: Whether to include decorators in the extracted code
        
    Returns:
        Tuple of (function_source, start_line, end_line) or (None, None, None) if not found
        Line numbers are 1-indexed.
    """
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
    
    # Find function end
    for i in range(func_start + 1, len(lines)):
        line = lines[i]
        stripped = line.lstrip()
        
        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            continue
        
        current_indent = len(line) - len(stripped)
        
        # Check if we've reached a new definition at the same or lower indent level
        if current_indent <= base_indent and (
            stripped.startswith("def ") or 
            stripped.startswith("async def ") or
            stripped.startswith("class ")
        ):
            func_end = i
            break
    
    # Include decorators if requested
    decorator_start = func_start
    if include_decorators:
        for i in range(func_start - 1, -1, -1):
            line = lines[i].strip()
            if line.startswith("@"):
                decorator_start = i
            elif line and not line.startswith("#"):
                break
    
    function_code = "\n".join(lines[decorator_start:func_end])
    return function_code, decorator_start + 1, func_end  # 1-indexed lines
