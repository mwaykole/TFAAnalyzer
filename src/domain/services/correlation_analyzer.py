"""Launch-wide correlation analyzer for detecting patterns across failures.

Analyzes all failures in a launch to:
1. Detect correlated failures with shared root causes
2. Identify temporal patterns (failures occurring together)
3. Find component-level issues
4. Detect infrastructure-wide problems
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CorrelatedFailure:
    """A group of correlated failures."""
    correlation_id: str
    test_ids: list[str]
    test_names: list[str]
    shared_error_pattern: str
    correlation_type: str  # "same_error", "same_component", "temporal", "infrastructure"
    confidence: float
    likely_root_cause: str
    recommendation: str


@dataclass
class LaunchAnalysis:
    """Complete analysis of a launch's failures."""
    launch_id: str
    total_failures: int
    correlated_groups: list[CorrelatedFailure]
    isolated_failures: list[str]  # test_ids not in any group
    
    # Summary metrics
    infrastructure_issue_detected: bool = False
    infrastructure_summary: str = ""
    component_issues: dict[str, int] = field(default_factory=dict)
    error_type_distribution: dict[str, int] = field(default_factory=dict)
    
    # Temporal analysis
    temporal_clusters: list[dict] = field(default_factory=list)
    
    def summary_for_llm(self) -> str:
        """Generate summary for LLM context."""
        parts = [
            f"## Launch Analysis Summary",
            f"Total failures: {self.total_failures}",
            f"Correlated groups: {len(self.correlated_groups)}",
            f"Isolated failures: {len(self.isolated_failures)}",
        ]
        
        if self.infrastructure_issue_detected:
            parts.append(f"\n⚠️ INFRASTRUCTURE ISSUE: {self.infrastructure_summary}")
        
        if self.correlated_groups:
            parts.append("\n### Correlated Failure Groups:")
            for group in self.correlated_groups[:3]:
                parts.append(
                    f"- {group.correlation_type}: {len(group.test_ids)} tests, "
                    f"pattern='{group.shared_error_pattern[:30]}'"
                )
        
        if self.component_issues:
            parts.append("\n### Component Breakdown:")
            for comp, count in sorted(self.component_issues.items(), key=lambda x: -x[1])[:5]:
                parts.append(f"- {comp}: {count} failures")
        
        return "\n".join(parts)


