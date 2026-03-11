"""Investigate RCA Use Case.

Single Responsibility: Orchestrates deep RCA investigation workflow.
Dependency Inversion: Depends on repository and service interfaces.

Enhanced with:
- Timeout analysis for intelligent timeout verdict
- Failure clustering for systemic issue detection
- Confidence calibration based on evidence quality
- Pre-error log extraction for better context
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from src.domain.entities.classification import FailureCategory
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
from src.domain.services.enhanced_analysis import (
    analyze_timeout,
    extract_pre_error_logs,
    calibrate_confidence,
    FailureClusterAnalyzer,
    TimeoutAnalysis,
    ClusterAnalysis,
)
from src.utils.logging import get_logger

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.domain.entities.evidence import Evidence
    from src.infrastructure.embeddings.failure_store import FailureEmbeddingStore
    from src.infrastructure.k8s.must_gather_analyzer import MustGatherAnalyzer

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
    
    # Enhanced analysis results
    timeout_analysis: dict[str, Any] | None = None
    cluster_info: dict[str, Any] | None = None
    calibrated_confidence: float | None = None
    confidence_explanation: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        result = {
            "test_name": self.test_name,
            "test_id": self.test_id,
            **self.rca.to_dict(),
            "verified": self.verified,
            "verification_result": self.verification_result,
            "verification_details": self.verification_details,
        }
        
        # Add enhanced analysis if available
        if self.timeout_analysis:
            result["timeout_analysis"] = self.timeout_analysis
        if self.cluster_info:
            result["cluster_info"] = self.cluster_info
        if self.calibrated_confidence is not None:
            result["calibrated_confidence"] = self.calibrated_confidence
            result["confidence_explanation"] = self.confidence_explanation
        
        return result


class InvestigateRCAUseCase:
    """Use case for deep RCA investigation using Thinker-Critic pattern.
    
    Unlike AnalyzeFailureUseCase, this always uses LLM for deep analysis.
    
    Dependency Inversion: All dependencies are abstractions (interfaces).
    
    Enhanced with:
    - Failure clustering for systemic issue detection
    - Timeout analysis
    - Few-shot learning with embeddings
    - Confidence calibration
    """
    
    def __init__(
        self,
        failure_repo: FailureRepository,
        llm_provider: LLMProvider,
        cache_repo: CacheRepository | None = None,
        history_repo: HistoryRepository | None = None,
        verification_service: VerificationService | None = None,
        code_fetcher: CodeFetcher | None = None,
        failure_store: "FailureEmbeddingStore | None" = None,
        must_gather_analyzer: "MustGatherAnalyzer | None" = None,
    ):
        """Initialize with dependencies."""
        self._failure_repo = failure_repo
        self._llm_provider = llm_provider
        self._cache_repo = cache_repo
        self._history_repo = history_repo
        self._verification_service = verification_service
        self._code_fetcher = code_fetcher
        self._failure_store = failure_store
        self._must_gather_analyzer = must_gather_analyzer
        
        self._classifier = ClassificationService()
        self._investigator = InvestigationService(
            llm_provider, 
            self._classifier,
            failure_store=failure_store,
        )
        self._verification_semaphore: asyncio.Semaphore | None = None
    
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
        
        # =========================================================
        # Launch-wide failure scan for cross-component patterns
        # =========================================================
        launch_summary: dict[str, Any] = {}
        try:
            launch_summary = await self._failure_repo.get_launch_failure_summary(
                request.launch_id,
            )
            if launch_summary:
                logger.info(
                    "launch_summary",
                    total_failed=launch_summary.get("total_failed"),
                    failure_rate=launch_summary.get("failure_rate"),
                    setup_timeouts=launch_summary.get("setup_timeout_count"),
                    login_failures=launch_summary.get("login_failure_count"),
                    launch_health=launch_summary.get("launch_health"),
                )
        except Exception as e:
            logger.debug("launch_summary_failed", error=str(e))
        
        # =========================================================
        # ENHANCED: Run failure clustering to detect systemic issues
        # =========================================================
        cluster_analysis: ClusterAnalysis | None = None
        cluster_map: dict[str, dict] = {}  # test_id -> cluster_info
        
        if len(failures) >= 2:
            logger.info("running_cluster_analysis", failure_count=len(failures))
            cluster_analyzer = FailureClusterAnalyzer()
            cluster_analysis = cluster_analyzer.analyze_failures([
                {
                    "test_id": f.id,
                    "test_name": f.test_name,
                    "error_message": f.logs[:500],
                    "error_type": self._extract_error_type(f.logs),
                }
                for f in failures
            ])
            
            if cluster_analysis.systemic_issue_detected:
                logger.warning("systemic_issue_detected",
                              clusters=len(cluster_analysis.clusters),
                              summary=cluster_analysis.summary[:100])
                
                # Build cluster map for quick lookup
                for cluster in cluster_analysis.clusters:
                    cluster_info = {
                        "cluster_id": cluster.cluster_id,
                        "likely_root_cause": cluster.likely_root_cause,
                        "category": cluster.category,
                        "recommendation": cluster.recommendation,
                        "affected_tests": len(cluster.failures),
                    }
                    for test_id in cluster.failures:
                        cluster_map[test_id] = cluster_info
        
        # Group by error signature for efficiency
        signature_groups = self._group_by_signature(failures)
        num_groups = len(signature_groups)
        logger.info("grouped_by_signature", 
                    unique_signatures=num_groups,
                    total_failures=len(failures))
        
        max_concurrent = min(num_groups, 5)
        semaphore = asyncio.Semaphore(max_concurrent)
        
        if self._verification_service and request.verify_mode != VerifyMode.NONE:
            from src.utils.config import Settings
            try:
                settings = Settings()
                max_verify = settings.verification.max_parallel
            except Exception:
                max_verify = 1
            self._verification_semaphore = asyncio.Semaphore(max_verify)
            logger.info("verification_concurrency", max_parallel=max_verify)
        
        async def _investigate_group(
            group_num: int,
            signature: str,
            group: list[Failure],
        ) -> list[InvestigateResponse]:
            async with semaphore:
                logger.info("investigating_group",
                            group=f"{group_num}/{num_groups}",
                            signature=signature[:12],
                            failures_in_group=len(group),
                            test_name=group[0].test_name[:40])
                
                cluster_info = cluster_map.get(group[0].id)
                
                first_result = await self._investigate_single(
                    group[0], request,
                    cluster_info=cluster_info,
                    launch_summary=launch_summary,
                )
                
                logger.info("investigation_result",
                            test_name=group[0].test_name[:30],
                            classification=first_result.rca.classification.category.value,
                            confidence=f"{first_result.rca.confidence:.0%}",
                            calibrated=f"{first_result.calibrated_confidence:.0%}" if first_result.calibrated_confidence else "N/A",
                            severity=first_result.rca.severity.value)
                
                group_results = [first_result]
                for failure in group[1:]:
                    logger.debug("reusing_rca", 
                                 test_name=failure.test_name[:30],
                                 same_signature=signature[:12])
                    group_results.append(InvestigateResponse(
                        test_name=failure.test_name,
                        test_id=failure.id,
                        rca=first_result.rca,
                        verified=first_result.verified,
                        verification_result=first_result.verification_result,
                        cluster_info=cluster_map.get(failure.id),
                        calibrated_confidence=first_result.calibrated_confidence,
                        confidence_explanation=first_result.confidence_explanation,
                    ))
                return group_results
        
        tasks = [
            _investigate_group(i + 1, sig, grp)
            for i, (sig, grp) in enumerate(signature_groups.items())
        ]
        
        if num_groups > 1:
            logger.info("parallel_investigation", groups=num_groups, concurrency=max_concurrent)
        
        group_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for gr in group_results:
            if isinstance(gr, Exception):
                logger.error("group_investigation_failed", error=str(gr))
                continue
            results.extend(gr)
        
        logger.info("investigation_complete", 
                    total_results=len(results),
                    systemic_issues=len(cluster_analysis.clusters) if cluster_analysis else 0)
        return results
    
    def _extract_error_type(self, logs: str) -> str:
        """Extract error type from logs."""
        import re
        match = re.search(r"(\w+Error|\w+Exception)", logs)
        return match.group(1) if match else "UnknownError"
    
    async def _investigate_single(
        self, 
        failure: Failure, 
        request: InvestigateRequest,
        cluster_info: dict[str, Any] | None = None,
        launch_summary: dict[str, Any] | None = None,
    ) -> InvestigateResponse:
        """Investigate a single failure with full Thinker-Critic pattern.
        
        Enhanced with:
        - Timeout analysis
        - Pre-error log extraction
        - Cluster-aware analysis
        - Confidence calibration
        """
        # =========================================================
        # ENHANCED: Extract pre-error logs for better context
        # =========================================================
        pre_error_logs = extract_pre_error_logs(failure.logs, max_lines=20)
        if pre_error_logs:
            logger.debug("pre_error_logs_extracted", 
                         lines=len(pre_error_logs.split('\n')))
        
        # Gather evidence
        logger.debug("extracting_evidence", 
                     test_name=failure.test_name[:30],
                     log_length=len(failure.logs))
        evidence = self._classifier.get_evidence_from_logs(
            failure.logs, failure.test_code
        )
        
        # Add pre-error context to evidence
        if pre_error_logs:
            evidence.pre_error_context = pre_error_logs
        
        if "failed on setup" in failure.logs.lower():
            evidence.failed_on_setup = True
        
        if launch_summary:
            ls_health = launch_summary.get("launch_health", "")
            if ls_health == "degraded" and not evidence.cluster_health:
                evidence.cluster_health = "degraded"
            login_fails = launch_summary.get("login_failure_count", 0)
            setup_tos = launch_summary.get("setup_timeout_count", 0)
            rate = launch_summary.get("failure_rate", 0)
            total_f = launch_summary.get("total_failed", 0)
            parts = []
            parts.append(
                f"Launch-wide: {total_f} failures "
                f"({rate:.0%} failure rate)"
            )
            if login_fails:
                parts.append(
                    f"{login_fails} cross-component login/auth failures detected"
                )
            if setup_tos:
                parts.append(
                    f"{setup_tos} cross-component setup timeouts detected"
                )
            if parts:
                launch_ctx = "; ".join(parts)
                existing = evidence.pre_error_context or ""
                evidence.pre_error_context = (
                    f"LAUNCH CONTEXT: {launch_ctx}\n{existing}"
                )
        
        logger.debug("evidence_extracted",
                     error_type=evidence.error_type or "unknown",
                     patterns=len(evidence.patterns),
                     has_stack_trace=bool(evidence.stack_trace))
        
        # =========================================================
        # ENHANCED: Timeout analysis
        # =========================================================
        timeout_analysis: TimeoutAnalysis | None = None
        if "timeout" in failure.logs.lower() or "TimeoutExpiredError" in failure.logs:
            timeout_analysis = analyze_timeout(
                error_message=evidence.error_message or "",
                stack_trace=evidence.stack_trace or "",
                test_name=failure.test_name,
            )
            if timeout_analysis:
                logger.info("timeout_analysis",
                            operation=timeout_analysis.operation_type,
                            timeout_used=timeout_analysis.timeout_used,
                            verdict=timeout_analysis.verdict)
                # Add to evidence for LLM context
                evidence.timeout_analysis = timeout_analysis.recommendation
        
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
            
            if self._verification_semaphore:
                async with self._verification_semaphore:
                    logger.info("verification_slot_acquired",
                                test_name=failure.test_name[:30])
                    verification_result = await self._verification_service.verify(
                        test_name=failure.test_name,
                        mode=verify_mode,
                        logs=failure.logs,
                        test_code=failure.test_code,
                        history=history,
                    )
            else:
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
        
        # =========================================================
        # ENHANCED: Add cluster info to evidence for LLM context
        # =========================================================
        if cluster_info:
            evidence.systemic_issue = cluster_info.get("likely_root_cause")
            evidence.cluster_recommendation = cluster_info.get("recommendation")
            logger.debug("cluster_context_added", 
                         root_cause=cluster_info.get("likely_root_cause"))
        
        # =========================================================
        # ENHANCED: Must-gather cluster state analysis
        # Priority: verification-collected must-gather > startup must-gather
        # =========================================================
        mg_report = None
        verify_mg_path = (
            verification_result.details.get("must_gather_path")
            if verification_result else None
        )

        if verify_mg_path:
            from src.infrastructure.k8s.must_gather_analyzer import MustGatherAnalyzer
            try:
                live_analyzer = MustGatherAnalyzer(
                    base_path=verify_mg_path,
                    auto_detect=False,
                )
                mg_report = live_analyzer.analyze()
                logger.info("verification_must_gather_analyzed",
                            path=verify_mg_path,
                            cluster_health=mg_report.cluster_health,
                            unhealthy_pods=len(mg_report.unhealthy_pods),
                            resource_failures=len(mg_report.resource_failures))
            except Exception as e:
                logger.warning("verification_must_gather_failed", error=str(e))

        if mg_report is None and self._must_gather_analyzer:
            try:
                mg_report = self._must_gather_analyzer.analyze(
                    test_name=failure.test_name,
                )
            except Exception as e:
                logger.warning("must_gather_analysis_failed", error=str(e))

        if mg_report and mg_report.cluster_health != "unknown":
            evidence.must_gather_context = mg_report.to_context()
            evidence.cluster_health = mg_report.cluster_health
            logger.info("must_gather_analyzed",
                        test_name=failure.test_name[:30],
                        cluster_health=mg_report.cluster_health,
                        unhealthy_pods=len(mg_report.unhealthy_pods),
                        warning_events=len(mg_report.warning_events))
        
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
        
        # =========================================================
        # ENHANCED: Calibrate confidence based on evidence quality
        # =========================================================
        evidence_strength = self._assess_evidence_strength(evidence)
        calibration = calibrate_confidence(
            raw_confidence=rca.confidence,
            evidence_strength=evidence_strength,
            has_timeout_analysis=timeout_analysis is not None,
            has_cluster_match=cluster_info is not None,
            has_similar_failures=self._check_similar_failures(failure, evidence),
            verification_result=self._map_verification_status(
                verification_result, rca.classification.category
            ),
        )
        
        logger.info("confidence_calibrated",
                    raw=f"{rca.confidence:.0%}",
                    calibrated=f"{calibration.calibrated_confidence:.0%}",
                    explanation=calibration.explanation[:50])
        
        # Push to RP if requested
        if request.push_to_rp:
            logger.info("pushing_to_rp", test_id=failure.id)
            comment = self._build_rp_comment(rca, verification_result, timeout_analysis, cluster_info)
            await self._failure_repo.save_classification(failure.id, rca, comment)
        
        # Cache result
        if self._cache_repo:
            cache_key = f"investigation:{failure.cache_key}"
            logger.debug("caching_result", cache_key=cache_key[:30])
            await self._cache_repo.set(cache_key, rca.to_dict(), ttl_seconds=86400)
        
        # =========================================================
        # ENHANCED: Store result for few-shot learning
        # =========================================================
        if self._failure_store and calibration.calibrated_confidence >= 0.7:
            self._investigator.store_result(failure, evidence, rca)
        
        return InvestigateResponse(
            test_name=failure.test_name,
            test_id=failure.id,
            rca=rca,
            verified=verify_mode != VerifyMode.NONE,
            verification_result=evidence.verification_result,
            verification_details=verification_details,
            timeout_analysis=timeout_analysis.__dict__ if timeout_analysis else None,
            cluster_info=cluster_info,
            calibrated_confidence=calibration.calibrated_confidence,
            confidence_explanation=calibration.explanation,
        )
    
    def _check_similar_failures(self, failure, evidence) -> bool:
        """Check if similar past failures exist in the embedding store."""
        if not self._failure_store:
            return False
        try:
            return bool(self._failure_store.find_similar(
                test_name=failure.test_name,
                error_type=evidence.error_type or "",
                error_message=evidence.error_message or "",
                k=1,
            ))
        except Exception:
            return False

    @staticmethod
    def _map_verification_status(
        verification_result: VerificationResult | None,
        category: FailureCategory | None = None,
    ) -> str | None:
        """Map verification result to calibration category.

        Context-aware: for Product Bug / Infrastructure Issue, a re-run
        failure *confirms* the persistent issue (boost confidence).  Only
        for Intermittent Failure does a re-run failure contradict the
        classification (we expected it to pass sometimes).
        """
        if not verification_result:
            return None

        status = verification_result.status
        is_persistent_category = category in (
            FailureCategory.PRODUCT_BUG,
            FailureCategory.INFRASTRUCTURE_ISSUE,
            FailureCategory.TEST_AUTOMATION_ISSUE,
        )

        if status == "passed":
            if is_persistent_category:
                return "contradicted"
            return "confirmed"

        if status == "failed":
            if is_persistent_category:
                return "confirmed"
            return "contradicted"

        static_mapping = {
            "flaky": "weak_confirm",
            "consistent_fail": "confirmed" if is_persistent_category else "strong_contradict",
            "rare_failure": "weak_confirm",
            "timeout": "inconclusive",
        }
        return static_mapping.get(status)

    def _assess_evidence_strength(self, evidence) -> str:
        """Assess the strength of evidence for calibration.

        Uses weighted scoring where definitive signals (e.g., CrashLoopBackOff pattern)
        count more than generic ones (e.g., "has an error message").
        """
        score = 0

        if evidence.patterns:
            definitive_keywords = {
                "crashloopbackoff", "oomkilled", "imagepullbackoff",
                "aws credentials", "gpu", "scheduling",
                "service mesh", "authentication",
            }
            has_definitive = any(
                any(kw in p.lower() for kw in definitive_keywords)
                for p in evidence.patterns
            )
            score += 4 if has_definitive else 2

        if evidence.stack_trace and len(evidence.stack_trace) > 100:
            score += 2
        if evidence.error_type:
            score += 1
        if evidence.error_message:
            score += 1

        if hasattr(evidence, 'pre_error_context') and evidence.pre_error_context:
            score += 1
        if hasattr(evidence, 'test_code') and evidence.test_code:
            score += 1

        if evidence.must_gather_context:
            has_unhealthy = "unhealthy" in evidence.must_gather_context.lower()
            score += 3 if has_unhealthy else 2

        if evidence.verification_result == "passed":
            score += 2
        elif evidence.verification_result == "failed":
            score += 1

        if evidence.historical_pass_rate < 1.0:
            score += 1

        if evidence.timeout_value:
            score += 1

        if score >= 9:
            return "definitive"
        elif score >= 6:
            return "strong"
        elif score >= 3:
            return "moderate"
        else:
            return "weak"
    
    def _build_rp_comment(
        self, 
        rca: RCA, 
        verification: VerificationResult | None,
        timeout_analysis: TimeoutAnalysis | None = None,
        cluster_info: dict[str, Any] | None = None,
    ) -> str:
        """Build ReportPortal comment with enhanced analysis details."""
        comment = rca.to_rp_comment()
        
        sections = []
        
        # Add timeout analysis if available
        if timeout_analysis:
            timeout_section = f"""
