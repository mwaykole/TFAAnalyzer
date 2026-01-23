"""Structured logging setup using structlog."""

import json
import logging
import sys
from collections import deque
from datetime import datetime
from typing import Any, Callable

import structlog
from structlog.types import Processor

# Global log buffer for UI streaming
_log_buffer: deque[dict] = deque(maxlen=200)
_log_subscribers: list[Callable[[dict], None]] = []


class BufferHandler(logging.Handler):
    """Handler that stores logs in a buffer for streaming to UI."""
    
    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            try:
                entry = json.loads(msg)
            except json.JSONDecodeError:
                entry = {"message": msg}
            
            entry["level"] = record.levelname
            entry["logger"] = record.name
            if "timestamp" not in entry:
                entry["timestamp"] = datetime.utcnow().isoformat()
            
            _log_buffer.append(entry)
            
            # Notify subscribers
            for callback in _log_subscribers:
                try:
                    callback(entry)
                except Exception:
                    pass
        except Exception:
            pass


def get_log_buffer() -> list[dict]:
    """Get recent logs from buffer."""
    return list(_log_buffer)


def subscribe_to_logs(callback: Callable[[dict], None]) -> Callable[[], None]:
    """Subscribe to log events. Returns unsubscribe function."""
    _log_subscribers.append(callback)
    return lambda: _log_subscribers.remove(callback)


def setup_logging(
    level: str = "INFO",
    log_format: str = "json",
    enable_buffer: bool = True,
) -> None:
    """Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_format: Output format (json or console)
        enable_buffer: Enable log buffer for UI streaming
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]

    if log_format == "json":
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    
    # Add buffer handler for UI streaming
    if enable_buffer:
        buffer_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
        buffer_handler = BufferHandler()
        buffer_handler.setFormatter(buffer_formatter)
        root_logger.addHandler(buffer_handler)
    
    root_logger.setLevel(log_level)

    for logger_name in ["aiohttp", "anthropic", "httpx"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


def bind_context(**kwargs: Any) -> None:
    """Bind context variables to all subsequent log messages.

    Args:
        **kwargs: Key-value pairs to bind to log context
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()

