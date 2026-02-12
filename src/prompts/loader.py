"""Prompt loader utility for reading and rendering prompt templates.

Provides:
- File-based prompt loading from .md files
- Template variable substitution using ${variable} syntax
- Caching for performance
- Hot-reload support for development
"""

from pathlib import Path
from string import Template
from typing import Any

_loader_instance: "PromptLoader | None" = None


class PromptLoader:
    """Loads and renders prompt templates from files.
    
    Prompts are stored as Markdown files with ${variable} placeholders.
    Supports caching for performance and hot-reload for development.
    """
    
    def __init__(
        self,
        prompts_dir: Path | None = None,
        cache_enabled: bool = True,
    ):
        """Initialize the prompt loader.
        
        Args:
            prompts_dir: Directory containing prompt files. Defaults to this module's directory.
            cache_enabled: Whether to cache loaded prompts in memory.
        """
        self.prompts_dir = prompts_dir or Path(__file__).parent
        self.cache_enabled = cache_enabled
        self._cache: dict[str, str] = {}
    
    def load(self, prompt_path: str) -> str:
        """Load raw prompt content from file.
        
        Args:
            prompt_path: Relative path to prompt file (e.g., "system/analysis_system.md")
            
        Returns:
            Raw prompt content as string
            
        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        if self.cache_enabled and prompt_path in self._cache:
            return self._cache[prompt_path]
        
        full_path = self.prompts_dir / prompt_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {full_path}")
        
        content = full_path.read_text(encoding="utf-8")
        
        if self.cache_enabled:
            self._cache[prompt_path] = content
        
        return content
    
    def render(self, prompt_path: str, **variables: Any) -> str:
        """Load and render prompt with variable substitution.
        
        Uses Python's string.Template for ${variable} substitution.
        
        Args:
            prompt_path: Relative path to prompt file
            **variables: Variables to substitute in the template
            
        Returns:
            Rendered prompt with variables substituted
            
        Raises:
            FileNotFoundError: If prompt file doesn't exist
            KeyError: If required template variable is missing
        """
        content = self.load(prompt_path)
        template = Template(content)
        return template.substitute(**variables)
    
    def render_safe(self, prompt_path: str, **variables: Any) -> str:
        """Load and render prompt with safe variable substitution.
        
        Missing variables are left as-is (${variable}) instead of raising an error.
        
        Args:
            prompt_path: Relative path to prompt file
            **variables: Variables to substitute in the template
            
        Returns:
            Rendered prompt with available variables substituted
        """
        content = self.load(prompt_path)
        template = Template(content)
        return template.safe_substitute(**variables)
    
    def clear_cache(self) -> None:
        """Clear the prompt cache.
        
        Useful for development when prompts are being edited.
        """
        self._cache.clear()
    
    def list_prompts(self) -> list[str]:
        """List all available prompt files.
        
        Returns:
            List of relative paths to all .md prompt files
        """
        prompts = []
        for path in self.prompts_dir.rglob("*.md"):
            relative = path.relative_to(self.prompts_dir)
            prompts.append(str(relative))
        return sorted(prompts)


def get_prompt_loader() -> PromptLoader:
    """Get the global prompt loader instance.
    
    Returns:
        Singleton PromptLoader instance
    """
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = PromptLoader()
    return _loader_instance
