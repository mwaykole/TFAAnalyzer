"""Enhanced analysis service for improved failure classification accuracy.

Implements research-backed improvements:
1. Failure clustering to detect systemic issues
2. Enhanced context from logs (INFO/WARNING before ERROR)
3. Timeout analysis based on operation type
4. Similar failure retrieval for few-shot learning
"""

import re
from dataclasses import dataclass, field
from typing import Any
from collections import defaultdict

from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Timeout Analysis
# =============================================================================

@dataclass
class TimeoutAnalysis:
    """Analysis of timeout-related failures."""
    operation_type: str
    timeout_used: int  # seconds
    expected_min: int
    expected_max: int
    verdict: str  # "reasonable", "too_short", "too_long", "within_range"
    recommendation: str


OPERATION_TIMEOUTS = {
    # Operation: (min_seconds, max_seconds)
    "pod_scheduling": (30, 120),
    "pod_ready": (60, 600),
    "model_load_small": (30, 120),
    "model_load_llm": (300, 900),
    "inference_request": (1, 300),
    "operator_reconcile": (30, 300),
    "rbac_propagation": (5, 120),
    "pvc_provisioning": (30, 300),
    "route_ready": (10, 60),
    "serverless_cold_start": (30, 300),
    "image_pull_small": (10, 60),
    "image_pull_large": (300, 900),
    "isvc_ready": (120, 600),
    "default": (60, 300),
}


def analyze_timeout(
    error_message: str,
    stack_trace: str,
    test_name: str,
) -> TimeoutAnalysis | None:
    """Analyze if a timeout failure has reasonable timeout value.
    
    Args:
        error_message: The error message from the failure
        stack_trace: Stack trace from the failure
        test_name: Name of the test
        
    Returns:
        TimeoutAnalysis if timeout-related, None otherwise
    """
    # Check if it's a timeout error
    timeout_patterns = [
        r"TimeoutExpiredError.*wait_timeout=(\d+)",
        r"timeout.*?(\d+)\s*(?:seconds?|s)",
        r"waited\s+(\d+)\s*(?:seconds?|s)",
        r"after\s+(\d+)\s*(?:seconds?|s)",
    ]
    
    timeout_value = None
    for pattern in timeout_patterns:
        match = re.search(pattern, error_message + " " + stack_trace, re.IGNORECASE)
        if match:
            timeout_value = int(match.group(1))
            break
    
    if timeout_value is None:
        return None
    
    # Determine operation type from context
    operation_type = _infer_operation_type(error_message, stack_trace, test_name)
    
    expected_min, expected_max = OPERATION_TIMEOUTS.get(
        operation_type, 
        OPERATION_TIMEOUTS["default"]
    )
    
    # Determine verdict
    if timeout_value < expected_min:
        verdict = "too_short"
        recommendation = f"Timeout of {timeout_value}s may be too short for {operation_type}. Expected {expected_min}-{expected_max}s. Consider increasing timeout - likely TEST AUTOMATION ISSUE."
    elif timeout_value > expected_max * 2:
        verdict = "too_long"
        recommendation = f"Timeout of {timeout_value}s exceeded even generous expectations for {operation_type}. Likely actual hang or resource issue - investigate further."
    else:
        verdict = "within_range"
        recommendation = f"Timeout of {timeout_value}s is reasonable for {operation_type}. Failure may indicate actual issue or resource constraints."
    
    return TimeoutAnalysis(
        operation_type=operation_type,
        timeout_used=timeout_value,
        expected_min=expected_min,
        expected_max=expected_max,
        verdict=verdict,
        recommendation=recommendation,
    )


