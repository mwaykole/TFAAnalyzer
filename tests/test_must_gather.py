"""Tests for must-gather parser and analyzer."""

import json
import os
import tempfile
import zipfile
from pathlib import Path

import pytest
import yaml

from src.infrastructure.k8s.must_gather_parser import (
    MustGatherEvent,
    MustGatherParser,
    MustGatherPodInfo,
    MustGatherReport,
)
from src.infrastructure.k8s.must_gather_analyzer import MustGatherAnalyzer


def _build_pod_yaml(
    name: str,
    namespace: str,
    phase: str = "Running",
    container_state: str = "running",
    restart_count: int = 0,
    exit_code: int | None = None,
    wait_reason: str = "",
    wait_message: str = "",
) -> dict:
    """Helper to build a pod YAML dict matching `oc adm inspect` output."""
    state: dict = {}
    if container_state == "running":
        state = {"running": {"startedAt": "2025-01-01T00:00:00Z"}}
    elif container_state == "waiting":
        state = {"waiting": {"reason": wait_reason, "message": wait_message}}
    elif container_state == "terminated":
        state = {"terminated": {"exitCode": exit_code or 1, "reason": "Error"}}

    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {"containers": [{"name": "main"}]},
        "status": {
            "phase": phase,
            "containerStatuses": [
                {
                    "name": "main",
                    "state": state,
                    "lastState": {},
                    "restartCount": restart_count,
                }
            ],
        },
    }


def _build_events_yaml(events: list[dict]) -> dict:
    """Helper to build an events.yaml matching `oc adm inspect` output."""
    return {
        "apiVersion": "v1",
        "kind": "EventList",
        "items": [
            {
                "type": ev.get("type", "Warning"),
                "reason": ev.get("reason", "BackOff"),
                "message": ev.get("message", "Back-off restarting failed container"),
                "involvedObject": {
                    "kind": ev.get("kind", "Pod"),
                    "name": ev.get("object", "test-pod"),
                },
                "count": ev.get("count", 1),
            }
            for ev in events
        ],
    }


def _create_must_gather_tree(base: Path, ns_data: dict) -> Path:
    """Create a realistic must-gather directory tree under base.

    Args:
        base: Root directory.
        ns_data: Mapping of namespace -> {"pods": [...], "events": [...]}

    Returns:
        Path to the must-gather root.
    """
    mg_root = base / "must-gather.local.123456" / "quay.io-image"
    ns_dir = mg_root / "namespaces"

    for ns, data in ns_data.items():
        ns_path = ns_dir / ns

        # Write pod YAMLs and container logs
        for pod in data.get("pods", []):
            pod_name = pod["metadata"]["name"]
            pod_dir = ns_path / "pods" / pod_name
            pod_dir.mkdir(parents=True, exist_ok=True)

            yaml_path = pod_dir / f"{pod_name}.yaml"
            yaml_path.write_text(yaml.dump(pod))

            # Write a container log
            container = pod["spec"]["containers"][0]["name"]
            log_dir = pod_dir / container / container / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "current.log").write_text(
                f"INFO starting {pod_name}\nERROR something went wrong\n"
            )

        # Write events
        events_data = data.get("events", [])
        if events_data:
            core_dir = ns_path / "core"
            core_dir.mkdir(parents=True, exist_ok=True)
            (core_dir / "events.yaml").write_text(
                yaml.dump(_build_events_yaml(events_data))
            )

    return mg_root


# =============================================================================
# MustGatherParser tests
# =============================================================================


