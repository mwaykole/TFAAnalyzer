"""Anthropic Claude LLM provider with cost optimization."""

from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from src.llm.base import (
    LLMContextLengthError,
    LLMError,
    LLMParsingError,
    LLMProvider,
    LLMRateLimitError,
    RateLimiter,
)
from src.infrastructure.reportportal.models import AnalysisResult, FailureClassification
from src.utils.logging import get_logger
from src.utils.retry import RetryConfig, async_retry

logger = get_logger(__name__)

# Model pricing (per 1M tokens) and context windows
MODEL_INFO = {
    # Haiku - Fast & cheap ($0.25/1M input, $1.25/1M output)
    "claude-3-5-haiku-20241022": {"context": 200000, "input_cost": 0.25, "output_cost": 1.25},
    "claude-3-haiku-20240307": {"context": 200000, "input_cost": 0.25, "output_cost": 1.25},
    # Sonnet - Balanced ($3/1M input, $15/1M output)  
    "claude-sonnet-4-20250514": {"context": 200000, "input_cost": 3.0, "output_cost": 15.0},
    "claude-3-5-sonnet-20241022": {"context": 200000, "input_cost": 3.0, "output_cost": 15.0},
    # Opus - Most capable ($15/1M input, $75/1M output)
    "claude-3-opus-20240229": {"context": 200000, "input_cost": 15.0, "output_cost": 75.0},
}

