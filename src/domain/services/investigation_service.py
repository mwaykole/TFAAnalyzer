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
        # Check knowledge base for quick rules and context
        kb = get_knowledge_base()
        kb_match = kb.match(failure.logs, failure.test_name, component)
        
        # Quick rule match - immediate classification without LLM
        if kb_match.has_quick_rule:
            rule = kb_match.matched_rule
            return self._create_quick_rule_rca(failure, evidence, rule)
        
        # Check for intermittent failure first
        if evidence.is_intermittent:
            return self._create_intermittent_rca(failure, evidence)
        
        # Try pattern-based classification first
        pattern_classification = self._classifier.classify(failure.logs, evidence)
        
        # High confidence pattern match - skip LLM
        if pattern_classification.is_high_confidence:
            return RCA(
                classification=pattern_classification,
                root_cause=evidence.error_message[:200] or "Pattern-matched failure",
                evidence_summary=evidence.summary(),
            )
        
        # Known flaky test
        if evidence.is_likely_flaky:
            return self._create_flaky_rca(failure, evidence)
        
        # Full LLM analysis with Thinker-Critic pattern + knowledge base context
        return await self._llm_investigation(failure, evidence, pattern_classification, kb_match)
    
    async def _llm_investigation(
        self,
        failure: Failure,
        evidence: Evidence,
        pattern_hint: Classification,
        kb_match: KnowledgeBaseMatch | None = None,
    ) -> RCA:
        """Run full LLM investigation with Thinker-Critic-Refiner."""
        # Prepare evidence prompt with knowledge base context
        evidence_prompt = self._build_evidence_prompt(failure, evidence, kb_match)
        
        # Run Thinker and Context gathering in parallel
        thinker_task = self._llm.think(evidence_prompt)
        context_task = self._prepare_context(evidence)
        
        initial_rca, context = await asyncio.gather(thinker_task, context_task)
        
        # Critic step
        critique = await self._llm.critique(initial_rca, context)
        
        # Refiner step
        evidence_summary = evidence.summary()
        refined_response = await self._llm.refine(initial_rca, critique, evidence_summary)
        
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
    ) -> str:
        """Build prompt with evidence for Thinker.
        
        Enhanced with:
        - Few-shot examples from similar past failures
        - Pre-error context
        - Enhanced analysis fields
        """
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
        
        return loader.render_safe(
            "investigation/evidence.md",
            few_shot_section=few_shot_section,
            test_name=failure.test_name,
            error_type=evidence.error_type or "UnknownError",
            error_message=evidence.error_message[:300] if evidence.error_message else "",
            patterns=', '.join(evidence.patterns) or 'None detected',
            stack_trace=evidence.stack_trace[:500] if evidence.stack_trace else 'N/A',
            decorators=', '.join(evidence.decorators[:5]) or 'None',
            pre_error_context=pre_error_context,
            timeout_analysis=timeout_analysis,
            systemic_issue=systemic_issue,
            kb_context=kb_context,
        )
    
    async def _prepare_context(self, evidence: Evidence) -> str:
        """Prepare context for Critic (runs in parallel with Thinker).
        
        Enhanced with additional analysis context.
        """
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
        
        # Enhanced: Add systemic issue context
        if hasattr(evidence, 'systemic_issue') and evidence.systemic_issue:
            context_parts.append(f"Systemic issue: {evidence.systemic_issue[:50]}")
        
        # Enhanced: Add timeout context
        if hasattr(evidence, 'timeout_analysis') and evidence.timeout_analysis:
            context_parts.append(f"Timeout: {evidence.timeout_analysis[:50]}")
        
        return " | ".join(context_parts) if context_parts else "No additional context"
    
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
        
        # Extract classification
        classification_str = extract(r"CLASSIFICATION:\s*([^\n]+)", "")
        if not classification_str:
            classification_str = extract(r"\*\*Classification:?\*\*\s*([^\n]+)", "")
        
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
