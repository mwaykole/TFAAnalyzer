"""Groq LLM adapter.

Implements LLMProvider interface for Groq API.
Open/Closed: Implements abstract interface without modifying it.
"""

from src.domain.interfaces.llm_provider import LLMProvider, LLMResponse


class GroqAdapter(LLMProvider):
    """Groq API adapter.
    
    Uses Groq's fast inference API.
    Requires GROQ_API_KEY.
    """
    
    def __init__(self, api_key: str, model: str | None = None):
        """Initialize Groq adapter."""
        self._api_key = api_key
        self._model = model or "llama-3.3-70b-versatile"
        self._client = None
    
    @property
    def provider_name(self) -> str:
        return "groq"
    
    @property
    def model_name(self) -> str:
        return self._model
    
    def _get_client(self):
        """Get or create Groq client."""
        if self._client is None:
            try:
                from groq import Groq
                self._client = Groq(api_key=self._api_key)
            except ImportError:
                raise ImportError("groq package required. Install with: pip install groq")
        return self._client
    
    async def analyze(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Send analysis request via Groq API."""
        client = self._get_client()
        
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=self._model,
            temperature=0.1,
            max_tokens=4096,
        )
        
        content = chat_completion.choices[0].message.content or ""
        tokens = chat_completion.usage.total_tokens if chat_completion.usage else 0
        
        return LLMResponse(
            content=content,
            model=self._model,
            provider=self.provider_name,
            tokens_used=tokens,
        )
    
    async def is_available(self) -> bool:
        """Check if Groq API is available."""
        return bool(self._api_key)
