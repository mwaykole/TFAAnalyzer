#!/usr/bin/env python3
"""Check for imports from deprecated module locations.

This script enforces the clean architecture by detecting imports
from deprecated module paths and suggesting the correct imports.

Run as pre-commit hook or manually:
    python scripts/check_deprecated_imports.py
"""

import re
import sys
from pathlib import Path

# Deprecated imports and their replacements
DEPRECATED_IMPORTS = {
    # Old ReportPortal location
    r"from src\.rp\.": "from src.infrastructure.reportportal.",
    r"from src\.rp import": "from src.infrastructure.reportportal import",
    r"import src\.rp\.": "import src.infrastructure.reportportal.",
    
    # Old storage location
    r"from src\.storage\.": "from src.infrastructure.storage.",
    r"from src\.storage import": "from src.infrastructure.storage import",
    
    # Old integrations location
    r"from src\.integrations\.": "from src.infrastructure.notifications.",
    r"from src\.integrations import": "from src.infrastructure.notifications import",
    
    # Old code_fetcher location  
    r"from src\.code_fetcher\.": "from src.infrastructure.code_fetcher.",
    r"from src\.code_fetcher import": "from src.infrastructure.code_fetcher import",
}

# Files to exclude from checking (compatibility layers themselves)
EXCLUDE_FILES = [
    "src/rp/__init__.py",
    "src/storage/__init__.py",
    "src/llm/__init__.py",
    "src/code_fetcher/__init__.py",
    "src/integrations/__init__.py",
    "src/learning/__init__.py",
]

# Directories to skip entirely
SKIP_DIRS = [
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".tfa_cache",
]


def check_file(filepath: Path) -> list[tuple[int, str, str]]:
    """Check a file for deprecated imports.
    
    Returns:
        List of (line_number, deprecated_import, suggested_replacement)
    """
    issues = []
    
    try:
        content = filepath.read_text()
        lines = content.split("\n")
        
        for line_num, line in enumerate(lines, 1):
            for deprecated_pattern, replacement in DEPRECATED_IMPORTS.items():
                if re.search(deprecated_pattern, line):
                    # Extract the actual import statement
                    match = re.search(deprecated_pattern + r"[^\s]*", line)
                    if match:
                        deprecated = match.group(0)
                        suggested = re.sub(deprecated_pattern, replacement, deprecated)
                        issues.append((line_num, deprecated, suggested))
    except Exception as e:
        print(f"Warning: Could not read {filepath}: {e}", file=sys.stderr)
    
    return issues


def main():
    """Main entry point."""
    src_dir = Path("src")
    
    if not src_dir.exists():
        print("Error: src/ directory not found", file=sys.stderr)
        sys.exit(1)
    
    all_issues: dict[str, list] = {}
    
    # Find all Python files
    for py_file in src_dir.rglob("*.py"):
        # Skip excluded files
        if any(str(py_file).endswith(exc) for exc in EXCLUDE_FILES):
            continue
        
        # Skip excluded directories
        if any(skip in str(py_file) for skip in SKIP_DIRS):
            continue
        
        issues = check_file(py_file)
        if issues:
            all_issues[str(py_file)] = issues
    
    # Report results
    if not all_issues:
        print("✅ No deprecated imports found!")
        sys.exit(0)
    
    print("❌ Found deprecated imports that should be updated:\n")
    
    for filepath, issues in sorted(all_issues.items()):
        print(f"📁 {filepath}")
        for line_num, deprecated, suggested in issues:
            print(f"   Line {line_num}: {deprecated}")
            print(f"            → {suggested}")
        print()
    
    total = sum(len(issues) for issues in all_issues.values())
    print(f"Total: {total} deprecated import(s) in {len(all_issues)} file(s)")
    print("\nPlease update these imports to use the new module locations.")
    print("See docs/DEVELOPER_GUIDE.md for the module structure.")
    
    # Exit with error to fail pre-commit
    sys.exit(1)


if __name__ == "__main__":
    main()
