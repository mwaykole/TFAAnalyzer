"""Analyze Failure Use Case.

Single Responsibility: Orchestrates the failure analysis workflow.
Dependency Inversion: Depends on repository and service interfaces.
"""

from dataclasses import dataclass
from typing import Any

from src.domain.entities.failure import Failure
from src.domain.entities.rca import RCA
from src.domain.interfaces.repositories import (
    CacheRepository,
    FailureRepository,
    HistoryRepository,
)
from src.domain.interfaces.llm_provider import LLMProvider
from src.domain.services.classification_service import ClassificationService
from src.domain.services.investigation_service import InvestigationService
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AnalyzeRequest:
    """Request for failure analysis."""
    
    launch_id: str
    component: str
    test_id: str | None = None
    push_to_rp: bool = False
    use_cache: bool = True
    use_llm: bool = True


@dataclass
class AnalyzeResponse:
    """Response from failure analysis."""
    
    test_name: str
    test_id: str
    rca: RCA
    cached: bool = False
    from_rp: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "test_name": self.test_name,
            "test_id": self.test_id,
            "classification": self.rca.classification.category.value,
            "confidence": self.rca.confidence,
            "confidence_percent": self.rca.classification.confidence_percent,
            "severity": self.rca.severity.value,
            "root_cause": self.rca.root_cause,
            "reasoning": self.rca.reasoning,
            "recommendation": self.rca.recommendation,
            "cached": self.cached,
            "from_rp": self.from_rp,
        }


class AnalyzeFailureUseCase:
    """Use case for analyzing test failures.
    
    Orchestrates:
    1. Check cache for existing result
    2. Check ReportPortal for existing AI classification
    3. Fetch failure data
    4. Run classification (rules-based or LLM)
    5. Store result in cache and optionally push to RP
    
    Dependency Inversion: All dependencies are abstractions (interfaces).
    """
    
    def __init__(
        self,
        failure_repo: FailureRepository,
        cache_repo: CacheRepository | None = None,
        history_repo: HistoryRepository | None = None,
        llm_provider: LLMProvider | None = None,
    ):
        """Initialize with dependencies.
        
        Dependency Inversion: Accepts interfaces, not concrete implementations.
        """
        self._failure_repo = failure_repo
        self._cache_repo = cache_repo
        self._history_repo = history_repo
        self._llm_provider = llm_provider
        
        self._classifier = ClassificationService()
        self._investigator = (
            InvestigationService(llm_provider, self._classifier)
            if llm_provider else None
        )
    
    async def execute(self, request: AnalyzeRequest) -> list[AnalyzeResponse]:
        """Execute the analysis use case.
        
        Args:
            request: Analysis request parameters
            
        Returns:
            List of analysis responses
        """
        results: list[AnalyzeResponse] = []
        
        # Get failures to analyze
        logger.info("fetching_failures", 
                    launch_id=request.launch_id, 
                    component=request.component)
        
        if request.test_id:
            failure = await self._failure_repo.get_failure(
                request.test_id, request.launch_id
            )
            failures = [failure] if failure else []
        else:
            failures = await self._failure_repo.get_failures_by_component(
                request.launch_id, request.component
            )
        
        logger.info("failures_found", count=len(failures))
        
        for i, failure in enumerate(failures, 1):
            logger.info("analyzing_failure", 
                        progress=f"{i}/{len(failures)}",
                        test_name=failure.test_name[:50])
            result = await self._analyze_single(failure, request)
            logger.info("failure_analyzed",
                        test_name=failure.test_name[:30],
                        classification=result.rca.classification.category.value,
                        confidence=f"{result.rca.confidence:.0%}",
                        cached=result.cached,
                        from_rp=result.from_rp)
            results.append(result)
        
        return results
    
    async def _analyze_single(
        self, failure: Failure, request: AnalyzeRequest
    ) -> AnalyzeResponse:
        """Analyze a single failure."""
        cache_key = f"analysis:{failure.cache_key}"
        
        # 1. Check cache
        if request.use_cache and self._cache_repo:
            logger.debug("checking_cache", test_id=failure.id)
            cached = await self._cache_repo.get(cache_key)
            if cached:
                logger.info("cache_hit", test_name=failure.test_name[:30])
                rca = RCA.from_dict(cached)
                return AnalyzeResponse(
                    test_name=failure.test_name,
                    test_id=failure.id,
                    rca=rca,
                    cached=True,
                )
        
        # 2. Check if already analyzed in RP
        logger.debug("checking_rp_classification", test_id=failure.id)
        if await self._failure_repo.has_ai_classification(failure.id):
            from src.infrastructure.repositories.rp_repository import RPRepository
            if isinstance(self._failure_repo, RPRepository):
                existing_rca = await self._failure_repo.get_existing_classification(
                    failure.id
                )
                if existing_rca:
                    logger.info("using_existing_rp_classification", 
                                test_name=failure.test_name[:30])
                    return AnalyzeResponse(
                        test_name=failure.test_name,
                        test_id=failure.id,
                        rca=existing_rca,
                        from_rp=True,
                    )
        
        # 3. Gather evidence
        logger.debug("extracting_evidence", log_length=len(failure.logs))
        evidence = self._classifier.get_evidence_from_logs(
            failure.logs, failure.test_code
        )
        logger.debug("evidence_extracted",
                     error_type=evidence.error_type or "unknown",
                     patterns=len(evidence.patterns),
                     has_stack_trace=bool(evidence.stack_trace))
        
        # Add historical context
        if self._history_repo:
            logger.debug("fetching_history", test_name=failure.test_name[:30])
            history = await self._history_repo.get_test_history(failure.test_name)
            if history:
                evidence.historical_failures = history.get("failure_count", 0)
                evidence.historical_pass_rate = history.get("pass_rate", 1.0)
                if evidence.historical_pass_rate < 0.8:
                    evidence.known_flaky = True
                    logger.debug("marked_as_flaky", pass_rate=evidence.historical_pass_rate)
        
        # 4. Run analysis
        if request.use_llm and self._investigator:
            logger.info("running_llm_analysis", test_name=failure.test_name[:30])
            rca = await self._investigator.investigate(failure, evidence)
        else:
            logger.info("running_rule_based_classification", test_name=failure.test_name[:30])
            classification = self._classifier.classify(failure.logs, evidence)
            rca = RCA(
                classification=classification,
                root_cause=evidence.error_message[:200] or "See logs for details",
                evidence_summary=evidence.summary(),
            )
        
        # 5. Store result
        if self._cache_repo:
            logger.debug("caching_result", test_id=failure.id)
            await self._cache_repo.set(cache_key, rca.to_dict(), ttl_seconds=86400)
        
        # 6. Push to RP if requested
        if request.push_to_rp:
            logger.info("pushing_to_rp", test_id=failure.id)
            comment = rca.to_rp_comment()
            await self._failure_repo.save_classification(failure.id, rca, comment)
        
        return AnalyzeResponse(
            test_name=failure.test_name,
            test_id=failure.id,
            rca=rca,
        )
