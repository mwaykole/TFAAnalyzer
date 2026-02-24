"""Claude CLI provider - Uses local Claude Code CLI."""

import asyncio
import shutil
from typing import Any

from src.llm.base import LLMError, LLMProvider
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ClaudeCLIProvider(LLMProvider):
    """Claude CLI provider - uses your existing Claude Code installation.
    
    This provider requires the Claude CLI to be installed and authenticated.
    No API key is needed as it uses your local Claude Code session.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        timeout: int = 300,
    ):
        """Initialize Claude CLI provider.

        Args:
            model: Model to use (passed to CLI)
            timeout: Timeout in seconds for CLI response (default 5 minutes)
        """
        self._model = model
        self.timeout = timeout
        self._claude_path = shutil.which("claude")

        if not self._claude_path:
            raise LLMError("Claude CLI not found. Install it or use --provider groq")

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def max_context_tokens(self) -> int:
        return 200000  # Claude's context window

    async def initialize(self) -> None:
        """No initialization needed for CLI."""
        pass

    async def close(self) -> None:
        """No cleanup needed for CLI."""
        pass

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send prompt to Claude CLI via stdin (handles large prompts).
        
        Args:
            system_prompt: System instructions
            user_prompt: User prompt with analysis request
            **kwargs: Additional parameters (ignored for CLI)
            
        Returns:
            Response as dict with 'summary' key or parsed JSON
        """
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        process = None

        try:
            process = await asyncio.create_subprocess_exec(
                self._claude_path,
                "--print",
                "--output-format", "text",
                "--max-turns", "1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=full_prompt.encode()),
                timeout=self.timeout,
            )

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise LLMError(f"Claude CLI error: {error_msg}")

            response_text = stdout.decode().strip()
            
            try:
                return self.parse_response(response_text)
            except Exception:
                return {"summary": response_text, "raw": response_text}

        except asyncio.TimeoutError:
            if process:
                process.kill()
            raise LLMError(f"Claude CLI timed out after {self.timeout}s")
        except FileNotFoundError:
            raise LLMError("Claude CLI not found")
        except Exception as e:
            if isinstance(e, LLMError):
                raise
            raise LLMError(f"Claude CLI failed: {e}")


def check_claude_cli_available() -> bool:
    """Check if Claude CLI is installed and available."""
    return shutil.which("claude") is not None
