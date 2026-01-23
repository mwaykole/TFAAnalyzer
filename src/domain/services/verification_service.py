"""Verification service for test re-execution and history analysis.

Provides two verification modes:
1. run_test: Actually execute the test using uv run pytest
2. analyze_history: Analyze pass/fail patterns from ReportPortal + test code
"""

import asyncio
import os
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


class VerifyMode(str, Enum):
    """Verification mode options."""
    NONE = "none"
    RUN_TEST = "run"
    ANALYZE_HISTORY = "analyze-history"


@dataclass
class VerificationResult:
    """Result of test verification."""
    mode: VerifyMode
    status: str  # "passed", "failed", "timeout", "error", "not_run", "flaky", "consistent_fail"
    output: str = ""
    confidence: float = 0.0
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_intermittent(self) -> bool:
        """Check if result indicates intermittent failure."""
        return self.status in ("passed", "flaky")
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "status": self.status,
            "output": self.output[:500] if self.output else "",
            "confidence": self.confidence,
            "reason": self.reason,
            "is_intermittent": self.is_intermittent,
            "details": self.details,
        }


@dataclass
class HistoryPattern:
    """Analysis of test history pattern."""
    total_runs: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    pattern: str = ""  # "alternating", "consistent_fail", "mostly_pass", "inconclusive"
    consecutive_failures: int = 0
    is_flaky: bool = False
    last_status: str = ""
    executions: list[str] = field(default_factory=list)  # ["PASS", "FAIL", "PASS", ...]


@dataclass 
class CodeAnalysis:
    """Analysis of test source code."""
    has_flaky_marker: bool = False
    has_xfail_marker: bool = False
    has_retry_decorator: bool = False
    has_sleep_calls: bool = False
    has_timeout_patterns: bool = False
    decorators: list[str] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    timing_issues: list[str] = field(default_factory=list)


