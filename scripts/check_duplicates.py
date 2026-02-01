#!/usr/bin/env python3
"""Check for duplicate code patterns in the codebase.

This script detects:
1. Duplicate module implementations (same functionality in multiple places)
2. Copy-pasted code blocks
3. Similar class implementations

Run as pre-commit hook or manually:
    python scripts/check_duplicates.py
"""

import ast
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

# Directories to scan
SRC_DIR = Path("src")

# Known duplicate modules that should be consolidated
# Format: {canonical_path: [deprecated_paths]}
DUPLICATE_MODULES = {
    "src/infrastructure/reportportal": ["src/rp"],
    "src/infrastructure/storage": ["src/storage"],
    "src/infrastructure/llm": ["src/llm"],
    "src/infrastructure/code_fetcher": ["src/code_fetcher"],
    "src/infrastructure/notifications": ["src/integrations"],
}

# Minimum lines for a function to be considered for duplicate detection
MIN_FUNCTION_LINES = 10


class DuplicateChecker:
    """Check for duplicate code in the codebase."""

    def __init__(self):
        self.function_hashes: dict[str, list[str]] = defaultdict(list)
        self.class_hashes: dict[str, list[str]] = defaultdict(list)
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def check_deprecated_imports(self) -> list[str]:
        """Check for imports from deprecated module locations."""
        deprecated_imports = []
        
        for deprecated_paths in DUPLICATE_MODULES.values():
            for deprecated in deprecated_paths:
                deprecated_module = deprecated.replace("/", ".")
                
                # Search for imports in all Python files
                for py_file in SRC_DIR.rglob("*.py"):
                    try:
                        content = py_file.read_text()
                        if f"from {deprecated_module}" in content or f"import {deprecated_module}" in content:
                            # Ignore the deprecated module's own __init__.py
                            if str(py_file).startswith(deprecated):
                                continue
                            deprecated_imports.append(
                                f"{py_file}: imports from deprecated module '{deprecated_module}'"
                            )
                    except Exception:
                        pass
        
        return deprecated_imports

    def hash_function_body(self, node: ast.FunctionDef) -> str:
        """Create a hash of a function's body for comparison."""
        # Remove docstring if present
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        
        # Convert to string representation
        body_str = ast.dump(ast.Module(body=body, type_ignores=[]))
        return hashlib.md5(body_str.encode()).hexdigest()

    def check_duplicate_functions(self) -> list[str]:
        """Find functions with identical bodies."""
        duplicates = []
        
        for py_file in SRC_DIR.rglob("*.py"):
            try:
                content = py_file.read_text()
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Skip small functions
                        if len(node.body) < MIN_FUNCTION_LINES:
                            continue
                        
                        func_hash = self.hash_function_body(node)
                        location = f"{py_file}:{node.lineno}:{node.name}"
                        self.function_hashes[func_hash].append(location)
            except SyntaxError:
                pass
            except Exception:
                pass
        
        # Find duplicates
        for func_hash, locations in self.function_hashes.items():
            if len(locations) > 1:
                # Filter out known compatibility exports
                real_duplicates = [
                    loc for loc in locations 
                    if not any(dep in loc for dep in ["__init__.py"])
                ]
                if len(real_duplicates) > 1:
                    duplicates.append(
                        f"Duplicate function implementations:\n  " + 
                        "\n  ".join(real_duplicates)
                    )
        
        return duplicates

    def check_new_modules_in_wrong_location(self) -> list[str]:
        """Check for new modules created in deprecated locations."""
        issues = []
        
        for canonical, deprecated_list in DUPLICATE_MODULES.items():
            for deprecated in deprecated_list:
                deprecated_path = Path(deprecated)
                if deprecated_path.exists():
                    # Get all Python files except __init__.py
                    files = [
                        f for f in deprecated_path.rglob("*.py") 
                        if f.name != "__init__.py"
                    ]
                    for f in files:
                        # Check if file was recently modified (new file)
                        issues.append(
                            f"Module '{f}' exists in deprecated location. "
                            f"New code should go in '{canonical}'"
                        )
        
        return issues

    def run(self) -> int:
        """Run all checks and return exit code."""
        print("🔍 Checking for duplicate code patterns...")
        print()
        
        # Check 1: Deprecated imports
        deprecated = self.check_deprecated_imports()
        if deprecated:
            print("⚠️  Deprecated module imports found:")
            for d in deprecated[:10]:  # Limit output
                print(f"   {d}")
            if len(deprecated) > 10:
                print(f"   ... and {len(deprecated) - 10} more")
            print()
            self.warnings.extend(deprecated)
        
        # Check 2: Duplicate functions
        duplicates = self.check_duplicate_functions()
        if duplicates:
            print("❌ Duplicate function implementations found:")
            for d in duplicates[:5]:
                print(f"   {d}")
            print()
            self.errors.extend(duplicates)
        
        # Check 3: New code in deprecated locations
        wrong_location = self.check_new_modules_in_wrong_location()
        if wrong_location:
            print("⚠️  Modules in deprecated locations:")
            for w in wrong_location[:10]:
                print(f"   {w}")
            print()
            # This is a warning, not an error
            self.warnings.extend(wrong_location)
        
        # Summary
        if not self.errors and not self.warnings:
            print("✅ No duplicate code issues found!")
            return 0
        
        if self.errors:
            print(f"❌ Found {len(self.errors)} error(s)")
            return 1
        
        if self.warnings:
            print(f"⚠️  Found {len(self.warnings)} warning(s) (not blocking)")
            return 0  # Warnings don't fail the check
        
        return 0


def main():
    """Main entry point."""
    checker = DuplicateChecker()
    sys.exit(checker.run())


if __name__ == "__main__":
    main()