class TestMustGatherParser:
    """Tests for MustGatherParser."""

    @pytest.fixture
    def healthy_cluster(self, tmp_path: Path) -> Path:
        return _create_must_gather_tree(tmp_path, {
            "redhat-ods-applications": {
                "pods": [
                    _build_pod_yaml("odh-dashboard-abc", "redhat-ods-applications"),
                ],
                "events": [],
            },
        })

    @pytest.fixture
    def unhealthy_cluster(self, tmp_path: Path) -> Path:
        return _create_must_gather_tree(tmp_path, {
            "redhat-ods-applications": {
                "pods": [
                    _build_pod_yaml(
                        "modelmesh-serving-xyz", "redhat-ods-applications",
                        phase="Running", container_state="waiting",
                        wait_reason="CrashLoopBackOff",
                        wait_message="back-off 5m0s restarting failed container",
                        restart_count=12,
                    ),
                    _build_pod_yaml("odh-dashboard-abc", "redhat-ods-applications"),
                ],
                "events": [
                    {"type": "Warning", "reason": "BackOff", "message": "Back-off restarting failed container", "object": "modelmesh-serving-xyz", "count": 10},
                    {"type": "Warning", "reason": "Unhealthy", "message": "Readiness probe failed", "object": "modelmesh-serving-xyz", "count": 5},
                ],
            },
            "redhat-ods-operator": {
                "pods": [
                    _build_pod_yaml(
                        "rhods-operator-abc", "redhat-ods-operator",
                        phase="Failed", container_state="terminated",
                        exit_code=137,
                    ),
                ],
                "events": [
                    {"type": "Warning", "reason": "OOMKilling", "message": "Memory cgroup out of memory: Killed process", "object": "rhods-operator-abc"},
                ],
            },
        })

    def test_open_directory(self, healthy_cluster: Path):
        with MustGatherParser(healthy_cluster) as parser:
            namespaces = parser.list_namespaces()
            assert "redhat-ods-applications" in namespaces

    def test_open_nonexistent_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            MustGatherParser(tmp_path / "nonexistent").open()

    def test_open_zip(self, healthy_cluster: Path, tmp_path: Path):
        zip_path = tmp_path / "must-gather.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for root, _, files in os.walk(healthy_cluster):
                for f in files:
                    full = Path(root) / f
                    zf.write(full, full.relative_to(healthy_cluster.parent))

        with MustGatherParser(zip_path) as parser:
            namespaces = parser.list_namespaces()
            assert len(namespaces) >= 1

    def test_list_namespaces(self, unhealthy_cluster: Path):
        with MustGatherParser(unhealthy_cluster) as parser:
            ns = parser.list_namespaces()
            assert "redhat-ods-applications" in ns
            assert "redhat-ods-operator" in ns

    def test_get_pod_infos_healthy(self, healthy_cluster: Path):
        with MustGatherParser(healthy_cluster) as parser:
            pods = parser.get_pod_infos("redhat-ods-applications")
            assert len(pods) == 1
            assert pods[0].name == "odh-dashboard-abc"
            assert pods[0].status == "Running"
            assert not pods[0].is_unhealthy

    def test_get_pod_infos_unhealthy(self, unhealthy_cluster: Path):
        with MustGatherParser(unhealthy_cluster) as parser:
            pods = parser.get_pod_infos("redhat-ods-applications")
            crash_pods = [p for p in pods if p.is_unhealthy]
            assert len(crash_pods) == 1
            assert crash_pods[0].status == "CrashLoopBackOff"
            assert crash_pods[0].restart_count == 12

    def test_get_pod_infos_terminated(self, unhealthy_cluster: Path):
        with MustGatherParser(unhealthy_cluster) as parser:
            pods = parser.get_pod_infos("redhat-ods-operator")
            assert len(pods) == 1
            assert pods[0].exit_code == 137
            assert pods[0].is_unhealthy

    def test_get_events(self, unhealthy_cluster: Path):
        with MustGatherParser(unhealthy_cluster) as parser:
            events = parser.get_events("redhat-ods-applications")
            assert len(events) == 2
            warnings = [e for e in events if e.type == "Warning"]
            assert len(warnings) == 2

    def test_get_events_empty_namespace(self, healthy_cluster: Path):
        with MustGatherParser(healthy_cluster) as parser:
            events = parser.get_events("redhat-ods-applications")
            assert events == []

    def test_container_logs_collected(self, unhealthy_cluster: Path):
        with MustGatherParser(unhealthy_cluster) as parser:
            pods = parser.get_pod_infos("redhat-ods-applications")
            crash_pod = [p for p in pods if p.is_unhealthy][0]
            assert len(crash_pod.container_logs) > 0
            assert any("ERROR" in log for log in crash_pod.container_logs.values())

    def test_get_container_log_direct(self, unhealthy_cluster: Path):
        with MustGatherParser(unhealthy_cluster) as parser:
            log = parser.get_container_log(
                "redhat-ods-applications", "modelmesh-serving-xyz", "main"
            )
            assert "ERROR" in log


