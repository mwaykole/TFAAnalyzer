"""Domain interfaces - abstractions for Dependency Inversion Principle."""

from src.domain.interfaces.repositories import (
    FailureRepository,
    CacheRepository,
    HistoryRepository,
)
from src.domain.interfaces.llm_provider import LLMProvider, LLMResponse
from src.domain.interfaces.log_parser import LogParser
from src.domain.interfaces.code_fetcher import CodeFetcher, TestCodeInfo
from src.domain.interfaces.notifier import Notifier, AnalysisSummary

__all__ = [
    "FailureRepository",
    "CacheRepository", 
    "HistoryRepository",
    "LLMProvider",
    "LLMResponse",
    "LogParser",
    "CodeFetcher",
    "TestCodeInfo",
    "Notifier",
    "AnalysisSummary",
]
