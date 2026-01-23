"""Classification service implementing core classification logic.

Single Responsibility: Only handles classification logic.
Dependency Inversion: Depends on abstractions (interfaces), not concretions.
"""

import re
from typing import Any

from src.domain.entities.classification import Classification, FailureCategory, Severity
from src.domain.entities.evidence import Evidence
from src.domain.interfaces.log_parser import LogParser, ParsedLogs


# Definitive patterns with confidence scores
DEFINITIVE_PATTERNS: list[tuple[str, str, str, float]] = [
    (r"CrashLoopBackOff|ImagePullBackOff|OOMKilled", "Infrastructure Issue", "Pod failure", 0.95),
    (r"AccessDenied|InvalidAccessKeyId|SignatureDoesNotMatch", "Infrastructure Issue", "AWS credentials", 0.95),
    (r"connection.*refused|connection.*reset|network.*unreachable", "Infrastructure Issue", "Network", 0.90),
    (r"TimeoutExpiredError|TimeoutSampler.*expired|Timed Out", "Test Automation Issue", "Timeout", 0.80),
    (r"AssertionError|assert.*failed", "Test Automation Issue", "Assertion", 0.75),
    (r"fixture.*not.*found|SetupError", "Test Automation Issue", "Fixture error", 0.90),
    (r"InferenceService.*Failed|InferenceService.*not.*[Rr]eady", "Product Bug", "Service failure", 0.70),
    (r"CRD.*not.*found|Couldn't find.*in.*api.*group", "Infrastructure Issue", "CRD missing", 0.90),
    (r"Internal.*[Ss]erver.*[Ee]rror|status.*code.*5[0-9]{2}", "Product Bug", "Server error", 0.80),
    (r"CUDA.*error|GPU.*not.*available|nvidia.*driver", "Infrastructure Issue", "GPU issue", 0.95),
    (r"ResourceQuota.*exceeded|quota.*exceeded", "Infrastructure Issue", "Quota exceeded", 0.95),
    (r"PodScheduled.*False|Unschedulable", "Infrastructure Issue", "Scheduling", 0.90),
]

SEVERITY_PATTERNS: dict[str, list[str]] = {
    "CRITICAL": [
        r"OOMKilled",
        r"CrashLoopBackOff",
        r"data.*corrupt",
        r"security.*breach",
    ],
    "HIGH": [
        r"status.*code.*5[0-9]{2}",
        r"InferenceService.*Failed",
        r"GPU.*not.*available",
    ],
    "MEDIUM": [
        r"TimeoutError",
        r"AssertionError",
        r"connection.*refused",
    ],
    "LOW": [
        r"warning",
        r"deprecated",
    ],
}


