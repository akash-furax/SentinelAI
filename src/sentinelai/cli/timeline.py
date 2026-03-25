"""Timeline, explain, and costs CLI commands.

Commands:
    sentinelai timeline [alert_id]    Show incident timeline events
    sentinelai explain <alert_id>     Show AI reasoning for a triage decision
    sentinelai costs                  Show API cost summary
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()

_DEFAULT_TIMELINE = Path("incidents/timeline.jsonl")

_SEVERITY_COLORS = {
    "P1": "bold red",
    "P2": "yellow",
    "P3": "cyan",
    "P4": "green",
    "UNKNOWN": "dim",
}


def _load_timeline(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().strip().split("\n"):
        if line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


@click.command()
@click.argument("alert_id", required=False, default=None)
@click.option("--path", "timeline_path", default=None, type=click.Path(), help="Path to timeline.jsonl")
@click.option("--limit", default=50, help="Max events to show")
def timeline(alert_id: str | None, timeline_path: str | None, limit: int) -> None:
    """Show incident timeline events. Optionally filter by alert_id."""
    path = Path(timeline_path) if timeline_path else _DEFAULT_TIMELINE
    entries = _load_timeline(path)

    if not entries:
        console.print("[yellow]No timeline events found.[/yellow]")
        console.print(f"[dim]Looking in: {path}[/dim]")
        return

    if alert_id:
        entries = [e for e in entries if e.get("alert_id") == alert_id]
        if not entries:
            console.print(f"[yellow]No events found for alert_id: {alert_id}[/yellow]")
            return

    entries = entries[-limit:]

    table = Table(title="Incident Timeline", show_lines=True)
    table.add_column("Time", style="dim", width=12)
    table.add_column("Event", width=20)
    table.add_column("Alert ID", width=15)
    table.add_column("Details", min_width=30)

    for entry in entries:
        ts = entry.get("timestamp", "")
        if "T" in ts:
            ts = ts.split("T")[1][:8]  # HH:MM:SS

        event_type = entry.get("event_type", "unknown")
        aid = entry.get("alert_id", "")[:15]

        details_parts = []
        if "severity" in entry:
            sev = entry["severity"]
            color = _SEVERITY_COLORS.get(sev, "dim")
            details_parts.append(f"[{color}]{sev}[/{color}]")
        if "confidence" in entry:
            details_parts.append(f"conf={entry['confidence']:.0%}")
        if "ticket_id" in entry:
            details_parts.append(f"ticket={entry['ticket_id']}")
        if "ticket_url" in entry:
            details_parts.append(entry["ticket_url"])

        details = " | ".join(details_parts) if details_parts else ""

        event_style = "green" if "complete" in event_type else "yellow" if "detected" in event_type else "dim"
        table.add_row(ts, f"[{event_style}]{event_type}[/{event_style}]", aid, details)

    console.print(table)
    console.print(f"[dim]{len(entries)} event(s) shown[/dim]")


@click.command()
@click.argument("alert_id")
@click.option("--path", "timeline_path", default=None, type=click.Path(), help="Path to timeline.jsonl")
def explain(alert_id: str, timeline_path: str | None) -> None:
    """Show AI reasoning for a specific triage decision."""
    path = Path(timeline_path) if timeline_path else _DEFAULT_TIMELINE
    entries = _load_timeline(path)

    triage_entries = [e for e in entries if e.get("alert_id") == alert_id and e.get("event_type") == "triage.complete"]

    if not triage_entries:
        console.print(f"[yellow]No triage found for alert_id: {alert_id}[/yellow]")
        console.print("[dim]Note: `explain` shows the AI reasoning stored in the timeline.[/dim]")
        console.print("[dim]The full reasoning is available when running triage with --file.[/dim]")
        return

    entry = triage_entries[-1]  # Most recent triage for this alert
    sev = entry.get("severity", "UNKNOWN")
    color = _SEVERITY_COLORS.get(sev, "dim")

    console.print(f"\n[bold]Triage Explanation: {alert_id}[/bold]\n")
    console.print(f"  Severity:   [{color}]{sev}[/{color}]")
    console.print(f"  Confidence: {entry.get('confidence', 0):.0%}")
    console.print(f"  Time:       {entry.get('timestamp', 'unknown')}")

    # Check for ticket
    ticket_entries = [e for e in entries if e.get("alert_id") == alert_id and e.get("event_type") == "ticket.created"]
    if ticket_entries:
        t = ticket_entries[-1]
        console.print(f"  Ticket:     {t.get('ticket_id', '')} — {t.get('ticket_url', '')}")

    console.print("\n[dim]Full AI reasoning is logged during triage — run:[/dim]")
    console.print("[dim]  sentinelai triage --file <your-alert.json>[/dim]")


@click.command()
@click.option("--path", "timeline_path", default=None, type=click.Path(), help="Path to timeline.jsonl")
def costs(timeline_path: str | None) -> None:
    """Show API cost summary based on timeline events."""
    path = Path(timeline_path) if timeline_path else _DEFAULT_TIMELINE
    entries = _load_timeline(path)

    triage_events = [e for e in entries if e.get("event_type") == "triage.complete"]
    alert_events = [e for e in entries if e.get("event_type") == "alert.detected"]
    ticket_events = [e for e in entries if e.get("event_type") == "ticket.created"]
    dedup_events = [e for e in entries if e.get("event_type") == "alert.deduplicated"]

    # Cost estimation: configurable per provider, default $0.01 per triage call
    cost_per_triage = 0.01
    total_cost = len(triage_events) * cost_per_triage

    console.print("[bold]SentinelAI Cost Summary[/bold]\n")

    table = Table(show_header=True, box=None)
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")

    table.add_row("Alerts received", str(len(alert_events)))
    table.add_row("Alerts deduplicated", str(len(dedup_events)))
    table.add_row("Triage calls", str(len(triage_events)))
    table.add_row("Tickets created", str(len(ticket_events)))
    table.add_row("", "")
    table.add_row("Est. cost (triage)", f"${total_cost:.2f}")
    table.add_row("Cost per triage", f"${cost_per_triage:.3f}")

    console.print(table)

    if triage_events:
        # Severity breakdown
        console.print("\n[bold]Severity Breakdown[/bold]")
        severity_counts: dict[str, int] = {}
        for e in triage_events:
            sev = e.get("severity", "UNKNOWN")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        for sev in ["P1", "P2", "P3", "P4", "UNKNOWN"]:
            count = severity_counts.get(sev, 0)
            if count > 0:
                color = _SEVERITY_COLORS.get(sev, "dim")
                console.print(f"  [{color}]{sev}[/{color}]: {count}")

    console.print(f"\n[dim]Data from: {path}[/dim]")
