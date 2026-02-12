"""Prompt management module for LLM interactions.

This module provides centralized prompt management with:
- File-based prompts for easy editing and version control
- Template variable substitution
- Caching for performance
- Backward compatibility with existing code
"""

from src.prompts.loader import PromptLoader, get_prompt_loader

__all__ = [
    "PromptLoader",
    "get_prompt_loader",
]