class TestMustGatherReport:
    """Tests for MustGatherReport.to_context()."""

    def test_healthy_report_context(self):
        report = MustGatherReport(cluster_health="healthy")
        ctx = report.to_context()
        assert "HEALTHY" in ctx

    def test_unhealthy_report_context(self):
        report = MustGatherReport(
            unhealthy_pods=[
                MustGatherPodInfo(
                    name="crash-pod",
                    namespace="ns",
                    phase="Running",
                    status="CrashLoopBackOff",
                    restart_count=10,
                    container_logs={"main": "FATAL: out of memory"},
                ),
            ],
            warning_events=[
                MustGatherEvent(
                    type="Warning",
                    reason="BackOff",
                    message="Back-off restarting failed container",
                    involved_object="Pod/crash-pod",
                    count=15,
                ),
            ],
            cluster_health="critical",
        )
        ctx = report.to_context()
        assert "CRITICAL" in ctx
        assert "crash-pod" in ctx
        assert "CrashLoopBackOff" in ctx
        assert "BackOff" in ctx
        assert "FATAL: out of memory" in ctx

    def test_context_limits_log_lines(self):
        long_log = "\n".join(f"line {i}" for i in range(100))
        report = MustGatherReport(
            unhealthy_pods=[
                MustGatherPodInfo(
                    name="pod1", namespace="ns", phase="Failed",
                    status="Error", container_logs={"main": long_log},
                ),
            ],
            cluster_health="degraded",
        )
        ctx = report.to_context(max_log_lines=5)
        assert "line 99" in ctx
        assert "line 90" not in ctx


# =============================================================================
# MustGatherAnalyzer tests
# =============================================================================


class TestMustGatherAnalyzer:
    """Tests for MustGatherAnalyzer."""

    @pytest.fixture
    def healthy_mg(self, tmp_path: Path) -> Path:
        return _create_must_gather_tree(tmp_path, {
            "redhat-ods-applications": {
                "pods": [
                    _build_pod_yaml("dashboard-1", "redhat-ods-applications"),
                    _build_pod_yaml("controller-1", "redhat-ods-applications"),
                ],
                "events": [],
            },
        })

    @pytest.fixture
    def critical_mg(self, tmp_path: Path) -> Path:
        return _create_must_gather_tree(tmp_path, {
            "redhat-ods-applications": {
                "pods": [
                    _build_pod_yaml(
                        "modelmesh-xyz", "redhat-ods-applications",
                        container_state="waiting",
                        wait_reason="CrashLoopBackOff",
                        restart_count=15,
                    ),
                    _build_pod_yaml(
                        "kserve-abc", "redhat-ods-applications",
                        phase="Failed", container_state="terminated",
                        exit_code=137,
                    ),
                ],
                "events": [
                    {"type": "Warning", "reason": "BackOff", "message": "container crash", "count": 20},
                    {"type": "Warning", "reason": "OOMKilled", "message": "out of memory", "count": 3},
                ],
            },
        })

    def test_analyze_healthy(self, healthy_mg: Path):
        analyzer = MustGatherAnalyzer(base_path=healthy_mg)
        report = analyzer.analyze()
        assert report.cluster_health == "healthy"
        assert len(report.unhealthy_pods) == 0

    def test_analyze_critical(self, critical_mg: Path):
        analyzer = MustGatherAnalyzer(base_path=critical_mg)
        report = analyzer.analyze()
        assert report.cluster_health in ("degraded", "critical")
        assert len(report.unhealthy_pods) >= 2
        assert len(report.warning_events) >= 1

    def test_analyze_nonexistent_path(self, tmp_path: Path):
        analyzer = MustGatherAnalyzer(base_path=tmp_path / "nonexistent")
        report = analyzer.analyze()
        assert report.cluster_health == "unknown"

    def test_analyze_with_explicit_path(self, critical_mg: Path, tmp_path: Path):
        analyzer = MustGatherAnalyzer(base_path=tmp_path / "does-not-exist")
        report = analyzer.analyze(must_gather_path=str(critical_mg))
        assert report.cluster_health in ("degraded", "critical")

    def test_auto_detect_test_directory(self, tmp_path: Path):
        """Test mapping a test name to its must-gather directory."""
        test_mg_dir = tmp_path / "inference" / "test_kserve" / "TestKServe" / "test_deploy"
        interact_dir = test_mg_dir / "pytest_exception_interact"
        interact_dir.mkdir(parents=True)

        mg_root = _create_must_gather_tree(interact_dir, {
            "redhat-ods-applications": {
                "pods": [
                    _build_pod_yaml(
                        "crash-pod", "redhat-ods-applications",
                        container_state="waiting", wait_reason="CrashLoopBackOff",
                        restart_count=5,
                    ),
                ],
                "events": [
                    {"type": "Warning", "reason": "BackOff", "message": "crash"},
                ],
            },
        })

        analyzer = MustGatherAnalyzer(base_path=tmp_path, auto_detect=True)
        report = analyzer.analyze(test_name="tests.inference.test_kserve::TestKServe::test_deploy")
        assert report.cluster_health != "unknown"
        assert len(report.unhealthy_pods) >= 1

    def test_event_deduplication(self, tmp_path: Path):
        mg_root = _create_must_gather_tree(tmp_path, {
            "ns1": {
                "pods": [],
                "events": [
                    {"type": "Warning", "reason": "BackOff", "message": "crash loop", "count": 5},
                    {"type": "Warning", "reason": "BackOff", "message": "crash loop", "count": 3},
                    {"type": "Warning", "reason": "Unhealthy", "message": "probe failed", "count": 1},
                ],
            },
        })
        analyzer = MustGatherAnalyzer(base_path=mg_root)
        report = analyzer.analyze()
        backoff_events = [e for e in report.warning_events if e.reason == "BackOff"]
        assert len(backoff_events) == 1
        assert backoff_events[0].count == 8

    def test_zip_support(self, critical_mg: Path, tmp_path: Path):
        """Test analyzing a zipped must-gather archive via explicit path."""
        zip_path = tmp_path / "mg.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for root, _, files in os.walk(critical_mg):
                for f in files:
                    full = Path(root) / f
                    zf.write(full, full.relative_to(critical_mg.parent))

        analyzer = MustGatherAnalyzer(base_path=tmp_path)
        report = analyzer.analyze(must_gather_path=str(zip_path))
        assert report.cluster_health in ("degraded", "critical")
        assert len(report.unhealthy_pods) >= 1