### Timeout Analysis
**Operation:** {timeout_analysis.operation_type}
**Timeout Used:** {timeout_analysis.timeout_used}s
**Verdict:** {timeout_analysis.verdict.upper()}
**Expected Range:** {timeout_analysis.expected_min}-{timeout_analysis.expected_max}s

**Recommendation:** {timeout_analysis.recommendation}
"""
            sections.append(timeout_section)
        
        # Add cluster info if systemic issue detected
        if cluster_info:
            cluster_section = f"""
### ⚠️ Systemic Issue Detected
**Root Cause:** {cluster_info.get('likely_root_cause', 'Unknown')}
**Category:** {cluster_info.get('category', 'unknown')}
**Affected Tests:** {cluster_info.get('affected_tests', 'Multiple')}

**Recommendation:** {cluster_info.get('recommendation', 'Investigate shared infrastructure')}
"""
            sections.append(cluster_section)
        
        # Add verification result
        if verification and verification.status != "not_run":
            verification_section = f"""
### Verification Result
**Mode:** {verification.mode.value}
**Status:** {'✅ PASSED' if verification.status == 'passed' else '❌ ' + verification.status.upper()}
**Confidence:** {verification.confidence:.0%}

**Analysis:** {verification.reason}
"""
            sections.append(verification_section)
        
        # Insert sections before the closing line
        if sections:
            all_sections = "\n".join(sections)
            if "---" in comment:
                parts = comment.rsplit("---", 1)
                comment = parts[0] + all_sections + "\n---" + parts[1]
            else:
                comment += "\n" + all_sections
        
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

        # Fallback: extract timeout value from error message if AST didn't find it
        if not evidence.timeout_value and evidence.error_message:
            import re
            m = re.search(r'(\d{2,4})\s*(?:seconds?|s)\b', evidence.error_message)
            if m:
                evidence.timeout_value = int(m.group(1))
                evidence.has_timeout = True
        
        # Update known_flaky based on code analysis
        if code_info.is_potentially_flaky:
            evidence.known_flaky = True