def _infer_operation_type(error_message: str, stack_trace: str, test_name: str) -> str:
    """Infer the type of operation from context."""
    context = f"{error_message} {stack_trace} {test_name}".lower()
    
    if any(x in context for x in ["vllm", "tgis", "llm", "bloom", "flan-t5-large"]):
        return "model_load_llm"
    if any(x in context for x in ["model", "serving", "inference"]) and "load" in context:
        return "model_load_small"
    if "pod" in context and any(x in context for x in ["schedul", "pending"]):
        return "pod_scheduling"
    if "pod" in context and any(x in context for x in ["ready", "running"]):
        return "pod_ready"
    if any(x in context for x in ["rbac", "unauthorized", "403"]):
        return "rbac_propagation"
    if any(x in context for x in ["pvc", "volume", "storage"]):
        return "pvc_provisioning"
    if any(x in context for x in ["image", "pull"]):
        if any(x in context for x in ["large", "workbench", "notebook"]):
            return "image_pull_large"
        return "image_pull_small"
    if any(x in context for x in ["serverless", "cold", "knative"]):
        return "serverless_cold_start"
    if any(x in context for x in ["inferenceservice", "isvc"]):
        return "isvc_ready"
    if any(x in context for x in ["route", "ingress"]):
        return "route_ready"
    if any(x in context for x in ["operator", "reconcil", "dsc"]):
        return "operator_reconcile"
    if any(x in context for x in ["inference", "predict"]):
        return "inference_request"
    
    return "default"


# =============================================================================
# Failure Clustering
# =============================================================================

@dataclass
class FailureCluster:
    """A cluster of related failures with shared root cause."""
    cluster_id: str
    failures: list[str]  # test_ids
    shared_patterns: list[str]
    likely_root_cause: str
    category: str  # "infrastructure", "operator", "component", "unknown"
    confidence: float
    recommendation: str


@dataclass
class ClusterAnalysis:
    """Result of failure clustering analysis."""
    clusters: list[FailureCluster]
    isolated_failures: list[str]  # test_ids not in any cluster
    systemic_issue_detected: bool
    summary: str


