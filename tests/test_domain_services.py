"""Tests for domain services."""

import pytest
from src.domain.entities import Classification, Evidence, FailureCategory, Severity
from src.domain.services import ClassificationService


class TestClassificationService:
    """Tests for ClassificationService."""

    @pytest.fixture
    def service(self):
        """Create a classification service instance."""
        return ClassificationService()

    def test_classify_infrastructure_pod_failure(self, service):
        """Test infrastructure pod failure classification."""
        logs = "Pod entered CrashLoopBackOff state after 5 restarts"
        result = service.classify(logs)
        assert result is not None
        assert result.category == FailureCategory.INFRASTRUCTURE_ISSUE
        assert result.confidence >= 0.9

    def test_classify_infrastructure_oom(self, service):
        """Test infrastructure OOM classification."""
        logs = "Container was OOMKilled due to memory pressure"
        result = service.classify(logs)
        assert result is not None
        assert result.category == FailureCategory.INFRASTRUCTURE_ISSUE
        assert result.confidence >= 0.9

    def test_classify_automation_timeout(self, service):
        """Test automation timeout classification."""
        logs = "TimeoutExpiredError: Operation timed out after 60s"
        result = service.classify(logs)
        assert result is not None
        assert result.category == FailureCategory.TEST_AUTOMATION_ISSUE

    def test_classify_automation_assertion(self, service):
        """Test automation assertion classification."""
        logs = "AssertionError: Expected True but got False"
        result = service.classify(logs)
        assert result is not None
        assert result.category == FailureCategory.TEST_AUTOMATION_ISSUE

    def test_classify_no_match_returns_to_investigate(self, service):
        """Test that unmatched patterns return TO_INVESTIGATE."""
        logs = "Some random log content that doesn't match any patterns"
        result = service.classify(logs)
        assert result is not None
        assert result.category == FailureCategory.TO_INVESTIGATE
        assert result.confidence < 0.5

    def test_classify_network_error(self, service):
        """Test network error classification."""
        logs = "Connection refused when connecting to api.example.com:8080"
        result = service.classify(logs)
        assert result is not None
        assert result.category == FailureCategory.INFRASTRUCTURE_ISSUE

    def test_classify_gpu_issue(self, service):
        """Test GPU issue classification."""
        logs = "CUDA error: device not found, GPU not available"
        result = service.classify(logs)
        assert result is not None
        assert result.category == FailureCategory.INFRASTRUCTURE_ISSUE
        assert result.confidence >= 0.9

    def test_classify_product_bug(self, service):
        """Test product bug classification."""
        logs = "InferenceService Failed to start with status code 503"
        result = service.classify(logs)
        assert result is not None
        # Should match server error or inference failure
        assert result.category in [FailureCategory.PRODUCT_BUG, FailureCategory.INFRASTRUCTURE_ISSUE]

    def test_get_recommendation_method(self, service):
        """Test _get_recommendation method."""
        rec = service._get_recommendation("Infrastructure Issue")
        assert rec is not None
        assert isinstance(rec, str)
        assert len(rec) > 0

    def test_get_recommendation_for_all_categories(self, service):
        """Test recommendations exist for all categories."""
        categories = [
            "Infrastructure Issue",
            "Test Automation Issue", 
            "Product Bug",
            "Intermittent Failure",
        ]
        for category in categories:
            rec = service._get_recommendation(category)
            assert rec is not None
            assert isinstance(rec, str)

    def test_determine_severity_critical(self, service):
        """Test critical severity detection."""
        logs = "Container OOMKilled after running out of memory"
        severity = service._determine_severity(logs)
        assert severity == Severity.CRITICAL

    def test_determine_severity_high(self, service):
        """Test high severity detection."""
        logs = "Request failed with status code 503"
        severity = service._determine_severity(logs)
        assert severity == Severity.HIGH

    def test_determine_severity_medium(self, service):
        """Test medium severity default."""
        logs = "Some generic error occurred"
        severity = service._determine_severity(logs)
        assert severity == Severity.MEDIUM

    def test_classify_with_evidence(self, service):
        """Test classification with evidence adjusts confidence."""
        logs = "Connection refused to database"
        evidence = Evidence(
            patterns=["network", "timeout", "connection"],
            stack_trace="Traceback...",
        )
        result = service.classify(logs, evidence=evidence)
        assert result is not None
        # With additional evidence, confidence should be boosted
        assert result.confidence >= 0.9

    def test_get_evidence_from_logs(self, service):
        """Test evidence extraction from logs."""
        logs = """
        TimeoutError: Connection timed out
        Traceback (most recent call last):
          File "test.py", line 42, in test_example
            raise TimeoutError()
        """
        evidence = service.get_evidence_from_logs(logs)
        assert evidence.error_type == "TimeoutError"
        assert len(evidence.stack_trace) > 0

    def test_get_evidence_with_test_code(self, service):
        """Test evidence extraction with test code."""
        logs = "Error occurred in test"
        test_code = """
        @pytest.mark.flaky(reruns=3)
        def test_example():
            pass
        """
        evidence = service.get_evidence_from_logs(logs, test_code=test_code)
        assert evidence.known_flaky is True
        assert "@pytest" in str(evidence.decorators) or "flaky" in str(evidence.decorators).lower()


