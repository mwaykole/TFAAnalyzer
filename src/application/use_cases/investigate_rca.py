"""Investigate RCA Use Case.

Single Responsibility: Orchestrates deep RCA investigation workflow.
Dependency Inversion: Depends on repository and service interfaces.
"""

from dataclasses import dataclass, field
from typing import Any

from src.domain.entities.failure import Failure
from src.domain.entities.rca import RCA
from src.domain.interfaces.repositories import (
    CacheRepository,
    FailureRepository,
    HistoryRepository,
)
from src.domain.interfaces.llm_provider import LLMProvider
from src.domain.interfaces.code_fetcher import CodeFetcher, TestCodeInfo
from src.domain.services.classification_service import ClassificationService
from src.domain.services.investigation_service import InvestigationService
from src.domain.services.verification_service import (
    VerificationService, 
    VerifyMode, 
    VerificationResult,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class InvestigateRequest:
    """Request for RCA investigation."""
    
    launch_id: str
    component: str
    test_id: str | None = None
    push_to_rp: bool = False
    verify_mode: VerifyMode = VerifyMode.NONE
    # Legacy support
    verify_tests: bool = False


@dataclass  
class InvestigateResponse:
    """Response from RCA investigation."""
    
    test_name: str
    test_id: str
    rca: RCA
    verified: bool = False
    verification_result: str = "not_run"
    verification_details: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "test_name": self.test_name,
            "test_id": self.test_id,
            **self.rca.to_dict(),
            "verified": self.verified,
            "verification_result": self.verification_result,
            "verification_details": self.verification_details,
        }


