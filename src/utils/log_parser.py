"""Structured log parser for extracting error information from test logs.

Provides intelligent extraction of:
- Exception types and messages
- Stack traces with file/line info
- Root cause identification (first error vs cascading failures)
- Error context and severity indicators
"""

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StackFrame:
    """A single frame in a stack trace."""
    
    file_path: str
    line_number: int | None
    function_name: str
    code_context: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "line": self.line_number,
            "function": self.function_name,
            "context": self.code_context,
        }


@dataclass
class ExtractedError:
    """A single extracted error from logs."""
    
    exception_type: str
    message: str
    stack_frames: list[StackFrame] = field(default_factory=list)
    full_traceback: str = ""
    line_number: int | None = None  # Line in original logs
    is_root_cause: bool = False
    severity: str = "MEDIUM"  # CRITICAL, HIGH, MEDIUM, LOW
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "exception_type": self.exception_type,
            "message": self.message,
            "stack_frames": [f.to_dict() for f in self.stack_frames],
            "is_root_cause": self.is_root_cause,
            "severity": self.severity,
        }
    
    @property
    def short_summary(self) -> str:
        """Get a short summary of the error."""
        msg = self.message[:100] + "..." if len(self.message) > 100 else self.message
        return f"{self.exception_type}: {msg}"


@dataclass
class ParsedLogs:
    """Result of parsing logs."""
    
    errors: list[ExtractedError] = field(default_factory=list)
    root_cause: ExtractedError | None = None
    error_count: int = 0
    has_timeout: bool = False
    has_assertion_error: bool = False
    has_connection_error: bool = False
    has_resource_error: bool = False
    key_indicators: list[str] = field(default_factory=list)
    structured_summary: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "error_count": self.error_count,
            "root_cause": self.root_cause.to_dict() if self.root_cause else None,
            "errors": [e.to_dict() for e in self.errors[:5]],  # Top 5
            "has_timeout": self.has_timeout,
            "has_assertion_error": self.has_assertion_error,
            "has_connection_error": self.has_connection_error,
            "has_resource_error": self.has_resource_error,
            "key_indicators": self.key_indicators,
        }


