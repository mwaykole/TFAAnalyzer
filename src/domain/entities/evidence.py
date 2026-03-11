"""Evidence entity for gathering analysis data."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Evidence:
    """Domain entity representing evidence collected for analysis.
    
    Single Responsibility: Only holds evidence data from logs and context.
    """
    
    error_message: str = ""
    error_type: str = ""
    patterns: list[str] = field(default_factory=list)
    test_code: str = ""
    test_file: str = ""
    fixtures: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    stack_trace: str = ""
    verification_result: str = "not_run"
    verification_output: str = ""
    historical_failures: int = 0
    historical_pass_rate: float = 1.0
    known_flaky: bool = False
    
    # Code fetcher fields
    github_url: str = ""
    function_name: str = ""
    line_start: int | None = None
    line_end: int | None = None
    has_timeout: bool = False
    timeout_value: int | None = None
    has_retry: bool = False
    uses_sleep: bool = False
    wait_patterns: list[str] = field(default_factory=list)
    parametrize_args: list[str] = field(default_factory=list)
    
    # Enhanced analysis fields
    pre_error_context: str = ""  # WARNING/INFO logs before ERROR
    timeout_analysis: str = ""   # Timeout verdict and recommendation
    systemic_issue: str = ""     # Detected systemic issue from clustering
    cluster_recommendation: str = ""  # Recommendation from cluster analysis
    failed_on_setup: bool = False  # Test failed during setup phase, not test body
    
    # Must-gather fields
    must_gather_context: str = ""  # Cluster state from must-gather analysis
    cluster_health: str = ""       # "healthy", "degraded", "critical", "warning"
    
    @property
    def has_strong_evidence(self) -> bool:
        """Check if there's strong evidence for classification."""
        return bool(self.patterns) or bool(self.stack_trace) or bool(self.error_type)
    
    @property
    def is_likely_flaky(self) -> bool:
        """Check if evidence suggests flaky test."""
        return self.known_flaky or self.is_code_flaky or (0.2 <= self.historical_pass_rate <= 0.8)
    
    @property
    def is_code_flaky(self) -> bool:
        """Check if code analysis suggests flaky test.
        
        Based on AST analysis of test source code.
        """
        indicators = [
            self.uses_sleep,
            self.has_timeout,
            len(self.wait_patterns) > 0,
            any("flaky" in d.lower() for d in self.decorators),
            any("skip" in d.lower() for d in self.decorators),
            any("xfail" in d.lower() for d in self.decorators),
        ]
        return sum(indicators) >= 2
    
    @property
    def is_intermittent(self) -> bool:
        """Check if test passed on verification (intermittent failure)."""
        return self.verification_result == "passed"
    
    @property
    def has_github_link(self) -> bool:
        """Check if GitHub URL is available."""
        return bool(self.github_url)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "error_message": self.error_message,
            "error_type": self.error_type,
            "patterns": self.patterns,
            "stack_trace": self.stack_trace[:500] if self.stack_trace else "",
            "historical_failures": self.historical_failures,
            "historical_pass_rate": self.historical_pass_rate,
            "known_flaky": self.known_flaky,
            "verification_result": self.verification_result,
            "github_url": self.github_url,
            "test_file": self.test_file,
            "fixtures": self.fixtures,
            "decorators": self.decorators,
            "has_timeout": self.has_timeout,
            "uses_sleep": self.uses_sleep,
            "wait_patterns": self.wait_patterns,
            "is_code_flaky": self.is_code_flaky,
        }
        
        # Add enhanced analysis fields if present
        if self.pre_error_context:
            result["pre_error_context"] = self.pre_error_context[:300]
        if self.timeout_analysis:
            result["timeout_analysis"] = self.timeout_analysis
        if self.systemic_issue:
            result["systemic_issue"] = self.systemic_issue
        if self.cluster_health:
            result["cluster_health"] = self.cluster_health
        
        return result
    
    def summary(self) -> str:
        """Generate evidence summary for display."""
        parts = []
        if self.error_type:
            parts.append(f"Error: {self.error_type}")
        if self.patterns:
            parts.append(f"Patterns: {', '.join(self.patterns[:3])}")
        if self.historical_pass_rate < 1.0:
            parts.append(f"Pass rate: {self.historical_pass_rate:.0%}")
        if self.is_code_flaky:
            parts.append("Code: flaky indicators")
        if self.fixtures:
            parts.append(f"Fixtures: {', '.join(self.fixtures[:3])}")
        
        # Enhanced analysis indicators
        if self.systemic_issue:
            parts.append(f"⚠️ Systemic: {self.systemic_issue[:30]}")
        if self.timeout_analysis:
            parts.append(f"⏱️ Timeout: {self.timeout_analysis[:30]}")
        if self.cluster_health and self.cluster_health not in ("healthy", ""):
            parts.append(f"Cluster: {self.cluster_health}")
        
        return " | ".join(parts) if parts else "No strong evidence"
    
    def code_analysis_summary(self) -> str:
        """Generate summary of code analysis findings."""
        findings = []
        if self.uses_sleep:
            findings.append("uses time.sleep()")
        if self.has_timeout:
            timeout_str = f"timeout={self.timeout_value}s" if self.timeout_value else "timeout decorator"
            findings.append(timeout_str)
        if self.wait_patterns:
            findings.append(f"wait patterns: {', '.join(self.wait_patterns[:3])}")
        if self.has_retry:
            findings.append("has retry/flaky decorator")
        if self.fixtures:
            findings.append(f"fixtures: {', '.join(self.fixtures[:3])}")
        return " | ".join(findings) if findings else "No notable patterns"
