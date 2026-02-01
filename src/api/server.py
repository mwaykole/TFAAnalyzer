"""FastAPI server for centralized TFA API.

Provides REST API for 30 QE engineers to share:
- Analysis cache (avoid duplicate LLM calls)
- Classification results
- Historical data

SOLID Principles:
- Single Responsibility: Only handles HTTP routing
- Dependency Inversion: Uses injected dependencies
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.dependencies import set_cache, set_rp_config, load_rp_config_from_env
from src.infrastructure.cache.redis_cache import RedisCache
from src.infrastructure.cache.memory_cache import MemoryCache
from src.utils.logging import setup_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager."""
    # Setup logging with buffer for UI streaming
    setup_logging(level="INFO", log_format="json", enable_buffer=True)
    logger = get_logger("tfa.server")
    logger.info("server_starting", version="2.0.0")
    
    # Initialize cache
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    cache = None
    
    try:
        if redis_url:
            parts = redis_url.replace("redis://", "").split(":")
            host = parts[0] if parts else "localhost"
            port = int(parts[1].split("/")[0]) if len(parts) > 1 else 6379
            cache = RedisCache(host=host, port=port)
            if await cache.health_check():
                print(f"✅ Connected to Redis at {host}:{port}")
            else:
                print("⚠️ Redis not available, using memory cache")
                cache = MemoryCache()
        else:
            cache = MemoryCache()
            print("ℹ️ Using in-memory cache (set REDIS_URL for shared cache)")
    except Exception as e:
        print(f"⚠️ Redis error: {e}, using memory cache")
        cache = MemoryCache()
    
    set_cache(cache)
    
    # Load RP configuration
    rp_config = load_rp_config_from_env()
    set_rp_config(rp_config)
    
    yield
    
    # Cleanup
    if isinstance(cache, RedisCache):
        await cache.close()


def create_app() -> FastAPI:
    """Create FastAPI application.
    
    Factory pattern for application creation.
    Enables easy testing with different configurations.
    """
    app = FastAPI(
        title="TFA API",
        description="Test Failure Analyzer - AI-powered classification for ReportPortal",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Import routes here to avoid circular imports
    from src.api.routes import analyze, investigate, health, logs, feedback
    from src.api.middleware.error_handler import ErrorHandlerMiddleware, RequestLoggingMiddleware
    
    # Add middlewares (order matters - first added = outermost)
    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    
    # Register routes
    app.include_router(health.router, tags=["Health"])
    app.include_router(analyze.router, prefix="/api/v1", tags=["Analysis"])
    app.include_router(investigate.router, prefix="/api/v1", tags=["Investigation"])
    app.include_router(logs.router, prefix="/api/v1", tags=["Logs"])
    app.include_router(feedback.router, prefix="/api/v1", tags=["Feedback & Learning"])
    
    return app


# Create default app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.api.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
