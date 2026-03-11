"""High-level must-gather analysis service.

Orchestrates parsing of must-gather artifacts, filters for infrastructure
signals, maps test names to per-test must-gather directories, and produces
a MustGatherReport consumable by the RCA investigation pipeline.
"""

import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from src.infrastructure.k8s.must_gather_parser import (
    MustGatherEvent,
    MustGatherParser,
    MustGatherPodInfo,
    MustGatherReport,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

RHOAI_NAMESPACES = frozenset({
    "redhat-ods-operator",
    "redhat-ods-applications",
    "rhods-notebooks",
    "redhat-ods-monitoring",
    "rhoai-model-registries",
    "opendatahub",
})

OPERATOR_CR_TYPES = (
    "datasciencecluster",
    "dscinitialization",
)


class MustGatherAnalyzer:
    """Analyzes must-gather artifacts to produce cluster health context.

    Supports two usage modes:
      1. A base directory matching the opendatahub-tests layout
         (``must-gather-collected/<test-path>/...``), where it auto-maps
         test names to per-test must-gather directories.
      2. A direct path to a single must-gather directory or zip.

    Args:
        base_path: Root of the must-gather-collected directory tree.
        max_log_lines: Max container log lines to include per pod.
        auto_detect: Attempt to map test names to per-test directories.
    """

    def __init__(
        self,
        base_path: str | Path,
        max_log_lines: int = 50,
        auto_detect: bool = True,
    ):
        self._base_path = Path(base_path)
        self._max_log_lines = max_log_lines
        self._auto_detect = auto_detect

    def analyze(
        self,
        test_name: str | None = None,
        must_gather_path: str | None = None,
    ) -> MustGatherReport:
        """Produce an analysis report from must-gather data.

        Args:
            test_name: Fully-qualified test name (for auto-mapping to per-test
                must-gather directories under ``base_path``).
            must_gather_path: Explicit path to a must-gather dir or zip,
                overriding auto-detection.

        Returns:
            MustGatherReport with cluster health signals.
        """
        resolved = self._resolve_path(test_name, must_gather_path)
        if resolved is None:
            logger.debug("must_gather_not_found", test_name=test_name)
            return MustGatherReport(cluster_health="unknown")

        try:
            with MustGatherParser(resolved, max_log_lines=self._max_log_lines) as parser:
                return self._build_report(parser)
        except Exception as e:
            logger.warning("must_gather_analysis_failed", error=str(e), path=str(resolved))
            return MustGatherReport(cluster_health="unknown")

    # -- path resolution --

    def _resolve_path(
        self,
        test_name: str | None,
        explicit_path: str | None,
    ) -> Path | None:
        if explicit_path:
            p = Path(explicit_path)
            return p if p.exists() else None

        if not test_name or not self._auto_detect:
            if self._base_path.exists():
                return self._base_path
            return None

        mg_dir = self._map_test_to_directory(test_name)
        if mg_dir and mg_dir.exists():
            return self._find_must_gather_artifact(mg_dir)

        if self._base_path.exists():
            return self._base_path
        return None

    def _map_test_to_directory(self, test_name: str) -> Path | None:
        """Convert a pytest node ID to the opendatahub-tests must-gather path.

        Example mapping:
            ``tests.inference.test_kserve::TestKServe::test_deploy`` ->
            ``<base>/inference/test_kserve/TestKServe/test_deploy/``
        """
        normalized = test_name.replace("::", "/").replace(".", "/")
        normalized = re.sub(r"^tests/", "", normalized)
        # Remove parametrize suffixes like [param0]
        normalized = re.sub(r"\[.*\]$", "", normalized)

        candidate = self._base_path / normalized
        if candidate.is_dir():
            return candidate

        # Try fuzzy match by searching for test function name in base tree
        func_name = normalized.rsplit("/", 1)[-1] if "/" in normalized else normalized
        for dirpath, dirnames, _ in os.walk(self._base_path):
            for d in dirnames:
                # Match exact name or parametrized dirs like test_foo[param0]
                bare = d.split("[")[0]
                if bare == func_name or func_name == d:
                    return Path(dirpath) / d

        return None

    @staticmethod
    def _find_must_gather_artifact(test_dir: Path) -> Path | None:
        """Find the must-gather artifact inside a per-test directory.

        opendatahub-tests puts data in ``pytest_exception_interact/``.
        Searches recursively since the directory structure can be nested
        (module/Class/test[params]/pytest_exception_interact/mg-*.zip).
        """
        interact_dir = test_dir / "pytest_exception_interact"
        if interact_dir.is_dir():
            for item in sorted(interact_dir.iterdir(), reverse=True):
                if item.suffix == ".zip":
                    return item
                if item.is_dir() and item.name.startswith("must-gather"):
                    return item

        # Recursive search for zips under the test directory tree
        zips = sorted(test_dir.rglob("*.zip"), reverse=True)
        if zips:
            return zips[0]

        # Recursive search for must-gather directories
        for d in test_dir.rglob("must-gather*"):
            if d.is_dir():
                return d

        return None

    # -- report building --

    def _build_report(self, parser: MustGatherParser) -> MustGatherReport:
        namespaces = parser.list_namespaces()
        if not namespaces:
            logger.debug("no_namespaces_found")
            return MustGatherReport(cluster_health="unknown")

        all_pods: list[MustGatherPodInfo] = []
        all_events: list[MustGatherEvent] = []

        for ns in namespaces:
            all_pods.extend(parser.get_pod_infos(ns))
            all_events.extend(parser.get_events(ns))

        unhealthy = [p for p in all_pods if p.is_unhealthy]
        warnings = [e for e in all_events if e.type == "Warning"]
        warnings = self._deduplicate_events(warnings)

        operator_status = self._extract_operator_status(parser)
        resource_failures = self._extract_resource_failures(parser)

        cluster_health = self._assess_health(unhealthy, warnings, operator_status)

        logger.info(
            "must_gather_analyzed",
            namespaces=len(namespaces),
            total_pods=len(all_pods),
            unhealthy_pods=len(unhealthy),
            warning_events=len(warnings),
            cluster_health=cluster_health,
        )

        return MustGatherReport(
            unhealthy_pods=unhealthy,
            warning_events=warnings,
            operator_status=operator_status,
            resource_failures=resource_failures,
            cluster_health=cluster_health,
        )

    def _extract_operator_status(self, parser: MustGatherParser) -> dict[str, str]:
        """Extract DSC/DSCI operator component status from cluster-scoped CRs."""
        status_map: dict[str, str] = {}

        for cr_type in OPERATOR_CR_TYPES:
            for cr in parser.get_cluster_scoped_resources(cr_type):
                self._parse_cr_conditions(cr, status_map)

        return status_map

    @staticmethod
    def _parse_cr_conditions(cr: dict, status_map: dict[str, str]) -> None:
        status = cr.get("status", {})

        conditions = status.get("conditions", [])
        for cond in conditions:
            cond_type = cond.get("type", "")
            cond_status = cond.get("status", "")
            cond_reason = cond.get("reason", "")
            if cond_type and cond_status != "True":
                status_map[cond_type] = cond_reason or f"status={cond_status}"

        # DSC has per-component status under status.components
        components = status.get("components", {})
        if isinstance(components, dict):
            for comp_name, comp_info in components.items():
                if isinstance(comp_info, dict):
                    mgmt_state = comp_info.get("managementState", "")
                    ready = comp_info.get("status", comp_info.get("ready", ""))
                    if mgmt_state == "Managed" and ready not in ("True", "Available", True):
                        status_map[comp_name] = f"Managed but {ready or 'not ready'}"

    def _extract_resource_failures(self, parser: MustGatherParser) -> list[str]:
        """Scan for CRs in non-Ready/non-Available state.

        Searches both cluster-scoped and namespace-scoped resources to find
        CRs like InferenceService, LLMInferenceService, ServingRuntime, etc.
        that have failing conditions with error messages.
        """
        failures: list[str] = []

        cr_types = (
            # KServe model serving CRs
            "inferenceservice",
            "llminferenceservice",
            "servingruntime",
            "clusterservingruntime",
            "predictor",
            "trainedmodel",
            # KServe multi-node / LLMD dependencies
            "leaderworkerset",
            # Knative (serverless KServe mode)
            "revision",
            "configuration",
            "route",
            "service",
            # RHOAI platform CRs
            "notebook",
            "datasciencepipelinesapplication",
            "raycluster",
            "rayservice",
            "trustyaiservice",
        )
        for cr_type in cr_types:
            crs = parser.get_cluster_scoped_resources(cr_type)
            crs.extend(parser.get_namespaced_resources(cr_type))
            for cr in crs:
                self._check_cr_failures(cr, cr_type, failures)

        return failures

    @staticmethod
    def _check_cr_failures(
        cr: dict, cr_type: str, failures: list[str]
    ) -> None:
        """Extract failure signals from a single CR's status."""
        metadata = cr.get("metadata", {})
        name = metadata.get("name", "?")
        ns = metadata.get("namespace", "")
        status = cr.get("status", {})

        conditions = status.get("conditions", [])
        for cond in conditions:
            cond_type = cond.get("type", "")
            cond_status = cond.get("status", "")
            if cond_status == "True":
                continue
            reason = cond.get("reason", "")
            msg = cond.get("message", "")[:500]
            if reason or msg:
                failures.append(
                    f"{cr_type}/{ns}/{name} [{cond_type}]: {reason} — {msg}"
                )

        for field_name in ("failureReason", "failureMessage", "error"):
            value = status.get(field_name, "")
            if value:
                failures.append(
                    f"{cr_type}/{ns}/{name} [{field_name}]: {str(value)[:500]}"
                )

    @staticmethod
    def _deduplicate_events(events: list[MustGatherEvent]) -> list[MustGatherEvent]:
        """Merge duplicate events by (reason, message) and sum counts."""
        seen: dict[tuple[str, str], MustGatherEvent] = {}
        for ev in events:
            key = (ev.reason, ev.message[:100])
            if key in seen:
                seen[key].count += ev.count
            else:
                seen[key] = MustGatherEvent(
                    type=ev.type,
                    reason=ev.reason,
                    message=ev.message,
                    involved_object=ev.involved_object,
                    count=ev.count,
                )
        return sorted(seen.values(), key=lambda e: e.count, reverse=True)

    @staticmethod
    def _assess_health(
        unhealthy_pods: list[MustGatherPodInfo],
        warning_events: list[MustGatherEvent],
        operator_status: dict[str, str],
    ) -> str:
        """Determine overall cluster health from collected signals."""
        critical_statuses = {"OOMKilled", "CrashLoopBackOff"}
        has_critical_pods = any(p.status in critical_statuses for p in unhealthy_pods)
        has_degraded_operators = len(operator_status) > 0

        if has_critical_pods and has_degraded_operators:
            return "critical"
        if has_critical_pods or has_degraded_operators or len(unhealthy_pods) >= 3:
            return "degraded"
        if unhealthy_pods or len(warning_events) >= 10:
            return "warning"
        return "healthy"