# Default to Haiku for cost savings (12x cheaper than Sonnet!)
DEFAULT_MODEL = "claude-3-5-haiku-20241022"
FALLBACK_MODEL = "claude-sonnet-4-20250514"  # Use Sonnet for complex cases


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider with cost optimization.
    
    Cost reduction strategies:
    1. Uses Haiku by default (12x cheaper than Sonnet)
    2. Smart log truncation to reduce input tokens
    3. Prompt caching for repeated system prompts
    4. Tiered model selection based on complexity
    5. Reduced max_tokens for typical responses
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        max_tokens: int = 1024,  # Reduced from 4096 - most analyses are <500 tokens
        temperature: float = 0.1,
        retry_config: RetryConfig | None = None,
        requests_per_minute: int = 50,
        use_prompt_caching: bool = True,
        auto_upgrade_model: bool = True,  # Auto-upgrade to Sonnet for complex cases
    ):
        """Initialize the Anthropic provider.

        Args:
            api_key: Anthropic API key
            model: Model identifier (default: haiku for cost savings)
            max_tokens: Maximum response tokens (reduced default)
            temperature: Response temperature (0.0-1.0)
            retry_config: Retry configuration
            requests_per_minute: Rate limit for API calls
            use_prompt_caching: Enable prompt caching (saves ~90% on cached prompts)
            auto_upgrade_model: Auto-upgrade to Sonnet for complex analyses
        """
        self.api_key = api_key
        self._model = model
        self._base_model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.use_prompt_caching = use_prompt_caching
        self.auto_upgrade_model = auto_upgrade_model
        self.retry_config = retry_config or RetryConfig(
            max_attempts=3,
            retryable_exceptions=(
                anthropic.RateLimitError,
                anthropic.APIConnectionError,
                anthropic.InternalServerError,
            ),
        )
        self._client = AsyncAnthropic(api_key=api_key)
        self._rate_limiter = RateLimiter(requests_per_minute)
        
        # Track usage for cost monitoring
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._request_count = 0

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def max_context_tokens(self) -> int:
        return MODEL_INFO.get(self._model, {}).get("context", 200000)

    @property
    def estimated_cost(self) -> float:
        """Get estimated cost in USD based on usage."""
        info = MODEL_INFO.get(self._model, {"input_cost": 3.0, "output_cost": 15.0})
        input_cost = (self._total_input_tokens / 1_000_000) * info["input_cost"]
        output_cost = (self._total_output_tokens / 1_000_000) * info["output_cost"]
        return input_cost + output_cost

    def get_usage_stats(self) -> dict[str, Any]:
        """Get usage statistics."""
        return {
            "model": self._model,
            "requests": self._request_count,
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
            "estimated_cost_usd": round(self.estimated_cost, 4),
        }

    async def close(self) -> None:
        """Close the client connection."""
        if self._request_count > 0:
            logger.info("anthropic_session_stats", **self.get_usage_stats())
        await self._client.close()

    def _should_upgrade_model(self, logs: str) -> bool:
        """Determine if we should use a more capable model.
        
        Args:
            logs: Log content to analyze
            
        Returns:
            True if should upgrade to Sonnet
        """
        if not self.auto_upgrade_model:
            return False
            
        # Upgrade for very long logs (complex issues)
        if len(logs) > 10000:
            return True
            
        # Upgrade if logs contain complex patterns
        complex_indicators = [
            "stack trace",
            "multiple errors",
            "caused by:",
            "suppressed:",
            "nested exception",
        ]
        log_lower = logs.lower()
        return sum(1 for ind in complex_indicators if ind in log_lower) >= 2

    def _truncate_logs_smart(self, logs: str, max_chars: int = 6000) -> str:
        """Smart log truncation to reduce tokens while preserving important info.
        
        Prioritizes:
        1. Error messages and stack traces
        2. Beginning and end of logs
        3. Lines containing keywords
        
        Args:
            logs: Full log content
            max_chars: Maximum characters to keep
            
        Returns:
            Truncated logs
        """
        if len(logs) <= max_chars:
            return logs
            
        lines = logs.split('\n')
        
        # Priority keywords for important lines
        priority_keywords = [
            'error', 'exception', 'failed', 'assert', 'timeout',
            'traceback', 'caused by', 'at ', 'raise', 'critical',
            'fatal', 'panic', 'crash', 'oom', 'killed',
        ]
        
        # Score each line
        scored_lines = []
        for i, line in enumerate(lines):
            line_lower = line.lower()
            score = 0
            
            # Position bonus (first and last lines are important)
            if i < 10:
                score += 3
            if i >= len(lines) - 10:
                score += 3
                
            # Keyword bonus
            for kw in priority_keywords:
                if kw in line_lower:
                    score += 2
                    break
                    
            # Stack trace indicators
            if line.strip().startswith('at ') or 'File "' in line:
                score += 1
                
            scored_lines.append((i, score, line))
        
        # Sort by score (descending) then by position
        scored_lines.sort(key=lambda x: (-x[1], x[0]))
        
        # Select lines up to max_chars
        selected = []
        total_chars = 0
        for i, score, line in scored_lines:
            if total_chars + len(line) + 1 > max_chars:
                break
            selected.append((i, line))
            total_chars += len(line) + 1
        
        # Sort back by original position
        selected.sort(key=lambda x: x[0])
        
        # Build result with truncation indicators
        result_lines = []
        last_idx = -1
        for idx, line in selected:
            if last_idx >= 0 and idx > last_idx + 1:
                result_lines.append(f"... ({idx - last_idx - 1} lines omitted) ...")
            result_lines.append(line)
            last_idx = idx
            
        return '\n'.join(result_lines)

    @async_retry()
    async def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        use_cache: bool = True,
    ) -> tuple[str, dict[str, int]]:
        """Make API call to Anthropic with prompt caching.

        Args:
            system_prompt: System instruction
            user_prompt: User message
            use_cache: Whether to use prompt caching

        Returns:
            Tuple of (response_text, usage_stats)
        """
        await self._rate_limiter.acquire()
        
        try:
            # Build messages with optional caching
            if self.use_prompt_caching and use_cache:
                # Use cache_control for system prompt (saves ~90% on repeated calls)
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ],
                    messages=[
                        {"role": "user", "content": user_prompt},
                    ],
                )
            else:
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": user_prompt},
                    ],
                )

            # Track usage
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            self._total_input_tokens += usage["input_tokens"]
            self._total_output_tokens += usage["output_tokens"]
            self._request_count += 1

            if response.content and len(response.content) > 0:
                return response.content[0].text, usage

            raise LLMError("Empty response from Claude")

        except anthropic.RateLimitError as e:
            logger.error("rate_limit_exceeded", error=str(e))
            raise LLMRateLimitError(str(e)) from e
        except anthropic.BadRequestError as e:
            if "context_length" in str(e).lower():
                raise LLMContextLengthError(str(e)) from e
            raise LLMError(str(e)) from e

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a prompt and get parsed JSON response.

        Args:
            system_prompt: System instruction
            user_prompt: User prompt
            **kwargs: Additional parameters
                - truncate_logs: Whether to smart-truncate logs (default: True)
                - max_log_chars: Max chars for logs (default: 6000)

        Returns:
            Parsed JSON response
        """
        # Apply smart truncation if logs are in the prompt
        truncate = kwargs.get("truncate_logs", True)
        max_chars = kwargs.get("max_log_chars", 6000)
        
        if truncate and "```" in user_prompt:
            # Find and truncate log sections
            parts = user_prompt.split("```")
            for i in range(1, len(parts), 2):  # Process code blocks
                if len(parts[i]) > max_chars:
                    parts[i] = self._truncate_logs_smart(parts[i], max_chars)
            user_prompt = "```".join(parts)
        
        # Check if we should upgrade model for this request
        original_model = self._model
        if self._should_upgrade_model(user_prompt):
            self._model = FALLBACK_MODEL
            logger.debug("model_upgraded", from_model=original_model, to_model=self._model)
        
        try:
            response_text, usage = await self._call_api(system_prompt, user_prompt)
            result = self.parse_response(response_text)
            result["_usage"] = usage
            return result
        finally:
            self._model = original_model

    async def analyze_failure(
        self,
        test_name: str,
        test_type: str,
        status: str,
        logs: str,
        attributes: list[dict[str, str]] | None = None,
    ) -> AnalysisResult:
        """Analyze a test failure with cost-optimized approach.

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

        # Smart truncate logs before building prompt
        truncated_logs = self._truncate_logs_smart(logs, max_chars=6000)
        
        user_prompt = build_analysis_prompt(
            test_name=test_name,
            test_type=test_type,
            status=status,
            logs=truncated_logs,
            attributes=attributes,
        )

        logger.debug(
            "analyzing_failure",
            test_name=test_name,
            original_log_length=len(logs),
            truncated_log_length=len(truncated_logs),
        )

        try:
            result = await self.analyze(SYSTEM_PROMPT, user_prompt, truncate_logs=False)
            return self.validate_result(result)
        except LLMContextLengthError:
            logger.warning(
                "context_length_exceeded",
                test_name=test_name,
                log_length=len(logs),
            )
            raise
        except LLMParsingError as e:
            logger.error(
                "analysis_parsing_failed",
                test_name=test_name,
                error=str(e),
            )
            return self._create_fallback_result(test_name, str(e))

    def _create_fallback_result(
        self,
        test_name: str,
        error: str,
    ) -> AnalysisResult:
        """Create a fallback result when analysis fails."""
        return AnalysisResult(
            summary=f"Analysis failed for test: {test_name}",
            root_cause=f"Unable to analyze due to error: {error}",
            classification=FailureClassification.APPLICATION_BUG,
            recommendation="Manual investigation required due to analysis failure",
            confidence=0.0,
        )


