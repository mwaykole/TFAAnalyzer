"""Tests for domain entities."""

import pytest
from src.domain.entities import (
    Failure,
    Classification,
    Evidence,
    RCA,
    FailureCategory,
    Severity,
)


class TestFailureCategory:
    """Tests for FailureCategory enum."""

    def test_from_string_exact_match(self):
        """Test exact string matching."""
        assert FailureCategory.from_string("Product Bug") == FailureCategory.PRODUCT_BUG
        assert FailureCategory.from_string("Test Automation Issue") == FailureCategory.TEST_AUTOMATION_ISSUE
        assert FailureCategory.from_string("Infrastructure Issue") == FailureCategory.INFRASTRUCTURE_ISSUE

    def test_from_string_case_insensitive(self):
        """Test case insensitive matching."""
        assert FailureCategory.from_string("product bug") == FailureCategory.PRODUCT_BUG
        assert FailureCategory.from_string("PRODUCT BUG") == FailureCategory.PRODUCT_BUG

    def test_from_string_unknown(self):
        """Test unknown category defaults to TO_INVESTIGATE."""
        assert FailureCategory.from_string("Unknown") == FailureCategory.TO_INVESTIGATE
        assert FailureCategory.from_string("random string") == FailureCategory.TO_INVESTIGATE

    def test_from_string_aliases(self):
        """Test alias mappings."""
        assert FailureCategory.from_string("pb") == FailureCategory.PRODUCT_BUG
        assert FailureCategory.from_string("ta") == FailureCategory.TEST_AUTOMATION_ISSUE
        assert FailureCategory.from_string("infra") == FailureCategory.INFRASTRUCTURE_ISSUE
        assert FailureCategory.from_string("flaky") == FailureCategory.INTERMITTENT_FAILURE

    def test_icon_property(self):
        """Test icon property."""
        assert FailureCategory.PRODUCT_BUG.icon == "🐛"
        assert FailureCategory.INFRASTRUCTURE_ISSUE.icon == "🌐"
        assert FailureCategory.TEST_AUTOMATION_ISSUE.icon == "🔧"
        assert FailureCategory.INTERMITTENT_FAILURE.icon == "🔄"
        assert FailureCategory.TO_INVESTIGATE.icon == "❓"

    def test_defect_type_code(self):
        """Test ReportPortal defect type codes."""
        assert FailureCategory.PRODUCT_BUG.defect_type_code == "pb001"
        assert FailureCategory.TEST_AUTOMATION_ISSUE.defect_type_code == "ab001"
        assert FailureCategory.INFRASTRUCTURE_ISSUE.defect_type_code == "si001"


class TestSeverity:
    """Tests for Severity enum."""

    def test_values(self):
        """Test severity values."""
        assert Severity.LOW.value == "LOW"
        assert Severity.MEDIUM.value == "MEDIUM"
        assert Severity.HIGH.value == "HIGH"
        assert Severity.CRITICAL.value == "CRITICAL"

    def test_icon_property(self):
        """Test icon property."""
        assert Severity.LOW.icon == "⚪"
        assert Severity.MEDIUM.icon == "🟡"
        assert Severity.HIGH.icon == "🟠"
        assert Severity.CRITICAL.icon == "🔴"


