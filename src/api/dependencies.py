"""API dependencies for dependency injection.

Separates dependencies to avoid circular imports.
"""

import os
from typing import Any

# Global state (set during app lifespan)
_cache = None
_rp_config: dict[str, Any] | None = None


def get_cache():
    """Get cache instance."""
    return _cache


def set_cache(cache):
    """Set cache instance."""
    global _cache
    _cache = cache


def get_rp_config() -> dict[str, Any] | None:
    """Get ReportPortal configuration."""
    return _rp_config


def set_rp_config(config: dict[str, Any]):
    """Set ReportPortal configuration."""
    global _rp_config
    _rp_config = config


def load_rp_config_from_env() -> dict[str, Any]:
    """Load RP configuration from environment variables."""
    return {
        "url": os.getenv("RP_URL", ""),
        "project": os.getenv("RP_PROJECT", ""),
        "username": os.getenv("RP_USERNAME", ""),
        "password": os.getenv("RP_PASSWORD", ""),
        "verify_ssl": os.getenv("RP_VERIFY_SSL", "true").lower() == "true",
    }
