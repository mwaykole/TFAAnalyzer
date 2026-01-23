"""Async retry utilities with exponential backoff."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from src.utils.logging import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
    )


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for next retry attempt using exponential backoff."""
    delay = config.base_delay * (config.exponential_base ** (attempt - 1))
    return min(delay, config.max_delay)


def async_retry(
    config: RetryConfig | None = None,
    retryable_exceptions: tuple[type[Exception], ...] | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator for async functions with exponential backoff retry.

    Args:
        config: Retry configuration
        retryable_exceptions: Exception types to retry on (overrides config)

    Returns:
        Decorated async function with retry logic
    """
    cfg = config or RetryConfig()
    exceptions = retryable_exceptions or cfg.retryable_exceptions

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception: Exception | None = None

            for attempt in range(1, cfg.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == cfg.max_attempts:
                        logger.error(
                            "max_retries_exceeded",
                            function=func.__name__,
                            attempt=attempt,
                            error=str(e),
                        )
                        raise

                    delay = calculate_delay(attempt, cfg)
                    logger.warning(
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=cfg.max_attempts,
                        delay=delay,
                        error=str(e),
                    )
                    await asyncio.sleep(delay)

            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper

    return decorator


class CircuitBreaker:
    """Circuit breaker pattern for handling repeated failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time: float | None = None
        self.state: str = "closed"

    async def call(
        self,
        func: Callable[P, Awaitable[T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        """Execute function through circuit breaker.

        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpen: If circuit is open
            Original exception if function fails
        """
        if self.state == "open":
            if self.last_failure_time:
                import time

                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = "half-open"
                    logger.info("circuit_breaker_half_open")
                else:
                    raise CircuitBreakerOpen(
                        f"Circuit breaker is open. Retry after {self.recovery_timeout}s"
                    )

        try:
            result = await func(*args, **kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failures = 0
                logger.info("circuit_breaker_closed")
            return result
        except Exception as e:
            self._record_failure()
            raise e

    def _record_failure(self) -> None:
        """Record a failure and potentially open the circuit."""
        import time

        self.failures += 1
        self.last_failure_time = time.time()

        if self.failures >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                "circuit_breaker_opened",
                failures=self.failures,
                threshold=self.failure_threshold,
            )

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self.failures = 0
        self.last_failure_time = None
        self.state = "closed"


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""

    pass

