"""Classification engine that uses YAML-based rules for test failure analysis."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ClassificationResult:
    """Result of classification analysis."""
    
    classification: str
    confidence: float
    severity: str
    defect_type: str
    matched_patterns: list[dict[str, Any]] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    reasoning: str = ""
    suggested_fix: str = ""


class ClassificationEngine:
    """Engine for classifying test failures using YAML-based rules."""
    
    def __init__(self, rules_path: str | Path | None = None):
        """Initialize the classification engine.
        
        Args:
            rules_path: Path to YAML rules file. If None, uses default location.
        """
        if rules_path is None:
            # Default to classification_rules.yaml in project root
            rules_path = Path(__file__).parent.parent / "classification_rules.yaml"
        
        self.rules_path = Path(rules_path)
        self.rules: dict[str, Any] = {}
        self._load_rules()
    
    def _load_rules(self) -> None:
        """Load rules from YAML file."""
        if not self.rules_path.exists():
            raise FileNotFoundError(f"Rules file not found: {self.rules_path}")
        
        with open(self.rules_path) as f:
            self.rules = yaml.safe_load(f)
    
    def reload_rules(self) -> None:
        """Reload rules from file (for hot-reloading)."""
        self._load_rules()
    
    def get_defect_type_code(self, classification: str) -> str:
        """Get ReportPortal defect type code for a classification.
        
        Args:
            classification: Classification name (e.g., "Product Bug")
            
        Returns:
            Defect type code (e.g., "pb001")
        """
        defect_types = self.rules.get("defect_types", {})
        
        # Normalize classification name
        normalized = classification.lower().replace(" ", "_")
        
        # Map common variations
        mapping = {
            "product_bug": "product_bug",
            "product bug": "product_bug",
            "automation_bug": "automation_bug",
            "automation bug": "automation_bug",
            "test_automation_issue": "automation_bug",
            "test automation issue": "automation_bug",
            "system_issue": "system_issue",
            "system issue": "system_issue",
            "flaky_test": "system_issue",
            "flaky test": "system_issue",
            "no_defect": "no_defect",
            "no defect": "no_defect",
        }
        
        key = mapping.get(normalized, "to_investigate")
        return defect_types.get(key, "ti001")
    
    def classify(
        self,
        error_logs: str,
        test_name: str = "",
        component: str = "",
        pass_rate: float | None = None,
        consecutive_failures: int = 0,
        is_flaky: bool = False,
    ) -> ClassificationResult:
        """Classify a test failure based on error logs and context.
        
        Args:
            error_logs: The error/failure logs
            test_name: Name of the test
            component: Component being tested
            pass_rate: Historical pass rate (0-100)
            consecutive_failures: Number of consecutive failures
            is_flaky: Whether test is marked as flaky
            
        Returns:
            ClassificationResult with classification, confidence, etc.
        """
        settings = self.rules.get("settings", {})
        weights = settings.get("weights", {})
        
        # Track evidence for each classification
        scores: dict[str, float] = {
            "product_bug": 0.0,
            "automation_bug": 0.0,
            "system_issue": 0.0,
            "no_defect": 0.0,
        }
        
        all_matched_patterns: list[dict[str, Any]] = []
        all_matched_keywords: list[str] = []
        suggested_fix = ""
        
        classifications = self.rules.get("classifications", {})
        
        # Check each classification's patterns
        for class_name, class_rules in classifications.items():
            if class_name not in scores:
                continue
            
            # Check definitive patterns
            for pattern_info in class_rules.get("definitive_patterns", []):
                pattern = pattern_info.get("pattern", "")
                if pattern and re.search(pattern, error_logs, re.IGNORECASE):
                    scores[class_name] += weights.get("definitive_pattern", 1.0)
                    all_matched_patterns.append({
                        "classification": class_name,
                        "pattern": pattern,
                        "description": pattern_info.get("description", ""),
                        "type": "definitive",
                    })
                    if "fix" in pattern_info:
                        suggested_fix = pattern_info["fix"]
            
            # Check RHOAI-specific patterns
            rhoai_key = f"rhoai_{'test_' if class_name == 'automation_bug' else ''}patterns"
            for pattern_info in class_rules.get(rhoai_key, []):
                pattern = pattern_info.get("pattern", "")
                pattern_component = pattern_info.get("component", "")
                
                if pattern and re.search(pattern, error_logs, re.IGNORECASE):
                    bonus = weights.get("component_match", 0.1) if component and pattern_component.lower() == component.lower() else 0
                    scores[class_name] += weights.get("definitive_pattern", 1.0) * 0.8 + bonus
                    all_matched_patterns.append({
                        "classification": class_name,
                        "pattern": pattern,
                        "description": pattern_info.get("description", ""),
                        "component": pattern_component,
                        "type": "rhoai_specific",
                    })
                    if "fix" in pattern_info and not suggested_fix:
                        suggested_fix = pattern_info["fix"]
            
            # Check keywords
            keywords = class_rules.get("keywords", {})
            for weight_level in ["high_weight", "medium_weight", "low_weight"]:
                weight_key = weight_level.replace("_weight", "_keyword")
                weight_value = weights.get(weight_key, 0.1)
                
                for keyword in keywords.get(weight_level, []):
                    if keyword.lower() in error_logs.lower():
                        scores[class_name] += weight_value
                        if keyword not in all_matched_keywords:
                            all_matched_keywords.append(keyword)
        
        # Apply component-specific rules
        if component and settings.get("features", {}).get("use_component_rules", True):
            component_rules = self.rules.get("component_rules", {}).get(component, {})
            for class_name, patterns in component_rules.get("extra_patterns", {}).items():
                if class_name in scores:
                    for pattern in patterns:
                        if re.search(pattern, error_logs, re.IGNORECASE):
                            scores[class_name] += weights.get("component_match", 0.1)
                            all_matched_patterns.append({
                                "classification": class_name,
                                "pattern": pattern,
                                "type": "component_specific",
                                "component": component,
                            })
        
        # Apply history-based adjustments
        if settings.get("features", {}).get("use_history", True):
            pass_rate_settings = settings.get("pass_rate", {})
            
            if pass_rate is not None:
                if pass_rate < pass_rate_settings.get("definitely_broken", 10):
                    # Consistently failing - likely real issue, not flaky
                    scores["system_issue"] *= 0.5
                elif pass_rate_settings.get("possibly_flaky_min", 20) <= pass_rate <= pass_rate_settings.get("possibly_flaky_max", 80):
                    # Might be flaky, but only if no definitive pattern
                    if not any(p.get("type") == "definitive" for p in all_matched_patterns):
                        scores["system_issue"] += weights.get("history_flaky", 0.2)
            
            if is_flaky:
                scores["system_issue"] += weights.get("history_flaky", 0.2)
            
            if consecutive_failures >= 5:
                # Many consecutive failures suggests not flaky
                scores["system_issue"] *= 0.5
        
        # Determine winner
        max_score = max(scores.values())
        if max_score == 0:
            classification = "to_investigate"
            confidence = 0.0
        else:
            classification = max(scores, key=scores.get)
            # Normalize confidence
            total = sum(scores.values())
            confidence = (scores[classification] / total) if total > 0 else 0.0
            confidence = min(confidence, 1.0)
        
        # Map to display name
        display_names = {
            "product_bug": "Product Bug",
            "automation_bug": "Test Automation Issue",
            "system_issue": "Infrastructure Issue",
            "no_defect": "No Defect",
            "to_investigate": "To Investigate",
        }
        classification_display = display_names.get(classification, classification)
        
        # Determine severity
        severity = self._determine_severity(error_logs)
        
        # Get defect type code
        defect_type = self.get_defect_type_code(classification)
        
        # Build reasoning
        reasoning = self._build_reasoning(
            classification_display,
            all_matched_patterns,
            all_matched_keywords,
            pass_rate,
            is_flaky,
        )
        
        return ClassificationResult(
            classification=classification_display,
            confidence=confidence,
            severity=severity,
            defect_type=defect_type,
            matched_patterns=all_matched_patterns,
            matched_keywords=all_matched_keywords,
            reasoning=reasoning,
            suggested_fix=suggested_fix,
        )
    
    def _determine_severity(self, error_logs: str) -> str:
        """Determine severity based on error patterns.
        
        Args:
            error_logs: The error logs
            
        Returns:
            Severity level (CRITICAL, HIGH, MEDIUM, LOW)
        """
        severity_rules = self.rules.get("severity_rules", {})
        
        for severity, rules in severity_rules.items():
            patterns = rules.get("patterns", [])
            for pattern in patterns:
                if re.search(pattern, error_logs, re.IGNORECASE):
                    return severity.upper()
        
        return "MEDIUM"  # Default
    
    def _build_reasoning(
        self,
        classification: str,
        matched_patterns: list[dict],
        matched_keywords: list[str],
        pass_rate: float | None,
        is_flaky: bool,
    ) -> str:
        """Build human-readable reasoning for classification.
        
        Args:
            classification: The determined classification
            matched_patterns: List of matched patterns
            matched_keywords: List of matched keywords
            pass_rate: Historical pass rate
            is_flaky: Whether marked as flaky
            
        Returns:
            Reasoning string
        """
        reasons = []
        
        # Add pattern matches
        definitive = [p for p in matched_patterns if p.get("type") == "definitive"]
        if definitive:
            reasons.append(f"Matched definitive pattern(s): {', '.join(p.get('description', p.get('pattern', '')) for p in definitive[:3])}")
        
        rhoai_specific = [p for p in matched_patterns if p.get("type") == "rhoai_specific"]
        if rhoai_specific:
            reasons.append(f"Matched RHOAI pattern(s): {', '.join(p.get('description', p.get('pattern', '')) for p in rhoai_specific[:3])}")
        
        # Add keyword info
        if matched_keywords:
            reasons.append(f"Keywords found: {', '.join(matched_keywords[:5])}")
        
        # Add history info
        if pass_rate is not None:
            reasons.append(f"Historical pass rate: {pass_rate:.0f}%")
        
        if is_flaky:
            reasons.append("Test is marked as flaky")
        
        return "; ".join(reasons) if reasons else "No strong evidence found"
    
    def get_prompt_rules(self) -> str:
        """Generate LLM prompt rules from YAML configuration.
        
        Returns:
            Formatted string of rules for LLM prompt
        """
        classifications = self.rules.get("classifications", {})
        
        lines = [
            "IMPORTANT: Focus on the ERROR TYPE and ROOT CAUSE first, not pass rate.",
            "",
            "Classify the test failure into EXACTLY ONE of these categories:",
            "",
        ]
        
        # Product Bug
        pb = classifications.get("product_bug", {})
        lines.append("## 1. **Product Bug** - The product/service has a REAL defect:")
        lines.append("ALWAYS Product Bug if you see:")
        for p in pb.get("definitive_patterns", [])[:8]:
            desc = p.get("description", p.get("pattern", ""))
            lines.append(f"- {desc}")
        lines.append("")
        
        # Automation Bug
        ab = classifications.get("automation_bug", {})
        lines.append("## 2. **Test Automation Issue** - The TEST CODE has a problem:")
        lines.append("ALWAYS Test Automation Issue if you see:")
        for p in ab.get("definitive_patterns", [])[:8]:
            desc = p.get("description", p.get("pattern", ""))
            fix = p.get("fix", "")
            line = f"- {desc}"
            if fix:
                line += f" ({fix})"
            lines.append(line)
        lines.append("")
        
        # System Issue / Infrastructure Issue
        si = classifications.get("system_issue", {})
        lines.append("## 3. **Infrastructure Issue** - External/environmental issues:")
        lines.append("ONLY classify as Flaky if:")
        for p in si.get("definitive_patterns", [])[:5]:
            desc = p.get("description", p.get("pattern", ""))
            lines.append(f"- {desc}")
        lines.append("")
        
        # Critical rules
        lines.append("## CRITICAL DECISION RULES:")
        lines.append("")
        lines.append("1. **TimeoutError waiting for metrics** → **Test Automation Issue**")
        lines.append("2. **Version mismatch** → **Product Bug**")
        lines.append("3. **Service not responding** → **Product Bug**")
        lines.append("4. **Do NOT default to Flaky just because pass rate is 50-80%**")
        lines.append("5. **Always analyze WHAT is failing to determine WHY**")
        
        return "\n".join(lines)


# Singleton instance for easy access
_engine: ClassificationEngine | None = None


def get_engine(rules_path: str | Path | None = None) -> ClassificationEngine:
    """Get or create the classification engine singleton.
    
    Args:
        rules_path: Optional path to rules file
        
    Returns:
        ClassificationEngine instance
    """
    global _engine
    if _engine is None or rules_path is not None:
        _engine = ClassificationEngine(rules_path)
    return _engine


def classify_failure(
    error_logs: str,
    test_name: str = "",
    component: str = "",
    pass_rate: float | None = None,
    consecutive_failures: int = 0,
    is_flaky: bool = False,
    rules_path: str | Path | None = None,
) -> ClassificationResult:
    """Convenience function to classify a test failure.
    
    Args:
        error_logs: The error/failure logs
        test_name: Name of the test
        component: Component being tested
        pass_rate: Historical pass rate (0-100)
        consecutive_failures: Number of consecutive failures
        is_flaky: Whether test is marked as flaky
        rules_path: Optional path to custom rules file
        
    Returns:
        ClassificationResult with classification, confidence, etc.
    """
    engine = get_engine(rules_path)
    return engine.classify(
        error_logs=error_logs,
        test_name=test_name,
        component=component,
        pass_rate=pass_rate,
        consecutive_failures=consecutive_failures,
        is_flaky=is_flaky,
    )

