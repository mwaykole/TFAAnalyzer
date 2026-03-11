"""Classification service implementing core classification logic.

Single Responsibility: Only handles classification logic.
Dependency Inversion: Depends on abstractions (interfaces), not concretions.
"""

import re
from typing import Any

from src.domain.entities.classification import Classification, FailureCategory, Severity
from src.domain.entities.evidence import Evidence
from src.domain.interfaces.log_parser import LogParser, ParsedLogs


# Definitive patterns with confidence scores
DEFINITIVE_PATTERNS: list[tuple[str, str, str, float]] = [
    # --- KServe / RHOAI-specific patterns (checked first, higher specificity) ---
    (r"LeaderWorkerSet.*not.*found|no matches for kind.*LeaderWorkerSet", "Product Bug", "Missing LWS CRD — LLMD dependency", 0.95),
    (r"failed to reconcile.*workload|failed to build.*expected.*LWS", "Product Bug", "LLMD reconciliation failure", 0.95),
    (r"LLMInferenceService.*[Ff]ailed|llminferenceservice.*not.*[Rr]eady", "Product Bug", "LLMD service failure", 0.90),
    (r"InferenceService.*[Ff]ailed|InferenceService.*not.*[Rr]eady|isvc.*not.*ready", "Product Bug", "KServe InferenceService failure — check CR status conditions", 0.85),
    (r"RevisionFailed|LatestCreatedRevision.*not.*[Rr]eady", "Product Bug", "Knative revision failed — container crash during model startup", 0.85),
    (r"ServingRuntime.*not.*found|ClusterServingRuntime.*not.*found|runtime.*not.*supported", "Product Bug", "ServingRuntime missing or misconfigured", 0.90),
    (r"storage-initializer.*(?:failed|exit|error|crash)", "Infrastructure Issue", "Model download failure — check S3/storage credentials", 0.90),
    (r"IngressNotConfigured|ingress.*not.*ready|gateway.*not.*found", "Infrastructure Issue", "Knative/Istio ingress not configured", 0.90),
    (r"DataScienceCluster.*degraded|DSC.*not.*[Rr]eady|DSC.*[Ff]ailed", "Infrastructure Issue", "RHOAI DataScienceCluster degraded", 0.90),
    (r"DSCInitialization.*[Ff]ailed|DSCI.*not.*[Rr]eady", "Infrastructure Issue", "RHOAI DSCI initialization failure", 0.90),
    (r"model.*server.*not.*[Rr]eady|predictor.*not.*[Rr]eady|transformer.*not.*[Rr]eady", "Product Bug", "KServe predictor/transformer not ready", 0.80),
    (r"no matches for kind.*InferenceService|no matches for kind.*ServingRuntime", "Product Bug", "KServe CRDs not installed", 0.95),
    (r"no matches for kind", "Product Bug", "Missing CRD — operator dependency not installed", 0.90),
    (r"kserve.*controller.*error|kserve.*webhook.*error", "Product Bug", "KServe controller/webhook error", 0.85),
    (r"model.*not.*loaded|failed.*load.*model|model.*loading.*error", "Product Bug", "Model loading failure", 0.80),
    (r"vllm.*error|vllm.*crash|vllm.*oom", "Product Bug", "vLLM runtime error", 0.85),
    (r"queue-proxy.*error|queue-proxy.*timeout", "Infrastructure Issue", "Knative queue-proxy issue", 0.80),
    (r"HuggingFace.*401|HF_ACCESS_TOKEN|Cannot.*access.*gated", "Infrastructure Issue", "HuggingFace token missing for gated model", 0.90),

    # --- General infrastructure patterns ---
    (r"CrashLoopBackOff|ImagePullBackOff|OOMKilled", "Infrastructure Issue", "Pod failure", 0.95),
    (r"AccessDenied|InvalidAccessKeyId|SignatureDoesNotMatch", "Infrastructure Issue", "AWS/S3 credentials", 0.95),
    (r"connection.*refused|connection.*reset|network.*unreachable", "Infrastructure Issue", "Network", 0.90),
    (r"CUDA.*error|GPU.*not.*available|nvidia.*driver", "Infrastructure Issue", "GPU issue", 0.95),
    (r"ResourceQuota.*exceeded|quota.*exceeded", "Infrastructure Issue", "Quota exceeded", 0.95),
    (r"PodScheduled.*False|Unschedulable", "Infrastructure Issue", "Scheduling", 0.90),
    (r"upstream connect error|reset before headers|connection termination", "Infrastructure Issue", "Service mesh", 0.90),
    (r"no healthy upstream|circuit.?breaker", "Infrastructure Issue", "Service mesh circuit breaker", 0.85),
    (r"401\s+Unauthorized|403\s+Forbidden|token.*expired", "Infrastructure Issue", "Authentication/authorization", 0.90),
    (r"PersistentVolumeClaim.*Pending|volume.*mount.*fail", "Infrastructure Issue", "Storage", 0.90),
    (r"readiness.*probe.*failed|liveness.*probe.*failed", "Infrastructure Issue", "Pod health check", 0.85),
    (r"node.*NotReady|node.*[Uu]nschedulable", "Infrastructure Issue", "Node not ready", 0.95),

    # --- General product bug patterns ---
    (r"Internal.*[Ss]erver.*[Ee]rror|status.*code.*5[0-9]{2}", "Product Bug", "Server error", 0.80),
    (r"gRPC.*UNAVAILABLE|gRPC.*DEADLINE_EXCEEDED", "Product Bug", "gRPC service error", 0.80),
    (r"reconcile.*failed|operator.*degraded", "Product Bug", "Operator reconciliation failure", 0.85),

    # --- Setup-phase timeout patterns (higher priority than generic timeout) ---
    (r"failed on setup[\s\S]*?TimeoutExpiredError[\s\S]*?wait_for_condition", "Infrastructure Issue", "Setup timeout waiting for K8s resource condition", 0.90),
    (r"failed on setup[\s\S]*?TimeoutExpiredError[\s\S]*?(?:Timed Out:\s*[3-9]\d{2}|Timed Out:\s*\d{4,})", "Infrastructure Issue", "Setup timeout with generous wait (>=300s)", 0.88),
    (r"wait_for_condition[\s\S]*?Timed Out[\s\S]*?Last exception:\s*N/?A", "Infrastructure Issue", "Resource never reached ready condition", 0.88),

    # --- Test automation patterns ---
    (r"TimeoutExpiredError|TimeoutSampler.*expired|Timed Out", "Test Automation Issue", "Timeout", 0.80),
    (r"AssertionError|assert.*failed", "Test Automation Issue", "Assertion", 0.75),
    (r"fixture.*not.*found|SetupError", "Test Automation Issue", "Fixture error", 0.90),
]