class TestClassification:
    """Tests for Classification entity."""

    def test_creation(self):
        """Test classification creation."""
        cls = Classification(
            category=FailureCategory.PRODUCT_BUG,
            confidence=0.85,
            severity=Severity.HIGH,
            reasoning="Test failed due to null pointer",
            recommendation="Fix the null check",
        )
        assert cls.category == FailureCategory.PRODUCT_BUG
        assert cls.confidence == 0.85
        assert cls.severity == Severity.HIGH

    def test_confidence_clamping(self):
        """Test confidence is clamped to [0, 1]."""
        cls = Classification(
            category=FailureCategory.PRODUCT_BUG,
            confidence=1.5,
            severity=Severity.MEDIUM,
            reasoning="",
            recommendation="",
        )
        assert cls.confidence == 1.0

        cls2 = Classification(
            category=FailureCategory.PRODUCT_BUG,
            confidence=-0.5,
            severity=Severity.MEDIUM,
            reasoning="",
            recommendation="",
        )
        assert cls2.confidence == 0.0

    def test_confidence_percent(self):
        """Test confidence_percent property."""
        cls = Classification(
            category=FailureCategory.PRODUCT_BUG,
            confidence=0.85,
            severity=Severity.MEDIUM,
            reasoning="",
            recommendation="",
        )
        assert cls.confidence_percent == 85

    def test_is_high_confidence(self):
        """Test is_high_confidence property."""
        high = Classification(
            category=FailureCategory.PRODUCT_BUG,
            confidence=0.95,
            severity=Severity.MEDIUM,
            reasoning="",
            recommendation="",
        )
        assert high.is_high_confidence is True

        low = Classification(
            category=FailureCategory.PRODUCT_BUG,
            confidence=0.5,
            severity=Severity.MEDIUM,
            reasoning="",
            recommendation="",
        )
        assert low.is_high_confidence is False

    def test_to_dict(self):
        """Test to_dict method."""
        cls = Classification(
            category=FailureCategory.PRODUCT_BUG,
            confidence=0.85,
            severity=Severity.HIGH,
            reasoning="Error in code",
            recommendation="Fix it",
        )
        d = cls.to_dict()
        assert d["category"] == "Product Bug"
        assert d["confidence"] == 0.85
        assert d["severity"] == "HIGH"
        assert d["defect_type_code"] == "pb001"


class TestEvidence:
    """Tests for Evidence entity."""

    def test_creation(self):
        """Test evidence creation."""
        ev = Evidence(
            error_message="Connection refused",
            error_type="ConnectionError",
            patterns=["timeout", "network"],
        )
        assert ev.error_message == "Connection refused"
        assert ev.error_type == "ConnectionError"
        assert "timeout" in ev.patterns

    def test_default_values(self):
        """Test default values."""
        ev = Evidence()
        assert ev.error_message == ""
        assert ev.patterns == []
        assert ev.historical_pass_rate == 1.0
        assert ev.known_flaky is False

    def test_has_strong_evidence(self):
        """Test has_strong_evidence property."""
        weak = Evidence()
        assert weak.has_strong_evidence is False

        strong = Evidence(error_type="TimeoutError")
        assert strong.has_strong_evidence is True

        strong2 = Evidence(patterns=["timeout"])
        assert strong2.has_strong_evidence is True

    def test_is_likely_flaky(self):
        """Test is_likely_flaky property."""
        not_flaky = Evidence(historical_pass_rate=0.95)
        assert not_flaky.is_likely_flaky is False

        flaky = Evidence(historical_pass_rate=0.5)
        assert flaky.is_likely_flaky is True

        known = Evidence(known_flaky=True)
        assert known.is_likely_flaky is True

    def test_to_dict(self):
        """Test to_dict method."""
        ev = Evidence(
            error_message="Error",
            error_type="TestError",
            patterns=["pattern1"],
        )
        d = ev.to_dict()
        assert d["error_message"] == "Error"
        assert d["error_type"] == "TestError"

    def test_summary(self):
        """Test summary method."""
        ev = Evidence(error_type="TimeoutError", patterns=["timeout"])
        summary = ev.summary()
        assert "TimeoutError" in summary


