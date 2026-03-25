"""SentinelAI CLI — the primary interface for the framework.

Commands:
    sentinelai triage --file <path>    One-shot triage from JSON file
    sentinelai demo                    Run simulated incident with bundled fixture
    sentinelai doctor                  Validate setup (API keys, config, plugins)
    sentinelai validate-config         Check config without running
    sentinelai timeline [alert_id]     Show incident timeline events
    sentinelai explain <alert_id>      Show AI reasoning for a triage
    sentinelai costs                   Show API cost summary
    sentinelai plugin new              Generate plugin skeleton
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sentinelai.contracts.alert_source import AlertSource
from sentinelai.contracts.ticket_system import TicketSystem
from sentinelai.contracts.triage_engine import TriageEngine
from sentinelai.core.config import SentinelConfig
from sentinelai.core.errors import AlertSourceError, ConfigValidationError, PluginLoadError
from sentinelai.core.events import Priority, TriageComplete
from sentinelai.core.pipeline import Pipeline
from sentinelai.core.plugin import load_plugin

console = Console()

_SEVERITY_COLORS = {
    Priority.P1: "bold red",
    Priority.P2: "yellow",
    Priority.P3: "cyan",
    Priority.P4: "green",
    Priority.UNKNOWN: "dim",
}

_DEMO_ALERT = {
    "alert_id": "demo-001",
    "source": "demo",
    "service_name": "auth-service",
    "summary": "Error rate spike: 500 errors increased 340% in last 5 minutes. "
    "Connection pool exhaustion detected. Active connections: 100/100. "
    "Affected endpoint: POST /api/v1/auth/login",
    "raw_payload": {
        "error_rate": 0.34,
        "error_count": 847,
        "latency_p99_ms": 12400,
        "active_connections": 100,
        "max_connections": 100,
        "affected_endpoints": ["/api/v1/auth/login", "/api/v1/auth/refresh"],
        "recent_deploy": "v2.14.3 deployed 47 minutes ago",
    },
}


def _render_triage(result: TriageComplete) -> None:
    """Render a triage result with rich formatting."""
    severity_style = _SEVERITY_COLORS.get(result.severity, "dim")

    # Header panel
    console.print()
    console.print(
        Panel(
            f"[{severity_style}]{result.severity.value}[/{severity_style}] — Confidence: {result.confidence:.0%}",
            title=f"[bold]Triage Result: {result.alert_id}[/bold]",
            border_style=severity_style,
        )
    )

    # Details table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Root Cause", result.root_cause_hypothesis)
    table.add_row("Affected", ", ".join(result.affected_services))
    table.add_row("Action", result.recommended_action)
    console.print(table)

    # Reasoning (collapsible-style)
    console.print()
    console.print("[dim]AI Reasoning:[/dim]")
    console.print(f"[dim]{result.ai_reasoning[:500]}[/dim]")
    if len(result.ai_reasoning) > 500:
        console.print(f"[dim]... ({len(result.ai_reasoning)} chars total)[/dim]")
    console.print()


@click.group()
@click.version_option(package_name="sentinelai")
def cli() -> None:
    """SentinelAI — AI-powered DevOps automation framework."""


# Register subcommands from other modules
from sentinelai.cli.deploy import deploy as deploy_cmd
from sentinelai.cli.fix import fix as fix_cmd
from sentinelai.cli.scaffold import plugin as plugin_group
from sentinelai.cli.timeline import costs as costs_cmd
from sentinelai.cli.timeline import explain as explain_cmd
from sentinelai.cli.timeline import timeline as timeline_cmd

cli.add_command(timeline_cmd)
cli.add_command(explain_cmd)
cli.add_command(costs_cmd)
cli.add_command(plugin_group)
cli.add_command(fix_cmd)
cli.add_command(deploy_cmd)


def _load_ticket_system(config: SentinelConfig) -> TicketSystem | None:
    """Load the optional ticket system plugin. Returns None if not configured."""
    if not config.pipeline.ticket_system:
        return None
    try:
        return load_plugin(config.pipeline.ticket_system, TicketSystem)
    except PluginLoadError as e:
        console.print(f"[yellow]Ticket system plugin failed to load: {e}[/yellow]")
        console.print("[yellow]Continuing without ticket creation.[/yellow]")
        return None


@cli.command()
@click.option("--file", "file_path", required=True, type=click.Path(), help="Path to JSON alert file")
@click.option("--config", "config_path", default=None, type=click.Path(), help="Path to sentinelai.yaml")
def triage(file_path: str, config_path: str | None) -> None:
    """Triage alerts from a JSON file."""
    try:
        config = SentinelConfig.load(config_path)
    except ConfigValidationError as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    try:
        triage_engine = load_plugin(config.pipeline.triage_engine, TriageEngine)
    except PluginLoadError as e:
        console.print(f"[red]Plugin error:[/red] {e}")
        sys.exit(1)

    from sentinelai.plugins.sources.file_source import FileAlertSource

    ticket_system = _load_ticket_system(config)

    source = FileAlertSource(file_path)
    pipeline = Pipeline(config, source, triage_engine, ticket_system=ticket_system)

    try:
        results = asyncio.run(pipeline.run())
    except AlertSourceError as e:
        console.print(f"[red]Alert source error:[/red] {e}")
        sys.exit(1)

    if not results:
        console.print("[yellow]No alerts to triage.[/yellow]")
        return

    for result in results:
        _render_triage(result)

    console.print(f"[green]Triaged {len(results)} alert(s).[/green]")


@cli.command()
@click.option("--config", "config_path", default=None, type=click.Path(), help="Path to sentinelai.yaml")
def demo(config_path: str | None) -> None:
    """Run a simulated incident triage with a bundled demo alert.

    This uses the real triage engine (Claude) against a realistic demo alert.
    Requires ANTHROPIC_API_KEY to be set.
    """
    try:
        config = SentinelConfig.load(config_path)
    except ConfigValidationError as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    console.print("[bold]SentinelAI Demo[/bold] — simulated incident triage\n")
    console.print("[dim]Injecting demo alert: auth-service connection pool exhaustion...[/dim]")

    # Write demo alert to temp file and use file_source (per CODING-STANDARDS.md rule 2)
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_DEMO_ALERT, f)
        demo_file = f.name

    try:
        triage_engine = load_plugin(config.pipeline.triage_engine, TriageEngine)
    except PluginLoadError as e:
        console.print(f"[red]Plugin error:[/red] {e}")
        sys.exit(1)

    from sentinelai.plugins.sources.file_source import FileAlertSource

    source = FileAlertSource(demo_file)
    pipeline = Pipeline(config, source, triage_engine)

    try:
        results = asyncio.run(pipeline.run())
    except Exception as e:
        console.print(f"[red]Demo failed:[/red] {e}")
        sys.exit(1)
    finally:
        Path(demo_file).unlink(missing_ok=True)

    for result in results:
        _render_triage(result)

    console.print("[green bold]Demo complete![/green bold] This is what SentinelAI does for real alerts.")


@cli.command()
@click.option("--config", "config_path", default=None, type=click.Path(), help="Path to sentinelai.yaml")
def doctor(config_path: str | None) -> None:
    """Validate your SentinelAI setup — config, API keys, plugins."""
    console.print("[bold]SentinelAI Doctor[/bold] — checking your setup\n")

    checks_passed = 0
    checks_failed = 0

    # Check 1: Config file
    try:
        config = SentinelConfig.load(config_path)
        console.print("[green]\u2714[/green] Config file loaded and valid")
        checks_passed += 1
    except ConfigValidationError as e:
        console.print(f"[red]\u2718[/red] Config error: {e}")
        checks_failed += 1
        console.print(f"\n[red]{checks_failed} check(s) failed.[/red]")
        sys.exit(1)

    # Check 2: API keys
    api_issues = config.validate_api_keys()
    if api_issues:
        for issue in api_issues:
            console.print(f"[red]\u2718[/red] {issue}")
            checks_failed += 1
    else:
        console.print("[green]\u2714[/green] API keys configured")
        checks_passed += 1

    # Check 3: Alert source plugin
    try:
        load_plugin(config.pipeline.alert_source, AlertSource)
        console.print(f"[green]\u2714[/green] Alert source plugin: {config.pipeline.alert_source}")
        checks_passed += 1
    except PluginLoadError as e:
        console.print(f"[red]\u2718[/red] Alert source plugin: {e}")
        checks_failed += 1

    # Check 4: Triage engine plugin
    try:
        load_plugin(config.pipeline.triage_engine, TriageEngine)
        console.print(f"[green]\u2714[/green] Triage engine plugin: {config.pipeline.triage_engine}")
        checks_passed += 1
    except PluginLoadError as e:
        console.print(f"[red]\u2718[/red] Triage engine plugin: {e}")
        checks_failed += 1

    # Check 5: Ticket system plugin (optional)
    if config.pipeline.ticket_system:
        try:
            load_plugin(config.pipeline.ticket_system, TicketSystem)
            console.print(f"[green]\u2714[/green] Ticket system plugin: {config.pipeline.ticket_system}")
            checks_passed += 1
        except PluginLoadError as e:
            console.print(f"[red]\u2718[/red] Ticket system plugin: {e}")
            checks_failed += 1
    else:
        console.print("[dim]- Ticket system: not configured (console output only)[/dim]")

    console.print()
    if checks_failed == 0:
        console.print(f"[green bold]All {checks_passed} checks passed![/green bold] You're ready to go.")
    else:
        console.print(
            f"[yellow]{checks_passed} passed, {checks_failed} failed.[/yellow] "
            f"Fix the issues above and run doctor again."
        )
        sys.exit(1)


@cli.command("validate-config")
@click.option("--config", "config_path", default=None, type=click.Path(), help="Path to sentinelai.yaml")
def validate_config(config_path: str | None) -> None:
    """Check config validity without running the pipeline."""
    try:
        config = SentinelConfig.load(config_path)
        console.print("[green]Config is valid.[/green]")
        console.print(f"  Alert source: {config.pipeline.alert_source}")
        console.print(f"  Triage engine: {config.pipeline.triage_engine}")
        console.print(f"  Dedup window: {config.dedup_window_minutes}m")
        console.print(f"  Triage timeout: {config.timeouts.triage_timeout_seconds}s")
    except ConfigValidationError as e:
        console.print(f"[red]Config invalid:[/red] {e}")
        sys.exit(1)
