"""Tests for metrics tracking module."""

import pytest
import time
from src.utils.metrics import (
    AnalysisMetrics,
    start_metrics,
    get_metrics,
    finish_metrics,
    LLM_PRICING,
)


class TestAnalysisMetrics:
    """Tests for AnalysisMetrics class."""

    def test_creation(self):
        """Test metrics creation."""
        m = AnalysisMetrics(model_name="test-model", provider="test")
        assert m.llm_calls == 0
        assert m.model_name == "test-model"
        assert m.provider == "test"

    def test_record_llm_call(self):
        """Test recording LLM calls."""
        m = AnalysisMetrics()
        m.record_llm_call(input_tokens=100, output_tokens=50)
        m.record_llm_call(input_tokens=200, output_tokens=100)
        
        assert m.llm_calls == 2
        assert m.total_input_tokens == 300
        assert m.total_output_tokens == 150

    def test_record_cache_hit(self):
        """Test recording cache hits."""
        m = AnalysisMetrics()
        m.record_cache_hit()
        m.record_cache_hit()
        m.record_cache_miss()
        
        assert m.cache_hits == 2
        assert m.cache_misses == 1

    def test_cache_hit_rate(self):
        """Test cache hit rate calculation."""
        m = AnalysisMetrics()
        m.cache_hits = 3
        m.cache_misses = 1
        
        assert m.cache_hit_rate == 0.75

    def test_cache_hit_rate_empty(self):
        """Test cache hit rate when no cache operations."""
        m = AnalysisMetrics()
        assert m.cache_hit_rate == 0.0

    def test_record_verification(self):
        """Test recording verification results."""
        m = AnalysisMetrics()
        m.record_verification("passed")
        m.record_verification("failed")
        m.record_verification("failed")
        m.record_verification("skipped_high_confidence")
        
        assert m.tests_verified == 4
        assert m.tests_passed == 1
        assert m.tests_failed == 2
        assert m.tests_skipped == 1

    def test_duration(self):
        """Test duration calculation."""
        m = AnalysisMetrics()
        time.sleep(0.1)
        m.finish()
        
        assert m.duration_seconds >= 0.1

    def test_estimated_cost_claude(self):
        """Test cost estimation for Claude models."""
        m = AnalysisMetrics(model_name="claude-sonnet-4-20250514")
        m.total_input_tokens = 1_000_000
        m.total_output_tokens = 100_000
        
        # Expected: $3 input + $1.5 output = $4.5
        expected = 3.0 + 1.5
        assert m.estimated_cost == expected

    def test_estimated_cost_free_provider(self):
        """Test cost estimation for free providers."""
        m = AnalysisMetrics(model_name="claude-cli")
        m.total_input_tokens = 1_000_000
        m.total_output_tokens = 1_000_000
        
        assert m.estimated_cost == 0.0

    def test_llm_calls_saved(self):
        """Test LLM calls saved property."""
        m = AnalysisMetrics()
        m.rca_reused = 5
        assert m.llm_calls_saved == 5

    def test_to_dict(self):
        """Test conversion to dictionary."""
        m = AnalysisMetrics(model_name="test", provider="test-provider")
        m.llm_calls = 2
        m.total_input_tokens = 100
        m.total_output_tokens = 50
        m.cache_hits = 3
        m.failures_analyzed = 5
        m.unique_signatures = 2
        m.rca_reused = 3
        m.finish()
        
        d = m.to_dict()
        
        assert "duration_seconds" in d
        assert d["llm"]["calls"] == 2
        assert d["llm"]["total_tokens"] == 150
        assert d["cache"]["hits"] == 3
        assert d["analysis"]["failures_analyzed"] == 5
        assert d["analysis"]["rca_reused"] == 3

    def test_summary(self):
        """Test summary generation."""
        m = AnalysisMetrics()
        m.failures_analyzed = 8
        m.unique_signatures = 2
        m.llm_calls = 2
        m.rca_reused = 6
        m.cache_hits = 3
        m.cache_misses = 1
        m.finish()
        
        summary = m.summary()
        
        assert "8 failures" in summary
        assert "2 unique signatures" in summary
        assert "2 calls" in summary
        assert "6 RCAs" in summary
        assert "75%" in summary  # cache hit rate


class TestMetricsGlobals:
    """Tests for global metrics functions."""

    def test_start_and_get_metrics(self):
        """Test starting and getting metrics."""
        m = start_metrics(model="test", provider="test-provider")
        
        assert m is not None
        assert m.model_name == "test"
        
        retrieved = get_metrics()
        assert retrieved is m

    def test_finish_metrics(self):
        """Test finishing metrics."""
        m = start_metrics()
        time.sleep(0.05)
        result = finish_metrics()
        
        assert result is m
        assert result.end_time > 0
        assert result.duration_seconds >= 0.05


class TestLLMPricing:
    """Tests for LLM pricing data."""

    def test_pricing_exists(self):
        """Test that pricing exists for known models."""
        assert "claude-sonnet-4-20250514" in LLM_PRICING
        assert "claude-cli" in LLM_PRICING
        assert "ollama" in LLM_PRICING

    def test_pricing_structure(self):
        """Test pricing has correct structure."""
        for model, pricing in LLM_PRICING.items():
            assert "input" in pricing
            assert "output" in pricing
            assert pricing["input"] >= 0
            assert pricing["output"] >= 0
