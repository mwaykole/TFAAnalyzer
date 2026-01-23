"""LLM Provider interface following Open/Closed Principle.

New LLM providers can be added without modifying existing code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


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
        system = """You are a senior RHOAI QE engineer. Analyze test failures concisely.
Be specific about the root cause. Consider RHOAI component interactions."""
        
        response = await self.analyze(system, evidence_prompt)
        return response.content
    
    async def critique(self, initial_rca: str, context: str) -> str:
        """Critic step: Challenge the analysis.
        
        Default implementation uses analyze() with critic system prompt.
        """
        system = "You are a critical code reviewer. Find flaws in reasoning. Be brief."
        prompt = f"""Review this RCA:

{initial_rca[:500]}

Additional context: {context}

Challenge:
1. What assumptions might be wrong?
2. Alternative explanations?
3. Missing evidence?

Be rigorous but concise."""
        
        response = await self.analyze(system, prompt)
        return response.content
    
    async def refine(
        self, initial_rca: str, critique: str, evidence_summary: str
    ) -> str:
        """Refiner step: Produce final RCA.
        
        Default implementation uses analyze() with refiner system prompt.
        """
        system = "You are an expert QE engineer. Provide final structured analysis."
        prompt = f"""Finalize RCA considering initial analysis and critique.

INITIAL: {initial_rca[:400]}

CRITIQUE: {critique[:300]}

EVIDENCE: {evidence_summary}

Format EXACTLY:
CLASSIFICATION: [Product Bug|Test Automation Issue|Infrastructure Issue|Intermittent Failure]
CONFIDENCE: [number]%
SEVERITY: [LOW|MEDIUM|HIGH|CRITICAL]
ROOT_CAUSE: [one specific sentence]
REASONING: [2 sentences max]
RECOMMENDATION: [actionable steps]"""
        
        response = await self.analyze(system, prompt)
        return response.content
