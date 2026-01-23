"""Error handling and logging middleware."""

import time
import traceback
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.utils.logging import get_logger

logger = get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Global error handler middleware."""
    
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            error_trace = traceback.format_exc()
            logger.error(
                "unhandled_error",
                error=str(e),
                path=request.url.path,
                traceback=error_trace,
            )
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": str(e),
                    "detail": "An internal error occurred",
                    "status_code": 500,
                },
            )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Request/response logging with timing."""
    
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        # Skip logging for health checks
        if request.url.path in ["/health", "/", "/favicon.ico"]:
            return await call_next(request)
        
        logger.info(
            "request_started",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else "unknown",
        )
        
        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000
            
            logger.info(
                "request_completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(duration_ms, 2),
            )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            return response
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "request_failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration_ms=round(duration_ms, 2),
            )
            raise
