"""Claude LLM adapters.

Implements LLMProvider interface for Claude CLI and Anthropic API.
Open/Closed: Implements abstract interface without modifying it.
"""

import subprocess

from src.domain.interfaces.llm_provider import LLMProvider, LLMResponse


class ClaudeAdapter(LLMProvider):
    """Claude CLI adapter for local Claude usage.
    
    Uses the Claude CLI tool for analysis.
    Free to use, no API key required.
    """
    
    def __init__(self, model: str | None = None):
        """Initialize Claude CLI adapter."""
        self._model = model or "claude-sonnet-4-20250514"
    
    @property
    def provider_name(self) -> str:
        return "claude-cli"
    
    @property
    def model_name(self) -> str:
        return self._model
    
    async def analyze(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Send analysis request via Claude CLI."""
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        try:
            result = subprocess.run(
                ["claude", "-p", full_prompt],
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Claude CLI error: {result.stderr}")
            
            return LLMResponse(
                content=result.stdout.strip(),
                model=self._model,
                provider=self.provider_name,
            )
        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-cli")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI timed out")
    
    async def is_available(self) -> bool:
        """Check if Claude CLI is available."""
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False


class AnthropicAdapter(LLMProvider):
    """Anthropic API adapter for Claude.
    
    Uses the Anthropic Python SDK.
    Requires ANTHROPIC_API_KEY.
    """
    
    def __init__(self, api_key: str, model: str | None = None):
        """Initialize Anthropic adapter."""
        self._api_key = api_key
        self._model = model or "claude-sonnet-4-20250514"
        self._client = None
    
    @property
    def provider_name(self) -> str:
        return "anthropic"
    
    @property
    def model_name(self) -> str:
        return self._model
    
    def _get_client(self):
        """Get or create Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                raise ImportError("anthropic package required. Install with: pip install anthropic")
        return self._client
    
    async def analyze(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Send analysis request via Anthropic API."""
        client = self._get_client()
        
        message = client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        
        content = message.content[0].text if message.content else ""
        tokens = message.usage.input_tokens + message.usage.output_tokens
        
        return LLMResponse(
            content=content,
            model=self._model,
            provider=self.provider_name,
            tokens_used=tokens,
        )
    
    async def is_available(self) -> bool:
        """Check if Anthropic API is available."""
        return bool(self._api_key)