class ClassificationService:
    """Service for classifying test failures.
    
    Single Responsibility: Only handles classification logic.
    Open/Closed: Add new patterns without modifying core logic.
    """
    
    def __init__(self, log_parser: LogParser | None = None):
        """Initialize with optional log parser.
        
        Dependency Inversion: Accepts interface, not concrete implementation.
        """
        self._log_parser = log_parser
        self._compiled_patterns: list[tuple[re.Pattern, str, str, float]] = [
            (re.compile(pattern, re.IGNORECASE), category, desc, conf)
            for pattern, category, desc, conf in DEFINITIVE_PATTERNS
        ]
    
    def classify(
        self,
        logs: str,
        evidence: Evidence | None = None,
        use_rules_only: bool = False,
    ) -> Classification:
        """Classify failure based on logs and evidence.
        
        Args:
            logs: Raw failure logs
            evidence: Optional evidence with historical context
            use_rules_only: If True, skip LLM and use only pattern matching
            
        Returns:
            Classification result
        """
        # Match patterns
        pattern_match = self._match_patterns(logs)
        
        if pattern_match:
            confidence = pattern_match["confidence"]
            
            # Adjust confidence based on evidence
            if evidence:
                confidence = self._adjust_confidence(confidence, evidence)
            
            # Determine severity
            severity = self._determine_severity(logs)
            
            return Classification(
                category=FailureCategory.from_string(pattern_match["category"]),
                confidence=confidence,
                severity=severity,
                reasoning=f"Pattern matched: {pattern_match['description']}",
                recommendation=self._get_recommendation(pattern_match["category"]),
                matched_patterns=[pattern_match["description"]],
            )
        
        # No pattern match - return low confidence result
        return Classification(
            category=FailureCategory.TO_INVESTIGATE,
            confidence=0.4,
            severity=Severity.MEDIUM,
            reasoning="No definitive pattern matched. LLM analysis recommended.",
            recommendation="Investigate logs manually or use LLM analysis.",
        )
    
    def _match_patterns(self, logs: str) -> dict[str, Any] | None:
        """Match logs against known patterns."""
        matches = []
        
        for pattern, category, desc, base_confidence in self._compiled_patterns:
            if pattern.search(logs):
                matches.append({
                    "category": category,
                    "description": desc,
                    "confidence": base_confidence,
                    "pattern": pattern.pattern,
                })
        
        if not matches:
            return None
        
        # Return highest confidence match
        return max(matches, key=lambda x: x["confidence"])
    
    def _adjust_confidence(self, base_confidence: float, evidence: Evidence) -> float:
        """Adjust confidence based on evidence strength."""
        confidence = base_confidence
        
        # Boost for multiple patterns
        if len(evidence.patterns) > 2:
            confidence = min(confidence + 0.05, 0.98)
        
        # Boost for stack trace
        if evidence.stack_trace:
            confidence = min(confidence + 0.03, 0.98)
        
        # Reduce if historically flaky
        if evidence.historical_failures > 3:
            confidence = max(confidence - 0.1, 0.5)
        
        return confidence
    
    def _determine_severity(self, logs: str) -> Severity:
        """Determine severity based on log patterns."""
        for severity_level, patterns in SEVERITY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, logs, re.IGNORECASE):
                    return Severity(severity_level)
        
        return Severity.MEDIUM
    
    def _get_recommendation(self, category: str) -> str:
        """Get recommendation based on category."""
        recommendations = {
            "Infrastructure Issue": (
                "1. Check cluster health with `oc get nodes`\n"
                "2. Verify credentials and secrets\n"
                "3. Check operator status"
            ),
            "Test Automation Issue": (
                "1. Review timeout values\n"
                "2. Add explicit waits\n"
                "3. Check test isolation"
            ),
            "Product Bug": (
                "1. File bug report with reproduction steps\n"
                "2. Check component logs\n"
                "3. Verify configuration"
            ),
            "Intermittent Failure": (
                "1. Add @pytest.mark.flaky decorator\n"
                "2. Replace sleeps with explicit waits\n"
                "3. Review resource cleanup"
            ),
        }
        return recommendations.get(category, "Investigate further.")
    
    def get_evidence_from_logs(self, logs: str, test_code: str = "") -> Evidence:
        """Extract evidence from logs and test code."""
        error_message = ""
        error_type = ""
        stack_trace = ""
        patterns = []
        
        # Extract error info
        error_match = re.search(r"(?:Error|Exception):\s*(.{10,500})", logs, re.IGNORECASE)
        if error_match:
            error_message = error_match.group(0)
        
        type_match = re.search(r"(\w+Error|\w+Exception)", logs)
        if type_match:
            error_type = type_match.group(1)
        
        trace_match = re.search(r"Traceback.*?(?=\n\n|\Z)", logs, re.DOTALL)
        if trace_match:
            stack_trace = trace_match.group(0)[:800]
        
        # Find matching patterns
        for compiled, category, desc, _ in self._compiled_patterns:
            if compiled.search(logs):
                patterns.append(f"{desc} ({category})")
        
        # Check for flaky indicators in test code
        known_flaky = False
        decorators = []
        if test_code:
            flaky_indicators = [
                r"@pytest\.mark\.flaky",
                r"@pytest\.mark\.xfail",
                r"@retry",
            ]
            for indicator in flaky_indicators:
                if re.search(indicator, test_code, re.IGNORECASE):
                    known_flaky = True
                    break
            
            decorator_matches = re.findall(r"@(\w+(?:\.\w+)*)", test_code)
            decorators = decorator_matches[:10]
        
        return Evidence(
            error_message=error_message,
            error_type=error_type,
            patterns=patterns,
            test_code=test_code[:3000] if test_code else "",
            stack_trace=stack_trace,
            decorators=decorators,
            known_flaky=known_flaky,
        )
