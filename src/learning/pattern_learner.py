"""Pattern management for classification_rules.yaml custom_rules section."""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from src.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_RULES_FILE = Path("classification_rules.yaml")

CATEGORY_MAP = {
    "Product Bug": "product_bug",
    "Test Automation Issue": "automation_bug",
    "Infrastructure Issue": "system_issue",
}

CATEGORY_MAP_REVERSE = {v: k for k, v in CATEGORY_MAP.items()}


@dataclass
class LearnedPattern:
    pattern: str = ""
    category: str = ""
    description: str = ""


class PatternLearner:
    """Manages custom rules in classification_rules.yaml."""
    
    ERROR_EXTRACTORS = [
        (r"(\w+Error|\w+Exception)[:\s]+(.{10,100})", "exception"),
        (r"(CrashLoopBackOff|ImagePullBackOff|OOMKilled|FailedScheduling)", "k8s_event"),
        (r"(AccessDenied|InvalidAccessKeyId|SignatureDoesNotMatch|NoSuchBucket)", "aws_error"),
        (r"(timeout|timed?\s*out)", "timeout"),
        (r"(connection\s+refused|connection\s+reset)", "connection"),
    ]
    
    def __init__(self, rules_file: Path | str | None = None):
        self.rules_file = Path(rules_file) if rules_file else DEFAULT_RULES_FILE
        self._compiled_extractors = [
            (re.compile(p, re.IGNORECASE), n) for p, n in self.ERROR_EXTRACTORS
        ]
    
    def _load_rules(self) -> dict:
        try:
            with open(self.rules_file) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("failed_to_load_rules", error=str(e))
            return {}
    
    def _save_rules(self, rules: dict) -> None:
        try:
            with open(self.rules_file, "w") as f:
                yaml.dump(rules, f, default_flow_style=False, sort_keys=False, width=120)
            logger.info("rules_saved", file=str(self.rules_file))
        except Exception as e:
            logger.error("failed_to_save_rules", error=str(e))
    
    def get_error_signature(self, logs: str) -> str:
        for pattern, _ in self._compiled_extractors:
            match = pattern.search(logs)
            if match:
                return hashlib.md5(match.group(0)[:150].encode()).hexdigest()[:16]
        return hashlib.md5(re.sub(r'\s+', ' ', logs[:500]).encode()).hexdigest()[:16]
    
    def get_custom_rules(self) -> list[LearnedPattern]:
        rules = self._load_rules()
        custom = rules.get("custom_rules") or {}
        return [
            LearnedPattern(
                pattern=rule.get("pattern", ""),
                category=CATEGORY_MAP_REVERSE.get(rule.get("classification", ""), "Infrastructure Issue"),
                description=rule.get("description", name),
            )
            for name, rule in custom.items()
            if isinstance(rule, dict) and rule.get("pattern")
        ]
    
    def add_custom_rule(self, pattern: str, category: str, description: str = "", rule_name: str | None = None) -> str:
        rules = self._load_rules()
        if "custom_rules" not in rules:
            rules["custom_rules"] = {}
        
        if not rule_name:
            rule_name = f"custom_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        rules["custom_rules"][rule_name] = {
            "classification": CATEGORY_MAP.get(category, "system_issue"),
            "pattern": pattern,
            "description": description or f"Custom: {pattern[:30]}",
            "severity": "medium",
        }
        
        self._save_rules(rules)
        logger.info("custom_rule_added", name=rule_name)
        return rule_name
    
    def match_custom_rules(self, logs: str) -> list[tuple[LearnedPattern, str]]:
        matches = []
        for rule in self.get_custom_rules():
            try:
                match = re.search(rule.pattern, logs, re.IGNORECASE)
                if match:
                    matches.append((rule, match.group(0)))
            except re.error:
                pass
        return matches
    
    def get_pattern_stats(self) -> dict[str, Any]:
        rules = self._load_rules()
        custom = rules.get("custom_rules") or {}
        by_category: dict[str, int] = {}
        for rule in custom.values():
            if isinstance(rule, dict):
                cat = CATEGORY_MAP_REVERSE.get(rule.get("classification", ""), "Infrastructure Issue")
                by_category[cat] = by_category.get(cat, 0) + 1
        return {
            "total_custom_rules": len(custom),
            "by_category": by_category,
            "rules_file": str(self.rules_file),
        }