class TestHealthAssessment:
    """Tests for cluster health assessment logic."""

    def test_critical_when_crashloop_and_degraded(self):
        from src.infrastructure.k8s.must_gather_analyzer import MustGatherAnalyzer
        health = MustGatherAnalyzer._assess_health(
            unhealthy_pods=[
                MustGatherPodInfo(name="p", namespace="ns", phase="R", status="CrashLoopBackOff"),
            ],
            warning_events=[],
            operator_status={"dashboard": "Degraded"},
        )
        assert health == "critical"

    def test_degraded_when_crashloop_only(self):
        from src.infrastructure.k8s.must_gather_analyzer import MustGatherAnalyzer
        health = MustGatherAnalyzer._assess_health(
            unhealthy_pods=[
                MustGatherPodInfo(name="p", namespace="ns", phase="R", status="CrashLoopBackOff"),
            ],
            warning_events=[],
            operator_status={},
        )
        assert health == "degraded"

    def test_degraded_when_many_unhealthy(self):
        from src.infrastructure.k8s.must_gather_analyzer import MustGatherAnalyzer
        pods = [
            MustGatherPodInfo(name=f"p{i}", namespace="ns", phase="Failed", status="Error", exit_code=1)
            for i in range(4)
        ]
        health = MustGatherAnalyzer._assess_health(pods, [], {})
        assert health == "degraded"

    def test_warning_when_few_unhealthy(self):
        from src.infrastructure.k8s.must_gather_analyzer import MustGatherAnalyzer
        health = MustGatherAnalyzer._assess_health(
            unhealthy_pods=[
                MustGatherPodInfo(name="p", namespace="ns", phase="Failed", status="Error", exit_code=1),
            ],
            warning_events=[],
            operator_status={},
        )
        assert health == "warning"

    def test_healthy_when_no_issues(self):
        from src.infrastructure.k8s.must_gather_analyzer import MustGatherAnalyzer
        health = MustGatherAnalyzer._assess_health([], [], {})
        assert health == "healthy"
