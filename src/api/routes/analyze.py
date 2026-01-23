"""Analysis routes."""

import os
from fastapi import APIRouter, HTTPException

from src.api.schemas.requests import AnalyzeRequest
from src.api.schemas.responses import AnalyzeResponse, AnalysisResult, ClassificationDetails
from src.api.dependencies import get_cache, get_rp_config
from src.application.use_cases.analyze_failure import (
    AnalyzeFailureUseCase,
    AnalyzeRequest as UseCaseRequest,
)
from src.infrastructure.repositories.rp_repository import RPRepository
from src.infrastructure.llm.llm_factory import LLMFactory
from src.utils.logging import get_logger


router = APIRouter()
logger = get_logger(__name__)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_failures(request: AnalyzeRequest) -> AnalyzeResponse:
    """Analyze test failures in a launch.
    
    This endpoint:
    1. Checks cache for existing results (shared across 30 users)
    2. Checks ReportPortal for existing AI classifications
    3. Runs new analysis only when needed
    4. Optionally pushes results to ReportPortal
    """
    logger.info("analyze_started", 
                launch_id=request.launch_id, 
                component=request.component,
                provider=request.provider,
                use_llm=request.use_llm,
                use_cache=request.use_cache)
    
    rp_config = get_rp_config()
    cache = get_cache()
    
    if not rp_config or not rp_config.get("url"):
        logger.error("rp_not_configured")
        raise HTTPException(
            status_code=503,
            detail="ReportPortal not configured. Set RP_URL, RP_PROJECT, etc.",
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
    
    # Create LLM provider if needed
    llm_provider = None
    if request.use_llm:
        try:
            api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("GROQ_API_KEY")
            llm_provider = LLMFactory.create(
                request.provider,
                api_key=api_key,
            )
            logger.info("llm_provider_initialized", provider=request.provider)
        except Exception as e:
            logger.warning("llm_provider_failed", provider=request.provider, error=str(e))
    
    # Create and execute use case
    use_case = AnalyzeFailureUseCase(
        failure_repo=rp_repo,
        cache_repo=cache,
        history_repo=rp_repo,
        llm_provider=llm_provider,
    )
    
    use_case_request = UseCaseRequest(
        launch_id=request.launch_id,
        component=request.component,
        test_id=request.test_id,
        push_to_rp=request.push_to_rp,
        use_cache=request.use_cache,
        use_llm=request.use_llm,
    )
    
    logger.info("fetching_failures", launch_id=request.launch_id, component=request.component)
    
    async with rp_repo:
        results = await use_case.execute(use_case_request)
    
    logger.info("analysis_complete", total_failures=len(results))
    
    # Build response
    summary: dict[str, int] = {}
    analysis_results: list[AnalysisResult] = []
    
    for result in results:
        category = result.rca.classification.category.value
        summary[category] = summary.get(category, 0) + 1
        
        analysis_results.append(AnalysisResult(
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
            recommendation=result.rca.recommendation,
            cached=result.cached,
            from_rp=result.from_rp,
        ))
    
    return AnalyzeResponse(
        launch_id=request.launch_id,
        component=request.component,
        total_failures=len(results),
        results=analysis_results,
        summary=summary,
    )
