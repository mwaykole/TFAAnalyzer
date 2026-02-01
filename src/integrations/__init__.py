"""Integrations module - DEPRECATED.

This module is deprecated. Please import from:
    src.infrastructure.notifications

This file exists for backward compatibility only.
"""

import warnings

warnings.warn(
    "src.integrations is deprecated. Use src.infrastructure.notifications instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new location
from src.infrastructure.notifications import SlackNotifier, TeamsNotifier

__all__ = ["SlackNotifier", "TeamsNotifier"]
