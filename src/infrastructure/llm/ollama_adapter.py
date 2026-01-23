"""Ollama LLM adapter.

Implements LLMProvider interface for local Ollama.
Open/Closed: Implements abstract interface without modifying it.
"""

import aiohttp

from src.domain.interfaces.llm_provider import LLMProvider, LLMResponse


class OllamaAdapter(LLMProvider):
    """Ollama adapter for local LLM inference.
    
    Uses Ollama REST API for local model inference.
    Free to use, no API key required.
    """
    
    def __init__(
        self,
        model: str | None = None,
        host: str = "http://localhost:11434",
    ):
        """Initialize Ollama adapter."""
        self._model = model or "llama3.2"
        self._host = host.rstrip("/")
    
    @property
    def provider_name(self) -> str:
        return "ollama"
    
    @property
    def model_name(self) -> str:
        return self._model
    
    async def analyze(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Send analysis request via Ollama API."""
        url = f"{self._host}/api/generate"
        
        payload = {
            "model": self._model,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 4096,
            },
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error = await response.text()
                    raise RuntimeError(f"Ollama error: {error}")
                
                data = await response.json()
                
                return LLMResponse(
                    content=data.get("response", ""),
                    model=self._model,
                    provider=self.provider_name,
                    tokens_used=data.get("eval_count", 0),
                )
    
    async def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            url = f"{self._host}/api/tags"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    return response.status == 200
        except Exception:
            return False
