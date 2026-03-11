"""LLM Provider interface following Open/Closed Principle.

New LLM providers can be added without modifying existing code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.prompts.loader import get_prompt_loader


@dataclass
class LLMResponse:
    """Response from LLM provider."""
    
    content: str
    model: str
    provider: str
    tokens_used: int = 0
    cached: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "tokens_used": self.tokens_used,
            "cached": self.cached,
        }


class LLMProvider(ABC):
    """Abstract interface for LLM providers.
    
    Open/Closed Principle:
    - Open for extension: Add new providers (Claude, Groq, Ollama, Gemini)
    - Closed for modification: Existing code doesn't change
    
    Liskov Substitution:
    - Any LLMProvider implementation can be used interchangeably
    """
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get provider name."""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Get current model name."""
        pass
    
    @abstractmethod
    async def analyze(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Send analysis request to LLM.
        
        Args:
            system_prompt: System instructions for the LLM
            user_prompt: User message with the analysis request
            
        Returns:
            LLMResponse with the analysis result
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """Check if provider is available and configured."""
        pass
    
    async def think(self, evidence_prompt: str) -> str:
        """Thinker step: Propose initial analysis.
        
        Default implementation uses analyze() with thinking system prompt.
        """
        loader = get_prompt_loader()
        system = loader.render(
            "investigation/thinker_system.md",
            rhoai_context=loader.load("context/rhoai_knowledge.md"),
        )
        
        response = await self.analyze(system, evidence_prompt)
        return response.content
    
    async def critique(self, initial_rca: str, context: str) -> str:
        """Critic step: Challenge the analysis.
        
        Default implementation uses analyze() with critic system prompt.
        """
        loader = get_prompt_loader()
        system = loader.load("investigation/critic_system.md")
        prompt = loader.render(
            "investigation/critic_user.md",
            initial_rca=initial_rca[:1000],
            context=context,
        )
        
        response = await self.analyze(system, prompt)
        return response.content
    
    async def refine(
        self, initial_rca: str, critique: str, evidence_summary: str,
        patterns: str = "", suggested_confidence: str = "60%",
    ) -> str:
        """Refiner step: Produce final RCA.
        
        Default implementation uses analyze() with refiner system prompt.
        """
        loader = get_prompt_loader()
        system = loader.load("investigation/refiner_system.md")
        prompt = loader.render(
            "investigation/refiner_user.md",
            initial_rca=initial_rca[:800],
            critique=critique[:500],
            error_message=evidence_summary,
            patterns=patterns or "See evidence summary",
            suggested_confidence=suggested_confidence,
        )
        
        response = await self.analyze(system, prompt)
        return response.content
