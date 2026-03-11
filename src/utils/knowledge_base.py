"""Knowledge Base loader for domain-specific context.

Loads user-provided hints, quick rules, and context from knowledge_base.yaml
to improve LLM analysis accuracy.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ContextHint:
    """A context hint for the LLM."""
    
    context: str
    hint: str
    keywords: list[str] = field(default_factory=list)
    
    def matches(self, text: str) -> bool:
        """Check if any keywords match the text."""
        if not self.keywords:
            return False
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in self.keywords)


@dataclass
class QuickRule:
    """A quick pattern-based classification rule."""
    
    name: str
    pattern: str
    classification: str
    reason: str
    severity: str = "medium"
    _compiled: re.Pattern | None = field(default=None, repr=False)
    
    def __post_init__(self):
        self._compiled = re.compile(self.pattern, re.IGNORECASE)
    
    def matches(self, text: str) -> bool:
        """Check if pattern matches the text."""
        return bool(self._compiled and self._compiled.search(text))


@dataclass
class KnowledgeBaseMatch:
    """Result of matching against knowledge base."""
    
    matched_hints: list[ContextHint] = field(default_factory=list)
    matched_rule: QuickRule | None = None
    platform_notes: dict[str, Any] = field(default_factory=dict)
    component_context: list[str] = field(default_factory=list)
    
    @property
    def has_quick_rule(self) -> bool:
        return self.matched_rule is not None
    
    def get_context_for_llm(self) -> str:
        """Format matched context for LLM prompt injection."""
        if not self.matched_hints and not self.component_context:
            return ""
        
        sections = []
        
        if self.matched_hints:
            sections.append("## Domain Knowledge (from knowledge base)")
            for hint in self.matched_hints[:5]:
                sections.append(f"\n### {hint.context}")
                sections.append(hint.hint.strip())
        
        if self.component_context:
            sections.append("\n## Component-Specific Notes")
            for note in self.component_context:
                sections.append(f"- {note}")
        
        if self.platform_notes:
            sections.append("\n## Platform Notes")
            for platform, info in self.platform_notes.items():
                if isinstance(info, dict):
                    sections.append(f"- **{platform}**: {info.get('note', '')}")
        
        return "\n".join(sections)


class KnowledgeBase:
    """Loads and queries the knowledge base for domain context."""
    
    def __init__(self, config_path: str | Path | None = None):
        """Initialize knowledge base.
        
        Args:
            config_path: Path to knowledge_base.yaml. If None, uses default location.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "knowledge_base.yaml"
        
        self._path = Path(config_path)
        self._data: dict[str, Any] = {}
        self._hints: list[ContextHint] = []
        self._quick_rules: list[QuickRule] = []
        self._platform_notes: dict[str, Any] = {}
        self._component_context: dict[str, list[str]] = {}
        self._settings: dict[str, Any] = {}
        
        self._load()
    
    def _load(self) -> None:
        """Load knowledge base from YAML file."""
        if not self._path.exists():
            return
        
        try:
            with open(self._path) as f:
                self._data = yaml.safe_load(f) or {}
        except Exception:
            return
        
        self._settings = self._data.get("settings", {})
        
        if not self._settings.get("enabled", True):
            return
        
        for hint_data in self._data.get("context_hints", []):
            self._hints.append(ContextHint(
                context=hint_data.get("context", ""),
                hint=hint_data.get("hint", ""),
                keywords=hint_data.get("keywords", []),
            ))
        
        for rule_data in self._data.get("quick_rules", []):
            self._quick_rules.append(QuickRule(
                name=rule_data.get("name", ""),
                pattern=rule_data.get("pattern", ""),
                classification=rule_data.get("classification", "to_investigate"),
                reason=rule_data.get("reason", ""),
                severity=rule_data.get("severity", "medium"),
            ))
        
        self._platform_notes = self._data.get("platform_notes", {})
        
        for component, data in self._data.get("component_context", {}).items():
            self._component_context[component] = data.get("notes", [])
    
    @property
    def is_enabled(self) -> bool:
        """Check if knowledge base is enabled."""
        return self._settings.get("enabled", True)
    
    @property
    def apply_quick_rules(self) -> bool:
        """Check if quick rules should be applied."""
        return self._settings.get("apply_quick_rules", True)
    
    def match(
        self,
        logs: str,
        test_name: str = "",
        component: str = "",
    ) -> KnowledgeBaseMatch:
        """Match logs against knowledge base.
        
        Args:
            logs: Failure logs to analyze
            test_name: Name of the test
            component: Component being tested
            
        Returns:
            KnowledgeBaseMatch with all matched context
        """
        result = KnowledgeBaseMatch()
        
        combined_text = f"{logs} {test_name}"
        
        for hint in self._hints:
            if hint.matches(combined_text):
                result.matched_hints.append(hint)
        
        if self.apply_quick_rules:
            for rule in self._quick_rules:
                if rule.matches(logs):
                    result.matched_rule = rule
                    break
        
        for platform, notes in self._platform_notes.items():
            if platform.lower() in combined_text.lower():
                result.platform_notes[platform] = notes
        
        if component and component in self._component_context:
            result.component_context = self._component_context[component]
        
        return result
    
    def get_all_hints(self) -> list[ContextHint]:
        """Get all context hints."""
        return self._hints.copy()
    
    def get_quick_rules(self) -> list[QuickRule]:
        """Get all quick rules."""
        return self._quick_rules.copy()
    
    def reload(self) -> None:
        """Reload knowledge base from file."""
        self._hints.clear()
        self._quick_rules.clear()
        self._platform_notes.clear()
        self._component_context.clear()
        self._load()


_knowledge_base: KnowledgeBase | None = None


def get_knowledge_base() -> KnowledgeBase:
    """Get the singleton knowledge base instance."""
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = KnowledgeBase()
    return _knowledge_base


