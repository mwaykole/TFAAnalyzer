"""LLM providers module - TRANSITIONAL.

This module provides backward compatibility for code that imports from src.llm.
The canonical implementations are in src.infrastructure.llm.

For new code, prefer:
    from src.infrastructure.llm import LLMFactory
    from src.domain.interfaces.llm_provider import LLMProvider
"""

import warnings

# Re-export the base interface and error
from src.llm.base import LLMProvider, LLMError

# Re-export the provider implementations
from src.llm.anthropic import AnthropicProvider
from src.llm.claude_cli import ClaudeCLIProvider
from src.llm.groq_provider import GroqProvider
from src.llm.ollama import OllamaProvider

# Also export the factory from infrastructure for convenience
try:
    from src.infrastructure.llm import LLMFactory
except ImportError:
    LLMFactory = None

__all__ = [
    "LLMProvider",
    "LLMError",
    "AnthropicProvider",
    "ClaudeCLIProvider",
    "GroqProvider",
    "OllamaProvider",
    "LLMFactory",
]