class CostOptimizedAnalyzer:
    """Higher-level analyzer with maximum cost optimization.
    
    Strategies:
    1. Pre-filter with rule engine (skip LLM for obvious cases)
    2. Batch similar failures together
    3. Use Haiku for simple cases, Sonnet for complex
    4. Cache aggressively
    """
    
    def __init__(self, provider: AnthropicProvider):
        self.provider = provider
        self._skipped_by_rules = 0
        self._analyzed_by_llm = 0
    
    async def analyze_with_prefilter(
        self,
        test_name: str,
        logs: str,
        component: str = "",
        classification_engine = None,
    ) -> dict[str, Any]:
        """Analyze with pre-filtering to skip obvious cases.
        
        Args:
            test_name: Name of the test
            logs: Log content
            component: Component name
            classification_engine: Rule-based classifier
            
        Returns:
            Analysis result (either from rules or LLM)
        """
        # Try rule-based classification first
        if classification_engine:
            pre_result = classification_engine.classify(
                error_logs=logs,
                test_name=test_name,
                component=component,
            )
            
            # If high confidence from rules, skip LLM entirely
            if pre_result.confidence >= 0.85:
                self._skipped_by_rules += 1
                return {
                    "summary": pre_result.reasoning,
                    "root_cause": f"Pattern matched: {pre_result.matched_patterns[0]['description'] if pre_result.matched_patterns else 'Rule match'}",
                    "classification": pre_result.classification,
                    "severity": pre_result.severity,
                    "confidence": pre_result.confidence,
                    "recommendation": pre_result.suggested_fix or "See matched pattern",
                    "_source": "rule_engine",
                }
        
        # Fall back to LLM
        self._analyzed_by_llm += 1
        system_prompt = _get_compact_system_prompt()
        user_prompt = f"""Test: {test_name}
Component: {component}
Logs:
```
{logs[:4000]}
```
JSON:"""
        
        return await self.provider.analyze(system_prompt, user_prompt)
    
    def get_stats(self) -> dict[str, Any]:
        """Get analyzer statistics."""
        total = self._skipped_by_rules + self._analyzed_by_llm
        return {
            "total_analyses": total,
            "skipped_by_rules": self._skipped_by_rules,
            "analyzed_by_llm": self._analyzed_by_llm,
            "rule_skip_rate": f"{(self._skipped_by_rules / total * 100):.1f}%" if total > 0 else "0%",
            **self.provider.get_usage_stats(),
        }


def _get_compact_system_prompt() -> str:
    """Get a compact system prompt to reduce input tokens."""
    return """Classify test failure as JSON:
{"summary":"brief","root_cause":"why","classification":"Product Bug|Test Automation Issue|Flaky Test","severity":"HIGH|MEDIUM|LOW","confidence":0.0-1.0,"recommendation":"fix"}

Rules:
- TimeoutError → Test Automation Issue
- Version mismatch/crash → Product Bug
- Network/S3 auth → Flaky Test
JSON only:"""
