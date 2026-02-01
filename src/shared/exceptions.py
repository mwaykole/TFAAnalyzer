"""Custom exceptions for the TFA application.

All custom exceptions should be defined here for consistency.
"""


class TFAError(Exception):
    """Base exception for all TFA errors."""
    pass


class ConfigurationError(TFAError):
    """Error in configuration."""
    pass


class ReportPortalError(TFAError):
    """Error communicating with ReportPortal."""
    pass


class LLMError(TFAError):
    """Error from LLM provider."""
    pass


class LLMRateLimitError(LLMError):
    """Rate limit exceeded for LLM provider."""
    pass


class LLMContextLengthError(LLMError):
    """Context length exceeded for LLM provider."""
    pass


class CacheError(TFAError):
    """Error with cache operations."""
    pass


class VerificationError(TFAError):
    """Error during test verification."""
    pass


class CodeFetchError(TFAError):
    """Error fetching test source code."""
    pass
