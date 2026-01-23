"""Metrics tracking for TFA analysis."""

from dataclasses import dataclass, field
from typing import Any
import time


# Pricing per 1M tokens (as of Jan 2025)
LLM_PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},  # Groq
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},  # Groq
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},  # Groq
    "claude-cli": {"input": 0.0, "output": 0.0},  # Free (local CLI)
    "ollama": {"input": 0.0, "output": 0.0},  # Free (local)
}


@dataclass
class AnalysisMetrics:
    """Metrics for a single analysis run."""
    
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    
    # LLM metrics
    llm_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    model_name: str = ""
    provider: str = ""
    
    # Cache metrics
    cache_hits: int = 0
    cache_misses: int = 0
    
    # Analysis metrics
    failures_analyzed: int = 0
    unique_signatures: int = 0
    rca_reused: int = 0
    
    # Verification metrics
    tests_verified: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    
    def record_llm_call(self, input_tokens: int = 0, output_tokens: int = 0):
        """Record an LLM API call."""
        self.llm_calls += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
    
    def record_cache_hit(self):
        """Record a cache hit."""
        self.cache_hits += 1
    
    def record_cache_miss(self):
        """Record a cache miss."""
        self.cache_misses += 1
    
    def record_verification(self, result: str):
        """Record a verification result."""
        self.tests_verified += 1
        if result == "passed":
            self.tests_passed += 1
        elif result == "failed":
            self.tests_failed += 1
        elif result in ("skipped_high_confidence", "not_run"):
            self.tests_skipped += 1
    
    def finish(self):
        """Mark analysis as complete."""
        self.end_time = time.time()
    
    @property
    def duration_seconds(self) -> float:
        """Get analysis duration in seconds."""
        end = self.end_time if self.end_time > 0 else time.time()
        return end - self.start_time
    
    @property
    def cache_hit_rate(self) -> float:
        """Get cache hit rate as percentage."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total
    
    @property
    def estimated_cost(self) -> float:
        """Estimate cost in USD based on token usage."""
        pricing = LLM_PRICING.get(self.model_name, {"input": 0, "output": 0})
        input_cost = (self.total_input_tokens / 1_000_000) * pricing["input"]
        output_cost = (self.total_output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost
    
    @property
    def llm_calls_saved(self) -> int:
        """Number of LLM calls saved by reusing RCA."""
        return self.rca_reused
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "duration_seconds": round(self.duration_seconds, 2),
            "llm": {
                "calls": self.llm_calls,
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
                "total_tokens": self.total_input_tokens + self.total_output_tokens,
                "model": self.model_name,
                "provider": self.provider,
                "estimated_cost_usd": round(self.estimated_cost, 4),
            },
            "cache": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "hit_rate": round(self.cache_hit_rate * 100, 1),
            },
            "analysis": {
                "failures_analyzed": self.failures_analyzed,
                "unique_signatures": self.unique_signatures,
                "rca_reused": self.rca_reused,
                "llm_calls_saved": self.llm_calls_saved,
            },
            "verification": {
                "tests_verified": self.tests_verified,
                "tests_passed": self.tests_passed,
                "tests_failed": self.tests_failed,
                "tests_skipped": self.tests_skipped,
            },
        }
    
    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"⏱  Duration: {self.duration_seconds:.1f}s",
            f"🔍 Analyzed: {self.failures_analyzed} failures → {self.unique_signatures} unique signatures",
        ]
        
        if self.llm_calls > 0:
            lines.append(f"🤖 LLM: {self.llm_calls} calls, {self.total_input_tokens + self.total_output_tokens:,} tokens")
            if self.estimated_cost > 0:
                lines.append(f"💰 Cost: ${self.estimated_cost:.4f}")
        
        if self.rca_reused > 0:
            lines.append(f"♻️  Reused: {self.rca_reused} RCAs (saved {self.rca_reused} LLM calls)")
        
        if self.cache_hits > 0:
            lines.append(f"📦 Cache: {self.cache_hit_rate:.0%} hit rate ({self.cache_hits}/{self.cache_hits + self.cache_misses})")
        
        if self.tests_verified > 0:
            lines.append(f"✅ Verified: {self.tests_verified} tests ({self.tests_passed} passed, {self.tests_failed} failed)")
        
        return "\n".join(lines)


# Global metrics instance for current analysis
_current_metrics: AnalysisMetrics | None = None


def start_metrics(model: str = "", provider: str = "") -> AnalysisMetrics:
    """Start tracking metrics for a new analysis."""
    global _current_metrics
    _current_metrics = AnalysisMetrics(model_name=model, provider=provider)
    return _current_metrics


def get_metrics() -> AnalysisMetrics | None:
    """Get current metrics instance."""
    return _current_metrics


def finish_metrics() -> AnalysisMetrics | None:
    """Finish and return metrics."""
    global _current_metrics
    if _current_metrics:
        _current_metrics.finish()
    return _current_metrics
