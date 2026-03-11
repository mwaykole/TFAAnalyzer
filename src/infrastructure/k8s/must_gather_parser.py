"""Low-level parser for OpenShift must-gather directory structures.

Navigates the directory layout produced by `oc adm inspect` and extracts
pod specs, container logs, events, and custom resources from must-gather
artifacts (raw directories or zip archives).
"""

import os
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.utils.logging import get_logger

logger = get_logger(__name__)

UNHEALTHY_STATUSES = frozenset({
    "CrashLoopBackOff",
    "ImagePullBackOff",
    "ErrImagePull",
    "OOMKilled",
    "Error",
    "CreateContainerConfigError",
    "RunContainerError",
    "InvalidImageName",
    "ContainerCannotRun",
    "DeadlineExceeded",
})


@dataclass
class MustGatherPodInfo:
    """Parsed pod status from a must-gather pod YAML."""

    name: str
    namespace: str
    phase: str
    status: str
    restart_count: int = 0
    exit_code: int | None = None
    error_message: str = ""
    container_logs: dict[str, str] = field(default_factory=dict)

    @property
    def is_unhealthy(self) -> bool:
        return (
            self.status in UNHEALTHY_STATUSES
            or self.phase in ("Failed", "Unknown")
            or self.restart_count >= 3
            or (self.exit_code is not None and self.exit_code != 0)
        )


@dataclass
class MustGatherEvent:
    """Parsed event from a must-gather events YAML."""

    type: str
    reason: str
    message: str
    involved_object: str = ""
    count: int = 1


@dataclass
class MustGatherReport:
    """Aggregated analysis of must-gather data."""

    unhealthy_pods: list[MustGatherPodInfo] = field(default_factory=list)
    warning_events: list[MustGatherEvent] = field(default_factory=list)
    operator_status: dict[str, str] = field(default_factory=dict)
    resource_failures: list[str] = field(default_factory=list)
    cluster_health: str = "healthy"

    def to_context(self, max_log_lines: int = 15) -> str:
        """Format report as markdown for LLM context window."""
        total_pods = len(self.unhealthy_pods)
        total_events = len(self.warning_events)
        total_degraded = len(self.operator_status)
        total_failed = len(self.resource_failures)

        parts = [f"## Cluster Health: {self.cluster_health.upper()}"]
        parts.append(
            f"Summary: {total_pods} unhealthy pods, {total_events} warning events, "
            f"{total_degraded} degraded operators, {total_failed} failed resources"
        )

        if self.operator_status:
            degraded = {k: v for k, v in self.operator_status.items() if v != "Available"}
            if degraded:
                parts.append("\n### Degraded Operators")
                for comp, status in degraded.items():
                    parts.append(f"- **{comp}**: {status}")

        if self.unhealthy_pods:
            parts.append(f"\n### Unhealthy Pods ({len(self.unhealthy_pods)})")
            for pod in self.unhealthy_pods[:15]:
                header = f"- **{pod.namespace}/{pod.name}** — {pod.status} (phase={pod.phase})"
                if pod.restart_count > 0:
                    header += f", restarts={pod.restart_count}"
                if pod.exit_code is not None:
                    header += f", exit={pod.exit_code}"
                parts.append(header)
                if pod.error_message:
                    parts.append(f"  Error: {pod.error_message[:300]}")
                for container, logs in pod.container_logs.items():
                    log_lines = logs.strip().splitlines()
                    if log_lines:
                        tail = log_lines[-max_log_lines:]
                        parts.append(f"  Container `{container}` (last {len(tail)} lines):")
                        parts.append("  ```")
                        parts.extend(f"  {line}" for line in tail)
                        parts.append("  ```")

        if self.warning_events:
            parts.append(f"\n### Warning Events ({len(self.warning_events)})")
            for ev in self.warning_events[:20]:
                count_str = f" (x{ev.count})" if ev.count > 1 else ""
                obj_str = f" [{ev.involved_object}]" if ev.involved_object else ""
                parts.append(f"- {ev.reason}{obj_str}{count_str}: {ev.message[:200]}")

        if self.resource_failures:
            parts.append(f"\n### Failed Resources ({len(self.resource_failures)})")
            for res in self.resource_failures[:15]:
                parts.append(f"- {res}")

        return "\n".join(parts)


