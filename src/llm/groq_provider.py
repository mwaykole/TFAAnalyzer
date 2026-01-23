"""Groq LLM provider - Free, fast cloud inference."""

from typing import Any

import aiohttp

from src.llm.base import LLMError, LLMProvider, LLMRateLimitError, RateLimiter
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Groq supported models (all free)
GROQ_MODELS = {
    "llama-3.3-70b-versatile": 128000,      # Best quality, free
    "llama-3.1-8b-instant": 128000,          # Fast, free
    "llama-3.2-90b-vision-preview": 8192,   # Vision capable
    "mixtral-8x7b-32768": 32768,             # Good for code
    "gemma2-9b-it": 8192,                    # Google's model
}


class GroqProvider(LLMProvider):
    """Groq cloud LLM provider - FREE and very fast.
    
    Uses Groq's API for fast inference. Get a free API key at:
    https://console.groq.com/
    """

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        requests_per_minute: int = 30,
    ):
        """Initialize Groq provider.

        Args:
            api_key: Groq API key (free from console.groq.com)
            model: Model name
            temperature: Response temperature (0.0-1.0)
            max_tokens: Max response tokens
            requests_per_minute: Rate limit for API calls
        """
        self.api_key = api_key
        self._model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = "https://api.groq.com/openai/v1"
        self._session: aiohttp.ClientSession | None = None
        self._rate_limiter = RateLimiter(requests_per_minute)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def max_context_tokens(self) -> int:
        return GROQ_MODELS.get(self._model, 32768)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send prompt to Groq and get JSON response.
        
        Args:
            system_prompt: System instructions
            user_prompt: User prompt with analysis request
            **kwargs: Additional parameters
            
        Returns:
            Parsed JSON response
        """
        # Apply rate limiting
        await self._rate_limiter.acquire()
        
        session = await self._get_session()
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
        }

        try:
            async with session.post(
                url, 
                json=payload, 
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status == 429:
                    raise LLMRateLimitError(
                        "Groq rate limit exceeded. Wait a moment and try again."
                    )

                if resp.status != 200:
                    text = await resp.text()
                    raise LLMError(f"Groq error {resp.status}: {text}")

                data = await resp.json()

                if "choices" not in data or not data["choices"]:
                    raise LLMError("No response from Groq")

                response_text = data["choices"][0]["message"]["content"]
                return self.parse_response(response_text)

        except aiohttp.ClientConnectorError as e:
            raise LLMError(f"Cannot connect to Groq: {e}")
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Groq request failed: {e}")
