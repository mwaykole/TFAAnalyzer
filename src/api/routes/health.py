"""Health check routes."""

from fastapi import APIRouter

from src.api.schemas.responses import HealthResponse
from src.api.dependencies import get_cache, get_rp_config
from src.infrastructure.llm.llm_factory import LLMFactory


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check API health status."""
    cache = get_cache()
    rp_config = get_rp_config()
    
    # Check cache
    cache_available = False
    if cache:
        try:
            from src.infrastructure.cache.redis_cache import RedisCache
            if isinstance(cache, RedisCache):
                cache_available = await cache.health_check()
            else:
                cache_available = True
        except Exception:
            pass
    
    # Check RP configuration
    rp_configured = bool(
        rp_config and 
        rp_config.get("url") and 
        rp_config.get("project")
    )
    
    # Determine overall status
    if cache_available and rp_configured:
        status = "healthy"
    elif rp_configured:
        status = "degraded"
    else:
        status = "unhealthy"
    
    return HealthResponse(
        status=status,
        cache_available=cache_available,
        rp_configured=rp_configured,
        llm_providers=LLMFactory.available_providers(),
    )


@router.get("/")
async def root():
    """API root endpoint."""
    return {
        "name": "TFA API",
        "version": "2.0.0",
        "description": "Test Failure Analyzer - AI-powered classification",
        "docs": "/docs",
    }
