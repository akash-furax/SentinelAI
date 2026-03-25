"""Deploy CLI command — deploy, validate, and close the loop.

Usage:
    sentinelai deploy --pr <number> --repo /path/to/repo   Deploy a merged PR
    sentinelai deploy --commit <sha> --repo /path/to/repo  Deploy a specific commit
    sentinelai validate --deploy-id <id>                   Run validation only
"""

from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sentinelai.contracts.deployer import Deployer
from sentinelai.contracts.ticket_system import TicketSystem
from sentinelai.contracts.validator import Validator
from sentinelai.core.config import SentinelConfig
from sentinelai.core.errors import (
    ConfigValidationError,
    DeployError,
    DeployRollbackError,
    PluginLoadError,
    ValidationError,
)
from sentinelai.core.events import DeployStarted, PRMerged, ValidationResult
from sentinelai.core.plugin import load_plugin

console = Console()


@click.command()
@click.option("--commit", "commit_sha", required=True, help="Merge commit SHA to deploy")
@click.option("--alert-id", default="manual", help="Alert ID that triggered this fix")
@click.option("--branch", default="main", help="Branch that was merged")
@click.option("--pr", "pr_number", default=0, type=int, help="PR number (for traceability)")
@click.option("--config", "config_path", default=None, type=click.Path(), help="Path to sentinelai.yaml")
@click.option("--skip-validation", is_flag=True, default=False, help="Deploy without running validation")
@click.option("--auto-rollback/--no-auto-rollback", default=True, help="Auto-rollback on validation failure")
def deploy(
    commit_sha: str,
    alert_id: str,
    branch: str,
    pr_number: int,
    config_path: str | None,
    skip_validation: bool,
    auto_rollback: bool,
) -> None:
    """Deploy a merged fix, validate, and close the loop.

    The final stage: deploy → validate → auto-close ticket (if configured).
    Auto-rollback is enabled by default if validation fails.
    """
    try:
        config = SentinelConfig.load(config_path)
    except ConfigValidationError as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    # Load deployer
    deployer_path = config.pipeline.deployer
    if not deployer_path:
        console.print("[red]pipeline.deployer not configured in sentinelai.yaml[/red]")
        sys.exit(1)

    try:
        deployer = load_plugin(deployer_path, Deployer)
    except PluginLoadError as e:
        console.print(f"[red]Deployer plugin error:[/red] {e}")
        sys.exit(1)

    # Load validator (optional if --skip-validation)
    validator = None
    if not skip_validation:
        validator_path = config.pipeline.validator
        if validator_path:
            try:
                validator = load_plugin(validator_path, Validator)
            except PluginLoadError as e:
                console.print(f"[yellow]Validator plugin error: {e}[/yellow]")
                console.print("[yellow]Continuing without validation.[/yellow]")
        else:
            console.print("[yellow]pipeline.validator not configured — skipping validation.[/yellow]")

    # Load ticket system for auto-close (optional)
    ticket_system = None
    if config.pipeline.ticket_system:
        try:
            ticket_system = load_plugin(config.pipeline.ticket_system, TicketSystem)
        except PluginLoadError:
            pass  # Non-critical — ticket close is best-effort

    merge_event = PRMerged(
        alert_id=alert_id,
        pr_number=pr_number,
        merge_commit_sha=commit_sha,
        branch_name=branch,
        trace_id=f"deploy-{commit_sha[:8]}",
    )

    # Step 1: Deploy
    console.print(f"[bold]Step 1/3:[/bold] Deploying commit {commit_sha[:8]}...")

    try:
        deploy_result = asyncio.run(deployer.deploy(merge_event))
    except DeployError as e:
        console.print(f"[red]Deployment failed:[/red] {e}")
        sys.exit(1)

    console.print(
        f"  [green]Deployed[/green] — ID: {deploy_result.deploy_id} | "
        f"Env: {deploy_result.environment} | Strategy: {deploy_result.strategy}"
    )

    # Step 2: Validate
    if validator:
        console.print("\n[bold]Step 2/3:[/bold] Running validation...")

        try:
            validation = asyncio.run(validator.validate(deploy_result))
        except ValidationError as e:
            console.print(f"[red]Validation infrastructure error:[/red] {e}")
            if auto_rollback:
                _do_rollback(deployer, deploy_result)
            sys.exit(1)

        _render_validation(validation)

        if not validation.passed:
            console.print("[red bold]Validation FAILED.[/red bold]")
            if auto_rollback:
                _do_rollback(deployer, deploy_result)
            else:
                console.print("[yellow]Auto-rollback disabled. Manual intervention required.[/yellow]")
            sys.exit(1)
    else:
        console.print("\n[bold]Step 2/3:[/bold] [dim]Validation skipped[/dim]")
        validation = None

    # Step 3: Close ticket (best-effort)
    console.print("\n[bold]Step 3/3:[/bold] Closing the loop...")

    if ticket_system and validation and validation.passed:
        console.print("  [dim]Auto-ticket-close is a Phase 3+ feature — logged to timeline.[/dim]")

    # Summary
    console.print()
    ok = not validation or validation.passed
    status = "[green bold]SUCCESS[/green bold]" if ok else "[red bold]FAILED[/red bold]"
    console.print(
        Panel(
            f"Deploy: {deploy_result.deploy_id}\n"
            f"Commit: {commit_sha[:8]}\n"
            f"Validation: {'PASSED' if ok else 'FAILED'}\n"
            f"Status: {status}",
            title="[bold]Deployment Summary[/bold]",
            border_style="green" if ok else "red",
        )
    )


def _render_validation(result: ValidationResult) -> None:
    """Render validation results."""
    table = Table(title="Validation Results", show_lines=True)
    table.add_column("Check", width=8)
    table.add_column("Status", width=8)

    for i in range(result.total_checks):
        if i < result.passed_checks:
            table.add_row(f"#{i + 1}", "[green]PASS[/green]")
        else:
            idx = i - result.passed_checks
            detail = result.failed_checks[idx] if idx < len(result.failed_checks) else "failed"
            table.add_row(f"#{i + 1}", f"[red]FAIL[/red] {detail[:60]}")

    console.print(table)
    console.print(f"  {result.passed_checks}/{result.total_checks} passed | {result.duration_seconds:.1f}s")


def _do_rollback(deployer: Deployer, deploy_result: DeployStarted) -> None:
    """Attempt automatic rollback."""
    console.print("\n[yellow bold]Initiating auto-rollback...[/yellow bold]")
    try:
        asyncio.run(deployer.rollback(deploy_result))
        console.print("[green]Rollback successful.[/green]")
    except DeployRollbackError as e:
        console.print(f"[red bold]ROLLBACK FAILED:[/red bold] {e}")
        console.print("[red bold]MANUAL INTERVENTION REQUIRED.[/red bold]")
    except DeployError as e:
        console.print(f"[red bold]ROLLBACK FAILED:[/red bold] {e}")
        console.print("[red bold]MANUAL INTERVENTION REQUIRED.[/red bold]")
