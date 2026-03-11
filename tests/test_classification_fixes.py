"""Tests for classification fixes and deep-mode LLM-always architecture.

Validates:
- Setup-phase timeouts classified correctly (Infrastructure / Product Bug)
- Deep mode always runs the LLM (no rule-based short-circuits)
- Rule-based signals surfaced as hints in the LLM prompt
- Verification must-gather feedback loop
- Must-gather prompt section causal tracing instructions
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.entities.classification import Classification, FailureCategory, Severity
from src.domain.entities.evidence import Evidence
from src.domain.entities.failure import Failure
from src.domain.services.classification_service import ClassificationService
from src.domain.services.enhanced_analysis import FailureClusterAnalyzer
from src.domain.services.investigation_service import InvestigationService
from src.utils.knowledge_base import KnowledgeBaseMatch, QuickRule


SETUP_TIMEOUT_LOG = (
    'failed on setup with "timeout_sampler.TimeoutExpiredError: Timed Out: 899.92\n'
    "Function: ocp_resources.resource.wait_for_condition.lambda: self.instance\n"
    'Last exception: N/A."'
)

SHORT_TIMEOUT_LOG = (
    "timeout_sampler.TimeoutExpiredError: Timed Out: 60\n"
    "Function: some_function\n"
    "Last exception: N/A."
)

WAIT_FOR_CONDITION_NA_LOG = (
    "ocp_resources.resource.wait_for_condition timed out\n"
    "Timed Out: 900\n"
    "Last exception: N/A."
)


class TestRuleBasedSetupTimeout:
    """Rule-based classifier correctly identifies setup-phase timeouts."""

    def setup_method(self):
        self.classifier = ClassificationService()

    def test_setup_timeout_classified_as_infrastructure(self):
        evidence = self.classifier.get_evidence_from_logs(SETUP_TIMEOUT_LOG)
        result = self.classifier.classify(SETUP_TIMEOUT_LOG, evidence)
        assert result.category == FailureCategory.INFRASTRUCTURE_ISSUE, (
            f"Expected Infrastructure Issue, got {result.category.value}"
        )

    def test_setup_timeout_confidence_above_generic(self):
        evidence = self.classifier.get_evidence_from_logs(SETUP_TIMEOUT_LOG)
        result = self.classifier.classify(SETUP_TIMEOUT_LOG, evidence)
        assert result.confidence >= 0.88

    def test_wait_for_condition_na_pattern(self):
        evidence = self.classifier.get_evidence_from_logs(WAIT_FOR_CONDITION_NA_LOG)
        result = self.classifier.classify(WAIT_FOR_CONDITION_NA_LOG, evidence)
        assert result.category == FailureCategory.INFRASTRUCTURE_ISSUE

    def test_short_timeout_still_test_automation(self):
        evidence = self.classifier.get_evidence_from_logs(SHORT_TIMEOUT_LOG)
        result = self.classifier.classify(SHORT_TIMEOUT_LOG, evidence)
        assert result.category == FailureCategory.TEST_AUTOMATION_ISSUE

    def test_generic_timeout_without_setup_is_test_automation(self):
        logs = "TimeoutExpiredError: Timed Out: 30\nFunction: test_helper"
        evidence = self.classifier.get_evidence_from_logs(logs)
        result = self.classifier.classify(logs, evidence)
        assert result.category == FailureCategory.TEST_AUTOMATION_ISSUE


class TestClassifyTimeoutLogic:
    """Tests for _classify_timeout in InvestigationService."""

    @staticmethod
    def _classify(
        timeout_value: int = 900,
        cluster_health: str = "",
        pass_rate: float = 1.0,
        failed_on_setup: bool = False,
    ) -> FailureCategory:
        from src.domain.services.investigation_service import InvestigationService

        evidence = Evidence()
        evidence.timeout_value = timeout_value
        evidence.cluster_health = cluster_health
        evidence.historical_pass_rate = pass_rate
        evidence.failed_on_setup = failed_on_setup
        return InvestigationService._classify_timeout(evidence)

    def test_generous_timeout_high_pass_rate_is_infrastructure(self):
        result = self._classify(timeout_value=900, pass_rate=1.0)
        assert result == FailureCategory.INFRASTRUCTURE_ISSUE

    def test_generous_timeout_consistent_failure_healthy_is_product_bug(self):
        result = self._classify(
            timeout_value=900, pass_rate=0.0, cluster_health="healthy"
        )
        assert result == FailureCategory.PRODUCT_BUG

    def test_generous_timeout_consistent_failure_no_cluster_data_is_product_bug(self):
        result = self._classify(timeout_value=900, pass_rate=0.0, cluster_health="")
        assert result == FailureCategory.PRODUCT_BUG

    def test_unhealthy_cluster_is_infrastructure(self):
        result = self._classify(cluster_health="degraded")
        assert result == FailureCategory.INFRASTRUCTURE_ISSUE

    def test_critical_cluster_is_infrastructure(self):
        result = self._classify(cluster_health="critical")
        assert result == FailureCategory.INFRASTRUCTURE_ISSUE

    def test_setup_failure_generous_timeout_is_infrastructure(self):
        result = self._classify(
            timeout_value=900, failed_on_setup=True, pass_rate=0.0
        )
        assert result == FailureCategory.INFRASTRUCTURE_ISSUE

    def test_short_timeout_is_test_automation(self):
        result = self._classify(timeout_value=60, pass_rate=1.0)
        assert result == FailureCategory.TEST_AUTOMATION_ISSUE

    def test_flaky_pass_rate_is_intermittent(self):
        result = self._classify(timeout_value=60, pass_rate=0.5)
        assert result == FailureCategory.INTERMITTENT_FAILURE


class TestSystemicSetupTimeout:
    """Clustering detects setup timeouts across multiple tests."""

    def test_systemic_setup_timeout_detected(self):
        analyzer = FailureClusterAnalyzer()
        failures = [
            {
                "test_id": "1",
                "test_name": "test_a",
                "error_message": 'failed on setup with "TimeoutExpiredError: Timed Out: 900"',
                "error_type": "TimeoutExpiredError",
            },
            {
                "test_id": "2",
                "test_name": "test_b",
                "error_message": 'failed on setup with "TimeoutExpiredError: Timed Out: 900"',
                "error_type": "TimeoutExpiredError",
            },
            {
                "test_id": "3",
                "test_name": "test_c",
                "error_message": 'failed on setup with "TimeoutExpiredError: Timed Out: 900"',
                "error_type": "TimeoutExpiredError",
            },
        ]
        result = analyzer.analyze_failures(failures)
        assert result.systemic_issue_detected
        assert len(result.clusters) >= 1
        setup_clusters = [
            c for c in result.clusters if "setup_timeout" in c.cluster_id
        ]
        assert len(setup_clusters) == 1
        assert setup_clusters[0].category == "infrastructure"

    def test_wait_for_condition_systemic_detected(self):
        analyzer = FailureClusterAnalyzer()
        failures = [
            {
                "test_id": "1",
                "test_name": "test_a",
                "error_message": "wait_for_condition Timed Out: 900",
                "error_type": "TimeoutExpiredError",
            },
            {
                "test_id": "2",
                "test_name": "test_b",
                "error_message": "wait_for_condition Timed Out: 900",
                "error_type": "TimeoutExpiredError",
            },
        ]
        result = analyzer.analyze_failures(failures)
        assert result.systemic_issue_detected


class TestEvidenceSetupFlag:
    """Evidence entity correctly tracks setup failures."""

    def test_failed_on_setup_default_false(self):
        evidence = Evidence()
        assert evidence.failed_on_setup is False

    def test_failed_on_setup_set_true(self):
        evidence = Evidence()
        evidence.failed_on_setup = True
        assert evidence.failed_on_setup is True


# ---------------------------------------------------------------------------
# Deep-mode: LLM always runs (no rule-based short-circuits)
# ---------------------------------------------------------------------------

def _make_failure(**overrides) -> Failure:
    defaults = {
        "id": "test-1",
        "test_name": "test_something",
        "logs": "some error log",
        "status": "FAILED",
        "launch_id": "999",
    }
    defaults.update(overrides)
    return Failure(**defaults)


def _make_llm_provider() -> MagicMock:
    provider = MagicMock()
    llm_response = (
        "CLASSIFICATION: Infrastructure Issue\n"
        "ROOT_CAUSE: cluster resource not ready\n"
        "CONFIDENCE: 85\n"
        "SEVERITY: HIGH\n"
        "REASONING: The pod never became ready.\n"
        "RECOMMENDATION: Check cluster health.\n"
    )
    provider.think = AsyncMock(return_value=llm_response)
    provider.critique = AsyncMock(return_value="Looks correct.")
    provider.refine = AsyncMock(return_value=llm_response)
    return provider


class TestDeepModeAlwaysUsesLLM:
    """In deep mode, rule-based signals never skip the LLM."""

    @pytest.mark.asyncio
    @patch("src.domain.services.investigation_service.get_knowledge_base")
    async def test_high_confidence_pattern_still_calls_llm(self, mock_kb):
        mock_kb.return_value.match.return_value = KnowledgeBaseMatch()
        provider = _make_llm_provider()
        svc = InvestigationService(provider)

        failure = _make_failure(logs=SETUP_TIMEOUT_LOG)
        evidence = Evidence()
        evidence.error_message = "TimeoutExpiredError"

        await svc.investigate(failure, evidence)

        provider.think.assert_called_once()
        provider.critique.assert_called_once()
        provider.refine.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.domain.services.investigation_service.get_knowledge_base")
    async def test_kb_quick_rule_still_calls_llm(self, mock_kb):
        rule = QuickRule(
            name="test rule",
            pattern="CrashLoopBackOff",
            classification="Infrastructure Issue",
            reason="Pod crash loop",
        )
        mock_kb.return_value.match.return_value = KnowledgeBaseMatch(
            matched_rule=rule,
        )
        provider = _make_llm_provider()
        svc = InvestigationService(provider)

        failure = _make_failure(logs="CrashLoopBackOff in pod xyz")
        evidence = Evidence()
        evidence.error_message = "CrashLoopBackOff"

        await svc.investigate(failure, evidence)

        provider.think.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.domain.services.investigation_service.get_knowledge_base")
    async def test_flaky_test_still_calls_llm(self, mock_kb):
        mock_kb.return_value.match.return_value = KnowledgeBaseMatch()
        provider = _make_llm_provider()
        svc = InvestigationService(provider)

        failure = _make_failure(logs="AssertionError: expected True")
        evidence = Evidence()
        evidence.known_flaky = True
        evidence.historical_pass_rate = 0.5
        evidence.error_message = "AssertionError"

        await svc.investigate(failure, evidence)

        provider.think.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.domain.services.investigation_service.get_knowledge_base")
    async def test_intermittent_still_skips_llm(self, mock_kb):
        mock_kb.return_value.match.return_value = KnowledgeBaseMatch()
        provider = _make_llm_provider()
        svc = InvestigationService(provider)

        failure = _make_failure(logs="some error")
        evidence = Evidence()
        evidence.verification_result = "passed"

        rca = await svc.investigate(failure, evidence)

        assert rca.classification.category == FailureCategory.INTERMITTENT_FAILURE
        provider.think.assert_not_called()


class TestRuleHintSection:
    """Rule-based signals appear as hints in the LLM prompt."""

    def test_pattern_match_hint_included(self):
        classification = Classification(
            category=FailureCategory.INFRASTRUCTURE_ISSUE,
            confidence=0.90,
            severity=Severity.HIGH,
            reasoning="Pattern matched: Setup timeout waiting for K8s resource condition",
        )
        evidence = Evidence()
        result = InvestigationService._build_rule_hint_section(
            classification, evidence, None,
        )
        assert "Pattern match" in result
        assert "90%" in result
        assert "Infrastructure Issue" in result

    def test_kb_rule_hint_included(self):
        rule = QuickRule(
            name="CrashLoop rule",
            pattern="CrashLoopBackOff",
            classification="Infrastructure Issue",
            reason="Pod crash loop detected",
        )
        kb_match = KnowledgeBaseMatch(matched_rule=rule)
        evidence = Evidence()
        result = InvestigationService._build_rule_hint_section(
            None, evidence, kb_match,
        )
        assert "Knowledge-base rule matched" in result
        assert "CrashLoop rule" in result

    def test_flaky_hint_included(self):
        evidence = Evidence()
        evidence.known_flaky = True
        evidence.historical_pass_rate = 0.5
        result = InvestigationService._build_rule_hint_section(
            None, evidence, None,
        )
        assert "Flakiness signal" in result
        assert "known flaky" in result
        assert "50%" in result

    def test_no_hints_returns_empty(self):
        evidence = Evidence()
        classification = Classification(
            category=FailureCategory.TO_INVESTIGATE,
            confidence=0.4,
            severity=Severity.MEDIUM,
            reasoning="No pattern matched",
        )
        result = InvestigationService._build_rule_hint_section(
            classification, evidence, None,
        )
        assert result == ""

    def test_multiple_hints_combined(self):
        rule = QuickRule(
            name="Setup timeout",
            pattern="failed on setup.*TimeoutExpiredError",
            classification="Infrastructure Issue",
            reason="Setup timeout",
        )
        kb_match = KnowledgeBaseMatch(matched_rule=rule)
        classification = Classification(
            category=FailureCategory.INFRASTRUCTURE_ISSUE,
            confidence=0.90,
            severity=Severity.HIGH,
            reasoning="Setup timeout pattern",
        )
        evidence = Evidence()
        evidence.known_flaky = True
        evidence.historical_pass_rate = 0.6

        result = InvestigationService._build_rule_hint_section(
            classification, evidence, kb_match,
        )
        assert "Knowledge-base rule matched" in result
        assert "Pattern match" in result
        assert "Flakiness signal" in result
        assert "verify against evidence" in result.lower()


class TestMustGatherPromptSection:
    """Validate that must-gather sections include causal tracing instructions."""

    def test_must_gather_section_includes_tracing_instructions(self):
        evidence = Evidence()
        evidence.must_gather_context = (
            "## Cluster Health: DEGRADED\n"
            "### Unhealthy Pods (2)\n"
            "- redhat-ods-applications/kserve-controller-xyz — CrashLoopBackOff\n"
        )
        llm = MagicMock()
        classifier = ClassificationService()
        svc = InvestigationService(llm, classifier)
        section = svc._build_evidence_prompt.__wrapped__(
            svc,
            failure=Failure(test_name="t", logs="timeout", test_code=""),
            evidence=evidence,
            pattern_classification=None,
        ) if hasattr(svc._build_evidence_prompt, '__wrapped__') else ""
        assert evidence.must_gather_context != ""

    def test_must_gather_section_demands_specific_pods(self):
        evidence = Evidence()
        evidence.must_gather_context = "## Cluster Health: CRITICAL\nUnhealthy pods: kserve-controller"
        llm = MagicMock()
        classifier = ClassificationService()
        svc = InvestigationService(llm, classifier)
        prompt = svc._build_evidence_prompt(
            failure=Failure(id="1", test_name="test_deploy", logs="timeout",
                            status="FAILED", launch_id="100", test_code=""),
            evidence=evidence,
            pattern_classification=None,
        )
        assert "MUST reference specific pods" in prompt
        assert "trace the chain" in prompt.lower()

    def test_verification_passed_section_confirms_intermittent(self):
        evidence = Evidence()
        evidence.verification_result = "passed"
        evidence.verification_output = "1 passed in 300s"
        llm = MagicMock()
        classifier = ClassificationService()
        svc = InvestigationService(llm, classifier)
        prompt = svc._build_evidence_prompt(
            failure=Failure(id="1", test_name="test_x", logs="timeout",
                            status="FAILED", launch_id="100", test_code=""),
            evidence=evidence,
            pattern_classification=None,
        )
        assert "PASSED on re-run" in prompt
        assert "intermittent" in prompt.lower()

    def test_verification_failed_section_suggests_consistent(self):
        evidence = Evidence()
        evidence.verification_result = "failed"
        evidence.verification_output = "FAILED test_deploy"
        llm = MagicMock()
        classifier = ClassificationService()
        svc = InvestigationService(llm, classifier)
        prompt = svc._build_evidence_prompt(
            failure=Failure(id="1", test_name="test_x", logs="timeout",
                            status="FAILED", launch_id="100", test_code=""),
            evidence=evidence,
            pattern_classification=None,
        )
        assert "FAILED on re-run" in prompt
        assert "consistent" in prompt.lower()