class InvestigateRCAUseCase:
    """Use case for deep RCA investigation using Thinker-Critic pattern.
    
    Unlike AnalyzeFailureUseCase, this always uses LLM for deep analysis.
    
    Dependency Inversion: All dependencies are abstractions (interfaces).
    """
    
    def __init__(
        self,
        failure_repo: FailureRepository,
        llm_provider: LLMProvider,
        cache_repo: CacheRepository | None = None,
        history_repo: HistoryRepository | None = None,
        verification_service: VerificationService | None = None,
        code_fetcher: CodeFetcher | None = None,
    ):
        """Initialize with dependencies."""
        self._failure_repo = failure_repo
        self._llm_provider = llm_provider
        self._cache_repo = cache_repo
        self._history_repo = history_repo
        self._verification_service = verification_service
        self._code_fetcher = code_fetcher
        
        self._classifier = ClassificationService()
        self._investigator = InvestigationService(llm_provider, self._classifier)
    
    async def execute(self, request: InvestigateRequest) -> list[InvestigateResponse]:
        """Execute the investigation use case.
        
        Args:
            request: Investigation request parameters
            
        Returns:
            List of investigation responses
        """
        results: list[InvestigateResponse] = []
        
        # Get failures to investigate
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
        
        # Group by error signature for efficiency
        signature_groups = self._group_by_signature(failures)
        logger.info("grouped_by_signature", 
                    unique_signatures=len(signature_groups),
                    total_failures=len(failures))
        
        group_num = 0
        for signature, group in signature_groups.items():
            group_num += 1
            logger.info("investigating_group",
                        group=f"{group_num}/{len(signature_groups)}",
                        signature=signature[:12],
                        failures_in_group=len(group),
                        test_name=group[0].test_name[:40])
            
            # Investigate first failure in group
            first_result = await self._investigate_single(group[0], request)
            
            logger.info("investigation_result",
                        test_name=group[0].test_name[:30],
                        classification=first_result.rca.classification.category.value,
                        confidence=f"{first_result.rca.confidence:.0%}",
                        severity=first_result.rca.severity.value)
            
            results.append(first_result)
            
            # Reuse RCA for similar failures
            for failure in group[1:]:
                logger.debug("reusing_rca", 
                             test_name=failure.test_name[:30],
                             same_signature=signature[:12])
                results.append(InvestigateResponse(
                    test_name=failure.test_name,
                    test_id=failure.id,
                    rca=first_result.rca,
                    verified=first_result.verified,
                    verification_result=first_result.verification_result,
                ))
        
        logger.info("investigation_complete", total_results=len(results))
        return results
    
    async def _investigate_single(
        self, failure: Failure, request: InvestigateRequest
    ) -> InvestigateResponse:
        """Investigate a single failure with full Thinker-Critic pattern."""
        # Gather evidence
        logger.debug("extracting_evidence", 
                     test_name=failure.test_name[:30],
                     log_length=len(failure.logs))
        evidence = self._classifier.get_evidence_from_logs(
            failure.logs, failure.test_code
        )
        logger.debug("evidence_extracted",
                     error_type=evidence.error_type or "unknown",
                     patterns=len(evidence.patterns),
                     has_stack_trace=bool(evidence.stack_trace))
        
        # Fetch test source code for enhanced analysis
        test_code_info: TestCodeInfo | None = None
        if self._code_fetcher:
            logger.debug("fetching_test_code", test_name=failure.test_name[:30])
            try:
                test_code_info = await self._code_fetcher.fetch_test_code(failure.test_name)
                if test_code_info:
                    logger.info("test_code_fetched",
                                file=test_code_info.file_path,
                                has_github_url=bool(test_code_info.github_url),
                                is_flaky=test_code_info.is_potentially_flaky)
                    # Enhance evidence with code analysis
                    self._enhance_evidence_with_code(evidence, test_code_info)
            except Exception as e:
                logger.warning("code_fetch_failed", error=str(e))
        
        # Get historical context
        history: dict[str, Any] = {}
        if self._history_repo:
            logger.debug("fetching_history", test_name=failure.test_name[:30])
            history = await self._history_repo.get_test_history(failure.test_name) or {}
            if history:
                evidence.historical_failures = history.get("failed", 0)
                pass_rate_pct = history.get("pass_rate", 100.0)
                evidence.historical_pass_rate = pass_rate_pct / 100.0
                evidence.known_flaky = history.get("is_flaky", False)
        
        # Determine verification mode (support legacy verify_tests flag)
        verify_mode = request.verify_mode
        if verify_mode == VerifyMode.NONE and request.verify_tests:
            verify_mode = VerifyMode.RUN_TEST
        
        # Run verification if requested
        verification_result: VerificationResult | None = None
        verification_details: dict[str, Any] = {}
        
        if verify_mode != VerifyMode.NONE and self._verification_service:
            logger.info("running_verification",
                        test_name=failure.test_name[:30],
                        mode=verify_mode.value)
            
            verification_result = await self._verification_service.verify(
                test_name=failure.test_name,
                mode=verify_mode,
                logs=failure.logs,
                test_code=failure.test_code,
                history=history,
            )
            
            logger.info("verification_complete",
                        test_name=failure.test_name[:30],
                        mode=verify_mode.value,
                        status=verification_result.status,
                        confidence=f"{verification_result.confidence:.0%}")
            
            # Update evidence based on verification
            evidence.verification_result = verification_result.status
            evidence.verification_output = verification_result.output
            verification_details = verification_result.to_dict()
            
            # If verification shows intermittent, mark evidence accordingly
            if verification_result.is_intermittent:
                evidence.known_flaky = True
        
        # Run full investigation with Thinker-Critic
        logger.info("running_thinker_critic", test_name=failure.test_name[:30])
        logger.debug("llm_step", step="THINKER", status="starting")
        rca = await self._investigator.investigate(failure, evidence)
        logger.debug("llm_step", step="COMPLETE", 
                     classification=rca.classification.category.value)
        
        # Enhance RCA with code info
        if test_code_info:
            rca.github_url = test_code_info.github_url
            rca.test_file = test_code_info.file_path
            rca.fixtures = test_code_info.fixtures
            rca.code_analysis = evidence.code_analysis_summary()
        
        # Push to RP if requested
        if request.push_to_rp:
            logger.info("pushing_to_rp", test_id=failure.id)
            comment = self._build_rp_comment(rca, verification_result)
            await self._failure_repo.save_classification(failure.id, rca, comment)
        
        # Cache result
        if self._cache_repo:
            cache_key = f"investigation:{failure.cache_key}"
            logger.debug("caching_result", cache_key=cache_key[:30])
            await self._cache_repo.set(cache_key, rca.to_dict(), ttl_seconds=86400)
        
        return InvestigateResponse(
            test_name=failure.test_name,
            test_id=failure.id,
            rca=rca,
            verified=verify_mode != VerifyMode.NONE,
            verification_result=evidence.verification_result,
            verification_details=verification_details,
        )
    
    def _build_rp_comment(
        self, 
        rca: RCA, 
        verification: VerificationResult | None
    ) -> str:
        """Build ReportPortal comment with verification details."""
        comment = rca.to_rp_comment()
        
        if verification and verification.status != "not_run":
            verification_section = f"""
### Verification Result
**Mode:** {verification.mode.value}
**Status:** {'✅ PASSED' if verification.status == 'passed' else '❌ ' + verification.status.upper()}
**Confidence:** {verification.confidence:.0%}

**Analysis:** {verification.reason}
"""
            # Insert before the closing line
            if "---" in comment:
                parts = comment.rsplit("---", 1)
                comment = parts[0] + verification_section + "\n---" + parts[1]
            else:
                comment += "\n" + verification_section
        
        return comment
    
    def _group_by_signature(self, failures: list[Failure]) -> dict[str, list[Failure]]:
        """Group failures by error signature for deduplication."""
        import hashlib
        import re
        
        groups: dict[str, list[Failure]] = {}
        
        for failure in failures:
            # Extract error signature
            patterns = [
                r"(\w+Error|\w+Exception)[:\s]+(.{10,100})",
                r"(CrashLoopBackOff|ImagePullBackOff|OOMKilled)",
            ]
            
            signature = None
            for pattern in patterns:
                match = re.search(pattern, failure.logs, re.IGNORECASE)
                if match:
                    signature = hashlib.md5(
                        match.group(0)[:100].encode()
                    ).hexdigest()[:12]
                    break
            
            if not signature:
                signature = hashlib.md5(failure.logs[:300].encode()).hexdigest()[:12]
            
            if signature not in groups:
                groups[signature] = []
            groups[signature].append(failure)
        
        return groups
    
    def _enhance_evidence_with_code(
        self, 
        evidence: "Evidence",
        code_info: TestCodeInfo,
    ) -> None:
        """Enhance evidence with test code analysis information."""
        from src.domain.entities.evidence import Evidence
        
        # Transfer code analysis fields to evidence
        evidence.test_code = code_info.source_code
        evidence.test_file = code_info.file_path
        evidence.github_url = code_info.github_url
        evidence.function_name = code_info.function_name
        evidence.line_start = code_info.line_start
        evidence.line_end = code_info.line_end
        
        # Transfer parsed metadata
        evidence.decorators = code_info.decorators
        evidence.fixtures = code_info.fixtures
        evidence.has_timeout = code_info.has_timeout
        evidence.timeout_value = code_info.timeout_value
        evidence.has_retry = code_info.has_retry
        evidence.uses_sleep = code_info.uses_sleep
        evidence.wait_patterns = code_info.wait_patterns
        evidence.parametrize_args = code_info.parametrize_args
        
        # Update known_flaky based on code analysis
        if code_info.is_potentially_flaky:
            evidence.known_flaky = True
