"""Dashboard for failure trends, component health, and analytics."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.infrastructure.storage.sqlite_store import get_store
from src.utils.logging import get_logger

logger = get_logger(__name__)
console = Console()


@dataclass
class TrendData:
    date: str
    total: int
    product_bugs: int
    auto_issues: int
    infra_issues: int


@dataclass
class ComponentHealth:
    component: str
    total_failures: int
    product_bugs: int
    health_score: float


class Dashboard:
    def __init__(self, store=None):
        self.store = store or get_store()
    
    def get_trends(self, days: int = 30) -> list[TrendData]:
        return [
            TrendData(
                date=r["date"], total=r["total"],
                product_bugs=r["product_bugs"] or 0,
                auto_issues=r["auto_issues"] or 0,
                infra_issues=r["infra_issues"] or 0,
            )
            for r in self.store.get_trends_by_day(days)
        ]
    
    def get_component_health(self, days: int = 30) -> list[ComponentHealth]:
        return [
            ComponentHealth(
                component=r["component"], total_failures=r["total_failures"],
                product_bugs=r["product_bugs"] or 0, health_score=r["health_score"] or 0.0,
            )
            for r in self.store.get_component_health_score(days)
        ]
    
    def get_top_offenders(self, days: int = 30, limit: int = 10) -> list[dict[str, Any]]:
        return self.store.get_top_offenders(days=days, limit=limit)
    
    def print_trends(self, days: int = 30) -> None:
        trends = self.get_trends(days)
        if not trends:
            console.print("[yellow]No trend data available[/yellow]")
            return
        
        console.print(Panel.fit(f"[bold cyan]Failure Trends (Last {days} Days)[/bold cyan]", border_style="cyan"))
        
        table = Table()
        table.add_column("Date", style="cyan")
        table.add_column("Total", justify="right")
        table.add_column("Product Bugs", justify="right", style="red")
        table.add_column("Auto Issues", justify="right", style="yellow")
        table.add_column("Infra Issues", justify="right", style="blue")
        
        for t in trends[:14]:
            table.add_row(t.date, str(t.total), str(t.product_bugs), str(t.auto_issues), str(t.infra_issues))
        
        console.print(table)
        
        total = sum(t.total for t in trends)
        bugs = sum(t.product_bugs for t in trends)
        console.print(f"\n[bold]Total:[/bold] {total} failures, {bugs} product bugs ({bugs/total*100:.1f}%)" if total else "")
    
    def print_health(self, days: int = 30) -> None:
        health = self.get_component_health(days)
        if not health:
            console.print("[yellow]No component data available[/yellow]")
            return
        
        console.print(Panel.fit(f"[bold cyan]Component Health (Last {days} Days)[/bold cyan]", border_style="cyan"))
        
        for h in health:
            bar_len, filled = 20, int(h.health_score / 100 * 20)
            bar = "█" * filled + "░" * (bar_len - filled)
            color = "green" if h.health_score >= 80 else ("yellow" if h.health_score >= 50 else "red")
            status = "✅" if h.health_score >= 80 else ("⚠️" if h.health_score >= 50 else "❌")
            console.print(f"{h.component:20} [{color}]{bar}[/{color}] {h.health_score:5.1f}% {status} [dim]({h.total_failures} failures)[/dim]")
    
    def print_top_offenders(self, days: int = 30, limit: int = 10) -> None:
        offenders = self.get_top_offenders(days, limit)
        if not offenders:
            console.print("[yellow]No failure data available[/yellow]")
            return
        
        console.print(Panel.fit(f"[bold cyan]Top Failing Tests (Last {days} Days)[/bold cyan]", border_style="cyan"))
        
        table = Table()
        table.add_column("#", style="dim")
        table.add_column("Test Name", max_width=50)
        table.add_column("Failures", justify="right", style="red")
        table.add_column("Classifications")
        
        for i, o in enumerate(offenders, 1):
            table.add_row(str(i), o["test_name"][:50], str(o["failure_count"]), o["classifications"] or "")
        
        console.print(table)
    
    def generate_digest(self, days: int = 7) -> str:
        trends = self.get_trends(days)
        health = self.get_component_health(days)
        offenders = self.get_top_offenders(days, limit=5)
        
        total = sum(t.total for t in trends)
        bugs = sum(t.product_bugs for t in trends)
        auto = sum(t.auto_issues for t in trends)
        
        lines = [
            f"# Test Failure Digest ({datetime.now().strftime('%Y-%m-%d')})", "",
            f"**Period:** Last {days} days", "",
            "## Summary", "",
            f"- **Total Failures:** {total}",
            f"- **Product Bugs:** {bugs}",
            f"- **Automation Issues:** {auto}", "",
            "## Component Health", "",
        ]
        
        for h in health:
            emoji = "✅" if h.health_score >= 80 else ("⚠️" if h.health_score >= 50 else "❌")
            lines.append(f"- {h.component}: {h.health_score:.0f}% {emoji}")
        
        lines.extend(["", "## Top Failing Tests", ""])
        for i, o in enumerate(offenders, 1):
            lines.append(f"{i}. **{o['test_name'][:40]}** - {o['failure_count']} failures")
        
        return "\n".join(lines)
    
    def print_summary(self, days: int = 30) -> None:
        console.print()
        console.print(Panel.fit("[bold white on blue] 📊 Test Failure Analytics Dashboard [/bold white on blue]", border_style="blue"))
        console.print()
        self.print_health(days)
        console.print()
        self.print_trends(days)
        console.print()
        self.print_top_offenders(days, limit=5)
