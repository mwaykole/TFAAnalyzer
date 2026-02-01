"""Shared module for cross-cutting concerns.

This module contains utilities that are used across all layers:
- Logging configuration
- Configuration loading
- Custom exceptions
- Common types

These are intentionally allowed to be imported from any layer.
"""

from src.utils.logging import get_logger, setup_logging
from src.utils.config import Settings, create_settings

__all__ = [
    "get_logger",
    "setup_logging",
    "Settings",
    "create_settings",
]