class TestFailure:
    """Tests for Failure entity."""

    def test_creation(self):
        """Test failure creation."""
        failure = Failure(
            id="123",
            test_name="test_model_deployment",
            logs="Error: Connection refused",
            status="FAILED",
            launch_id="9657",
        )
        assert failure.id == "123"
        assert failure.test_name == "test_model_deployment"
        assert failure.status == "FAILED"

    def test_validation_empty_id(self):
        """Test that empty ID raises ValueError."""
        with pytest.raises(ValueError, match="ID cannot be empty"):
            Failure(
                id="",
                test_name="test_example",
                logs="log",
                status="FAILED",
                launch_id="123",
            )

    def test_validation_empty_name(self):
        """Test that empty test name raises ValueError."""
        with pytest.raises(ValueError, match="Test name cannot be empty"):
            Failure(
                id="123",
                test_name="",
                logs="log",
                status="FAILED",
                launch_id="123",
            )

    def test_cache_key_generation(self):
        """Test cache key generation."""
        failure = Failure(
            id="123",
            test_name="test_example",
            logs="Some log content",
            status="FAILED",
            launch_id="9657",
        )
        key = failure.cache_key
        assert key is not None
        assert key.startswith("failure:123:")
        assert isinstance(key, str)

    def test_same_cache_key_for_similar_logs(self):
        """Test that similar logs produce the same cache key."""
        failure1 = Failure(
            id="1",
            test_name="test_a",
            logs="Same log content here",
            status="FAILED",
            launch_id="123",
        )
        failure2 = Failure(
            id="1",
            test_name="test_b",
            logs="Same log content here",
            status="FAILED",
            launch_id="123",
        )
        # Same ID and logs = same cache key
        assert failure1.cache_key == failure2.cache_key

    def test_to_dict(self):
        """Test to_dict method."""
        failure = Failure(
            id="123",
            test_name="test_example",
            logs="log content",
            status="FAILED",
            launch_id="9657",
            component="Model_server",
        )
        d = failure.to_dict()
        assert d["id"] == "123"
        assert d["test_name"] == "test_example"
        assert d["component"] == "Model_server"

    def test_from_dict(self):
        """Test from_dict class method."""
        data = {
            "id": "123",
            "test_name": "test_example",
            "logs": "log",
            "status": "FAILED",
            "launch_id": "9657",
            "component": "test",
        }
        failure = Failure.from_dict(data)
        assert failure.id == "123"
        assert failure.test_name == "test_example"


class TestRCA:
    """Tests for RCA entity."""

    def test_creation(self):
        """Test RCA creation."""
        cls = Classification(
            category=FailureCategory.PRODUCT_BUG,
            confidence=0.9,
            severity=Severity.HIGH,
            reasoning="Bug in code",
            recommendation="Fix it",
        )
        rca = RCA(
            classification=cls,
            root_cause="Null pointer in service",
            evidence_summary="Log shows NPE at line 42",
        )
        assert rca.category == FailureCategory.PRODUCT_BUG
        assert rca.confidence == 0.9

    def test_properties(self):
        """Test RCA properties delegate to classification."""
        cls = Classification(
            category=FailureCategory.INFRASTRUCTURE_ISSUE,
            confidence=0.8,
            severity=Severity.MEDIUM,
            reasoning="Network issue",
            recommendation="Check network",
        )
        rca = RCA(
            classification=cls,
            root_cause="DNS failure",
            evidence_summary="DNS lookup failed",
        )
        assert rca.severity == Severity.MEDIUM
        assert rca.reasoning == "Network issue"
        assert rca.recommendation == "Check network"

    def test_to_dict(self):
        """Test to_dict method."""
        cls = Classification(
            category=FailureCategory.PRODUCT_BUG,
            confidence=0.9,
            severity=Severity.HIGH,
            reasoning="Bug in code",
            recommendation="Fix it",
        )
        rca = RCA(
            classification=cls,
            root_cause="Null pointer in service",
            evidence_summary="Log shows NPE at line 42",
        )
        d = rca.to_dict()
        assert d["classification"] == "Product Bug"
        assert d["root_cause"] == "Null pointer in service"

    def test_to_rp_comment(self):
        """Test ReportPortal comment generation."""
        cls = Classification(
            category=FailureCategory.PRODUCT_BUG,
            confidence=0.9,
            severity=Severity.HIGH,
            reasoning="Bug in code",
            recommendation="Fix it",
        )
        rca = RCA(
            classification=cls,
            root_cause="Null pointer in service",
            evidence_summary="Log shows NPE at line 42",
        )
        comment = rca.to_rp_comment()
        assert "AI Classification" in comment
        assert "Product Bug" in comment
        assert "90%" in comment
        assert "🤖 AI:" in comment

    def test_from_dict(self):
        """Test from_dict class method."""
        data = {
            "classification": "Product Bug",
            "confidence": 0.85,
            "severity": "HIGH",
            "root_cause": "Bug found",
            "reasoning": "Test analysis",
            "evidence_summary": "Evidence here",
            "recommendation": "Fix it",
        }
        rca = RCA.from_dict(data)
        assert rca.category == FailureCategory.PRODUCT_BUG
        assert rca.confidence == 0.85
        assert rca.root_cause == "Bug found"