class FailureClusterAnalyzer:
    """Analyze failures to detect systemic issues affecting multiple tests."""
    
    # Patterns that indicate systemic issues
    SYSTEMIC_PATTERNS = {
        "cluster_resources": [
            r"Insufficient.*(?:cpu|memory)",
            r"0/\d+.*nodes.*available",
            r"quota.*exceeded",
        ],
        "storage": [
            r"storage-initializer.*failed",
            r"PVC.*(?:Pending|failed)",
            r"volume.*mount.*failed",
            r"S3.*(?:error|failed|timeout)",
        ],
        "network": [
            r"connection.*refused",
            r"no.*such.*host",
            r"timeout.*dial",
            r"network.*unreachable",
        ],
        "operator": [
            r"operator.*not.*ready",
            r"DSC.*reconcile.*failed",
            r"component.*degraded",
            r"CRD.*not.*found",
        ],
        "registry": [
            r"ImagePullBackOff",
            r"unauthorized.*registry",
            r"repository.*not.*found",
        ],
    }
    
    def analyze_failures(
        self,
        failures: list[dict[str, Any]],
    ) -> ClusterAnalysis:
        """Analyze a batch of failures to detect clusters.
        
        Args:
            failures: List of failure dicts with keys:
                - test_id: str
                - test_name: str
                - error_message: str
                - error_type: str
                
        Returns:
            ClusterAnalysis with detected clusters
        """
        if len(failures) < 2:
            return ClusterAnalysis(
                clusters=[],
                isolated_failures=[f["test_id"] for f in failures],
                systemic_issue_detected=False,
                summary="Single failure, no clustering possible",
            )
        
        # Match patterns for each failure
        pattern_matches: dict[str, list[str]] = defaultdict(list)  # pattern_type -> [test_ids]
        
        for failure in failures:
            context = f"{failure.get('error_message', '')} {failure.get('error_type', '')}"
            
            for pattern_type, patterns in self.SYSTEMIC_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, context, re.IGNORECASE):
                        pattern_matches[pattern_type].append(failure["test_id"])
                        break
        
        # Build clusters from pattern matches
        clusters = []
        clustered_ids = set()
        
        for pattern_type, test_ids in pattern_matches.items():
            if len(test_ids) >= 2:  # At least 2 failures with same pattern
                cluster = FailureCluster(
                    cluster_id=f"cluster_{pattern_type}",
                    failures=list(set(test_ids)),
                    shared_patterns=[pattern_type],
                    likely_root_cause=self._get_root_cause(pattern_type),
                    category=self._get_category(pattern_type),
                    confidence=min(0.95, 0.6 + 0.1 * len(test_ids)),
                    recommendation=self._get_recommendation(pattern_type),
                )
                clusters.append(cluster)
                clustered_ids.update(test_ids)
        
        # Find isolated failures
        all_ids = {f["test_id"] for f in failures}
        isolated = list(all_ids - clustered_ids)
        
        # Build summary
        systemic = len(clusters) > 0
        if systemic:
            summary = f"Detected {len(clusters)} failure cluster(s) affecting {len(clustered_ids)} tests. "
            summary += f"Root causes: {', '.join(c.likely_root_cause for c in clusters)}. "
            summary += f"{len(isolated)} isolated failures."
        else:
            summary = f"No systemic patterns detected. {len(failures)} isolated failures."
        
        logger.info("cluster_analysis_complete",
                    total_failures=len(failures),
                    clusters_found=len(clusters),
                    clustered_count=len(clustered_ids),
                    isolated_count=len(isolated))
        
        return ClusterAnalysis(
            clusters=clusters,
            isolated_failures=isolated,
            systemic_issue_detected=systemic,
            summary=summary,
        )
    
    def _get_root_cause(self, pattern_type: str) -> str:
        causes = {
            "cluster_resources": "Cluster resource exhaustion (CPU/memory/quota)",
            "storage": "Storage subsystem issue (S3/PVC/volumes)",
            "network": "Network connectivity issue (DNS/routing/firewall)",
            "operator": "Operator not healthy or degraded",
            "registry": "Container registry access issue",
        }
        return causes.get(pattern_type, "Unknown systemic issue")
    
    def _get_category(self, pattern_type: str) -> str:
        categories = {
            "cluster_resources": "infrastructure",
            "storage": "infrastructure",
            "network": "infrastructure",
            "operator": "operator",
            "registry": "infrastructure",
        }
        return categories.get(pattern_type, "unknown")
    
    def _get_recommendation(self, pattern_type: str) -> str:
        recommendations = {
            "cluster_resources": "Check cluster capacity. May need to scale up nodes or reduce parallel test execution.",
            "storage": "Verify S3 credentials, check PVC provisioner, ensure storage class is available.",
            "network": "Check DNS resolution, verify network policies, ensure external services are accessible.",
            "operator": "Check operator pod status and logs. May need to restart operator or check CRDs.",
            "registry": "Verify registry credentials, check image exists, ensure pull secrets are configured.",
        }
        return recommendations.get(pattern_type, "Investigate shared failure patterns.")


# =============================================================================
# Enhanced Evidence Extraction
# =============================================================================

@dataclass
class EnhancedEvidence:
    """Enhanced evidence with additional context."""
    # Basic evidence
    error_message: str
    error_type: str
    stack_trace: str
    
    # Enhanced context
    pre_error_logs: str  # WARNING/INFO before ERROR
    related_failures: list[str]  # Other failures in same launch
    timeout_analysis: TimeoutAnalysis | None
    cluster_info: FailureCluster | None
    
    # Inferred context
    operation_type: str
    expected_duration: str
    component_notes: list[str]
    
    def to_prompt_context(self) -> str:
        """Generate enhanced context for LLM prompt."""
        parts = []
        
        parts.append(f"ERROR: {self.error_type}: {self.error_message}")
        parts.append(f"STACK TRACE:\n{self.stack_trace[:800]}")
        
        if self.pre_error_logs:
            parts.append(f"CONTEXT (logs before error):\n{self.pre_error_logs[:500]}")
        
        if self.timeout_analysis:
            parts.append(f"TIMEOUT ANALYSIS: {self.timeout_analysis.recommendation}")
        
        if self.cluster_info:
            parts.append(f"SYSTEMIC ISSUE DETECTED: {self.cluster_info.likely_root_cause}")
            parts.append(f"Affects {len(self.cluster_info.failures)} tests")
        
        if self.related_failures:
            parts.append(f"RELATED FAILURES IN LAUNCH: {len(self.related_failures)} other tests failed")
        
        if self.component_notes:
            parts.append(f"COMPONENT CONTEXT:\n" + "\n".join(f"- {n}" for n in self.component_notes))
        
        return "\n\n".join(parts)