class TestClassificationPatterns:
    """Test classification pattern coverage."""

    @pytest.fixture
    def service(self):
        return ClassificationService()

    @pytest.mark.parametrize("log_msg,expected_category", [
        ("CrashLoopBackOff detected", FailureCategory.INFRASTRUCTURE_ISSUE),
        ("ImagePullBackOff for image", FailureCategory.INFRASTRUCTURE_ISSUE),
        ("OOMKilled by system", FailureCategory.INFRASTRUCTURE_ISSUE),
        ("AccessDenied for S3 bucket", FailureCategory.INFRASTRUCTURE_ISSUE),
        ("connection refused", FailureCategory.INFRASTRUCTURE_ISSUE),
        ("TimeoutExpiredError in test", FailureCategory.TEST_AUTOMATION_ISSUE),
        ("AssertionError: test failed", FailureCategory.TEST_AUTOMATION_ISSUE),
        ("fixture not found", FailureCategory.TEST_AUTOMATION_ISSUE),
        ("status code 500 error", FailureCategory.PRODUCT_BUG),
        ("CUDA error occurred", FailureCategory.INFRASTRUCTURE_ISSUE),
        ("ResourceQuota exceeded", FailureCategory.INFRASTRUCTURE_ISSUE),
    ])
    def test_pattern_classification(self, service, log_msg, expected_category):
        """Test that specific patterns map to expected categories."""
        result = service.classify(log_msg)
        assert result.category == expected_category, \
            f"Expected {expected_category} for '{log_msg}', got {result.category}"


class TestClassificationServiceEdgeCases:
    """Test edge cases for classification service."""

    @pytest.fixture
    def service(self):
        return ClassificationService()

    def test_empty_logs(self, service):
        """Test handling of empty logs."""
        result = service.classify("")
        assert result is not None
        assert result.category == FailureCategory.TO_INVESTIGATE

    def test_very_long_logs(self, service):
        """Test handling of very long logs."""
        logs = "Error: " + "a" * 100000  # 100KB of content
        result = service.classify(logs)
        # Should not crash
        assert result is not None

    def test_special_characters_in_logs(self, service):
        """Test handling of special characters."""
        logs = "Error: 特殊文字 <script>alert('xss')</script> \x00\x01"
        result = service.classify(logs)
        assert result is not None

    def test_multiple_pattern_matches(self, service):
        """Test that highest confidence pattern wins."""
        # Contains both OOMKilled (0.95) and AssertionError (0.75)
        logs = "OOMKilled - AssertionError in cleanup"
        result = service.classify(logs)
        # Should match OOMKilled with higher confidence
        assert result.category == FailureCategory.INFRASTRUCTURE_ISSUE
        assert result.confidence >= 0.9