class LogParser:
    """Parse test logs to extract structured error information."""
    
    # Python exception patterns
    PYTHON_EXCEPTION_PATTERN = re.compile(
        r'^(\w+(?:\.\w+)*(?:Error|Exception|Failure|Warning)):\s*(.+?)$',
        re.MULTILINE
    )
    
    # Python traceback patterns
    PYTHON_TRACEBACK_START = re.compile(r'Traceback \(most recent call last\):')
    PYTHON_TRACEBACK_FILE = re.compile(
        r'^\s*File "([^"]+)", line (\d+), in (\w+)',
        re.MULTILINE
    )
    
    # Java/Kubernetes exception patterns
    JAVA_EXCEPTION_PATTERN = re.compile(
        r'^([\w.]+(?:Exception|Error|Throwable)):\s*(.+?)$',
        re.MULTILINE
    )
    
    # Kubernetes/OpenShift error patterns
    K8S_ERROR_PATTERNS = [
        (re.compile(r'(CrashLoopBackOff)', re.IGNORECASE), "Pod crashing repeatedly"),
        (re.compile(r'(OOMKilled)', re.IGNORECASE), "Out of memory"),
        (re.compile(r'(ImagePullBackOff|ErrImagePull)', re.IGNORECASE), "Image pull failure"),
        (re.compile(r'(FailedScheduling)', re.IGNORECASE), "Pod scheduling failure"),
        (re.compile(r'(CreateContainerError)', re.IGNORECASE), "Container creation failed"),
        (re.compile(r'(PersistentVolumeClaim.*Pending)', re.IGNORECASE), "Storage issue"),
    ]
    
    # Severity indicators
    CRITICAL_KEYWORDS = [
        'fatal', 'panic', 'crash', 'oomkilled', 'segmentation fault',
        'data loss', 'corruption', 'security',
    ]
    HIGH_KEYWORDS = [
        'failed', 'error', 'exception', 'timeout', 'refused',
        'denied', 'unauthorized', 'crashloopbackoff',
    ]
    
    # Classification hints
    AUTOMATION_INDICATORS = [
        'timeouterror', 'timeoutexpirederror', 'timeoutsampler',
        'assertionerror', 'nosuchelementexception', 'staleelement',
        'fixture', 'setup', 'teardown', 'wait_timeout',
    ]
    PRODUCT_INDICATORS = [
        'internalservererror', 'nullpointer', 'segmentationfault',
        'crashloop', 'oomkilled', 'version.*mismatch', 'not.*ready',
    ]
    INFRA_INDICATORS = [
        's3', 'minio', 'connection.*refused', 'connection.*reset',
        'dns.*resolution', 'network.*unreachable', 'imagepull',
        'certificate.*expired', 'accessdenied', 'rate.*limit',
    ]
    
    def parse(self, logs: str) -> ParsedLogs:
        """Parse logs and extract structured error information.
        
        Args:
            logs: Raw log content
            
        Returns:
            ParsedLogs with extracted errors and metadata
        """
        result = ParsedLogs()
        
        if not logs or len(logs.strip()) == 0:
            return result
        
        logs_lower = logs.lower()
        
        # Extract Python exceptions
        python_errors = self._extract_python_errors(logs)
        result.errors.extend(python_errors)
        
        # Extract Kubernetes/OpenShift errors
        k8s_errors = self._extract_k8s_errors(logs)
        result.errors.extend(k8s_errors)
        
        # Extract generic errors
        generic_errors = self._extract_generic_errors(logs)
        for err in generic_errors:
            # Don't add duplicates
            if not any(e.exception_type == err.exception_type and e.message == err.message 
                      for e in result.errors):
                result.errors.append(err)
        
        # Identify root cause (first significant error)
        result.root_cause = self._identify_root_cause(result.errors)
        result.error_count = len(result.errors)
        
        # Set classification hints
        result.has_timeout = 'timeout' in logs_lower
        result.has_assertion_error = 'assertionerror' in logs_lower or 'assertion failed' in logs_lower
        result.has_connection_error = any(kw in logs_lower for kw in 
            ['connection refused', 'connection reset', 'connection timed out'])
        result.has_resource_error = any(kw in logs_lower for kw in 
            ['oomkilled', 'out of memory', 'insufficient cpu', 'insufficient memory'])
        
        # Extract key indicators for classification
        result.key_indicators = self._extract_key_indicators(logs_lower)
        
        # Build structured summary
        result.structured_summary = self._build_summary(result)
        
        return result
    
    def _extract_python_errors(self, logs: str) -> list[ExtractedError]:
        """Extract Python exception information."""
        errors = []
        
        # Find all tracebacks
        traceback_blocks = self._split_tracebacks(logs)
        
        for block in traceback_blocks:
            # Find the exception line (usually last line of traceback)
            match = self.PYTHON_EXCEPTION_PATTERN.search(block)
            if match:
                exception_type = match.group(1)
                message = match.group(2).strip()
                
                # Extract stack frames
                frames = []
                for frame_match in self.PYTHON_TRACEBACK_FILE.finditer(block):
                    frames.append(StackFrame(
                        file_path=frame_match.group(1),
                        line_number=int(frame_match.group(2)),
                        function_name=frame_match.group(3),
                    ))
                
                error = ExtractedError(
                    exception_type=exception_type,
                    message=message,
                    stack_frames=frames,
                    full_traceback=block,
                    severity=self._determine_severity(exception_type, message),
                )
                errors.append(error)
        
        return errors
    
    def _split_tracebacks(self, logs: str) -> list[str]:
        """Split logs into individual traceback blocks."""
        blocks = []
        lines = logs.split('\n')
        current_block = []
        in_traceback = False
        
        for line in lines:
            if self.PYTHON_TRACEBACK_START.search(line):
                if current_block and in_traceback:
                    blocks.append('\n'.join(current_block))
                current_block = [line]
                in_traceback = True
            elif in_traceback:
                current_block.append(line)
                # Check if we've reached the exception line
                if self.PYTHON_EXCEPTION_PATTERN.match(line):
                    blocks.append('\n'.join(current_block))
                    current_block = []
                    in_traceback = False
        
        # Handle remaining block
        if current_block and in_traceback:
            blocks.append('\n'.join(current_block))
        
        return blocks
    
    def _extract_k8s_errors(self, logs: str) -> list[ExtractedError]:
        """Extract Kubernetes/OpenShift errors."""
        errors = []
        
        for pattern, description in self.K8S_ERROR_PATTERNS:
            matches = pattern.findall(logs)
            for match in matches:
                error = ExtractedError(
                    exception_type=match if isinstance(match, str) else match[0],
                    message=description,
                    severity="HIGH",
                )
                errors.append(error)
        
        return errors
    
    def _extract_generic_errors(self, logs: str) -> list[ExtractedError]:
        """Extract generic error patterns."""
        errors = []
        
        # Generic error line patterns
        error_patterns = [
            # Error: message
            (re.compile(r'^(?:ERROR|Error|error)[:\s]+(.+)$', re.MULTILINE), "Error"),
            # FAILED: message  
            (re.compile(r'^(?:FAILED|Failed)[:\s]+(.+)$', re.MULTILINE), "Failure"),
            # AssertionError
            (re.compile(r'(AssertionError[:\s].+)$', re.MULTILINE), "AssertionError"),
        ]
        
        for pattern, error_type in error_patterns:
            matches = pattern.findall(logs)
            for match in matches[:3]:  # Limit to first 3
                msg = match[:200].strip()
                if msg and len(msg) > 5:
                    errors.append(ExtractedError(
                        exception_type=error_type,
                        message=msg,
                        severity=self._determine_severity(error_type, msg),
                    ))
        
        return errors
    
    def _identify_root_cause(self, errors: list[ExtractedError]) -> ExtractedError | None:
        """Identify the root cause error (first significant error)."""
        if not errors:
            return None
        
        # Prefer errors with stack traces (more informative)
        errors_with_trace = [e for e in errors if e.stack_frames]
        if errors_with_trace:
            # First error with stack trace is likely root cause
            root = errors_with_trace[0]
            root.is_root_cause = True
            return root
        
        # Otherwise, first error
        errors[0].is_root_cause = True
        return errors[0]
    
    def _determine_severity(self, exception_type: str, message: str) -> str:
        """Determine error severity."""
        combined = f"{exception_type} {message}".lower()
        
        if any(kw in combined for kw in self.CRITICAL_KEYWORDS):
            return "CRITICAL"
        if any(kw in combined for kw in self.HIGH_KEYWORDS):
            return "HIGH"
        return "MEDIUM"
    
    def _extract_key_indicators(self, logs_lower: str) -> list[str]:
        """Extract key classification indicators."""
        indicators = []
        
        # Automation indicators
        for ind in self.AUTOMATION_INDICATORS:
            if ind in logs_lower:
                indicators.append(f"automation:{ind}")
        
        # Product indicators
        for ind in self.PRODUCT_INDICATORS:
            if re.search(ind, logs_lower):
                indicators.append(f"product:{ind}")
        
        # Infrastructure indicators
        for ind in self.INFRA_INDICATORS:
            if re.search(ind, logs_lower):
                indicators.append(f"infra:{ind}")
        
        return indicators[:10]  # Limit to top 10
    
    def _build_summary(self, result: ParsedLogs) -> str:
        """Build a structured summary for LLM analysis."""
        parts = []
        
        if result.root_cause:
            parts.append(f"ROOT CAUSE: {result.root_cause.short_summary}")
            if result.root_cause.stack_frames:
                top_frame = result.root_cause.stack_frames[-1]  # Most recent call
                parts.append(f"  at {top_frame.file_path}:{top_frame.line_number} in {top_frame.function_name}")
        
        if result.error_count > 1:
            parts.append(f"\nADDITIONAL ERRORS ({result.error_count - 1}):")
            for err in result.errors[1:4]:  # Show 3 more
                parts.append(f"  - {err.short_summary}")
        
        indicators = []
        if result.has_timeout:
            indicators.append("TIMEOUT")
        if result.has_assertion_error:
            indicators.append("ASSERTION_FAILURE")
        if result.has_connection_error:
            indicators.append("CONNECTION_ERROR")
        if result.has_resource_error:
            indicators.append("RESOURCE_ERROR")
        
        if indicators:
            parts.append(f"\nINDICATORS: {', '.join(indicators)}")
        
        return '\n'.join(parts)
    
    def get_classification_hints(self, parsed: ParsedLogs) -> dict[str, float]:
        """Get classification hints with confidence scores.
        
        Returns dict with scores for each classification type.
        """
        scores = {
            "product_bug": 0.0,
            "automation_bug": 0.0,
            "infrastructure": 0.0,
            "flaky": 0.0,
        }
        
        # Analyze indicators
        for ind in parsed.key_indicators:
            if ind.startswith("automation:"):
                scores["automation_bug"] += 0.15
            elif ind.startswith("product:"):
                scores["product_bug"] += 0.15
            elif ind.startswith("infra:"):
                scores["infrastructure"] += 0.15
        
        # Analyze root cause
        if parsed.root_cause:
            exc_type = parsed.root_cause.exception_type.lower()
            msg = parsed.root_cause.message.lower()
            
            # Timeout errors are usually automation issues
            if 'timeout' in exc_type:
                scores["automation_bug"] += 0.3
            
            # Assertion errors need context
            if 'assertion' in exc_type:
                if 'expected' in msg and 'actual' in msg:
                    scores["product_bug"] += 0.2  # Could be real bug
                else:
                    scores["automation_bug"] += 0.2  # Likely bad assertion
            
            # Connection/auth errors are infrastructure
            if any(kw in exc_type + msg for kw in ['connection', 's3', 'auth', 'denied']):
                scores["infrastructure"] += 0.25
            
            # Crash/OOM are product bugs
            if any(kw in exc_type + msg for kw in ['crash', 'oom', 'killed', 'segfault']):
                scores["product_bug"] += 0.3
        
        # Normalize
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}
        
        return scores


# Singleton instance
_parser: LogParser | None = None


def get_parser() -> LogParser:
    """Get or create the log parser singleton."""
    global _parser
    if _parser is None:
        _parser = LogParser()
    return _parser


def parse_logs(logs: str) -> ParsedLogs:
    """Convenience function to parse logs."""
    return get_parser().parse(logs)
