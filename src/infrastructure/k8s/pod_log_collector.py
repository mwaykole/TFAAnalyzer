"""Pod log collector for Kubernetes/OpenShift.

Fetches container logs from pods when test failures involve pod issues.
Helps distinguish between product bugs and infrastructure issues.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ContainerLog:
    """Logs from a single container."""
    container_name: str
    logs: str
    tail_lines: int
    truncated: bool = False


@dataclass
class PodLogs:
    """Logs collected from a pod."""
    pod_name: str
    namespace: str
    status: str
    phase: str
    containers: list[ContainerLog] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    conditions: dict[str, str] = field(default_factory=dict)
    error_summary: str = ""
    
    def to_context(self, max_lines: int = 50) -> str:
        """Format logs for LLM context."""
        parts = [
            f"## Pod: {self.pod_name} ({self.namespace})",
            f"Status: {self.status} | Phase: {self.phase}",
        ]
        
        if self.conditions:
            cond_str = ", ".join(f"{k}={v}" for k, v in self.conditions.items())
            parts.append(f"Conditions: {cond_str}")
        
        if self.error_summary:
            parts.append(f"Error: {self.error_summary}")
        
        if self.events:
            parts.append("\nRecent Events:")
            for event in self.events[-5:]:
                parts.append(f"  - {event}")
        
        for container in self.containers:
            parts.append(f"\n### Container: {container.container_name}")
            # Take last N lines
            log_lines = container.logs.strip().split('\n')
            if len(log_lines) > max_lines:
                log_lines = log_lines[-max_lines:]
                parts.append(f"(showing last {max_lines} lines)")
            parts.append("```")
            parts.append('\n'.join(log_lines))
            parts.append("```")
        
        return '\n'.join(parts)


class PodLogCollector:
    """Collector for pod logs from Kubernetes/OpenShift.
    
    Supports:
    - Direct kubernetes client
    - OpenShift CLI (oc)
    - kubectl fallback
    """
    
    def __init__(
        self,
        kubeconfig: str | None = None,
        context: str | None = None,
        use_cli: bool = True,
    ):
        """Initialize collector.
        
        Args:
            kubeconfig: Path to kubeconfig file
            context: Kubernetes context to use
            use_cli: Whether to use CLI (oc/kubectl) instead of client library
        """
        self.kubeconfig = kubeconfig
        self.context = context
        self.use_cli = use_cli
        self._client = None
    
    async def get_pod_logs(
        self,
        pod_name: str,
        namespace: str,
        tail_lines: int = 100,
        previous: bool = False,
    ) -> PodLogs:
        """Get logs from a pod.
        
        Args:
            pod_name: Name of the pod (can be partial, will match)
            namespace: Kubernetes namespace
            tail_lines: Number of log lines to fetch
            previous: Whether to get logs from previous container instance
            
        Returns:
            PodLogs with container logs and events
        """
        if self.use_cli:
            return await self._get_logs_via_cli(pod_name, namespace, tail_lines, previous)
        else:
            return await self._get_logs_via_client(pod_name, namespace, tail_lines, previous)
    
    async def _get_logs_via_cli(
        self,
        pod_name: str,
        namespace: str,
        tail_lines: int,
        previous: bool,
    ) -> PodLogs:
        """Get logs using oc/kubectl CLI."""
        import asyncio
        import shutil
        
        # Determine CLI to use
        cli = "oc" if shutil.which("oc") else "kubectl"
        
        # Build base command
        base_cmd = [cli]
        if self.kubeconfig:
            base_cmd.extend(["--kubeconfig", self.kubeconfig])
        if self.context:
            base_cmd.extend(["--context", self.context])
        base_cmd.extend(["-n", namespace])
        
        pod_logs = PodLogs(
            pod_name=pod_name,
            namespace=namespace,
            status="Unknown",
            phase="Unknown",
        )
        
        try:
            # Get pod info
            describe_cmd = base_cmd + ["get", "pod", pod_name, "-o", "json"]
            proc = await asyncio.create_subprocess_exec(
                *describe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                import json
                pod_info = json.loads(stdout.decode())
                
                status = pod_info.get("status", {})
                pod_logs.phase = status.get("phase", "Unknown")
                
                # Get conditions
                for cond in status.get("conditions", []):
                    pod_logs.conditions[cond.get("type", "")] = cond.get("status", "")
                
                # Get container statuses
                container_statuses = status.get("containerStatuses", [])
                for cs in container_statuses:
                    state = cs.get("state", {})
                    if "waiting" in state:
                        pod_logs.status = state["waiting"].get("reason", "Waiting")
                        pod_logs.error_summary = state["waiting"].get("message", "")[:200]
                    elif "terminated" in state:
                        pod_logs.status = f"Terminated (exit {state['terminated'].get('exitCode', '?')})"
                        pod_logs.error_summary = state["terminated"].get("reason", "")
                    elif "running" in state:
                        pod_logs.status = "Running"
                
                # Get container names
                containers = [c.get("name") for c in pod_info.get("spec", {}).get("containers", [])]
            else:
                # Pod might not exist or name is partial
                logger.warning("pod_info_failed", 
                               pod=pod_name, 
                               error=stderr.decode()[:100])
                containers = ["main"]  # Default container name
            
            # Get logs for each container
            for container in containers:
                log_cmd = base_cmd + ["logs", pod_name, "-c", container, f"--tail={tail_lines}"]
                if previous:
                    log_cmd.append("--previous")
                
                proc = await asyncio.create_subprocess_exec(
                    *log_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                
                if proc.returncode == 0:
                    logs = stdout.decode()
                    pod_logs.containers.append(ContainerLog(
                        container_name=container,
                        logs=logs,
                        tail_lines=tail_lines,
                        truncated=len(logs.split('\n')) >= tail_lines,
                    ))
                else:
                    logger.debug("container_logs_failed",
                                 container=container,
                                 error=stderr.decode()[:50])
            
            # Get events
            events_cmd = base_cmd + [
                "get", "events",
                f"--field-selector=involvedObject.name={pod_name}",
                "--sort-by=.lastTimestamp",
                "-o", "custom-columns=MESSAGE:.message",
                "--no-headers",
            ]
            proc = await asyncio.create_subprocess_exec(
                *events_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                events = [e.strip() for e in stdout.decode().strip().split('\n') if e.strip()]
                pod_logs.events = events[-10:]  # Last 10 events
            
        except Exception as e:
            logger.error("pod_log_collection_failed",
                         pod=pod_name,
                         namespace=namespace,
                         error=str(e))
            pod_logs.error_summary = f"Failed to collect logs: {str(e)}"
        
        return pod_logs
    
    async def _get_logs_via_client(
        self,
        pod_name: str,
        namespace: str,
        tail_lines: int,
        previous: bool,
    ) -> PodLogs:
        """Get logs using kubernetes Python client."""
        try:
            from kubernetes import client, config
            
            # Load config
            if self.kubeconfig:
                config.load_kube_config(config_file=self.kubeconfig, context=self.context)
            else:
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config(context=self.context)
            
            v1 = client.CoreV1Api()
            
            pod_logs = PodLogs(
                pod_name=pod_name,
                namespace=namespace,
                status="Unknown",
                phase="Unknown",
            )
            
            # Get pod info
            try:
                pod = v1.read_namespaced_pod(pod_name, namespace)
                pod_logs.phase = pod.status.phase
                
                # Get conditions
                if pod.status.conditions:
                    for cond in pod.status.conditions:
                        pod_logs.conditions[cond.type] = cond.status
                
                # Get container statuses
                if pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        if cs.state.waiting:
                            pod_logs.status = cs.state.waiting.reason or "Waiting"
                            pod_logs.error_summary = (cs.state.waiting.message or "")[:200]
                        elif cs.state.terminated:
                            pod_logs.status = f"Terminated (exit {cs.state.terminated.exit_code})"
                            pod_logs.error_summary = cs.state.terminated.reason or ""
                        elif cs.state.running:
                            pod_logs.status = "Running"
                
                # Get container names
                containers = [c.name for c in pod.spec.containers]
            except Exception as e:
                logger.warning("pod_read_failed", error=str(e))
                containers = ["main"]
            
            # Get logs for each container
            for container in containers:
                try:
                    logs = v1.read_namespaced_pod_log(
                        pod_name,
                        namespace,
                        container=container,
                        tail_lines=tail_lines,
                        previous=previous,
                    )
                    pod_logs.containers.append(ContainerLog(
                        container_name=container,
                        logs=logs,
                        tail_lines=tail_lines,
                        truncated=len(logs.split('\n')) >= tail_lines,
                    ))
                except Exception as e:
                    logger.debug("container_log_failed", container=container, error=str(e))
            
            # Get events
            try:
                events = v1.list_namespaced_event(
                    namespace,
                    field_selector=f"involvedObject.name={pod_name}",
                )
                pod_logs.events = [
                    e.message for e in sorted(
                        events.items,
                        key=lambda x: x.last_timestamp or x.event_time,
                    )[-10:]
                ]
            except Exception as e:
                logger.debug("events_failed", error=str(e))
            
            return pod_logs
            
        except ImportError:
            logger.warning("kubernetes_client_not_available")
            return PodLogs(
                pod_name=pod_name,
                namespace=namespace,
                status="Unknown",
                phase="Unknown",
                error_summary="Kubernetes client not installed",
            )
    
    def extract_pod_info_from_logs(self, test_logs: str) -> list[tuple[str, str]]:
        """Extract pod names and namespaces from test logs.
        
        Args:
            test_logs: Test failure logs
            
        Returns:
            List of (pod_name, namespace) tuples
        """
        pods = []
        
        # Common patterns for pod references in test logs
        patterns = [
            # namespace/pod-name
            r"(?:pod|Pod)\s+([a-z0-9-]+)/([a-z0-9][a-z0-9-]*)",
            # pod pod-name in namespace ns
            r"[Pp]od\s+([a-z0-9][a-z0-9-]*)\s+in\s+(?:namespace\s+)?([a-z0-9-]+)",
            # waiting for pod xyz
            r"waiting.*?[Pp]od\s+([a-z0-9][a-z0-9-]*)",
            # pod/xyz CrashLoopBackOff
            r"([a-z0-9][a-z0-9-]*)\s+(?:CrashLoopBackOff|ImagePullBackOff|Error|Failed)",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, test_logs)
            for match in matches:
                if isinstance(match, tuple) and len(match) == 2:
                    pods.append(match)
                elif isinstance(match, str):
                    pods.append((match, ""))  # Unknown namespace
        
        # Deduplicate
        seen = set()
        unique_pods = []
        for pod, ns in pods:
            if pod not in seen:
                seen.add(pod)
                unique_pods.append((pod, ns))
        
        return unique_pods[:5]  # Limit to 5 pods
