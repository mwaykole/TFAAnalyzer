#!/usr/bin/env python3
"""
Test Failure Analyzer (TFA) - AI-powered analysis of test failures in ReportPortal.

This tool analyzes test failures using LLM to classify them as:
- Product Bug: Real defects in the product
- Test Automation Issue: Problems with test code
- Infrastructure Issue: Cluster/environment problems
- Intermittent Failure: Flaky tests that pass on re-run

Usage:
    # Basic analysis
    python main.py analyze -l LAUNCH_ID -c COMPONENT [--push]
    
    # Deep investigation with Thinker-Critic pattern
    python main.py investigate -l LAUNCH_ID -c COMPONENT [--push]
    
    # Start centralized API server for team (shared cache)
    python main.py serve --port 8000
    
    # Use server mode (shared cache across 30 users)
    python main.py analyze -l LAUNCH_ID -c COMPONENT --server http://tfa:8000 --push
    
    # Utility commands
    python main.py list-launches [-n 20]
    python main.py component-logs -l LAUNCH_ID [-c COMPONENT]
    python main.py test-history -l LAUNCH_ID [-c COMPONENT]
    python main.py stats [--days 30]
    python main.py dashboard [--days 30]
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

import typer

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from src.utils.config import create_settings
from src.utils.logging import setup_logging, get_logger

app = typer.Typer(
    name="tfa",
    help="Test Failure Analyzer - AI-powered analysis of ReportPortal test failures",
    add_completion=False,
)
console = Console()

# Global verbose flag
_verbose = False


def log_step(message: str, **kwargs):
    """Log a step with optional details."""
    if _verbose:
        details = " ".join(f"{k}={v}" for k, v in kwargs.items())
        console.print(f"[dim]› {message}[/dim] {details}" if details else f"[dim]› {message}[/dim]")


def log_debug(message: str, **kwargs):
    """Log debug info when verbose mode is on."""
    if _verbose:
        details = " ".join(f"{k}={v}" for k, v in kwargs.items())
        console.print(f"[dim cyan]  DEBUG: {message}[/dim cyan] {details}" if details else f"[dim cyan]  DEBUG: {message}[/dim cyan]")


@app.callback()
def main_callback(
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose logging for debugging"),
    ] = False,
):
    """Global options for TFA CLI."""
    global _verbose
    _verbose = verbose
    if verbose:
        setup_logging(level="DEBUG", log_format="console")
        console.print("[dim]Verbose logging enabled[/dim]")


# =============================================================================
# UTILITY COMMANDS
# =============================================================================


@app.command()
def list_launches(
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="ReportPortal project name", envvar="RP_PROJECT"),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to configuration file", exists=True),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Number of launches to show"),
    ] = 20,
) -> None:
    """List recent launches from ReportPortal."""
    setup_logging(level="WARNING", log_format="console")

    try:
        settings = create_settings(config)
        if project:
            settings.rp_project = project
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1) from e

    from src.infrastructure.reportportal import ReportPortalClient

    async def fetch_launches() -> None:
        rp_client = ReportPortalClient(
            url=settings.get_rp_url(),
            project=settings.get_rp_project(),
            username=settings.get_rp_username(),
            password=settings.get_rp_password(),
            verify_ssl=settings.reportportal.verify_ssl,
        )

        async with rp_client:
            launches, paged = await rp_client.get_launches(size=limit)

            table = Table(title=f"Recent Launches ({len(launches)} of {paged.total_elements})")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="white", max_width=50)
            table.add_column("Status", style="bold")
            table.add_column("Passed", style="green", justify="right")
            table.add_column("Failed", style="red", justify="right")
            table.add_column("Total", justify="right")

            for launch in launches:
                stats = launch.statistics or {}
                executions = stats.get("executions", {})
                status_color = "green" if launch.status == "PASSED" else "red"
                table.add_row(
                    str(launch.id),
                    (launch.name or "")[:50],
                    f"[{status_color}]{launch.status}[/{status_color}]",
                    str(executions.get("passed", 0)),
                    str(executions.get("failed", 0)),
                    str(executions.get("total", 0)),
                )

            console.print(table)

    try:
        asyncio.run(fetch_launches())
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def component_logs(
    launch_id: Annotated[
        str,
        typer.Option("--launch-id", "-l", help="ReportPortal launch ID"),
    ],
    component: Annotated[
        str | None,
        typer.Option("--component", "-c", help="Filter by component name"),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="ReportPortal project name", envvar="RP_PROJECT"),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to configuration file", exists=True),
    ] = None,
    full_logs: Annotated[
        bool,
        typer.Option("--full-logs", help="Show complete logs without truncation"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """Fetch and display component failures with logs."""
    setup_logging(level="WARNING", log_format="console")

    try:
        settings = create_settings(config)
        if project:
            settings.rp_project = project
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1) from e

    from src.infrastructure.reportportal import fetch_component_logs

    async def fetch() -> None:
        result = await fetch_component_logs(
            url=settings.get_rp_url(),
            project=settings.get_rp_project(),
            username=settings.get_rp_username(),
            password=settings.get_rp_password(),
            launch_id=launch_id,
            component_name=component,
            verify_ssl=settings.reportportal.verify_ssl,
        )

        if json_output:
            console.print(json.dumps(result.to_dict(), indent=2, default=str))
            return

        console.print(
            Panel(
                f"[bold]Launch:[/bold] {result.launch_name}\n"
                f"[bold]ID:[/bold] {result.launch_id}\n"
                f"[bold]Start Time:[/bold] {result.start_time}\n"
                f"[bold]Status:[/bold] {result.status}",
                title="Launch Information",
                border_style="blue",
            )
        )

        table = Table(title=f"Components ({len(result.components)})")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Failures", justify="right")

        for comp in result.components:
            status_color = "green" if comp.status == "PASSED" else "red" if comp.status == "FAILED" else "yellow"
            failures = len(comp.failures) if comp.failures else "-"
            table.add_row(comp.name[:55], f"[{status_color}]{comp.status}[/{status_color}]", str(failures))

        console.print(table)

        for comp in result.components:
            if comp.failures:
                console.print(f"\n[bold cyan]Component: {comp.name}[/bold cyan]")
                for failure in comp.failures:
                    console.print(f"\n  [red]✗[/red] {failure.test_item.name}")
                    if failure.logs:
                        max_len = None if full_logs else 800
                        log_text = failure.combined_logs[:max_len] if max_len else failure.combined_logs
                        if not full_logs and len(failure.combined_logs) > 800:
                            log_text += "\n... (truncated, use --full-logs for complete logs)"
                        console.print(f"    [dim]{log_text}[/dim]")

    try:
        asyncio.run(fetch())
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def test_history(
    launch_id: Annotated[
        str,
        typer.Option("--launch-id", "-l", help="ReportPortal launch ID"),
    ],
    component: Annotated[
        str | None,
        typer.Option("--component", "-c", help="Filter by component name"),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="ReportPortal project name", envvar="RP_PROJECT"),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to configuration file", exists=True),
    ] = None,
    history_depth: Annotated[
        int,
        typer.Option("--max-history", "-d", help="Number of past launches to check"),
    ] = 15,
) -> None:
    """Show pass/fail history for tests in a launch."""
    setup_logging(level="WARNING", log_format="console")

    try:
        settings = create_settings(config)
        if project:
            settings.rp_project = project
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1) from e

    from src.infrastructure.reportportal import fetch_component_logs
    from src.infrastructure.reportportal import fetch_test_history

    async def fetch() -> None:
        result = await fetch_component_logs(
            url=settings.get_rp_url(),
            project=settings.get_rp_project(),
            username=settings.get_rp_username(),
            password=settings.get_rp_password(),
            launch_id=launch_id,
            component_name=component,
            verify_ssl=settings.reportportal.verify_ssl,
        )

        histories = await fetch_test_history(
            url=settings.get_rp_url(),
            project=settings.get_rp_project(),
            username=settings.get_rp_username(),
            password=settings.get_rp_password(),
            launch_id=launch_id,
            max_history=history_depth,
            verify_ssl=settings.reportportal.verify_ssl,
        )

        console.print(f"[bold]Test History (last {history_depth} launches)[/bold]\n")

        table = Table()
        table.add_column("Test Name", style="cyan", max_width=50)
        table.add_column("Pass Rate", justify="right")
        table.add_column("Passed", style="green", justify="right")
        table.add_column("Failed", style="red", justify="right")
        table.add_column("Flaky?", justify="center")

        for test_name, history in sorted(histories.items(), key=lambda x: x[1].pass_rate):
            flaky = "[yellow]⚠ YES[/yellow]" if history.is_flaky else "[dim]No[/dim]"
            rate_color = "green" if history.pass_rate >= 80 else "yellow" if history.pass_rate >= 50 else "red"
            table.add_row(
                test_name[:50],
                f"[{rate_color}]{history.pass_rate:.0f}%[/{rate_color}]",
                str(history.passed_count),
                str(history.failed_count),
                flaky,
            )

        console.print(table)

    try:
        asyncio.run(fetch())
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def stats(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to look back"),
    ] = 30,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="Path to SQLite database"),
    ] = Path("tfa_history.db"),
) -> None:
    """Show analysis statistics and trends from stored history."""
    setup_logging(level="WARNING", log_format="console")

    from src.infrastructure.storage.sqlite_store import AnalysisStore

    if not db_path.exists():
        console.print("[yellow]No analysis history found. Run some analyses first.[/yellow]")
        raise typer.Exit(0)

    store = AnalysisStore(db_path)
    
    # Overall stats
    overall = store.get_stats()
    console.print(Panel(
        f"[bold]Total Analyses:[/bold] {overall.get('total_analyses', 0)}\n"
        f"[bold]Unique Launches:[/bold] {overall.get('unique_launches', 0)}\n"
        f"[bold]Unique Tests:[/bold] {overall.get('unique_tests', 0)}\n"
        f"[bold]Components:[/bold] {overall.get('unique_components', 0)}\n"
        f"[bold]First Analysis:[/bold] {overall.get('first_analysis', 'N/A')}\n"
        f"[bold]Last Analysis:[/bold] {overall.get('last_analysis', 'N/A')}",
        title="📊 Overall Statistics",
        border_style="blue",
    ))

    # Classification summary
    summary = store.get_classification_summary(days)
    if summary:
        table = Table(title=f"Classification Summary (Last {days} Days)")
        table.add_column("Classification")
        table.add_column("Count", justify="right")
        table.add_column("Percentage", justify="right")
        
        total = sum(summary.values())
        for cls, count in sorted(summary.items(), key=lambda x: -x[1]):
            icon = {"Product Bug": "🐛", "Test Automation Issue": "🔧", "Flaky Test": "⚡"}.get(cls, "❓")
            pct = (count / total * 100) if total > 0 else 0
            table.add_row(f"{icon} {cls}", str(count), f"{pct:.1f}%")
        
        console.print(table)

    # Component health
    health = store.get_component_health(days)
    if health:
        table = Table(title=f"Component Health (Last {days} Days)")
        table.add_column("Component", style="cyan")
        table.add_column("Total", justify="right")
        table.add_column("🐛 Bugs", justify="right", style="red")
        table.add_column("🔧 Auto", justify="right", style="yellow")
        table.add_column("⚡ Flaky", justify="right", style="blue")
        table.add_column("Avg Conf", justify="right")
        
        for row in health:
            table.add_row(
                row["component"] or "Unknown",
                str(row["total_failures"]),
                str(row["product_bugs"]),
                str(row["auto_issues"]),
                str(row["flaky_tests"]),
                f"{row['avg_confidence']:.0%}" if row["avg_confidence"] else "N/A",
            )
        
        console.print(table)

    # Potentially flaky tests
    flaky = store.get_flaky_tests(days)
    if flaky:
        console.print(f"\n[bold yellow]⚠️ Tests with Inconsistent Classifications ({len(flaky)}):[/bold yellow]")
        for test in flaky[:10]:
            console.print(f"  • {test['test_name'][:60]} - {test['classifications']}")

@app.command()
def accuracy_report(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to analyze"),
    ] = 30,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="Path to SQLite database"),
    ] = Path("tfa_history.db"),
) -> None:
    """Show accuracy metrics and classification report."""
    setup_logging(level="WARNING", log_format="console")
    
    from src.infrastructure.storage.sqlite_store import AnalysisStore
    
    if not db_path.exists():
        console.print("[yellow]No analysis history found. Run some analyses first.[/yellow]")
        raise typer.Exit(0)
    
    store = AnalysisStore(db_path)
    
    console.print(Panel(
        "[bold]🎯 Classification Accuracy Report[/bold]",
        border_style="green",
    ))
    
    # Get model accuracy from feedback
    model_accuracy = store.get_model_accuracy(days)
    if model_accuracy:
        table = Table(title=f"Model Performance (Last {days} Days)")
        table.add_column("Model")
        table.add_column("Provider")
        table.add_column("Analyses", justify="right")
        table.add_column("Avg Confidence", justify="right")
        table.add_column("Feedback", justify="right")
        
        for row in model_accuracy:
            table.add_row(
                row["model"] or "Unknown",
                row["provider"] or "N/A",
                str(row["total_analyses"]),
                f"{row['avg_confidence']:.0%}" if row["avg_confidence"] else "N/A",
                str(row["feedback_count"]),
            )
        console.print(table)
    
    # Get flaky tests (inconsistent classifications)
    flaky = store.get_flaky_tests(days)
    if flaky:
        console.print(f"\n[yellow]⚠️ Tests with Inconsistent Classifications ({len(flaky)}):[/yellow]")
        for test in flaky[:10]:
            console.print(f"  • {test['test_name'][:50]}...")
            console.print(f"    Classifications: {test['classifications']}")
    
    # Get classification summary
    summary = store.get_classification_summary(days)
    if summary:
        console.print(f"\n[bold]Classification Distribution (Last {days} Days):[/bold]")
        total = sum(summary.values())
        for cls, count in sorted(summary.items(), key=lambda x: -x[1]):
            pct = count / total * 100 if total > 0 else 0
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            console.print(f"  {cls:25} {bar} {count:4} ({pct:.1f}%)")


@app.command()
def record_feedback(
    analysis_id: Annotated[
        int,
        typer.Option("--id", "-i", help="Analysis ID from database"),
    ],
    correct_classification: Annotated[
        str,
        typer.Option("--correct", "-c", help="Correct classification"),
    ],
    feedback_by: Annotated[
        str,
        typer.Option("--by", "-b", help="Who provided feedback"),
    ] = "",
    db_path: Annotated[
        Path,
        typer.Option("--db", help="Path to SQLite database"),
    ] = Path("tfa_history.db"),
) -> None:
    """Record feedback/correction for a classification.
    
    Use this to improve accuracy by correcting misclassifications.
    
    Example:
        python main.py record-feedback --id 42 --correct "Product Bug" --by "John"
    """
    setup_logging(level="WARNING", log_format="console")
    
    from src.infrastructure.storage.sqlite_store import AnalysisStore
    
    if not db_path.exists():
        console.print("[red]Database not found[/red]")
        raise typer.Exit(1)
    
    store = AnalysisStore(db_path)
    
    # Get original analysis
    with store._conn() as conn:
        cursor = conn.execute(
            "SELECT test_name, classification FROM analyses WHERE id = ?",
            (analysis_id,)
        )
        row = cursor.fetchone()
        if not row:
            console.print(f"[red]Analysis {analysis_id} not found[/red]")
            raise typer.Exit(1)
        
        original = row["classification"]
    
    # Record feedback
    store.record_feedback(
        analysis_id=analysis_id,
        original_classification=original,
        corrected_classification=correct_classification,
        feedback_by=feedback_by,
    )
    
    if original == correct_classification:
        console.print(f"[green]✓[/green] Confirmed classification: {correct_classification}")
    else:
        console.print(f"[yellow]✓[/yellow] Recorded correction: {original} → {correct_classification}")


@app.command()
def parse_logs(
    log_file: Annotated[
        Path,
        typer.Argument(help="Path to log file to parse"),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """Parse a log file and extract structured error information.
    
    Useful for debugging and understanding how the log parser works.
    """
    setup_logging(level="WARNING", log_format="console")
    
    from src.utils.log_parser import parse_logs as do_parse
    
    if not log_file.exists():
        console.print(f"[red]File not found: {log_file}[/red]")
        raise typer.Exit(1)
    
    logs = log_file.read_text()
    parsed = do_parse(logs)
    
    if json_output:
        console.print(json.dumps(parsed.to_dict(), indent=2))
        return
    
    console.print(Panel("[bold]📋 Parsed Log Analysis[/bold]", border_style="blue"))
    
    if parsed.root_cause:
        console.print(f"\n[bold red]Root Cause:[/bold red]")
        console.print(f"  Exception: {parsed.root_cause.exception_type}")
        console.print(f"  Message: {parsed.root_cause.message[:200]}")
        console.print(f"  Severity: {parsed.root_cause.severity}")
        
        if parsed.root_cause.stack_frames:
            console.print(f"\n  Stack Trace ({len(parsed.root_cause.stack_frames)} frames):")
            for frame in parsed.root_cause.stack_frames[-5:]:
                console.print(f"    {frame.file_path}:{frame.line_number} in {frame.function_name}")
    
    if parsed.error_count > 1:
        console.print(f"\n[bold]Additional Errors ({parsed.error_count - 1}):[/bold]")
        for err in parsed.errors[1:5]:
            console.print(f"  • {err.exception_type}: {err.message[:80]}")
    
    console.print(f"\n[bold]Indicators:[/bold]")
    console.print(f"  Timeout: {'Yes' if parsed.has_timeout else 'No'}")
    console.print(f"  Assertion Error: {'Yes' if parsed.has_assertion_error else 'No'}")
    console.print(f"  Connection Error: {'Yes' if parsed.has_connection_error else 'No'}")
    console.print(f"  Resource Error: {'Yes' if parsed.has_resource_error else 'No'}")
    
    if parsed.key_indicators:
        console.print(f"\n[bold]Classification Hints:[/bold]")
        for ind in parsed.key_indicators[:10]:
            console.print(f"  • {ind}")


# =============================================================================
# DEEP INVESTIGATION (shared by analyze --deep and investigate alias)
# =============================================================================


def _run_deep_analysis(
    launch_id: str,
    component: str,
    settings,
    provider: str,
    post_to_rp: bool,
    json_output: bool,
    verify: bool = False,
    analyze_history: bool = False,
    must_gather_path: str | None = None,
) -> None:
    """Run deep LLM-powered investigation using InvestigateRCAUseCase.

    Shared implementation for both ``analyze --deep`` and ``investigate``.
    """
    from src.utils.ui import CLASSIFICATION_ICONS, SEVERITY_ICONS
    from src.utils.metrics import start_metrics, finish_metrics
    from src.domain.services.verification_service import VerificationService, VerifyMode
    from src.domain.interfaces.notifier import AnalysisSummary
    from src.application.use_cases.investigate_rca import (
        InvestigateRCAUseCase,
        InvestigateRequest as UseCaseRequest,
    )
    from src.infrastructure.repositories.rp_repository import RPRepository

    # Determine verification mode
    if verify and analyze_history:
        verify_mode = VerifyMode.ALL
    elif verify:
        verify_mode = VerifyMode.RUN_TEST
    elif analyze_history:
        verify_mode = VerifyMode.ANALYZE_HISTORY
    else:
        verify_mode = VerifyMode.NONE

    log_step("Initializing LLM provider", provider=provider)
    llm_provider = _get_llm_provider(provider, settings)
    if not llm_provider:
        console.print(f"[yellow]Warning:[/yellow] LLM ({provider}) not available")
        raise typer.Exit(1)
    log_debug("LLM provider initialized", model=getattr(llm_provider, 'model_name', 'unknown'))

    # Create verification service if needed
    verification_service = None
    if verify_mode != VerifyMode.NONE:
        test_repo_path = None
        if settings.test_repo.enabled and settings.test_repo.local_path:
            test_repo_path = settings.test_repo.local_path

        verification_service = VerificationService(
            test_repo_path=test_repo_path,
            timeout=settings.verification.timeout_per_test,
            collect_must_gather=settings.verification.collect_must_gather,
        )
        log_step(f"Verification mode: {verify_mode.value}",
                 repo=test_repo_path if test_repo_path else "not configured")

    # Create code fetcher for test source analysis
    code_fetcher = None
    if settings.is_code_fetcher_enabled():
        from pathlib import Path
        if settings.test_repo.local_path:
            from src.infrastructure.code_fetcher.local_adapter import LocalCodeFetcher
            code_fetcher = LocalCodeFetcher(
                base_path=Path(settings.test_repo.local_path),
                github_repo=settings.test_repo.repo,
                github_branch=settings.test_repo.branch,
            )
            log_step("Code fetcher: local", path=settings.test_repo.local_path)
        elif settings.test_repo.repo:
            from src.infrastructure.code_fetcher.github_adapter import GitHubCodeFetcher
            code_fetcher = GitHubCodeFetcher(
                repo=settings.test_repo.repo,
                branch=settings.test_repo.branch,
                token=settings.get_github_token(),
                test_dir=settings.test_repo.test_dir,
                cache_dir=Path(settings.test_repo.cache_dir),
            )
            log_step("Code fetcher: GitHub", repo=settings.test_repo.repo)

    # Create notifiers for team alerts
    notifiers = []
    if settings.is_notifications_enabled():
        if settings.get_slack_webhook():
            from src.infrastructure.notifications.slack_notifier import SlackNotifier
            notifiers.append(SlackNotifier(settings.get_slack_webhook()))
            log_step("Notifications: Slack enabled")
        if settings.get_teams_webhook():
            from src.infrastructure.notifications.teams_notifier import TeamsNotifier
            notifiers.append(TeamsNotifier(settings.get_teams_webhook()))
            log_step("Notifications: Teams enabled")

    # Create must-gather analyzer if enabled or path provided
    mg_analyzer = None
    mg_base = must_gather_path or (settings.must_gather.base_path if settings.is_must_gather_enabled() else None)
    if mg_base:
        from src.infrastructure.k8s.must_gather_analyzer import MustGatherAnalyzer
        mg_analyzer = MustGatherAnalyzer(
            base_path=mg_base,
            max_log_lines=settings.must_gather.max_log_lines,
            auto_detect=settings.must_gather.auto_detect,
        )
        log_step("Must-gather analyzer enabled", base_path=mg_base)

    # Start metrics tracking
    metrics = start_metrics(model=getattr(llm_provider, 'model_name', 'unknown'), provider=provider)

    # Initialize few-shot learning store
    failure_store = None
    try:
        from src.infrastructure.embeddings.failure_store import FailureEmbeddingStore
        cache_dir = Path(settings.cache_dir if hasattr(settings, 'cache_dir') else ".tfa_cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        failure_store = FailureEmbeddingStore(db_path=cache_dir / "failure_embeddings.db")
        log_step("Few-shot learning enabled", db=str(cache_dir / "failure_embeddings.db"))
    except Exception as e:
        log_debug(f"Few-shot learning unavailable: {e}")

    async def run_investigations() -> None:
        rp_repo = RPRepository(
            url=settings.get_rp_url(),
            project=settings.get_rp_project(),
            username=settings.get_rp_username(),
            password=settings.get_rp_password(),
            verify_ssl=settings.reportportal.verify_ssl,
        )

        use_case = InvestigateRCAUseCase(
            failure_repo=rp_repo,
            llm_provider=llm_provider,
            history_repo=rp_repo,
            verification_service=verification_service,
            code_fetcher=code_fetcher,
            must_gather_analyzer=mg_analyzer,
            failure_store=failure_store,
        )

        use_case_request = UseCaseRequest(
            launch_id=launch_id,
            component=component,
            push_to_rp=post_to_rp,
            verify_mode=verify_mode,
        )

        log_step("Connecting to ReportPortal")
        console.print(f"Fetching {component} failures from launch {launch_id}...")
        console.print(f"Using LLM: {provider} (Thinker-Critic pattern)")

        try:
            async with rp_repo:
                with console.status("[bold cyan]Investigating failures...[/bold cyan]"):
                    results = await use_case.execute(use_case_request)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            return

        if not results:
            console.print("[yellow]No failures found[/yellow]")
            return

        console.print(f"Investigated {len(results)} failure(s)")

        finish_metrics()

        if json_output:
            output = {
                "results": [r.to_dict() for r in results],
                "metrics": metrics.to_dict(),
            }
            console.print_json(data=output)
        else:
            _print_rca_results(results, launch_id, component)
            console.print()
            console.print(Panel(metrics.summary(), title="📊 Metrics", border_style="dim"))

        if post_to_rp:
            console.print(f"[green]✓[/green] Results posted to ReportPortal")

        if notifiers and results:
            log_step("Sending notifications")
            notif_summary = AnalysisSummary.from_results(
                launch_name=launch_id,
                launch_id=launch_id,
                component=component,
                results=[r.to_dict() for r in results],
                rp_url=settings.get_rp_url(),
            )
            for notifier in notifiers:
                try:
                    await notifier.send_summary(notif_summary)
                    console.print(f"[green]✓[/green] Sent notification to {notifier.channel_name}")
                except Exception as e:
                    console.print(f"[yellow]Warning:[/yellow] Failed to send {notifier.channel_name} notification: {e}")

    asyncio.run(run_investigations())


# =============================================================================
# INVESTIGATE (alias for analyze --deep, kept for backward compatibility)
# =============================================================================


@app.command()
def investigate(
    launch_id: Annotated[
        str,
        typer.Option("--launch-id", "-l", help="ReportPortal launch ID or full URL"),
    ],
    component: Annotated[
        str,
        typer.Option("--component", "-c", help="Component to investigate"),
    ],
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="ReportPortal project", envvar="RP_PROJECT"),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to config file", exists=True),
    ] = None,
    verify: Annotated[
        bool,
        typer.Option("--verify", help="Re-run tests using uv run pytest to verify"),
    ] = False,
    analyze_history: Annotated[
        bool,
        typer.Option("--analyze-history", help="Analyze pass/fail pattern from RP history + test code"),
    ] = False,
    post_to_rp: Annotated[
        bool,
        typer.Option("--push", help="Post results to ReportPortal"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
    provider: Annotated[
        str,
        typer.Option("--provider", help="LLM provider: claude-cli, anthropic, groq, ollama"),
    ] = "claude-cli",
    must_gather_path: Annotated[
        str | None,
        typer.Option("--must-gather-path", help="Path to must-gather artifacts directory"),
    ] = None,
) -> None:
    """Alias for 'analyze --deep'. Kept for backward compatibility.

    See 'analyze --help' for full documentation.
    """
    from src.utils.url_parser import extract_launch_id
    original_input = launch_id
    launch_id = extract_launch_id(launch_id)
    if original_input != launch_id:
        console.print(f"[dim]Extracted launch ID [cyan]{launch_id}[/cyan] from URL[/dim]")

    if not _verbose:
        setup_logging(level="WARNING", log_format="console")

    console.print("[dim]Tip: you can also use 'analyze --deep' instead of 'investigate'[/dim]")

    log_step("Loading configuration")
    try:
        settings = create_settings(config)
        if project:
            settings.rp_project = project
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1) from e

    _run_deep_analysis(
        launch_id=launch_id,
        component=component,
        settings=settings,
        provider=provider,
        post_to_rp=post_to_rp,
        json_output=json_output,
        verify=verify,
        analyze_history=analyze_history,
        must_gather_path=must_gather_path,
    )


def _get_llm_provider(provider: str, settings):
    """Initialize LLM provider using new infrastructure layer."""
    from src.infrastructure.llm.llm_factory import LLMFactory
    
    try:
        api_key = None
        if provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY") or getattr(settings, 'anthropic_api_key', None)
            if not api_key:
                console.print("[yellow]Warning:[/yellow] ANTHROPIC_API_KEY not set")
                return None
        elif provider == "groq":
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                console.print("[yellow]Warning:[/yellow] GROQ_API_KEY not set")
                return None
        
        return LLMFactory.create(provider, api_key=api_key)
    except Exception as e:
        console.print(f"[red]LLM init error:[/red] {e}")
    return None



def _print_rca_results(results: list, launch_name: str, component: str) -> None:
    """Print investigation results to console."""
    from src.utils.ui import CLASSIFICATION_ICONS, SEVERITY_ICONS
    
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]🔍 Investigation Results[/bold cyan]\n"
        f"Launch: {launch_name}\n"
        f"Component: {component}\n"
        f"Failures: {len(results)}",
        border_style="cyan",
    ))
    
    for resp in results:
        rca = resp.rca
        category = rca.category.value
        severity = rca.severity.value
        icon = CLASSIFICATION_ICONS.get(category, "❓")
        sev_icon = SEVERITY_ICONS.get(severity, "⚪")
        
        console.print()
        console.print(f"[bold]{icon} {resp.test_name[:60]}[/bold]")
        console.print(f"   Classification: {category}")
        console.print(f"   Severity: {sev_icon} {severity} | Confidence: {rca.confidence * 100:.0f}%")
        if resp.calibrated_confidence is not None:
            console.print(f"   Calibrated: {resp.calibrated_confidence * 100:.0f}% ({resp.confidence_explanation or ''})")
        console.print(f"   Root Cause: [dim]{rca.root_cause[:100]}[/dim]")
        console.print(f"   [dim]{rca.reasoning[:150]}[/dim]")
        
        if resp.timeout_analysis:
            verdict = resp.timeout_analysis.get("verdict", "")
            if verdict:
                console.print(f"   Timeout: [dim]{verdict}[/dim]")
        
        if resp.cluster_info:
            cause = resp.cluster_info.get("likely_root_cause", "")
            affected = resp.cluster_info.get("affected_tests", 0)
            if cause:
                console.print(f"   Cluster: [dim]{cause} ({affected} tests affected)[/dim]")
        
        if resp.verification_result and resp.verification_result != "not_run":
            v_dict = resp.verification_details or {}
            v_reason = v_dict.get("reason", "")
            v_inner = v_dict.get("details", {})
            v_exit = v_inner.get("exit_code", "")
            v_line = f"   Verification: {resp.verification_result}"
            if v_exit != "":
                v_line += f" (exit={v_exit})"
            if v_reason:
                v_line += f" — {v_reason[:120]}"
            console.print(v_line)
            v_output = v_dict.get("output", "")
            if v_output and resp.verification_result in ("failed", "error"):
                last_lines = "\n".join(v_output.strip().splitlines()[-5:])
                console.print(f"   [dim]{last_lines}[/dim]")
    
    summary: dict[str, int] = {}
    for resp in results:
        cat = resp.rca.category.value
        summary[cat] = summary.get(cat, 0) + 1
    
    console.print()
    table = Table(title="Summary")
    table.add_column("Classification")
    table.add_column("Count", justify="right")
    for c, count in summary.items():
        icon = CLASSIFICATION_ICONS.get(c, "❓")
        table.add_row(f"{icon} {c}", str(count))
    console.print(table)


# =============================================================================
# LEARNING COMMANDS
# =============================================================================


@app.command()
def learn(
    stats: Annotated[
        bool,
        typer.Option("--stats", "-s", help="Show pattern learning statistics"),
    ] = False,
    add: Annotated[
        bool,
        typer.Option("--add", "-a", help="Add a new pattern manually"),
    ] = False,
    rules_file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Path to classification rules YAML file"),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to configuration file", exists=True),
    ] = None,
) -> None:
    """Manage custom classification patterns.
    
    Patterns are stored in classification_rules.yaml under the custom_rules section.
    You can also edit the file directly.
    """
    setup_logging(level="WARNING", log_format="console")

    from src.learning.pattern_learner import PatternLearner

    learner = PatternLearner(rules_file=rules_file)

    if stats:
        _show_learning_stats(learner)
        return

    if add:
        _add_pattern_interactive(learner)
        return

    # Default: show summary
    _show_learning_summary(learner)


def _show_learning_stats(learner) -> None:
    """Show custom rule statistics."""
    stats = learner.get_pattern_stats()
    
    console.print(Panel.fit(
        "[bold cyan]Custom Rules Statistics[/bold cyan]",
        border_style="cyan",
    ))
    
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")
    
    table.add_row("Custom Rules", str(stats.get("total_custom_rules", 0)))
    table.add_row("Rules File", stats.get("rules_file", "classification_rules.yaml"))
    
    console.print(table)
    
    by_category = stats.get("by_category", {})
    if by_category:
        console.print("\n[bold]Custom Rules by Category:[/bold]")
        cat_table = Table()
        cat_table.add_column("Category", style="cyan")
        cat_table.add_column("Count", justify="right")
        
        for cat, count in by_category.items():
            cat_table.add_row(cat, str(count))
        
        console.print(cat_table)
    
    console.print(f"\n[dim]Edit {stats.get('rules_file')} directly to add/modify patterns[/dim]")


def _show_learning_summary(learner) -> None:
    """Show summary of custom rules."""
    patterns = learner.get_custom_rules()
    stats = learner.get_pattern_stats()
    
    console.print(Panel.fit(
        "[bold cyan]Custom Classification Rules[/bold cyan]",
        border_style="cyan",
    ))
    
    console.print(f"[green]✓[/green] Custom rules: {len(patterns)}")
    console.print(f"[dim]📁 File: {stats.get('rules_file')}[/dim]")
    
    if patterns:
        console.print("\n[bold]Custom Rules:[/bold]")
        for p in patterns[:5]:
            console.print(f"  [{p.category}] {p.description or p.pattern[:40]}")
        if len(patterns) > 5:
            console.print(f"  [dim]... and {len(patterns) - 5} more[/dim]")
    
    console.print("\n[dim]Commands:[/dim]")
    console.print("[dim]  tfa learn --add    Add a new custom rule[/dim]")
    console.print("[dim]  tfa learn --stats  Show statistics[/dim]")
    console.print(f"[dim]  Or edit {stats.get('rules_file')} custom_rules section directly[/dim]")


def _add_pattern_interactive(learner) -> None:
    """Interactively add a new custom rule."""
    console.print(Panel.fit(
        "[bold cyan]Add Custom Rule[/bold cyan]",
        border_style="cyan",
    ))
    
    pattern = typer.prompt("Regex pattern to match")
    
    console.print("\nCategories:")
    console.print("  1. Product Bug")
    console.print("  2. Test Automation Issue")
    console.print("  3. Infrastructure Issue")
    
    cat_choice = typer.prompt("Category (1-3)", default="1")
    categories = {
        "1": "Product Bug",
        "2": "Test Automation Issue", 
        "3": "Infrastructure Issue",
    }
    category = categories.get(cat_choice, "Product Bug")
    
    description = typer.prompt("Description", default="")
    
    try:
        import re
        re.compile(pattern)
    except re.error as e:
        console.print(f"[red]Invalid regex pattern:[/red] {e}")
        raise typer.Exit(1)
    
    rule_name = learner.add_custom_rule(
        pattern=pattern,
        category=category,
        description=description,
    )
    
    console.print(f"\n[green]✓[/green] Rule added: {rule_name}")
    console.print(f"  [{category}] {description or pattern[:40]}")


@app.command()
def trends(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to analyze"),
    ] = 30,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to configuration file", exists=True),
    ] = None,
) -> None:
    """Show failure trends over time."""
    setup_logging(level="WARNING", log_format="console")

    from src.reporting.dashboard import Dashboard
    
    dashboard = Dashboard()
    dashboard.print_trends(days)


@app.command()
def health(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to analyze"),
    ] = 30,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to configuration file", exists=True),
    ] = None,
) -> None:
    """Show component health dashboard."""
    setup_logging(level="WARNING", log_format="console")

    from src.reporting.dashboard import Dashboard
    
    dashboard = Dashboard()
    dashboard.print_health(days)


@app.command()
def dashboard(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to analyze"),
    ] = 30,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to configuration file", exists=True),
    ] = None,
) -> None:
    """Show full analytics dashboard with trends, health, and top offenders."""
    setup_logging(level="WARNING", log_format="console")

    from src.reporting.dashboard import Dashboard
    
    dash = Dashboard()
    dash.print_summary(days)


@app.command()
def digest(
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to include"),
    ] = 7,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file for digest"),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to configuration file", exists=True),
    ] = None,
) -> None:
    """Generate weekly digest report."""
    setup_logging(level="WARNING", log_format="console")

    from src.reporting.dashboard import Dashboard
    
    dash = Dashboard()
    digest_text = dash.generate_digest(days)
    
    if output:
        output.write_text(digest_text)
        console.print(f"[green]✓[/green] Digest saved to {output}")
    else:
        console.print(digest_text)



@app.command()
def feedback(
    logs: Annotated[
        str,
        typer.Argument(help="Error logs or description of the failure"),
    ],
    correct_category: Annotated[
        str,
        typer.Argument(help="Correct classification: 'Product Bug', 'Test Automation Issue', 'Infrastructure Issue'"),
    ],
    original_category: Annotated[
        str,
        typer.Option("--original", "-o", help="Original (incorrect) classification"),
    ] = "Unknown",
    patterns_file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Path to learned patterns YAML file"),
    ] = None,
) -> None:
    """Record feedback from a classification correction.
    
    This extracts patterns from the error logs and adds them as suggestions.
    
    Example:
        tfa feedback "TimeoutError: waiting for metrics" "Test Automation Issue"
    """
    setup_logging(level="WARNING", log_format="console")

    from src.learning.pattern_learner import PatternLearner

    learner = PatternLearner(patterns_file=patterns_file)
    
    # Validate the correction
    valid_categories = ["Product Bug", "Test Automation Issue", "Infrastructure Issue"]
    if correct_category not in valid_categories:
        console.print(f"[red]Error:[/red] Invalid category. Must be one of: {', '.join(valid_categories)}")
        raise typer.Exit(1)
    
    # Extract and add pattern suggestions
    suggestions = learner.extract_patterns_from_feedback(
        original_category=original_category,
        corrected_category=correct_category,
        logs=logs,
    )
    
    if suggestions:
        console.print(f"[green]✓[/green] Extracted {len(suggestions)} pattern(s) from feedback")
        for s in suggestions:
            console.print(f"  [{s.target_category}] {s.description}")
        console.print("\n[dim]Use 'tfa learn --review' to approve these patterns[/dim]")
    else:
        console.print("[yellow]No patterns extracted from the provided logs[/yellow]")
        console.print("[dim]You can add a pattern manually with 'tfa learn --add'[/dim]")


# =============================================================================
# SERVER COMMANDS (Centralized Mode)
# =============================================================================


@app.command()
def serve(
    host: Annotated[
        str,
        typer.Option("--host", "-h", help="Host to bind to"),
    ] = "0.0.0.0",
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Port to listen on"),
    ] = 8000,
    reload: Annotated[
        bool,
        typer.Option("--reload", help="Enable auto-reload for development"),
    ] = False,
    workers: Annotated[
        int,
        typer.Option("--workers", "-w", help="Number of worker processes"),
    ] = 1,
) -> None:
    """Start the TFA API server for centralized analysis.
    
    This enables 30 QE engineers to share:
    - Analysis cache (avoid duplicate LLM calls)
    - Classification results via ReportPortal
    - Consistent configuration
    
    Example:
        python main.py serve --port 8000
        
    Then use CLI with --server flag:
        python main.py analyze --server http://localhost:8000 -l 9657 -c Model_server
    """
    import uvicorn
    
    console.print(Panel.fit(
        "[bold cyan]🚀 Starting TFA API Server[/bold cyan]\n"
        f"Host: {host}:{port}\n"
        f"Workers: {workers}\n"
        f"Reload: {'enabled' if reload else 'disabled'}\n\n"
        "[dim]API docs available at /docs[/dim]",
        border_style="cyan",
    ))
    
    uvicorn.run(
        "src.api.server:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers if not reload else 1,
    )


@app.command()
def analyze(
    launch_id: Annotated[
        str,
        typer.Option("--launch-id", "-l", help="ReportPortal launch ID or full URL (e.g., https://rp.example.com/ui/#project/launches/all/9657)"),
    ],
    component: Annotated[
        str,
        typer.Option("--component", "-c", help="Component to analyze"),
    ],
    deep: Annotated[
        bool,
        typer.Option("--deep", "-d", help="Deep LLM analysis with Thinker-Critic pattern, clustering, and calibration"),
    ] = False,
    server: Annotated[
        str | None,
        typer.Option("--server", "-s", help="TFA server URL (e.g., http://tfa.internal:8000)"),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="ReportPortal project", envvar="RP_PROJECT"),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to config file", exists=True),
    ] = None,
    push_to_rp: Annotated[
        bool,
        typer.Option("--push", help="Push results to ReportPortal"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without pushing to RP"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
    provider: Annotated[
        str,
        typer.Option("--provider", help="LLM provider: claude-cli, anthropic, groq, ollama"),
    ] = "claude-cli",
    no_cache: Annotated[
        bool,
        typer.Option("--no-cache", help="Skip cache and force fresh analysis"),
    ] = False,
    no_llm: Annotated[
        bool,
        typer.Option("--no-llm", help="Use only rule-based classification (fast path only)"),
    ] = False,
    verify: Annotated[
        bool,
        typer.Option("--verify", help="Re-run tests using uv run pytest to verify (requires --deep)"),
    ] = False,
    analyze_history: Annotated[
        bool,
        typer.Option("--analyze-history", help="Analyze RP history for flakiness patterns (requires --deep)"),
    ] = False,
    must_gather_path: Annotated[
        str | None,
        typer.Option("--must-gather-path", help="Path to pre-collected must-gather artifacts (requires --deep)"),
    ] = None,
) -> None:
    """Analyze test failures using AI classification.
    
    Two modes:
    
    Fast (default): Rule-based pattern matching -- instant, no LLM cost.
    
    Deep (--deep): Full LLM Thinker-Critic analysis with failure clustering,
    timeout analysis, confidence calibration, and optional verification.
    
    Examples:
        # Fast classification
        python main.py analyze -l 9657 -c Model_server --push
        
        # Deep LLM investigation
        python main.py analyze -l 9657 -c Model_server --deep --push
        
        # Deep + verify + history analysis
        python main.py analyze -l 9657 -c Model_server --deep --verify --analyze-history
        
        # Deep + must-gather cluster diagnostics
        python main.py analyze -l 9657 -c Model_server --deep --must-gather-path /path/to/artifacts
        
        # Server mode (shared cache)
        python main.py analyze -l 9657 -c Model_server --server http://tfa:8000 --push
        
    Use -v/--verbose for detailed debugging output.
    """
    from src.utils.url_parser import extract_launch_id, is_rp_url
    original_input = launch_id
    launch_id = extract_launch_id(launch_id)
    if original_input != launch_id:
        console.print(f"[dim]Extracted launch ID [cyan]{launch_id}[/cyan] from URL[/dim]")
    
    if not _verbose:
        setup_logging(level="WARNING", log_format="console")
    
    # Auto-enable --deep when deep-only flags are used
    if (verify or analyze_history or must_gather_path) and not deep:
        deep = True
        console.print("[dim]Auto-enabled --deep mode (required by --verify/--analyze-history/--must-gather-path)[/dim]")
    
    # Server mode: Use centralized API
    if server:
        log_step("Using server mode", server=server)
        asyncio.run(_analyze_via_server(
            server_url=server,
            launch_id=launch_id,
            component=component,
            push_to_rp=push_to_rp and not dry_run,
            use_cache=not no_cache,
            use_llm=not no_llm,
            provider=provider,
            json_output=json_output,
        ))
        return
    
    log_step("Loading configuration")
    try:
        settings = create_settings(config)
        if project:
            settings.rp_project = project
        log_debug("Configuration loaded", project=settings.get_rp_project())
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1) from e
    
    # Deep mode: full LLM Thinker-Critic pipeline
    if deep:
        _run_deep_analysis(
            launch_id=launch_id,
            component=component,
            settings=settings,
            provider=provider,
            post_to_rp=push_to_rp and not dry_run,
            json_output=json_output,
            verify=verify,
            analyze_history=analyze_history,
            must_gather_path=must_gather_path,
        )
        return
    
    # Fast mode: rule-based pattern matching
    from src.infrastructure.reportportal import fetch_component_logs
    from src.domain.services.classification_service import ClassificationService
    
    log_step("Initializing classifier")
    classifier = ClassificationService()
    
    async def run_analysis() -> None:
        from src.infrastructure.reportportal import ReportPortalClient
        
        rp_client = ReportPortalClient(
            url=settings.get_rp_url(),
            project=settings.get_rp_project(),
            username=settings.get_rp_username(),
            password=settings.get_rp_password(),
            verify_ssl=settings.reportportal.verify_ssl,
        )
        
        async with rp_client:
            log_step("Connecting to ReportPortal")
            console.print(f"Fetching {component} failures from launch {launch_id}...")
            
            log_step("Fetching component logs", launch_id=launch_id, component=component)
            try:
                result = await fetch_component_logs(
                    url=settings.get_rp_url(),
                    project=settings.get_rp_project(),
                    username=settings.get_rp_username(),
                    password=settings.get_rp_password(),
                    launch_id=launch_id,
                    component_name=component,
                    verify_ssl=settings.reportportal.verify_ssl,
                )
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1) from e
            log_debug("Launch fetched", launch_name=result.launch_name)
            
            target = result.get_component(component)
            if not target or not target.failures:
                console.print("[yellow]No failures found[/yellow]")
                return
            
            total = len(target.failures)
            console.print(f"Found {total} failure(s)")
            log_debug("Starting analysis", failures=total)
            
            results = []
            rp_updates = []
            for i, failure in enumerate(target.failures, 1):
                log_step(f"Analyzing [{i}/{total}]: {failure.test_item.name[:40]}...")
                
                evidence = classifier.get_evidence_from_logs(failure.combined_logs)
                classification = classifier.classify(failure.combined_logs, evidence)
                log_debug("Classification result",
                          category=classification.category.value,
                          confidence=f"{classification.confidence:.0%}")
                
                results.append({
                    "test_name": failure.test_item.name,
                    "test_id": str(failure.test_item.id),
                    "classification": classification.category.value,
                    "confidence": classification.confidence,
                    "severity": classification.severity.value,
                    "reasoning": classification.reasoning,
                })
                
                if push_to_rp and not dry_run:
                    defect_type = classification.category.defect_type_code
                    comment = f"🤖 AI: {classification.category.value} ({classification.confidence_percent}%)\n{classification.reasoning}"
                    rp_updates.append(
                        rp_client.update_defect_type(str(failure.test_item.id), defect_type, comment)
                    )
            
            if rp_updates:
                log_step(f"Pushing {len(rp_updates)} results to ReportPortal in parallel...")
                await asyncio.gather(*rp_updates)
            
            if json_output:
                console.print_json(data=results)
            else:
                _print_analysis_results(results, result.launch_name, component, push_to_rp and not dry_run)
    
    asyncio.run(run_analysis())


async def _analyze_via_server(
    server_url: str,
    launch_id: str,
    component: str,
    push_to_rp: bool,
    use_cache: bool,
    use_llm: bool,
    provider: str,
    json_output: bool,
) -> None:
    """Analyze via centralized TFA server."""
    from src.api.client import TFAClient
    
    client = TFAClient(server_url)
    
    console.print(f"[dim]Connecting to TFA server: {server_url}[/dim]")
    
    if not await client.is_available():
        console.print(f"[red]Error:[/red] Server not available at {server_url}")
        raise typer.Exit(1)
    
    console.print(f"Analyzing {component} failures in launch {launch_id}...")
    
    try:
        response = await client.analyze(
            launch_id=launch_id,
            component=component,
            push_to_rp=push_to_rp,
            use_cache=use_cache,
            use_llm=use_llm,
            provider=provider,
        )
        
        if json_output:
            console.print_json(data=response)
        else:
            results = [
                {
                    "test_name": r["test_name"],
                    "test_id": r["test_id"],
                    "classification": r["classification"]["category"],
                    "confidence": r["classification"]["confidence"],
                    "severity": r["classification"]["severity"],
                    "reasoning": r.get("reasoning", ""),
                    "cached": r.get("cached", False),
                }
                for r in response.get("results", [])
            ]
            _print_analysis_results(results, f"Launch {launch_id}", component, push_to_rp)
            
            # Show cache statistics
            cached_count = sum(1 for r in response.get("results", []) if r.get("cached"))
            if cached_count:
                console.print(f"\n[dim]💾 {cached_count} result(s) from shared cache[/dim]")
    
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def _print_analysis_results(
    results: list[dict],
    launch_name: str,
    component: str,
    pushed: bool,
) -> None:
    """Print analysis results in a formatted table."""
    from src.utils.ui import CLASSIFICATION_ICONS, SEVERITY_ICONS
    
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]📊 Analysis Results[/bold cyan]\n"
        f"Launch: {launch_name}\n"
        f"Component: {component}\n"
        f"Failures: {len(results)}",
        border_style="cyan",
    ))
    
    for r in results:
        icon = CLASSIFICATION_ICONS.get(r["classification"], "❓")
        sev_icon = SEVERITY_ICONS.get(r["severity"], "⚪")
        cached = " [dim](cached)[/dim]" if r.get("cached") else ""
        
        console.print()
        console.print(f"[bold]{icon} {r['test_name'][:60]}[/bold]{cached}")
        console.print(f"   Classification: {r['classification']}")
        console.print(f"   Severity: {sev_icon} {r['severity']} | Confidence: {r['confidence']*100:.0f}%")
        if r.get("reasoning"):
            console.print(f"   [dim]{r['reasoning'][:150]}[/dim]")
    
    # Summary
    summary: dict[str, int] = {}
    for r in results:
        summary[r["classification"]] = summary.get(r["classification"], 0) + 1
    
    console.print()
    table = Table(title="Summary")
    table.add_column("Classification")
    table.add_column("Count", justify="right")
    for c, count in summary.items():
        icon = CLASSIFICATION_ICONS.get(c, "❓")
        table.add_row(f"{icon} {c}", str(count))
    console.print(table)
    
    if pushed:
        console.print(f"\n[green]✓[/green] Results pushed to ReportPortal")


if __name__ == "__main__":
    app()