class VerificationService:
    """Service for test verification and history analysis."""
    
    def __init__(
        self,
        test_repo_path: str | None = None,
        timeout: int = 300,
        command: str = "uv run pytest",
    ):
        self.test_repo_path = Path(test_repo_path) if test_repo_path else None
        self.timeout = timeout
        self.command = command
    
    async def verify(
        self,
        test_name: str,
        mode: VerifyMode,
        logs: str = "",
        test_code: str = "",
        history: dict[str, Any] | None = None,
    ) -> VerificationResult:
        """Run verification based on mode.
        
        Args:
            test_name: Name of the test to verify
            mode: Verification mode (run, analyze-history, none)
            logs: Original failure logs (for context)
            test_code: Test source code (for analysis)
            history: ReportPortal history data
            
        Returns:
            VerificationResult with status and details
        """
        if mode == VerifyMode.NONE:
            return VerificationResult(
                mode=mode,
                status="not_run",
                reason="Verification disabled",
            )
        
        if mode == VerifyMode.RUN_TEST:
            return await self.run_test(test_name)
        
        if mode == VerifyMode.ANALYZE_HISTORY:
            return await self.analyze_history(test_name, test_code, history)
        
        return VerificationResult(
            mode=mode,
            status="error",
            reason=f"Unknown verification mode: {mode}",
        )
    
    async def run_test(self, test_name: str) -> VerificationResult:
        """Actually run the test using uv run pytest.
        
        Args:
            test_name: Name of test to execute
            
        Returns:
            VerificationResult with execution outcome
        """
        if not self.test_repo_path or not self.test_repo_path.exists():
            logger.warning("test_repo_not_configured", 
                          path=str(self.test_repo_path))
            return VerificationResult(
                mode=VerifyMode.RUN_TEST,
                status="error",
                reason="Test repository path not configured or doesn't exist",
            )
        
        # Extract function name for -k filter
        func_name = test_name.split("::")[-1].split("[")[0] if "::" in test_name else test_name.split("[")[0]
        
        logger.info("running_test_verification",
                    test_name=func_name[:50],
                    repo=str(self.test_repo_path),
                    timeout=self.timeout)
        
        try:
            # Run in thread pool to not block event loop
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["uv", "run", "pytest", "-k", func_name, "-v", "--tb=short", "-x"],
                    cwd=self.test_repo_path,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env={**os.environ},
                )
            )
            
            if result.returncode == 0:
                logger.info("test_verification_passed", test_name=func_name[:50])
                return VerificationResult(
                    mode=VerifyMode.RUN_TEST,
                    status="passed",
                    output=result.stdout,
                    confidence=0.95,
                    reason="Test passed on re-run, confirming intermittent behavior",
                    details={
                        "exit_code": 0,
                        "passed_on_rerun": True,
                    }
                )
            else:
                logger.info("test_verification_failed", 
                           test_name=func_name[:50],
                           exit_code=result.returncode)
                return VerificationResult(
                    mode=VerifyMode.RUN_TEST,
                    status="failed",
                    output=result.stdout + "\n" + result.stderr,
                    confidence=0.0,
                    reason="Test failed on re-run, confirming consistent failure",
                    details={
                        "exit_code": result.returncode,
                        "passed_on_rerun": False,
                    }
                )
                
        except subprocess.TimeoutExpired:
            logger.warning("test_verification_timeout",
                          test_name=func_name[:50],
                          timeout=self.timeout)
            return VerificationResult(
                mode=VerifyMode.RUN_TEST,
                status="timeout",
                output=f"Test execution timed out after {self.timeout}s",
                reason=f"Test did not complete within {self.timeout}s timeout",
            )
        except Exception as e:
            logger.error("test_verification_error",
                        test_name=func_name[:50],
                        error=str(e))
            return VerificationResult(
                mode=VerifyMode.RUN_TEST,
                status="error",
                output=str(e),
                reason=f"Error running test: {e}",
            )
    
    async def analyze_history(
        self,
        test_name: str,
        test_code: str = "",
        history: dict[str, Any] | None = None,
    ) -> VerificationResult:
        """Analyze test history pattern and code for flakiness indicators.
        
        Combines:
        1. ReportPortal history - pass/fail pattern across launches
        2. Test code analysis - decorators, timing issues, fixtures
        
        Args:
            test_name: Name of test
            test_code: Test source code
            history: ReportPortal history data
            
        Returns:
            VerificationResult with analysis
        """
        logger.info("analyzing_test_history",
                    test_name=test_name[:50],
                    has_code=bool(test_code),
                    has_history=bool(history))
        
        # Analyze RP history pattern
        history_pattern = self._analyze_history_pattern(history or {})
        
        # Analyze test code
        code_analysis = self._analyze_test_code(test_code)
        
        # Combine analyses
        result = self._combine_analyses(test_name, history_pattern, code_analysis)
        
        logger.info("history_analysis_complete",
                    test_name=test_name[:30],
                    status=result.status,
                    confidence=f"{result.confidence:.0%}",
                    pattern=history_pattern.pattern)
        
        return result
    
    def _analyze_history_pattern(self, history: dict[str, Any]) -> HistoryPattern:
        """Analyze pass/fail pattern from history data."""
        pattern = HistoryPattern()
        
        if not history:
            return pattern
        
        pattern.total_runs = history.get("total_runs", 0)
        pattern.passed = history.get("passed", 0)
        pattern.failed = history.get("failed", 0)
        pattern.pass_rate = history.get("pass_rate", 0) / 100.0  # Convert from percentage
        pattern.is_flaky = history.get("is_flaky", False)
        pattern.last_status = history.get("last_status", "")
        pattern.consecutive_failures = history.get("consecutive_failures", 0)
        
        # Get execution sequence
        executions = history.get("executions", [])
        pattern.executions = [e.get("status", "UNKNOWN") for e in executions]
        
        # Determine pattern type
        if pattern.total_runs < 2:
            pattern.pattern = "insufficient_data"
        elif pattern.is_flaky and self._is_alternating(pattern.executions):
            pattern.pattern = "alternating"
        elif pattern.consecutive_failures >= 3:
            pattern.pattern = "consistent_fail"
        elif pattern.pass_rate >= 0.9:
            pattern.pattern = "mostly_pass"
        elif pattern.is_flaky:
            pattern.pattern = "flaky"
        else:
            pattern.pattern = "inconclusive"
        
        return pattern
    
    def _is_alternating(self, executions: list[str]) -> bool:
        """Check if executions show alternating pattern."""
        if len(executions) < 4:
            return False
        
        # Count transitions
        transitions = 0
        for i in range(1, len(executions)):
            if executions[i] != executions[i-1]:
                transitions += 1
        
        # High transition rate indicates alternating
        return transitions >= len(executions) * 0.5
    
    def _analyze_test_code(self, test_code: str) -> CodeAnalysis:
        """Analyze test source code for flakiness indicators."""
        analysis = CodeAnalysis()
        
        if not test_code:
            return analysis
        
        # Check for flaky markers
        analysis.has_flaky_marker = bool(re.search(r"@pytest\.mark\.flaky", test_code, re.IGNORECASE))
        analysis.has_xfail_marker = bool(re.search(r"@pytest\.mark\.xfail", test_code, re.IGNORECASE))
        analysis.has_retry_decorator = bool(re.search(r"@retry|@tenacity\.retry", test_code, re.IGNORECASE))
        
        # Check for timing issues
        sleep_matches = re.findall(r"(?:time\.)?sleep\s*\(\s*(\d+)", test_code)
        if sleep_matches:
            analysis.has_sleep_calls = True
            for match in sleep_matches:
                analysis.timing_issues.append(f"sleep({match})")
        
        wait_matches = re.findall(r"wait.*?timeout\s*=\s*(\d+)", test_code, re.IGNORECASE)
        if wait_matches:
            analysis.has_timeout_patterns = True
            for match in wait_matches:
                analysis.timing_issues.append(f"wait(timeout={match})")
        
        # Extract decorators
        decorator_matches = re.findall(r"@(\w+(?:\.\w+)*(?:\([^)]*\))?)", test_code)
        analysis.decorators = decorator_matches[:10]
        
        # Extract fixtures from function signature
        fixture_match = re.search(r"def\s+test_\w+\s*\(([^)]+)\)", test_code)
        if fixture_match:
            fixtures = [f.strip().split(":")[0].strip() for f in fixture_match.group(1).split(",")]
            analysis.fixtures = [f for f in fixtures if f and f != "self"]
        
        return analysis
    
    def _combine_analyses(
        self,
        test_name: str,
        history: HistoryPattern,
        code: CodeAnalysis,
    ) -> VerificationResult:
        """Combine history and code analysis into final result."""
        details = {
            "history": {
                "total_runs": history.total_runs,
                "passed": history.passed,
                "failed": history.failed,
                "pass_rate": f"{history.pass_rate:.0%}",
                "pattern": history.pattern,
                "is_flaky": history.is_flaky,
                "last_status": history.last_status,
                "consecutive_failures": history.consecutive_failures,
            },
            "code": {
                "has_flaky_marker": code.has_flaky_marker,
                "has_xfail_marker": code.has_xfail_marker,
                "has_timing_issues": bool(code.timing_issues),
                "timing_issues": code.timing_issues,
                "decorators": code.decorators[:5],
                "fixtures": code.fixtures[:5],
            }
        }
        
        # Decision logic
        if history.pattern == "alternating":
            return VerificationResult(
                mode=VerifyMode.ANALYZE_HISTORY,
                status="flaky",
                confidence=0.90,
                reason=f"Alternating PASS/FAIL pattern detected ({history.pass_rate:.0%} pass rate)",
                details=details,
            )
        
        if history.pattern == "consistent_fail":
            return VerificationResult(
                mode=VerifyMode.ANALYZE_HISTORY,
                status="consistent_fail",
                confidence=0.88,
                reason=f"Consistent failures ({history.consecutive_failures} consecutive failures)",
                details=details,
            )
        
        if history.is_flaky or (code.has_flaky_marker and history.pass_rate < 0.95):
            confidence = 0.85
            reasons = []
            if history.is_flaky:
                reasons.append(f"history shows flakiness ({history.pass_rate:.0%} pass rate)")
            if code.has_flaky_marker:
                reasons.append("code has @pytest.mark.flaky")
            if code.timing_issues:
                reasons.append(f"timing patterns: {', '.join(code.timing_issues[:2])}")
            
            return VerificationResult(
                mode=VerifyMode.ANALYZE_HISTORY,
                status="flaky",
                confidence=confidence,
                reason=f"Likely flaky: {'; '.join(reasons)}",
                details=details,
            )
        
        if history.pattern == "mostly_pass" and history.failed <= 1:
            return VerificationResult(
                mode=VerifyMode.ANALYZE_HISTORY,
                status="rare_failure",
                confidence=0.70,
                reason=f"Rare failure: {history.pass_rate:.0%} pass rate with only {history.failed} failure(s)",
                details=details,
            )
        
        if code.timing_issues and not code.has_flaky_marker:
            return VerificationResult(
                mode=VerifyMode.ANALYZE_HISTORY,
                status="needs_investigation",
                confidence=0.60,
                reason=f"Timing issues detected ({', '.join(code.timing_issues[:2])}) but no flaky marker",
                details=details,
            )
        
        # Inconclusive
        return VerificationResult(
            mode=VerifyMode.ANALYZE_HISTORY,
            status="inconclusive",
            confidence=0.50,
            reason="Insufficient data for pattern detection. Consider using --verify to run test.",
            details=details,
        )
