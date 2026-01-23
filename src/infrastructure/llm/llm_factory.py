"""LLM Provider Factory.

Open/Closed Principle: Add new providers without modifying existing code.
Factory Pattern: Centralizes provider creation logic.
"""

from typing import Literal

from src.domain.interfaces.llm_provider import LLMProvider


ProviderType = Literal["claude-cli", "anthropic", "groq", "ollama"]


class LLMFactory:
    """Factory for creating LLM providers.
    
    Open/Closed Principle:
    - Open for extension: Register new providers dynamically
    - Closed for modification: Core factory logic doesn't change
    """
    
    _providers: dict[str, type] = {}
    
    @classmethod
    def register(cls, name: str, provider_class: type):
        """Register a new provider type."""
        cls._providers[name] = provider_class
    
    @classmethod
    def create(
        cls,
        provider_type: ProviderType | str,
        api_key: str | None = None,
        model: str | None = None,
        **kwargs,
    ) -> LLMProvider:
        """Create an LLM provider instance.
        
        Args:
            provider_type: Type of provider (claude-cli, anthropic, groq, ollama)
            api_key: API key for the provider (if required)
            model: Model name to use
            **kwargs: Additional provider-specific arguments
            
        Returns:
            LLMProvider instance
            
        Raises:
            ValueError: If provider type is unknown
        """
        if provider_type == "claude-cli":
            from src.infrastructure.llm.claude_adapter import ClaudeAdapter
            return ClaudeAdapter(model=model)
        
        elif provider_type == "anthropic":
            from src.infrastructure.llm.claude_adapter import AnthropicAdapter
            if not api_key:
                import os
                api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY required for anthropic provider")
            return AnthropicAdapter(api_key=api_key, model=model)
        
        elif provider_type == "groq":
            from src.infrastructure.llm.groq_adapter import GroqAdapter
            if not api_key:
                import os
                api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY required for groq provider")
            return GroqAdapter(api_key=api_key, model=model)
        
        elif provider_type == "ollama":
            from src.infrastructure.llm.ollama_adapter import OllamaAdapter
            return OllamaAdapter(model=model, **kwargs)
        
        elif provider_type in cls._providers:
            return cls._providers[provider_type](api_key=api_key, model=model, **kwargs)
        
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")
    
    @classmethod
    def available_providers(cls) -> list[str]:
        """Get list of available provider types."""
        builtin = ["claude-cli", "anthropic", "groq", "ollama"]
        custom = list(cls._providers.keys())
        return builtin + custom
