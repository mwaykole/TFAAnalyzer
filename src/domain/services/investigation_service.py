"""Investigation service implementing Thinker-Critic-Refiner pattern.

Single Responsibility: Only handles deep investigation logic.
Dependency Inversion: Depends on LLMProvider interface.

Enhanced with:
- Few-shot learning using similar past failures
- Pre-error context inclusion
- Enhanced evidence prompts
"""

import asyncio
import re
from typing import Any, TYPE_CHECKING

from src.domain.entities.classification import Classification, FailureCategory, Severity
from src.domain.entities.evidence import Evidence
from src.domain.entities.failure import Failure
from src.domain.entities.rca import RCA
from src.domain.interfaces.llm_provider import LLMProvider
from src.domain.services.classification_service import ClassificationService
from src.prompts.loader import get_prompt_loader
from src.utils.knowledge_base import get_knowledge_base, KnowledgeBaseMatch
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.infrastructure.embeddings.failure_store import FailureEmbeddingStore

logger = get_logger(__name__)


class InvestigationService:
    """Service for deep RCA investigation using Thinker-Critic pattern.
    
    Single Responsibility: Only handles investigation logic.
    Dependency Inversion: Depends on LLMProvider abstraction.
    
    Enhanced with few-shot learning using similar past failures.
    """
    
    def __init__(
        self,
        llm_provider: LLMProvider,
        classification_service: ClassificationService | None = None,
        failure_store: "FailureEmbeddingStore | None" = None,
    ):
        """Initialize with LLM provider.
        
        Dependency Inversion: Accepts interface, not concrete implementation.
        
        Args:
            llm_provider: LLM provider for analysis
            classification_service: Optional classification service
            failure_store: Optional embedding store for few-shot learning
        """
        self._llm = llm_provider
        self._classifier = classification_service or ClassificationService()
        self._failure_store = failure_store
    
    async def investigate(
        self,
        failure: Failure,
        evidence: Evidence,
        component: str = "",
    ) -> RCA:
        """Investigate failure using Thinker-Critic-Refiner pattern.
        
        Args:
            failure: The failure to investigate
            evidence: Evidence collected from logs and history
            component: Component being tested (for knowledge base context)
            
        Returns:
            RCA with detailed analysis
        """
        kb = get_knowledge_base()
        kb_match = kb.match(failure.logs, failure.test_name, component)
        
        if evidence.is_intermittent:
            return self._create_intermittent_rca(failure, evidence)
        
        pattern_classification = self._classifier.classify(failure.logs, evidence)
        
        return await self._llm_investigation(failure, evidence, pattern_classification, kb_match)
    
    async def _llm_investigation(
        self,
        failure: Failure,
        evidence: Evidence,
        pattern_hint: Classification,
        kb_match: KnowledgeBaseMatch | None = None,
    ) -> RCA:
        """Run full LLM investigation with Thinker-Critic-Refiner."""
        evidence_prompt = self._build_evidence_prompt(
            failure, evidence, kb_match, pattern_hint,
        )
        
        # Run Thinker and Context gathering in parallel
        thinker_task = self._llm.think(evidence_prompt)
        context_task = self._prepare_context(evidence)
        
        initial_rca, context = await asyncio.gather(thinker_task, context_task)
        
        # Critic step
        critique = await self._llm.critique(initial_rca, context)
        
        # Extract Thinker's confidence for the Refiner
        thinker_conf_match = re.search(r"(?:CONFIDENCE|confidence)[:\s]*(\d+)", initial_rca)
        thinker_confidence = f"{thinker_conf_match.group(1)}%" if thinker_conf_match else "60%"
        actual_patterns = ', '.join(evidence.patterns) if evidence.patterns else ""
        
        # Refiner step
        evidence_summary = evidence.summary()
        refined_response = await self._llm.refine(
            initial_rca, critique, evidence_summary,
            patterns=actual_patterns,
            suggested_confidence=thinker_confidence,
        )
        
        # Parse refined response
        return self._parse_rca_response(
            refined_response, 
            failure, 
            evidence,
            pattern_hint.confidence,
        )
    
    def _build_evidence_prompt(
        self,
        failure: Failure,
        evidence: Evidence,
        kb_match: KnowledgeBaseMatch | None = None,
        pattern_classification: Classification | None = None,
    ) -> str:
        """Build prompt with evidence for Thinker."""
        loader = get_prompt_loader()
        
        # Build optional sections
        few_shot_section = ""
        if self._failure_store:
            try:
                few_shot_section = self._failure_store.build_few_shot_prompt(
                    test_name=failure.test_name,
                    error_type=evidence.error_type or "UnknownError",
                    error_message=evidence.error_message or failure.logs[:300],
                    stack_trace=evidence.stack_trace or "",
                    k=2,
                )
                if few_shot_section:
                    few_shot_section += "\n"
                    logger.debug("few_shot_examples_added", test_name=failure.test_name[:30])
            except Exception as e:
                logger.warning("few_shot_failed", error=str(e))
        
        setup_failure_section = ""
        if getattr(evidence, "failed_on_setup", False):
            setup_failure_section = (
                "\n\n### IMPORTANT: Setup Phase Failure\n"
                "This test failed during SETUP — the test body never executed. "
                "The failure is in environment/platform preparation, NOT in the test code itself. "
                "Setup timeouts with generous waits (>=300s) are almost never Test Automation Issues.\n"
            )

        pre_error_context = ""
        if hasattr(evidence, 'pre_error_context') and evidence.pre_error_context:
            pre_error_context = f"\nCONTEXT (logs before error):\n{evidence.pre_error_context[:400]}\n"
        
        timeout_analysis = ""
        if hasattr(evidence, 'timeout_analysis') and evidence.timeout_analysis:
            timeout_analysis = f"\nTIMEOUT ANALYSIS: {evidence.timeout_analysis}\n"
        
        systemic_issue = ""
        if hasattr(evidence, 'systemic_issue') and evidence.systemic_issue:
            cluster_rec = getattr(evidence, 'cluster_recommendation', 'Investigate infrastructure')
            systemic_issue = f"""
⚠️ SYSTEMIC ISSUE DETECTED: {evidence.systemic_issue}
This failure is likely part of a broader infrastructure issue affecting multiple tests.
Recommendation: {cluster_rec}
"""
        
        kb_context = ""
        if kb_match:
            kb_ctx = kb_match.get_context_for_llm()
            if kb_ctx:
                kb_context = f"\n{kb_ctx}\n\nIMPORTANT: Consider the domain knowledge above when classifying this failure.\n"
        
        must_gather_section = ""
        if evidence.must_gather_context:
            must_gather_section = (
                f"\n### CLUSTER STATE (from must-gather diagnostics)\n"
                f"{evidence.must_gather_context[:4000]}\n"
                f"\n**CRITICAL — Root Cause Tracing Instructions:**\n"
                f"The must-gather data above contains the ACTUAL cluster state "
                f"at the time of failure. You MUST use it to explain WHY the "
                f"failure occurred, not just state that the cluster was degraded.\n"
                f"- If unhealthy pods are listed, explain which pod failure "
                f"caused the test to fail (e.g., model server pod in CrashLoopBackOff)\n"
                f"- If resource_failures show CR conditions, trace the chain: "
                f"InferenceService → Predictor → Pod → container error\n"
                f"- If degraded operators are listed, explain which operator "
                f"being unavailable blocked the test\n"
                f"- If warning events show scheduling/pull/OOM issues, cite them "
                f"as the specific infrastructure cause\n"
                f"- Your Root Cause MUST reference specific pods, CRs, or "
                f"conditions from the must-gather — not generic statements "
                f"like 'degraded cluster'\n"
            )
        
        verification_section = ""
        if evidence.verification_result and evidence.verification_result != "not_run":
            verification_section = (
                f"\n### Verification Result: {evidence.verification_result.upper()}\n"
            )
            if evidence.verification_output:
                output_tail = evidence.verification_output[-800:]
                verification_section += (
                    f"```\n{output_tail}\n```\n"
                )
            if evidence.verification_result == "passed":
                verification_section += (
                    f"\n**The test PASSED on re-run**, confirming the original "
                    f"failure was intermittent/environmental. The product code "
                    f"is working correctly on a healthy cluster.\n"
                )
            elif evidence.verification_result == "failed":
                verification_section += (
                    f"\n**The test FAILED on re-run** — this is a consistent "
                    f"failure. Check the verification output and must-gather "
                    f"(if available) to determine whether the failure is caused "
                    f"by a product defect or ongoing infrastructure issues.\n"
                )
            else:
                verification_section += (
                    f"\nThe test was re-run during verification. "
                    f"Use this result to confirm or adjust your classification.\n"
                )
        
        test_code_section = ""
        if evidence.test_code:
            file_ref = f" ({evidence.test_file})" if evidence.test_file else ""
            github_ref = f"\nSource: {evidence.github_url}" if evidence.github_url else ""
            code_snippet = evidence.test_code[:3000]
            fixtures_info = ""
            if evidence.fixtures:
                fixtures_info = f"\nFixtures: {', '.join(evidence.fixtures[:10])}"
            test_code_section = (
                f"\n### Test Source Code{file_ref}{github_ref}{fixtures_info}\n"
                f"```python\n{code_snippet}\n```\n"
                f"\nIMPORTANT: Analyze the test code above to understand what the test "
                f"does, what it expects, and whether the failure is in the test logic "
                f"or the product under test.\n"
            )

        code_analysis_section = ""
        code_meta_parts = []
        if evidence.timeout_value:
            code_meta_parts.append(f"- Test timeout: {evidence.timeout_value}s")
        if evidence.wait_patterns:
            code_meta_parts.append(f"- Wait patterns: {', '.join(evidence.wait_patterns[:5])}")
        if evidence.github_url:
            code_meta_parts.append(f"- Source: {evidence.github_url}")
        if evidence.parametrize_args:
            code_meta_parts.append(f"- Parametrize: {', '.join(evidence.parametrize_args[:5])}")
        if evidence.has_retry:
            code_meta_parts.append("- Has retry/flaky decorator")
        if evidence.uses_sleep:
            code_meta_parts.append("- Uses sleep() calls")
        if code_meta_parts:
            code_analysis_section = "\n### Code Analysis\n" + "\n".join(code_meta_parts) + "\n"

        defect_section = ""
        if hasattr(failure, 'defect_type') and failure.defect_type:
            defect_section += f"\n### Previous Classification\n- Defect type: {failure.defect_type}\n"
        if hasattr(failure, 'linked_issues') and failure.linked_issues:
            defect_section += f"- Linked issues: {', '.join(failure.linked_issues[:5])}\n"
        
        rule_hint_section = self._build_rule_hint_section(
            pattern_classification, evidence, kb_match,
        )
        
        return loader.render_safe(
            "investigation/evidence.md",
            few_shot_section=few_shot_section,
            test_name=failure.test_name,
            error_type=evidence.error_type or "UnknownError",
            error_message=evidence.error_message[:300] if evidence.error_message else "",
            patterns=', '.join(evidence.patterns) or 'None detected',
            stack_trace=evidence.stack_trace[:500] if evidence.stack_trace else 'N/A',
            decorators=', '.join(evidence.decorators[:5]) or 'None',
            setup_failure_section=setup_failure_section,
            test_code_section=test_code_section,
            pre_error_context=pre_error_context,
            timeout_analysis=timeout_analysis,
            systemic_issue=systemic_issue,
            kb_context=kb_context,
            must_gather_section=must_gather_section,
            verification_section=verification_section,
            code_analysis_section=code_analysis_section,
            defect_section=defect_section,
            rule_hint_section=rule_hint_section,
        )
    
    @staticmethod
    def _build_rule_hint_section(
        pattern_classification: Classification | None,
        evidence: Evidence,
        kb_match: KnowledgeBaseMatch | None,
    ) -> str:
        """Build a hint section from rule-based signals for the LLM.

        These are advisory — the LLM should verify against evidence
        and override if the evidence contradicts the hint.
        """
        parts: list[str] = []

        if kb_match and kb_match.has_quick_rule:
            rule = kb_match.matched_rule
            parts.append(
                f"- **Knowledge-base rule matched**: \"{rule.name}\" "
                f"→ {rule.classification} (reason: {rule.reason})"
            )

        if (
            pattern_classification
            and pattern_classification.category.value != "To Investigate"
        ):
            parts.append(
                f"- **Pattern match** ({pattern_classification.confidence_percent}% confidence): "
                f"{pattern_classification.reasoning} "
                f"→ suggested {pattern_classification.category.value}"
            )

        if evidence.is_likely_flaky:
            flaky_reasons = []
            if evidence.known_flaky:
                flaky_reasons.append("known flaky")
            if evidence.is_code_flaky:
                flaky_reasons.append("flaky decorator in code")
            if 0.2 <= evidence.historical_pass_rate <= 0.8:
                flaky_reasons.append(
                    f"pass rate {evidence.historical_pass_rate:.0%}"
                )
            parts.append(
                f"- **Flakiness signal**: {', '.join(flaky_reasons)}"
            )

        if not parts:
            return ""

        header = (
            "\n### Pre-analysis Hints (verify against evidence)\n"
            "The following signals were detected by rule-based matching. "
            "Use them as starting hypotheses, but override if evidence "
            "contradicts them.\n"
        )
        return header + "\n".join(parts) + "\n"

    async def _prepare_context(self, evidence: Evidence) -> str:
        """Prepare rich context for Critic (runs in parallel with Thinker)."""
        context_parts = []

        if evidence.historical_failures > 0:
            context_parts.append(
                f"Historical: {evidence.historical_failures} failures, "
                f"{evidence.historical_pass_rate:.0%} pass rate"
            )

        if evidence.known_flaky:
            context_parts.append("Test has flaky indicators in code")

        if evidence.verification_result != "not_run":
            context_parts.append(f"Verification: {evidence.verification_result}")

        if hasattr(evidence, 'systemic_issue') and evidence.systemic_issue:
            context_parts.append(f"Systemic issue: {evidence.systemic_issue[:80]}")

        if hasattr(evidence, 'timeout_analysis') and evidence.timeout_analysis:
            context_parts.append(f"Timeout: {evidence.timeout_analysis[:80]}")

        if evidence.timeout_value:
            context_parts.append(f"Test timeout value: {evidence.timeout_value}s")

        if evidence.cluster_health:
            context_parts.append(f"Cluster health: {evidence.cluster_health}")

        if getattr(evidence, "failed_on_setup", False):
            context_parts.append("SETUP FAILURE: Test failed in setup phase — test body never ran")

        if evidence.stack_trace:
            context_parts.append(f"\nStack trace (excerpt):\n{evidence.stack_trace[:400]}")

        if evidence.test_code:
            context_parts.append(f"\nTest code (excerpt):\n{evidence.test_code[:500]}")

        if evidence.must_gather_context:
            mg_summary = evidence.must_gather_context[:300]
            context_parts.append(f"\nMust-gather:\n{mg_summary}")

        return "\n".join(context_parts) if context_parts else "No additional context"
    
    def store_result(
        self,
        failure: Failure,
        evidence: Evidence,
        rca: RCA,
    ) -> None:
        """Store investigation result for future few-shot learning.
        
        Args:
            failure: The analyzed failure
            evidence: Evidence used for analysis
            rca: The RCA result
        """
        if not self._failure_store:
            return
        
        try:
            self._failure_store.store(
                test_id=failure.id,
                test_name=failure.test_name,
                error_type=evidence.error_type or "UnknownError",
                error_message=evidence.error_message or "",
                classification=rca.classification.category.value,
                root_cause=rca.root_cause,
                reasoning=rca.reasoning,
                confidence=rca.confidence,
                stack_trace=evidence.stack_trace or "",
            )
            logger.debug("result_stored_for_learning",
                         test_name=failure.test_name[:30],
                         classification=rca.classification.category.value)
        except Exception as e:
            logger.warning("failed_to_store_result", error=str(e))
    
    def _parse_rca_response(
        self,
        response: str,
        failure: Failure,
        evidence: Evidence,
        suggested_confidence: float,
    ) -> RCA:
        """Parse LLM response into RCA."""
        def extract(pattern: str, default: str) -> str:
            match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
            return match.group(1).strip() if match else default
        
        classification_str = self._extract_classification(response)
        category = FailureCategory.from_string(classification_str or "To Investigate")
        
        # Extract confidence
        conf_match = re.search(r"(?:CONFIDENCE|confidence)[:\s]*(\d+)", response)
        confidence = min(int(conf_match.group(1)) / 100, 0.98) if conf_match else suggested_confidence
        
        # Extract severity
        severity_str = extract(r"SEVERITY:\s*(\w+)", "MEDIUM").upper()
        try:
            severity = Severity(severity_str)
        except ValueError:
            severity = Severity.MEDIUM
        
        # Extract other fields
        root_cause = extract(r"ROOT_CAUSE:\s*([^\n]+)", evidence.error_message[:200])
        reasoning = extract(r"REASONING:\s*(.+?)(?=RECOMMENDATION|$)", "Based on error analysis.")
        recommendation = extract(r"RECOMMENDATION:\s*(.+?)$", "Investigate further.")
        
        # Post-LLM heuristic: reclassify if still TO_INVESTIGATE
        if category == FailureCategory.TO_INVESTIGATE:
            category, confidence = self._evidence_based_reclassify(
                evidence, root_cause, confidence,
            )

        # Correct misclassified timeouts using evidence context
        timeout_categories = (
            FailureCategory.TEST_AUTOMATION_ISSUE,
            FailureCategory.INFRASTRUCTURE_ISSUE,
            FailureCategory.PRODUCT_BUG,
        )
        if category in timeout_categories:
            rc_lower = root_cause.lower()
            is_timeout = any(
                kw in rc_lower
                for kw in ("timeout", "timed out", "timeoutexpired", "timeoutsampler")
            )
            if is_timeout:
                corrected = self._classify_timeout(evidence)
                if corrected != category:
                    logger.info(
                        "timeout_reclassified",
                        original=category.value,
                        corrected=corrected.value,
                        timeout_value=evidence.timeout_value,
                        cluster_health=evidence.cluster_health,
                        pass_rate=evidence.historical_pass_rate,
                    )
                    category = corrected
        
        classification = Classification(
            category=category,
            confidence=confidence,
            severity=severity,
            reasoning=reasoning[:500],
            recommendation=recommendation[:500],
        )
        
        return RCA(
            classification=classification,
            root_cause=root_cause[:400],
            evidence_summary=evidence.summary(),
        )
    
    def _extract_classification(self, response: str) -> str:
        """Extract classification from LLM response, trying multiple formats."""
        patterns = [
            r"CLASSIFICATION:\s*([^\n]+)",
            r"\*\*Classification:?\*\*[:\s]*([^\n]+)",
            r"Classification:\s*([^\n]+)",
            r"\*\*Category:?\*\*[:\s]*([^\n]+)",
            r"Category:\s*([^\n]+)",
            r"\|\s*Classification\s*\|\s*([^\|]+)\|",
        ]
        for pat in patterns:
            match = re.search(pat, response, re.IGNORECASE)
            if match:
                raw = match.group(1).strip().strip("*").strip()
                if raw and raw.lower() != "to investigate":
                    return raw
        
        # Last resort: scan for category keywords anywhere in last 500 chars
        tail = response[-500:].lower()
        category_signals = [
            ("product bug", "Product Bug"),
            ("test automation issue", "Test Automation Issue"),
            ("infrastructure issue", "Infrastructure Issue"),
            ("intermittent failure", "Intermittent Failure"),
        ]
        for keyword, label in category_signals:
            if keyword in tail:
                return label
        
        return ""
    
    def _evidence_based_reclassify(
        self,
        evidence: Evidence,
        root_cause: str,
        confidence: float,
    ) -> tuple[FailureCategory, float]:
        """Reclassify TO_INVESTIGATE using strong evidence signals."""
        rc_lower = root_cause.lower()
        err_lower = (evidence.error_message or "").lower()
        combined = f"{rc_lower} {err_lower}"

        # KServe/RHOAI CR-level product bug signals (highest priority)
        kserve_bug_keywords = [
            "no matches for kind", "crd not installed",
            "failed to reconcile", "failed to build",
            "leaderworkerset", "llminferenceservice",
            "revisionfailed", "revision failed",
            "servingruntime not found", "runtime not supported",
            "inferenceservice failed", "isvc not ready",
            "inferenceservice not ready",
            "model server not ready", "predictor not ready",
            "kserve controller error", "webhook error",
        ]
        if any(kw in combined for kw in kserve_bug_keywords):
            return FailureCategory.PRODUCT_BUG, max(confidence, 0.85)

        # KServe/RHOAI infra signals
        kserve_infra_keywords = [
            "storage-initializer", "ingressnotconfigured",
            "ingress not ready", "gateway not found",
            "datasciencecluster degraded", "dsc not ready",
            "dscinitialization failed",
            "queue-proxy error",
            "huggingface 401", "hf_access_token",
            "cannot access gated",
        ]
        if any(kw in combined for kw in kserve_infra_keywords):
            return FailureCategory.INFRASTRUCTURE_ISSUE, max(confidence, 0.80)

        # Must-gather resource failures containing KServe signals
        mg_ctx = (evidence.must_gather_context or "").lower()
        if mg_ctx and any(kw in mg_ctx for kw in kserve_bug_keywords):
            return FailureCategory.PRODUCT_BUG, max(confidence, 0.85)

        # General infra signals
        infra_keywords = [
            "crashloopbackoff", "imagepullbackoff", "oomkilled",
            "connection refused", "connection reset", "503",
            "upstream connect error", "service unavailable",
            "authentication fail", "certificate", "dns resolution",
            "gpu", "cuda", "node not ready",
        ]
        if any(kw in rc_lower for kw in infra_keywords):
            return FailureCategory.INFRASTRUCTURE_ISSUE, max(confidence, 0.75)

        if evidence.cluster_health and evidence.cluster_health in ("degraded", "critical"):
            return FailureCategory.INFRASTRUCTURE_ISSUE, max(confidence, 0.70)

        # Timeout classification -- context-dependent
        timeout_keywords = [
            "timeoutexpirederror", "timeoutsampler", "timeout_sampler",
            "wait_for_", "wait_until", "timed out", "timeout expired",
            "fixture timed out", "fixture timeout",
        ]
        has_timeout = any(kw in rc_lower for kw in timeout_keywords) or evidence.timeout_analysis
        if has_timeout:
            category = self._classify_timeout(evidence)
            return category, max(confidence, 0.75)

        # Product bug signals
        bug_keywords = [
            "api returned", "wrong value", "unexpected response",
            "regression", "500 internal server error", "null pointer",
            "attributeerror", "typeerror", "keyerror",
            "service fails", "not responding", "inference failed",
            "model not loaded", "model loading error",
            "vllm error", "vllm crash",
        ]
        if any(kw in rc_lower for kw in bug_keywords):
            return FailureCategory.PRODUCT_BUG, max(confidence, 0.70)

        # Flaky signals
        if evidence.known_flaky or evidence.is_code_flaky:
            return FailureCategory.INTERMITTENT_FAILURE, max(confidence, 0.65)

        if 0.2 <= evidence.historical_pass_rate <= 0.8:
            return FailureCategory.INTERMITTENT_FAILURE, max(confidence, 0.60)

        # Error patterns from fast-path classifier
        error_lower = (evidence.error_type or "").lower()
        if "timeout" in error_lower or "timeout" in err_lower:
            return self._classify_timeout(evidence), max(confidence, 0.65)

        return FailureCategory.TO_INVESTIGATE, confidence

    @staticmethod
    def _classify_timeout(evidence: Evidence) -> FailureCategory:
        """Classify a timeout based on context.

        Decision priority:
        1. Unhealthy cluster → Infrastructure Issue
        2. Generous timeout + confirmed healthy + consistent failure → Product Bug
        3. Setup-phase + generous timeout → Infrastructure Issue
        4. Generous timeout + high pass rate → Infrastructure Issue (env regressed)
        5. Generous timeout + consistent failure → Product Bug
        6. Flaky pass rate → Intermittent Failure
        7. Truly short timeout → Test Automation Issue (default)
        """
        generous_timeout = (evidence.timeout_value or 0) >= 300
        cluster_unhealthy = evidence.cluster_health in ("degraded", "critical")
        cluster_healthy_confirmed = evidence.cluster_health == "healthy"
        consistent_failure = evidence.historical_pass_rate <= 0.1
        high_pass_rate = evidence.historical_pass_rate >= 0.8
        setup_failure = getattr(evidence, "failed_on_setup", False)

        if cluster_unhealthy:
            return FailureCategory.INFRASTRUCTURE_ISSUE
        if generous_timeout and cluster_healthy_confirmed and consistent_failure:
            return FailureCategory.PRODUCT_BUG
        if setup_failure and generous_timeout:
            return FailureCategory.INFRASTRUCTURE_ISSUE
        if generous_timeout and high_pass_rate:
            return FailureCategory.INFRASTRUCTURE_ISSUE
        if generous_timeout and consistent_failure:
            return FailureCategory.PRODUCT_BUG
        if 0.2 <= evidence.historical_pass_rate <= 0.8:
            return FailureCategory.INTERMITTENT_FAILURE
        return FailureCategory.TEST_AUTOMATION_ISSUE
    
    def _create_quick_rule_rca(
        self,
        failure: Failure,
        evidence: Evidence,
        rule: Any,
    ) -> RCA:
        """Create RCA from knowledge base quick rule match."""
        from src.utils.knowledge_base import QuickRule
        
        if not isinstance(rule, QuickRule):
            return self._create_intermittent_rca(failure, evidence)
        
        category = FailureCategory.from_string(rule.classification)
        
        severity_map = {
            "critical": Severity.CRITICAL,
            "high": Severity.HIGH,
            "medium": Severity.MEDIUM,
            "low": Severity.LOW,
        }
        severity = severity_map.get(rule.severity.lower(), Severity.MEDIUM)
        
        classification = Classification(
            category=category,
            confidence=0.92,
            severity=severity,
            reasoning=f"Knowledge base quick rule: {rule.name}. {rule.reason}",
            recommendation="See knowledge_base.yaml for domain-specific guidance.",
        )
        
        return RCA(
            classification=classification,
            root_cause=rule.reason,
            evidence_summary=f"Matched rule: {rule.name}. Pattern: {rule.pattern}",
        )
    
    def _create_intermittent_rca(self, failure: Failure, evidence: Evidence) -> RCA:
        """Create RCA for intermittent failure (passed on re-run)."""
        classification = Classification(
            category=FailureCategory.INTERMITTENT_FAILURE,
            confidence=0.95,
            severity=Severity.LOW,
            reasoning=f"Original error: {evidence.error_type}. Passed on verification run.",
            recommendation=(
                "1. Add @pytest.mark.flaky decorator\n"
                "2. Replace sleeps with explicit waits\n"
                "3. Review resource cleanup"
            ),
        )
        
        return RCA(
            classification=classification,
            root_cause="Test passed on re-run, confirming intermittent behavior.",
            evidence_summary=f"Verification: PASSED. Historical flaky: {evidence.known_flaky}",
        )
    
    def _create_flaky_rca(self, failure: Failure, evidence: Evidence) -> RCA:
        """Create RCA for known flaky test."""
        classification = Classification(
            category=FailureCategory.INTERMITTENT_FAILURE,
            confidence=0.85,
            severity=Severity.MEDIUM,
            reasoning=(
                f"Historical data shows {evidence.historical_failures} failures. "
                f"Known flaky indicators in code: {evidence.known_flaky}"
            ),
            recommendation=(
                "1. Investigate timing dependencies\n"
                "2. Add retry mechanism\n"
                "3. Review test isolation"
            ),
        )
        
        return RCA(
            classification=classification,
            root_cause=f"Test has {evidence.historical_pass_rate:.0%} pass rate over recent runs.",
            evidence_summary=f"Pass rate: {evidence.historical_pass_rate:.0%}. "
                           f"Decorators: {', '.join(evidence.decorators[:3])}",
        )
