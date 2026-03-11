"""Investigation routes for deep RCA analysis."""

import os
from fastapi import APIRouter, HTTPException

from src.api.schemas.requests import InvestigateRequest, VerifyModeEnum
from src.api.schemas.responses import (
    InvestigateResponse,
    InvestigationResult,
    ClassificationDetails,
)
from src.api.dependencies import get_cache, get_rp_config
from src.application.use_cases.investigate_rca import (
    InvestigateRCAUseCase,
    InvestigateRequest as UseCaseRequest,
)
from src.domain.services.verification_service import VerificationService, VerifyMode
from src.infrastructure.repositories.rp_repository import RPRepository
from src.infrastructure.llm.llm_factory import LLMFactory
from src.utils.config import get_settings
from src.utils.logging import get_logger


router = APIRouter()
logger = get_logger(__name__)


def _map_verify_mode(api_mode: VerifyModeEnum) -> VerifyMode:
    """Map API enum to domain enum (legacy support)."""
    mapping = {
        VerifyModeEnum.NONE: VerifyMode.NONE,
        VerifyModeEnum.RUN: VerifyMode.RUN_TEST,
        VerifyModeEnum.ANALYZE_HISTORY: VerifyMode.ANALYZE_HISTORY,
        VerifyModeEnum.ALL: VerifyMode.ALL,
    }
    return mapping.get(api_mode, VerifyMode.NONE)


def _get_effective_verify_mode(request: InvestigateRequest) -> VerifyMode:
    """Determine verification mode from request options.
    
    Supports both new checkbox-style (run_test, analyze_history) and 
    legacy single-select (verify_mode).
    """
    # New checkbox-style takes precedence
    if request.run_test and request.analyze_history:
        return VerifyMode.ALL
    elif request.run_test:
        return VerifyMode.RUN_TEST
    elif request.analyze_history:
        return VerifyMode.ANALYZE_HISTORY
    
    # Fall back to legacy single-select
    if request.verify_mode != VerifyModeEnum.NONE:
        return _map_verify_mode(request.verify_mode)
    
    # Legacy verify_tests flag
    if request.verify_tests:
        return VerifyMode.RUN_TEST
    
    return VerifyMode.NONE