SEVERITY_PATTERNS: dict[str, list[str]] = {
    "CRITICAL": [
        r"OOMKilled",
        r"CrashLoopBackOff",
        r"data.*corrupt",
        r"security.*breach",
        r"node.*NotReady",
        r"no matches for kind",
        r"failed to reconcile.*workload",
        r"DataScienceCluster.*degraded",
    ],
    "HIGH": [
        r"status.*code.*5[0-9]{2}",
        r"InferenceService.*Failed",
        r"InferenceService.*not.*[Rr]eady",
        r"LLMInferenceService.*[Ff]ailed",
        r"RevisionFailed",
        r"GPU.*not.*available",
        r"upstream connect error",
        r"401.*Unauthorized",
        r"reconcile.*failed",
        r"ServingRuntime.*not.*found",
        r"storage-initializer.*failed",
    ],
    "MEDIUM": [
        r"TimeoutError",
        r"AssertionError",
        r"connection.*refused",
        r"model.*not.*loaded",
    ],
    "LOW": [
        r"warning",
        r"deprecated",
    ],
}


class ClassificationService:
    """Service for classifying test failures.
    
    Single Responsibility: Only handles classification logic.
    Open/Closed: Add new patterns without modifying core logic.
    """
    
    def __init__(self, log_parser: LogParser | None = None):
        """Initialize with optional log parser.
        
        Dependency Inversion: Accepts interface, not concrete implementation.
        """
        self._log_parser = log_parser
        self._compiled_patterns: list[tuple[re.Pattern, str, str, float]] = [
            (re.compile(pattern, re.IGNORECASE), category, desc, conf)
            for pattern, category, desc, conf in DEFINITIVE_PATTERNS
        ]
    
    def classify(
        self,
        logs: str,
        evidence: Evidence | None = None,
        use_rules_only: bool = False,
    ) -> Classification:
        """Classify failure based on logs and evidence.
        
        Args:
            logs: Raw failure logs
            evidence: Optional evidence with historical context
            use_rules_only: If True, skip LLM and use only pattern matching
            
        Returns:
            Classification result
        """
        # Match patterns
        pattern_match = self._match_patterns(logs)
        
        if pattern_match:
            confidence = pattern_match["confidence"]
            
            # Adjust confidence based on evidence
            if evidence:
                confidence = self._adjust_confidence(confidence, evidence)
            
            # Determine severity
            severity = self._determine_severity(logs)
            
            return Classification(
                category=FailureCategory.from_string(pattern_match["category"]),
                confidence=confidence,
                severity=severity,
                reasoning=f"Pattern matched: {pattern_match['description']}",
                recommendation=self._get_recommendation(pattern_match["category"]),
                matched_patterns=[pattern_match["description"]],
            )
        
        # No pattern match - return low confidence result
        return Classification(
            category=FailureCategory.TO_INVESTIGATE,
            confidence=0.4,
            severity=Severity.MEDIUM,
            reasoning="No definitive pattern matched. LLM analysis recommended.",
            recommendation="Investigate logs manually or use LLM analysis.",
        )
    
    def _match_patterns(self, logs: str) -> dict[str, Any] | None:
        """Match logs against known patterns."""
        matches = []
        
        for pattern, category, desc, base_confidence in self._compiled_patterns:
            if pattern.search(logs):
                matches.append({
                    "category": category,
                    "description": desc,
                    "confidence": base_confidence,
                    "pattern": pattern.pattern,
                })
        
        if not matches:
            return None
        
        # Return highest confidence match
        return max(matches, key=lambda x: x["confidence"])
    
    def _adjust_confidence(self, base_confidence: float, evidence: Evidence) -> float:
        """Adjust confidence based on evidence strength."""
        confidence = base_confidence
        
        # Boost for multiple patterns
        if len(evidence.patterns) > 2:
            confidence = min(confidence + 0.05, 0.98)
        
        # Boost for stack trace
        if evidence.stack_trace:
            confidence = min(confidence + 0.03, 0.98)
        
        # Reduce if historically flaky
        if evidence.historical_failures > 3:
            confidence = max(confidence - 0.1, 0.5)
        
        return confidence
    
    def _determine_severity(self, logs: str) -> Severity:
        """Determine severity based on log patterns."""
        for severity_level, patterns in SEVERITY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, logs, re.IGNORECASE):
                    return Severity(severity_level)
        
        return Severity.MEDIUM
    
    def _get_recommendation(self, category: str) -> str:
        """Get recommendation based on category."""
        recommendations = {
            "Infrastructure Issue": (
                "1. Check cluster health: `oc get nodes` and `oc get clusterversion`\n"
                "2. Check RHOAI operator: `oc get pods -n redhat-ods-operator`\n"
                "3. Check DSC status: `oc get dsc -A -o yaml` (look at .status.conditions)\n"
                "4. Verify credentials/secrets and storage class"
            ),
            "Test Automation Issue": (
                "1. Review timeout values against expected operation durations\n"
                "2. Add explicit waits with proper conditions\n"
                "3. Check test isolation and fixture setup"
            ),
            "Product Bug": (
                "1. Check CR status conditions: `oc get isvc -A -o yaml` or `oc get llmisvc -A -o yaml`\n"
                "2. Check operator/controller logs: `oc logs -n redhat-ods-applications deploy/kserve-controller-manager`\n"
                "3. Check predictor pod logs: `oc logs <pod> -c kserve-container` and `oc logs <pod> -c storage-initializer`\n"
                "4. File JIRA with CR status conditions and pod logs"
            ),
            "Intermittent Failure": (
                "1. Add @pytest.mark.flaky decorator\n"
                "2. Replace sleeps with explicit waits on resource conditions\n"
                "3. Review resource cleanup between tests"
            ),
        }
        return recommendations.get(category, "Investigate further.")
    
    def get_evidence_from_logs(self, logs: str, test_code: str = "") -> Evidence:
        """Extract evidence from logs and test code."""
        error_message = ""
        error_type = ""
        stack_trace = ""
        patterns = []
        
        # Extract error info
        error_match = re.search(r"(?:Error|Exception):\s*(.{10,500})", logs, re.IGNORECASE)
        if error_match:
            error_message = error_match.group(0)
        
        type_match = re.search(r"(\w+Error|\w+Exception)", logs)
        if type_match:
            error_type = type_match.group(1)
        
        trace_match = re.search(r"Traceback.*?(?=\n\n|\Z)", logs, re.DOTALL)
        if trace_match:
            stack_trace = trace_match.group(0)[:800]
        
        # Find matching patterns
        for compiled, category, desc, _ in self._compiled_patterns:
            if compiled.search(logs):
                patterns.append(f"{desc} ({category})")
        
        # Check for flaky indicators in test code
        known_flaky = False
        decorators = []
        if test_code:
            flaky_indicators = [
                r"@pytest\.mark\.flaky",
                r"@pytest\.mark\.xfail",
                r"@retry",
            ]
            for indicator in flaky_indicators:
                if re.search(indicator, test_code, re.IGNORECASE):
                    known_flaky = True
                    break
            
            decorator_matches = re.findall(r"@(\w+(?:\.\w+)*)", test_code)
            decorators = decorator_matches[:10]
        
        return Evidence(
            error_message=error_message,
            error_type=error_type,
            patterns=patterns,
            test_code=test_code[:3000] if test_code else "",
            stack_trace=stack_trace,
            decorators=decorators,
            known_flaky=known_flaky,
        )
