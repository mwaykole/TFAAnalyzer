"""Abstract base class for LLM providers with shared utilities."""

import asyncio
import json
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timedelta
from typing import Any

from src.rp.models import AnalysisResult, FailureClassification
from src.utils.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Token bucket rate limiter for LLM API calls.
    
    Prevents exceeding API rate limits by tracking requests
    within a sliding time window.
    """

    def __init__(self, requests_per_minute: int = 30):
        """Initialize rate limiter.
        
        Args:
            requests_per_minute: Maximum requests allowed per minute
        """
        self.rpm = requests_per_minute
        self.requests: deque[datetime] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Acquire permission to make a request.
        
        Blocks if rate limit would be exceeded.
        
        Returns:
            Time waited in seconds (0 if no wait needed)
        """
        async with self._lock:
            now = datetime.now()
            window_start = now - timedelta(minutes=1)
            
            # Remove old requests outside the window
            while self.requests and self.requests[0] < window_start:
                self.requests.popleft()
            
            waited = 0.0
            if len(self.requests) >= self.rpm:
                # Wait until oldest request expires
                oldest = self.requests[0]
                wait_time = (oldest + timedelta(minutes=1) - now).total_seconds()
                if wait_time > 0:
                    logger.debug("rate_limit_wait", wait_seconds=wait_time)
                    await asyncio.sleep(wait_time)
                    waited = wait_time
                    # Clean up again after waiting
                    now = datetime.now()
                    window_start = now - timedelta(minutes=1)
                    while self.requests and self.requests[0] < window_start:
                        self.requests.popleft()
            
            self.requests.append(datetime.now())
            return waited

    @property
    def current_usage(self) -> int:
        """Get current number of requests in the window."""
        now = datetime.now()
        window_start = now - timedelta(minutes=1)
        return sum(1 for r in self.requests if r >= window_start)


class ResponseParser:
    """Shared JSON response parsing utilities for LLM providers."""

    @staticmethod
    def parse_json_response(text: str) -> dict[str, Any]:
        """Parse JSON from LLM response text.
        
        Handles common response formats:
        - Raw JSON
        - JSON wrapped in markdown code blocks
        - JSON embedded in text
        
        Args:
            text: Raw response text from LLM
            
        Returns:
            Parsed JSON as dict
        """
        text = text.strip()

        # Try to extract from markdown code blocks
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            # Generic code block
            start = text.find("```") + 3
            # Skip language identifier if present
            newline = text.find("\n", start)
            if newline > start and newline - start < 20:
                start = newline + 1
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()

        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in text
        brace_start = text.find("{")
        brace_end = text.rfind("}") + 1
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end])
            except json.JSONDecodeError:
                pass

        # Return fallback response
        logger.warning("json_parse_failed", text_preview=text[:200])
        return {
            "summary": text[:500] if text else "No response received",
            "root_cause": "Could not parse LLM response",
            "classification": "Unknown",
            "severity": "MEDIUM",
            "recommendation": "Manual investigation required",
            "confidence": 0.3,
            "_parse_error": True,
        }

    @staticmethod
    def validate_analysis_result(raw: dict[str, Any]) -> AnalysisResult:
        """Validate and convert raw response to AnalysisResult.
        
        Args:
            raw: Raw parsed JSON response
            
        Returns:
            Validated AnalysisResult
        """
        # Map classification string to enum
        classification_str = raw.get("classification", "Application Bug")
        try:
            classification = FailureClassification(classification_str)
        except ValueError:
            classification_map = {
                "application bug": FailureClassification.APPLICATION_BUG,
                "product bug": FailureClassification.APPLICATION_BUG,
                "test bug": FailureClassification.TEST_BUG,
                "test automation issue": FailureClassification.TEST_BUG,
                "automation bug": FailureClassification.TEST_BUG,
                "flaky": FailureClassification.FLAKY,
                "flaky test": FailureClassification.FLAKY,
                "environment": FailureClassification.ENVIRONMENT,
                "system issue": FailureClassification.ENVIRONMENT,
                "infrastructure": FailureClassification.ENVIRONMENT,
                "data issue": FailureClassification.DATA_ISSUE,
            }
            classification = classification_map.get(
                classification_str.lower(),
                FailureClassification.APPLICATION_BUG,
            )

        # Normalize confidence
        confidence = raw.get("confidence", 0.5)
        if isinstance(confidence, str):
            try:
                confidence = float(confidence.rstrip("%")) / 100 if "%" in confidence else float(confidence)
            except ValueError:
                confidence = 0.5
        confidence = max(0.0, min(1.0, float(confidence)))

        return AnalysisResult(
            summary=raw.get("summary", "Unable to determine failure summary"),
            root_cause=raw.get("root_cause", "Unable to determine root cause"),
            classification=classification,
            recommendation=raw.get("recommendation", "Manual investigation required"),
            confidence=confidence,
        )


class LLMProvider(ABC):
    """Abstract base class for LLM providers.
    
    Defines the interface for LLM integrations used for test failure analysis.
    Includes shared utilities for JSON parsing and response validation.
    """

    # Shared parser instance
    _parser = ResponseParser()

    def parse_response(self, text: str) -> dict[str, Any]:
        """Parse JSON from response text using shared parser."""
        return self._parser.parse_json_response(text)

    def validate_result(self, raw: dict[str, Any]) -> AnalysisResult:
        """Validate raw response into AnalysisResult."""
        return self._parser.validate_analysis_result(raw)

    @abstractmethod
    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a prompt to the LLM and get a response.
        
        Args:
            system_prompt: System instruction prompt
            user_prompt: User prompt with analysis request
            **kwargs: Provider-specific parameters
            
        Returns:
            Parsed JSON response from the LLM
        """
        pass

    async def analyze_failure(
        self,
        test_name: str,
        test_type: str,
        status: str,
        logs: str,
        attributes: list[dict[str, str]] | None = None,
    ) -> AnalysisResult:
        """Analyze a test failure and return structured result.
        
        Default implementation using analyze() method.
        Override in subclass for custom behavior.
        
        Args:
            test_name: Name of the test
            test_type: Type of test item
            status: Test status
            logs: Log content
            attributes: Optional test attributes
            
        Returns:
            AnalysisResult with structured analysis
        """
        from src.llm.prompts import SYSTEM_PROMPT, build_analysis_prompt

        user_prompt = build_analysis_prompt(
            test_name=test_name,
            test_type=test_type,
            status=status,
            logs=logs,
            attributes=attributes,
        )

        try:
            result = await self.analyze(SYSTEM_PROMPT, user_prompt)
            return self.validate_result(result)
        except Exception as e:
            logger.error("analysis_failed", test_name=test_name, error=str(e))
            return AnalysisResult(
                summary=f"Analysis failed for test: {test_name}",
                root_cause=str(e),
                classification=FailureClassification.APPLICATION_BUG,
                recommendation="Manual investigation required",
                confidence=0.0,
            )

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Get the model name being used."""
        pass

    @property
    @abstractmethod
    def max_context_tokens(self) -> int:
        """Get the maximum context window size in tokens."""
        pass


class LLMError(Exception):
    """Base exception for LLM-related errors."""
    pass


class LLMRateLimitError(LLMError):
    """Raised when LLM rate limit is exceeded."""
    pass


class LLMContextLengthError(LLMError):
    """Raised when input exceeds context length."""
    pass


class LLMParsingError(LLMError):
    """Raised when LLM response cannot be parsed."""
    pass