class CorrelationAnalyzer:
    """Analyzer for launch-wide failure correlations.
    
    Detects patterns across multiple test failures to identify:
    - Systemic infrastructure issues
    - Component-specific problems
    - Related failures with shared root causes
    """
    
    # Infrastructure-level error patterns
    INFRASTRUCTURE_PATTERNS = {
        "cluster_resources": [
            r"Insufficient.*(?:cpu|memory)",
            r"0/\d+.*nodes.*available",
            r"quota.*exceeded",
            r"FailedScheduling",
        ],
        "storage": [
            r"storage-initializer.*failed",
            r"PVC.*(?:Pending|failed)",
            r"volume.*mount.*failed",
            r"S3.*(?:error|failed|timeout)",
            r"MinIO.*(?:error|failed)",
        ],
        "network": [
            r"connection.*refused",
            r"no.*such.*host",
            r"timeout.*dial",
            r"network.*unreachable",
            r"DNS.*(?:failed|timeout)",
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
            r"ErrImagePull",
        ],
    }
    
    def analyze_launch(
        self,
        failures: list[dict[str, Any]],
        launch_id: str,
    ) -> LaunchAnalysis:
        """Analyze all failures in a launch for correlations.
        
        Args:
            failures: List of failure dicts with:
                - test_id: str
                - test_name: str
                - error_message: str
                - error_type: str
                - component: str (optional)
                - timestamp: str (optional)
            launch_id: The launch identifier
            
        Returns:
            LaunchAnalysis with correlation insights
        """
        if not failures:
            return LaunchAnalysis(
                launch_id=launch_id,
                total_failures=0,
                correlated_groups=[],
                isolated_failures=[],
            )
        
        logger.info("analyzing_launch_correlations",
                    launch_id=launch_id,
                    failure_count=len(failures))
        
        # Collect all analysis data
        correlated_groups: list[CorrelatedFailure] = []
        all_correlated_ids: set[str] = set()
        
        # 1. Infrastructure pattern matching
        infra_groups = self._find_infrastructure_patterns(failures)
        for group in infra_groups:
            correlated_groups.append(group)
            all_correlated_ids.update(group.test_ids)
        
        # 2. Same error type grouping
        error_groups = self._find_same_error_groups(failures, all_correlated_ids)
        for group in error_groups:
            correlated_groups.append(group)
            all_correlated_ids.update(group.test_ids)
        
        # 3. Component-level grouping
        component_groups = self._find_component_groups(failures, all_correlated_ids)
        for group in component_groups:
            correlated_groups.append(group)
            all_correlated_ids.update(group.test_ids)
        
        # Find isolated failures
        all_ids = {f["test_id"] for f in failures}
        isolated = list(all_ids - all_correlated_ids)
        
        # Build component distribution
        component_issues: dict[str, int] = defaultdict(int)
        for f in failures:
            comp = f.get("component", "unknown")
            component_issues[comp] += 1
        
        # Build error type distribution
        error_distribution: dict[str, int] = defaultdict(int)
        for f in failures:
            error_type = f.get("error_type", "unknown")
            error_distribution[error_type] += 1
        
        # Detect infrastructure-wide issues
        infra_detected = any(
            g.correlation_type == "infrastructure" 
            for g in correlated_groups
        )
        infra_summary = ""
        if infra_detected:
            infra_groups_list = [
                g for g in correlated_groups 
                if g.correlation_type == "infrastructure"
            ]
            affected = sum(len(g.test_ids) for g in infra_groups_list)
            causes = list(set(g.likely_root_cause for g in infra_groups_list))
            infra_summary = f"{affected} tests affected by: {', '.join(causes)}"
        
        analysis = LaunchAnalysis(
            launch_id=launch_id,
            total_failures=len(failures),
            correlated_groups=correlated_groups,
            isolated_failures=isolated,
            infrastructure_issue_detected=infra_detected,
            infrastructure_summary=infra_summary,
            component_issues=dict(component_issues),
            error_type_distribution=dict(error_distribution),
        )
        
        logger.info("launch_analysis_complete",
                    launch_id=launch_id,
                    correlated_groups=len(correlated_groups),
                    isolated=len(isolated),
                    infrastructure_issue=infra_detected)
        
        return analysis
    
    def _find_infrastructure_patterns(
        self,
        failures: list[dict],
    ) -> list[CorrelatedFailure]:
        """Find failures matching infrastructure patterns."""
        groups: list[CorrelatedFailure] = []
        
        for pattern_type, patterns in self.INFRASTRUCTURE_PATTERNS.items():
            matching_failures = []
            
            for failure in failures:
                context = f"{failure.get('error_message', '')} {failure.get('error_type', '')}"
                for pattern in patterns:
                    if re.search(pattern, context, re.IGNORECASE):
                        matching_failures.append(failure)
                        break
            
            if len(matching_failures) >= 2:
                groups.append(CorrelatedFailure(
                    correlation_id=f"infra_{pattern_type}",
                    test_ids=[f["test_id"] for f in matching_failures],
                    test_names=[f["test_name"] for f in matching_failures],
                    shared_error_pattern=pattern_type,
                    correlation_type="infrastructure",
                    confidence=min(0.95, 0.7 + 0.05 * len(matching_failures)),
                    likely_root_cause=self._get_infra_root_cause(pattern_type),
                    recommendation=self._get_infra_recommendation(pattern_type),
                ))
        
        return groups
    
    def _find_same_error_groups(
        self,
        failures: list[dict],
        exclude_ids: set[str],
    ) -> list[CorrelatedFailure]:
        """Find failures with same error type."""
        groups: list[CorrelatedFailure] = []
        
        # Group by error type
        by_error: dict[str, list[dict]] = defaultdict(list)
        for failure in failures:
            if failure["test_id"] in exclude_ids:
                continue
            error_type = failure.get("error_type", "")
            if error_type:
                by_error[error_type].append(failure)
        
        for error_type, error_failures in by_error.items():
            if len(error_failures) >= 2:
                groups.append(CorrelatedFailure(
                    correlation_id=f"error_{error_type}",
                    test_ids=[f["test_id"] for f in error_failures],
                    test_names=[f["test_name"] for f in error_failures],
                    shared_error_pattern=error_type,
                    correlation_type="same_error",
                    confidence=min(0.85, 0.6 + 0.05 * len(error_failures)),
                    likely_root_cause=f"Multiple tests failing with {error_type}",
                    recommendation=f"Investigate common cause of {error_type} across tests",
                ))
        
        return groups
    
    def _find_component_groups(
        self,
        failures: list[dict],
        exclude_ids: set[str],
    ) -> list[CorrelatedFailure]:
        """Find failures concentrated in a component."""
        groups: list[CorrelatedFailure] = []
        
        # Group by component
        by_component: dict[str, list[dict]] = defaultdict(list)
        for failure in failures:
            if failure["test_id"] in exclude_ids:
                continue
            component = failure.get("component", "")
            if component:
                by_component[component].append(failure)
        
        total_remaining = sum(len(fs) for fs in by_component.values())
        
        for component, comp_failures in by_component.items():
            # Only flag if component has high concentration
            if len(comp_failures) >= 3 and len(comp_failures) / max(total_remaining, 1) > 0.3:
                groups.append(CorrelatedFailure(
                    correlation_id=f"component_{component}",
                    test_ids=[f["test_id"] for f in comp_failures],
                    test_names=[f["test_name"] for f in comp_failures],
                    shared_error_pattern=f"Component: {component}",
                    correlation_type="same_component",
                    confidence=min(0.80, 0.5 + 0.05 * len(comp_failures)),
                    likely_root_cause=f"Issue concentrated in {component} component",
                    recommendation=f"Investigate {component} - multiple tests failing",
                ))
        
        return groups
    
    def _get_infra_root_cause(self, pattern_type: str) -> str:
        """Get root cause description for infrastructure pattern."""
        causes = {
            "cluster_resources": "Cluster resource exhaustion (CPU/memory/quota)",
            "storage": "Storage subsystem issue (S3/PVC/volumes)",
            "network": "Network connectivity issue (DNS/routing)",
            "operator": "Operator not healthy or degraded",
            "registry": "Container registry access issue",
        }
        return causes.get(pattern_type, "Infrastructure issue")
    
    def _get_infra_recommendation(self, pattern_type: str) -> str:
        """Get recommendation for infrastructure pattern."""
        recommendations = {
            "cluster_resources": "Check cluster capacity. Scale up nodes or reduce parallel tests.",
            "storage": "Verify S3/storage credentials and configuration.",
            "network": "Check DNS resolution and network policies.",
            "operator": "Check operator pod status and logs. May need restart.",
            "registry": "Verify registry credentials and pull secrets.",
        }
        return recommendations.get(pattern_type, "Investigate infrastructure.")
    
    def get_related_failures(
        self,
        test_id: str,
        analysis: LaunchAnalysis,
    ) -> list[str]:
        """Get IDs of failures related to a specific test.
        
        Args:
            test_id: The test to find relations for
            analysis: Launch analysis result
            
        Returns:
            List of related test IDs
        """
        related = []
        
        for group in analysis.correlated_groups:
            if test_id in group.test_ids:
                related.extend([t for t in group.test_ids if t != test_id])
        
        return list(set(related))