@router.post("/investigate", response_model=InvestigateResponse)
async def investigate_failures(request: InvestigateRequest) -> InvestigateResponse:
    """Deep RCA investigation using Thinker-Critic pattern.
    
    This endpoint always uses LLM for deep analysis with:
    - Thinker: Proposes initial RCA
    - Critic: Challenges the analysis
    - Refiner: Produces final classification
    
    Verification modes:
    - none: No verification (default)
    - run: Actually execute the test using uv run pytest
    - analyze-history: Analyze pass/fail pattern from RP + test code
    """
    verify_mode = _get_effective_verify_mode(request)
    
    logger.info("investigate_started",
                launch_id=request.launch_id,
                component=request.component,
                provider=request.provider,
                verify_mode=verify_mode.value,
                run_test=request.run_test,
                analyze_history=request.analyze_history)
    
    rp_config = get_rp_config()
    cache = get_cache()
    
    if not rp_config or not rp_config.get("url"):
        logger.error("rp_not_configured")
        raise HTTPException(
            status_code=503,
            detail="ReportPortal not configured",
        )
    
    logger.debug("connecting_to_rp", project=rp_config["project"])
    
    # Create repository
    rp_repo = RPRepository(
        url=rp_config["url"],
        project=rp_config["project"],
        username=rp_config["username"],
        password=rp_config["password"],
        verify_ssl=rp_config["verify_ssl"],
    )
    
    # Create LLM provider (required for investigation)
    logger.info("initializing_llm", provider=request.provider)
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("GROQ_API_KEY")
        llm_provider = LLMFactory.create(
            request.provider,
            api_key=api_key,
        )
        logger.info("llm_ready", provider=request.provider)
    except Exception as e:
        logger.error("llm_init_failed", provider=request.provider, error=str(e))
        raise HTTPException(
            status_code=503,
            detail=f"LLM provider not available: {e}",
        )
    
    settings = get_settings()
    
    # Create verification service if needed
    verification_service = None
    if verify_mode != VerifyMode.NONE:
        test_repo_path = None
        if settings.test_repo.enabled and settings.test_repo.local_path:
            test_repo_path = settings.test_repo.local_path
        
        verification_service = VerificationService(
            test_repo_path=test_repo_path,
            timeout=settings.verification.timeout_per_test,
        )
        logger.info("verification_service_created",
                    mode=verify_mode.value,
                    repo_path=test_repo_path)
    
    # Create code fetcher if enabled
    code_fetcher = None
    if settings.is_code_fetcher_enabled():
        from pathlib import Path
        if settings.test_repo.local_path:
            from src.infrastructure.code_fetcher.local_adapter import LocalCodeFetcher
            code_fetcher = LocalCodeFetcher(
                base_path=Path(settings.test_repo.local_path),
                github_repo=settings.test_repo.repo,
                github_branch=settings.test_repo.branch,
            )
            logger.info("code_fetcher_created", type="local", path=settings.test_repo.local_path)
        elif settings.test_repo.repo:
            from src.infrastructure.code_fetcher.github_adapter import GitHubCodeFetcher
            code_fetcher = GitHubCodeFetcher(
                repo=settings.test_repo.repo,
                branch=settings.test_repo.branch,
                token=settings.get_github_token(),
                test_dir=settings.test_repo.test_dir,
                cache_dir=Path(settings.test_repo.cache_dir),
            )
            logger.info("code_fetcher_created", type="github", repo=settings.test_repo.repo)
    
    # Create must-gather analyzer if enabled
    must_gather_analyzer = None
    if settings.is_must_gather_enabled():
        from src.infrastructure.k8s.must_gather_analyzer import MustGatherAnalyzer
        mg_path = request.must_gather_path or settings.must_gather.base_path
        must_gather_analyzer = MustGatherAnalyzer(
            base_path=mg_path,
            max_log_lines=settings.must_gather.max_log_lines,
            auto_detect=settings.must_gather.auto_detect,
        )
        logger.info("must_gather_analyzer_created", base_path=mg_path)
    
    # Create and execute use case
    use_case = InvestigateRCAUseCase(
        failure_repo=rp_repo,
        llm_provider=llm_provider,
        cache_repo=cache,
        history_repo=rp_repo,
        verification_service=verification_service,
        code_fetcher=code_fetcher,
        must_gather_analyzer=must_gather_analyzer,
    )
    
    use_case_request = UseCaseRequest(
        launch_id=request.launch_id,
        component=request.component,
        test_id=request.test_id,
        push_to_rp=request.push_to_rp,
        verify_mode=verify_mode,
        verify_tests=request.verify_tests,  # Legacy support
    )
    
    logger.info("fetching_failures", launch_id=request.launch_id, component=request.component)
    
    async with rp_repo:
        results = await use_case.execute(use_case_request)
    
    logger.info("investigation_complete", total_failures=len(results))
    
    # Build response
    from src.api.schemas.responses import VerificationDetailsSchema
    
    summary: dict[str, int] = {}
    investigation_results: list[InvestigationResult] = []
    
    for result in results:
        category = result.rca.classification.category.value
        summary[category] = summary.get(category, 0) + 1
        
        # Build verification details if present
        verification_details = None
        if result.verification_details:
            verification_details = VerificationDetailsSchema(
                mode=result.verification_details.get("mode", "none"),
                status=result.verification_details.get("status", "not_run"),
                output=result.verification_details.get("output", "")[:500],
                confidence=result.verification_details.get("confidence", 0.0),
                reason=result.verification_details.get("reason", ""),
                is_intermittent=result.verification_details.get("is_intermittent", False),
                details=result.verification_details.get("details", {}),
            )
        
        # Build enhanced analysis schemas if present
        from src.api.schemas.responses import TimeoutAnalysisSchema, ClusterInfoSchema
        
        timeout_analysis_schema = None
        if result.timeout_analysis:
            timeout_analysis_schema = TimeoutAnalysisSchema(
                operation_type=result.timeout_analysis.get("operation_type", ""),
                timeout_used=result.timeout_analysis.get("timeout_used", 0),
                expected_min=result.timeout_analysis.get("expected_min", 0),
                expected_max=result.timeout_analysis.get("expected_max", 0),
                verdict=result.timeout_analysis.get("verdict", ""),
                recommendation=result.timeout_analysis.get("recommendation", ""),
            )
        
        cluster_info_schema = None
        if result.cluster_info:
            cluster_info_schema = ClusterInfoSchema(
                cluster_id=result.cluster_info.get("cluster_id", ""),
                likely_root_cause=result.cluster_info.get("likely_root_cause", ""),
                category=result.cluster_info.get("category", ""),
                recommendation=result.cluster_info.get("recommendation", ""),
                affected_tests=result.cluster_info.get("affected_tests", 0),
            )
        
        investigation_results.append(InvestigationResult(
            test_name=result.test_name,
            test_id=result.test_id,
            classification=ClassificationDetails(
                category=category,
                confidence=result.rca.confidence,
                confidence_percent=result.rca.classification.confidence_percent,
                severity=result.rca.severity.value,
            ),
            root_cause=result.rca.root_cause,
            reasoning=result.rca.reasoning,
            evidence_summary=result.rca.evidence_summary,
            recommendation=result.rca.recommendation,
            verified=result.verified,
            verification_result=result.verification_result,
            verification_details=verification_details,
            github_url=result.rca.github_url,
            test_file=result.rca.test_file,
            code_analysis=result.rca.code_analysis,
            fixtures=result.rca.fixtures,
            # Enhanced analysis fields
            timeout_analysis=timeout_analysis_schema,
            cluster_info=cluster_info_schema,
            calibrated_confidence=result.calibrated_confidence,
            confidence_explanation=result.confidence_explanation,
        ))
    
    return InvestigateResponse(
        launch_id=request.launch_id,
        component=request.component,
        total_failures=len(results),
        results=investigation_results,
        summary=summary,
    )