class MustGatherParser:
    """Parses an `oc adm must-gather` output directory or zip archive.

    The expected layout (produced by `oc adm inspect namespace/<ns>`):

        <root>/
          namespaces/
            <namespace>/
              pods/<pod-name>/<pod-name>.yaml
              pods/<pod-name>/<container>/<container>/logs/current.log
              core/events.yaml
          cluster-scoped-resources/
            ...
    """

    def __init__(self, path: str | Path, max_log_lines: int = 50):
        self._original_path = Path(path)
        self._max_log_lines = max_log_lines
        self._root: Path | None = None
        self._tmp_dir: tempfile.TemporaryDirectory | None = None

    def open(self) -> "MustGatherParser":
        """Resolve the must-gather root directory, extracting zips if needed."""
        path = self._original_path

        if not path.exists():
            raise FileNotFoundError(f"Must-gather path not found: {path}")

        if path.is_file() and path.suffix == ".zip":
            self._tmp_dir = tempfile.TemporaryDirectory(prefix="mg_")
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(self._tmp_dir.name)
            path = Path(self._tmp_dir.name)

        self._root = self._find_root(path)
        logger.info("must_gather_opened", root=str(self._root))
        return self

    def close(self) -> None:
        if self._tmp_dir:
            self._tmp_dir.cleanup()
            self._tmp_dir = None

    def __enter__(self) -> "MustGatherParser":
        return self.open()

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _find_root(self, path: Path) -> Path:
        """Walk down to the actual must-gather content root.

        `oc adm must-gather` wraps output in `must-gather.local.<ts>/`
        which may itself contain another image-named subdirectory.
        We look for the first directory that contains `namespaces/` or
        `cluster-scoped-resources/`.
        """
        if (path / "namespaces").is_dir() or (path / "cluster-scoped-resources").is_dir():
            return path

        for child in sorted(path.iterdir()):
            if child.is_dir():
                found = self._find_root(child)
                if found != child or (child / "namespaces").is_dir():
                    return found

        return path

    def list_namespaces(self) -> list[str]:
        ns_dir = self._root / "namespaces"
        if not ns_dir.is_dir():
            return []
        return sorted(d.name for d in ns_dir.iterdir() if d.is_dir())

    def get_pod_infos(self, namespace: str) -> list[MustGatherPodInfo]:
        """Parse all pod YAMLs in a namespace and return structured info."""
        pods_dir = self._root / "namespaces" / namespace / "pods"
        if not pods_dir.is_dir():
            return []

        results: list[MustGatherPodInfo] = []
        for pod_dir in sorted(pods_dir.iterdir()):
            if not pod_dir.is_dir():
                continue
            yaml_path = pod_dir / f"{pod_dir.name}.yaml"
            if not yaml_path.is_file():
                continue
            info = self._parse_pod_yaml(yaml_path, namespace)
            if info:
                info.container_logs = self._collect_container_logs(pod_dir)
                results.append(info)
        return results

    def get_events(self, namespace: str) -> list[MustGatherEvent]:
        """Parse events from the namespace core/events.yaml."""
        events_path = self._root / "namespaces" / namespace / "core" / "events.yaml"
        if not events_path.is_file():
            return []
        return self._parse_events_yaml(events_path)

    def get_container_log(self, namespace: str, pod: str, container: str) -> str:
        """Read a specific container log file."""
        for log_name in ("current.log", "previous.log"):
            log_path = (
                self._root / "namespaces" / namespace / "pods" / pod
                / container / container / "logs" / log_name
            )
            if log_path.is_file():
                return self._read_tail(log_path, self._max_log_lines)
        return ""

    def get_cluster_scoped_resources(self, resource_group: str) -> list[dict]:
        """Read cluster-scoped resource YAMLs (e.g. 'dscinitialization')."""
        cs_dir = self._root / "cluster-scoped-resources"
        if not cs_dir.is_dir():
            return []

        results: list[dict] = []
        for dirpath, _, filenames in os.walk(cs_dir):
            for fn in filenames:
                if resource_group in fn.lower() and fn.endswith(".yaml"):
                    full = Path(dirpath) / fn
                    try:
                        data = yaml.safe_load(full.read_text(errors="replace"))
                        if isinstance(data, dict):
                            results.append(data)
                    except Exception:
                        logger.debug("yaml_parse_error", path=str(full))
        return results

    def get_namespaced_resources(
        self,
        resource_group: str,
        namespaces: list[str] | None = None,
    ) -> list[dict]:
        """Read namespace-scoped resource YAMLs (e.g. 'inferenceservice').

        Searches under ``namespaces/<ns>/`` for YAML files whose name or
        parent directory matches *resource_group* (case-insensitive).

        Args:
            resource_group: CR kind to search for (e.g. 'inferenceservice').
            namespaces: Limit search to these namespaces.  ``None`` = all.

        Returns:
            List of parsed YAML dicts.
        """
        ns_root = self._root / "namespaces"
        if not ns_root.is_dir():
            return []

        search_dirs: list[Path] = []
        if namespaces:
            for ns in namespaces:
                ns_dir = ns_root / ns
                if ns_dir.is_dir():
                    search_dirs.append(ns_dir)
        else:
            search_dirs = [d for d in ns_root.iterdir() if d.is_dir()]

        results: list[dict] = []
        rg_lower = resource_group.lower()
        for ns_dir in search_dirs:
            for dirpath, _, filenames in os.walk(ns_dir):
                dir_lower = Path(dirpath).name.lower()
                for fn in filenames:
                    if not fn.endswith(".yaml"):
                        continue
                    if rg_lower not in fn.lower() and rg_lower not in dir_lower:
                        continue
                    full = Path(dirpath) / fn
                    try:
                        data = yaml.safe_load(full.read_text(errors="replace"))
                        if isinstance(data, dict):
                            items = data.get("items", None)
                            if items is not None and isinstance(items, list):
                                results.extend(
                                    item for item in items if isinstance(item, dict)
                                )
                            else:
                                results.append(data)
                    except Exception:
                        logger.debug("yaml_parse_error", path=str(full))
        return results

    # -- internal helpers --

    def _parse_pod_yaml(self, path: Path, namespace: str) -> MustGatherPodInfo | None:
        try:
            data = yaml.safe_load(path.read_text(errors="replace"))
        except Exception:
            logger.debug("pod_yaml_parse_error", path=str(path))
            return None

        if not isinstance(data, dict):
            return None

        metadata = data.get("metadata", {})
        status = data.get("status", {})
        pod_name = metadata.get("name", path.parent.name)
        phase = status.get("phase", "Unknown")

        pod_status = "Unknown"
        restart_count = 0
        exit_code = None
        error_message = ""

        for cs in status.get("containerStatuses", []) + status.get("initContainerStatuses", []):
            restart_count = max(restart_count, cs.get("restartCount", 0))
            state = cs.get("state", {})
            last_state = cs.get("lastState", {})

            for st in (state, last_state):
                if "waiting" in st:
                    reason = st["waiting"].get("reason", "Waiting")
                    if reason in UNHEALTHY_STATUSES or pod_status == "Unknown":
                        pod_status = reason
                        error_message = st["waiting"].get("message", "")[:300]
                elif "terminated" in st:
                    ec = st["terminated"].get("exitCode")
                    if ec and ec != 0:
                        exit_code = ec
                        pod_status = st["terminated"].get("reason", f"Terminated(exit={ec})")
                        error_message = st["terminated"].get("message", "")[:300]
                elif "running" in st:
                    if pod_status == "Unknown":
                        pod_status = "Running"

        return MustGatherPodInfo(
            name=pod_name,
            namespace=namespace,
            phase=phase,
            status=pod_status,
            restart_count=restart_count,
            exit_code=exit_code,
            error_message=error_message,
        )

    def _parse_events_yaml(self, path: Path) -> list[MustGatherEvent]:
        try:
            data = yaml.safe_load(path.read_text(errors="replace"))
        except Exception:
            logger.debug("events_yaml_parse_error", path=str(path))
            return []

        if not isinstance(data, dict):
            return []

        events: list[MustGatherEvent] = []
        for item in data.get("items", []):
            ev_type = item.get("type", "Normal")
            reason = item.get("reason", "")
            message = item.get("message", "")
            involved = item.get("involvedObject", {})
            obj_name = involved.get("name", "")
            obj_kind = involved.get("kind", "")
            count = item.get("count", 1)

            events.append(MustGatherEvent(
                type=ev_type,
                reason=reason,
                message=message,
                involved_object=f"{obj_kind}/{obj_name}" if obj_kind else obj_name,
                count=count,
            ))

        return events

    def _collect_container_logs(self, pod_dir: Path) -> dict[str, str]:
        """Walk pod directory to find container log files."""
        logs: dict[str, str] = {}
        for child in pod_dir.iterdir():
            if not child.is_dir() or child.name == pod_dir.name:
                continue
            container_name = child.name
            for log_name in ("current.log", "previous.log"):
                log_path = child / container_name / "logs" / log_name
                if log_path.is_file():
                    content = self._read_tail(log_path, self._max_log_lines)
                    if content:
                        key = container_name if log_name == "current.log" else f"{container_name}(previous)"
                        logs[key] = content
        return logs

    @staticmethod
    def _read_tail(path: Path, max_lines: int) -> str:
        try:
            text = path.read_text(errors="replace")
            lines = text.strip().splitlines()
            if len(lines) > max_lines:
                lines = lines[-max_lines:]
            return "\n".join(lines)
        except Exception:
            return ""
