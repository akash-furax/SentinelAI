"""Run command — start the SentinelAI pipeline as a long-running service.

Usage:
    sentinelai run                          # Start with default config
    sentinelai run --config path/to/config  # Start with custom config
"""

from __future__ import annotations

import asyncio
import logging
import sys

import click
from rich.console import Console

from sentinelai.contracts.alert_source import AlertSource
from sentinelai.contracts.ticket_system import TicketSystem
from sentinelai.contracts.triage_engine import TriageEngine
from sentinelai.core.config import SentinelConfig
from sentinelai.core.errors import ConfigValidationError, PluginLoadError
from sentinelai.core.pipeline import Pipeline
from sentinelai.core.plugin import load_plugin

console = Console()
logger = logging.getLogger("sentinelai")


def _setup_logging() -> None:
    """Configure structured logging for long-running mode."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)


@click.command("run")
@click.option("--config", "config_path", default=None, type=click.Path(), help="Path to sentinelai.yaml")
def run(config_path: str | None) -> None:
    """Start the SentinelAI pipeline as a long-running service.

    Starts the configured alert source (e.g., webhook server) and processes
    alerts continuously through the triage pipeline. Use Ctrl+C to stop.
    """
    _setup_logging()

    try:
        config = SentinelConfig.load(config_path)
    except ConfigValidationError as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    # Load plugins
    try:
        alert_source = load_plugin(config.pipeline.alert_source, AlertSource)
        triage_engine = load_plugin(config.pipeline.triage_engine, TriageEngine)
    except PluginLoadError as e:
        console.print(f"[red]Plugin error:[/red] {e}")
        sys.exit(1)

    ticket_system = None
    if config.pipeline.ticket_system:
        try:
            ticket_system = load_plugin(config.pipeline.ticket_system, TicketSystem)
        except PluginLoadError as e:
            console.print(f"[yellow]Ticket system failed to load: {e}[/yellow]")

    pipeline = Pipeline(config, alert_source, triage_engine, ticket_system=ticket_system)

    console.print("[bold green]SentinelAI Pipeline Started[/bold green]")
    console.print(f"  Alert source:  {config.pipeline.alert_source}")
    console.print(f"  Triage engine: {config.pipeline.triage_engine}")
    if config.pipeline.ticket_system:
        console.print(f"  Ticket system: {config.pipeline.ticket_system}")
    console.print()

    source_name = config.pipeline.alert_source.split(".")[-1]
    if "webhook" in source_name:
        port = int(__import__("os").environ.get("SENTINELAI_WEBHOOK_PORT", "8090"))
        console.print(f"[bold]Webhook server listening on port {port}[/bold]")
        console.print(f"[dim]Send alerts to: POST http://localhost:{port}/[/dim]")
        console.print("[dim]Press Ctrl+C to stop.[/dim]\n")
    else:
        console.print("[dim]Processing alerts... Press Ctrl+C to stop.[/dim]\n")

    try:
        asyncio.run(pipeline.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline stopped.[/yellow]")
    except Exception as e:
        console.print(f"[red]Pipeline error:[/red] {e}")
        sys.exit(1)
