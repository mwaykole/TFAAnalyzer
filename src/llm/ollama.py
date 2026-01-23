"""Ollama LLM provider - Free, local AI models."""

from typing import Any

import aiohttp

from src.llm.base import LLMError, LLMProvider
from src.utils.logging import get_logger

logger = get_logger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider - completely free.
    
    Runs models locally using Ollama. Requires Ollama to be installed
    and running on your machine.
    """

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.1,
    ):
        """Initialize Ollama provider.

        Args:
            model: Model name (e.g., llama3.2, mistral, codellama)
            base_url: Ollama server URL
            temperature: Response temperature (0.0-1.0)
        """
        self._model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self._session: aiohttp.ClientSession | None = None

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def max_context_tokens(self) -> int:
        # Most Ollama models support 4k-8k context
        return 8000

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
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
        """Send prompt to Ollama and get JSON response.
        
        Args:
            system_prompt: System instructions
            user_prompt: User prompt with analysis request
            **kwargs: Additional parameters
            
        Returns:
            Parsed JSON response
        """
        session = await self._get_session()

        # Ollama API endpoint
        url = f"{self.base_url}/api/generate"

        # Combine prompts
        full_prompt = f"""<|system|>
{system_prompt}
<|user|>
{user_prompt}
<|assistant|>"""

        payload = {
            "model": self._model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.temperature),
            },
        }

        try:
            async with session.post(
                url, 
                json=payload, 
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise LLMError(f"Ollama error {resp.status}: {text}")

                data = await resp.json()
                response_text = data.get("response", "")

                return self.parse_response(response_text)

        except aiohttp.ClientConnectorError:
            raise LLMError(
                "Cannot connect to Ollama. Make sure it's running:\n"
                "  1. Install: curl -fsSL https://ollama.com/install.sh | sh\n"
                "  2. Pull model: ollama pull llama3.2\n"
                "  3. Run: ollama serve"
            )
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"Ollama request failed: {e}")


async def check_ollama_available(base_url: str = "http://localhost:11434") -> bool:
    """Check if Ollama is running and accessible."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/api/tags", 
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


async def list_ollama_models(base_url: str = "http://localhost:11434") -> list[str]:
    """List available Ollama models."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/api/tags", 
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []
