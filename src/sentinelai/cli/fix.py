"""Fix CLI command — the full triage → fix → PR pipeline.

Usage:
    sentinelai fix --file alert.json --repo /path/to/target/repo
    sentinelai fix --file alert.json --repo . --no-pr   # Generate fix without opening PR
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from sentinelai.contracts.code_fixer import CodeFixer
from sentinelai.contracts.pr_opener import PROpener
from sentinelai.contracts.triage_engine import TriageEngine
from sentinelai.core.config import SentinelConfig
from sentinelai.core.errors import (
    AlertSourceError,
    CodeFixError,
    ConfigValidationError,
    PluginLoadError,
    PRCreationError,
)
from sentinelai.core.events import FixGenerated, Priority, TriageComplete
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


def _render_fix(fix: FixGenerated, triage: TriageComplete) -> None:
    """Render a generated fix with rich formatting."""
    sev_style = _SEVERITY_COLORS.get(triage.severity, "dim")

    console.print()
    console.print(
        Panel(
            f"[{sev_style}]{triage.severity.value}[/{sev_style}] — Fix confidence: {fix.confidence:.0%}",
            title=f"[bold]Code Fix: {fix.alert_id}[/bold]",
            border_style="green" if fix.confidence >= 0.7 else "yellow",
        )
    )

    # Files changed
    table = Table(title="Files Changed", show_lines=True)
    table.add_column("File", style="bold")
    table.add_column("Description")
    for code_fix in fix.fixes:
        table.add_row(code_fix.file_path, code_fix.description)
    console.print(table)

    # Rationale
    console.print("\n[bold]Rationale:[/bold]")
    console.print(fix.rationale)

    # Show diff preview for each file
    for code_fix in fix.fixes:
        if code_fix.original_content and code_fix.fixed_content:
            console.print(f"\n[bold dim]--- {code_fix.file_path} (preview) ---[/bold dim]")
            # Show first 30 lines of fixed content
            preview = "\n".join(code_fix.fixed_content.split("\n")[:30])
            try:
                ext = code_fix.file_path.rsplit(".", 1)[-1]
                syntax = Syntax(preview, ext, theme="monokai", line_numbers=True)
                console.print(syntax)
            except Exception:
                console.print(f"[dim]{preview}[/dim]")
            if len(code_fix.fixed_content.split("\n")) > 30:
                console.print("[dim]... (truncated)[/dim]")

    # Test code
    if fix.test_code:
        console.print(f"\n[bold]Generated Test:[/bold] {fix.test_file_path}")

    # Rollback
    console.print(f"\n[dim]Rollback: {fix.rollback_instructions}[/dim]")


@click.command()
@click.option("--file", "file_path", required=True, type=click.Path(exists=True), help="Path to JSON alert file")
@click.option("--repo", "repo_path", required=True, type=click.Path(exists=True), help="Path to target repository")
@click.option("--config", "config_path", default=None, type=click.Path(), help="Path to sentinelai.yaml")
@click.option("--no-pr", is_flag=True, default=False, help="Generate fix without opening a PR")
@click.option("--write-files", is_flag=True, default=False, help="Write fixed files to disk")
def fix(file_path: str, repo_path: str, config_path: str | None, no_pr: bool, write_files: bool) -> None:
    """Triage an alert, generate a code fix, and open a pull request.

    This is the full SentinelAI pipeline: alert → triage → fix → PR.
    The PR requires human approval before merge (enforced by design).
    """
    try:
        config = SentinelConfig.load(config_path)
    except ConfigValidationError as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)

    # Load plugins
    try:
        triage_engine = load_plugin(config.pipeline.triage_engine, TriageEngine)
    except PluginLoadError as e:
        console.print(f"[red]Triage plugin error:[/red] {e}")
        sys.exit(1)

    code_fixer_path = config.pipeline.code_fixer
    if not code_fixer_path:
        console.print("[red]pipeline.code_fixer not configured in sentinelai.yaml[/red]")
        sys.exit(1)

    try:
        code_fixer = load_plugin(code_fixer_path, CodeFixer)
    except PluginLoadError as e:
        console.print(f"[red]Code fixer plugin error:[/red] {e}")
        sys.exit(1)

    pr_opener = None
    if not no_pr:
        pr_opener_path = config.pipeline.pr_opener
        if not pr_opener_path:
            console.print("[yellow]pipeline.pr_opener not configured — generating fix without PR.[/yellow]")
            no_pr = True
        else:
            try:
                pr_opener = load_plugin(pr_opener_path, PROpener)
            except PluginLoadError as e:
                console.print(f"[yellow]PR opener plugin failed: {e}[/yellow]")
                console.print("[yellow]Continuing without PR creation.[/yellow]")
                no_pr = True

    # Step 1: Triage
    console.print("[bold]Step 1/3:[/bold] Triaging alert...")

    from sentinelai.plugins.sources.file_source import FileAlertSource

    source = FileAlertSource(file_path)
    pipeline = Pipeline(config, source, triage_engine)

    try:
        triage_results = asyncio.run(pipeline.run())
    except AlertSourceError as e:
        console.print(f"[red]Alert source error:[/red] {e}")
        sys.exit(1)

    if not triage_results:
        console.print("[yellow]No alerts to process.[/yellow]")
        return

    triage_result = triage_results[0]  # Process the first alert
    sev_style = _SEVERITY_COLORS.get(triage_result.severity, "dim")
    console.print(
        f"  [{sev_style}]{triage_result.severity.value}[/{sev_style}] — {triage_result.root_cause_hypothesis[:80]}"
    )

    # Step 2: Generate fix
    console.print("\n[bold]Step 2/3:[/bold] Generating code fix...")

    try:
        fix_result = asyncio.run(code_fixer.generate_fix(triage_result, repo_path))
    except CodeFixError as e:
        console.print(f"[red]Fix generation failed:[/red] {e}")
        sys.exit(1)

    _render_fix(fix_result, triage_result)

    # Optionally write files without PR
    if write_files:
        console.print("\n[bold]Writing fixed files to disk...[/bold]")
        for code_fix in fix_result.fixes:
            target = Path(repo_path) / code_fix.file_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code_fix.fixed_content)
            console.print(f"  Wrote: {code_fix.file_path}")
        if fix_result.test_code:
            test_target = Path(repo_path) / fix_result.test_file_path
            test_target.parent.mkdir(parents=True, exist_ok=True)
            test_target.write_text(fix_result.test_code)
            console.print(f"  Wrote: {fix_result.test_file_path}")

    # Step 3: Open PR
    if no_pr:
        console.print("\n[green]Fix generated (no PR created — use --write-files to save to disk).[/green]")
        return

    console.print("\n[bold]Step 3/3:[/bold] Opening pull request...")

    try:
        pr_result = asyncio.run(pr_opener.open_pr(fix_result, triage_result, repo_path))
    except PRCreationError as e:
        console.print(f"[red]PR creation failed:[/red] {e}")
        sys.exit(1)

    console.print()
    console.print(
        Panel(
            f"[bold green]PR #{pr_result.pr_number}[/bold green]\n{pr_result.pr_url}",
            title="[bold]Pull Request Opened[/bold]",
            border_style="green",
        )
    )
    console.print("[dim]The PR requires human approval before merge.[/dim]")
    console.print(f"[dim]Branch: {pr_result.branch_name}[/dim]")