def extract_pre_error_logs(full_logs: str, max_lines: int = 20) -> str:
    """Extract WARNING and INFO logs that occurred before the ERROR.
    
    This provides context on what was happening when the failure occurred.
    """
    lines = full_logs.split('\n')
    
    # Find last ERROR line
    error_index = -1
    for i in range(len(lines) - 1, -1, -1):
        if 'ERROR' in lines[i] or 'FAILED' in lines[i] or 'Exception' in lines[i]:
            error_index = i
            break
    
    if error_index <= 0:
        return ""
    
    # Get lines before error
    start_index = max(0, error_index - max_lines)
    pre_error = lines[start_index:error_index]
    
    # Filter to only INFO and WARNING
    relevant = [
        line for line in pre_error
        if any(level in line for level in ['INFO', 'WARNING', 'WARN', 'DEBUG'])
    ]
    
    return '\n'.join(relevant[-max_lines:])


# =============================================================================
# Confidence Calibration
# =============================================================================

@dataclass
class CalibratedConfidence:
    """Confidence score with calibration factors."""
    raw_confidence: float
    calibrated_confidence: float
    factors: dict[str, float]
    explanation: str


def calibrate_confidence(
    raw_confidence: float,
    evidence_strength: str,  # "definitive", "strong", "moderate", "weak"
    has_timeout_analysis: bool = False,
    has_cluster_match: bool = False,
    has_similar_failures: bool = False,
    verification_result: str | None = None,  # "confirmed", "contradicted", None
) -> CalibratedConfidence:
    """Calibrate confidence score based on evidence quality.
    
    Raw LLM confidence is often not well-calibrated. This adjusts
    based on objective evidence factors.
    """
    factors = {}
    
    # Base calibration (LLM tends to be overconfident)
    calibrated = raw_confidence * 0.85
    factors["base_calibration"] = 0.85
    
    # Evidence strength adjustment
    evidence_multipliers = {
        "definitive": 1.15,
        "strong": 1.05,
        "moderate": 0.95,
        "weak": 0.80,
    }
    multiplier = evidence_multipliers.get(evidence_strength, 1.0)
    calibrated *= multiplier
    factors["evidence_strength"] = multiplier
    
    # Bonus for additional analysis
    if has_timeout_analysis:
        calibrated *= 1.05
        factors["timeout_analysis"] = 1.05
    
    if has_cluster_match:
        calibrated *= 1.10  # High confidence when pattern matches cluster
        factors["cluster_match"] = 1.10
    
    if has_similar_failures:
        calibrated *= 1.08
        factors["similar_failures"] = 1.08
    
    # Verification impact
    if verification_result == "confirmed":
        calibrated = min(0.98, calibrated * 1.20)
        factors["verification_confirmed"] = 1.20
    elif verification_result == "contradicted":
        calibrated *= 0.60
        factors["verification_contradicted"] = 0.60
    
    # Clamp to valid range
    calibrated = max(0.10, min(0.99, calibrated))
    
    # Build explanation
    explanation_parts = [f"Raw: {raw_confidence:.0%}"]
    for factor_name, factor_value in factors.items():
        if factor_value != 1.0:
            direction = "+" if factor_value > 1.0 else ""
            explanation_parts.append(f"{factor_name}: {direction}{(factor_value-1)*100:.0f}%")
    explanation_parts.append(f"Final: {calibrated:.0%}")
    
    return CalibratedConfidence(
        raw_confidence=raw_confidence,
        calibrated_confidence=calibrated,
        factors=factors,
        explanation=" → ".join(explanation_parts),
    )
