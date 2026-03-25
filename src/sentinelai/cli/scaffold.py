"""Plugin scaffold generator — creates plugin skeletons from templates.

Usage:
    sentinelai plugin new --type triage --name my_custom_triage
    sentinelai plugin new --type source --name datadog
    sentinelai plugin new --type ticket --name linear
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

console = Console()

_TEMPLATES = {
    "source": '''"""{{ name }} alert source plugin."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from sentinelai.contracts.alert_source import AlertSource
from sentinelai.core.errors import AlertSourceError
from sentinelai.core.events import AlertDetected


class {{ class_name }}(AlertSource):
    """Reads alerts from {{ name }}."""

    def __init__(self) -> None:
        # TODO: Initialize your connection / client here
        pass

    async def read_alerts(self) -> AsyncIterator[AlertDetected]:
        """Yield AlertDetected events from {{ name }}.

        Must raise AlertSourceError on failure — never generic exceptions.
        """
        # TODO: Implement your alert source logic
        raise AlertSourceError("{{ class_name }} not yet implemented")
        yield  # type: ignore[misc]  # makes this an async generator
''',
    "triage": '''"""{{ name }} triage engine plugin."""

from __future__ import annotations

from sentinelai.contracts.triage_engine import TriageEngine
from sentinelai.core.errors import (
    TriageError,
    TriageMalformedResponse,
    TriageRateLimitError,
    TriageTimeoutError,
)
from sentinelai.core.events import AlertDetected, Priority, TriageComplete


class {{ class_name }}(TriageEngine):
    """Triage engine using {{ name }}."""

    def __init__(self) -> None:
        # TODO: Initialize your AI client here
        pass

    async def triage(self, alert: AlertDetected) -> TriageComplete:
        """Analyze alert and produce a triage result.

        Must raise TriageError subtypes on failure:
        - TriageTimeoutError if the AI call exceeds timeout
        - TriageRateLimitError if the provider returns 429
        - TriageMalformedResponse if the response is unparseable
        """
        # TODO: Implement your triage logic
        raise TriageError("{{ class_name }} not yet implemented", trace_id=alert.trace_id)
''',
    "ticket": '''"""{{ name }} ticket system plugin."""

from __future__ import annotations

from sentinelai.contracts.ticket_system import TicketResult, TicketSystem
from sentinelai.core.errors import TicketCreationError
from sentinelai.core.events import TriageComplete


class {{ class_name }}(TicketSystem):
    """Creates tickets in {{ name }} from triage results."""

    def __init__(self) -> None:
        # TODO: Initialize your ticket system client here
        pass

    async def create_ticket(self, triage: TriageComplete) -> TicketResult:
        """Create a ticket from a triage result.

        Must raise TicketCreationError on failure — never generic exceptions.
        """
        # TODO: Implement your ticket creation logic
        raise TicketCreationError("{{ class_name }} not yet implemented", trace_id=triage.trace_id)
''',
}

_TEST_TEMPLATE = '''"""Tests for {{ name }} plugin."""

import pytest

# TODO: Add your tests here
# See tests/unit/test_file_source.py for an example of how to test an alert source plugin
# See tests/unit/test_plugin.py for plugin loading tests
'''


def _to_class_name(name: str) -> str:
    """Convert snake_case to PascalCase and append type suffix."""
    parts = name.replace("-", "_").split("_")
    return "".join(p.capitalize() for p in parts)


@click.group()
def plugin() -> None:
    """Manage SentinelAI plugins."""


@plugin.command("new")
@click.option("--type", "plugin_type", required=True, type=click.Choice(["source", "triage", "ticket"]))
@click.option("--name", required=True, help="Plugin name in snake_case (e.g., datadog, my_custom)")
@click.option("--output", "output_dir", default=None, type=click.Path(), help="Output directory (default: current dir)")
def new_plugin(plugin_type: str, name: str, output_dir: str | None) -> None:
    """Generate a new plugin skeleton with contract, error handling, and test file."""
    type_suffixes = {"source": "AlertSource", "triage": "TriageEngine", "ticket": "TicketSystem"}
    class_name = _to_class_name(name) + type_suffixes[plugin_type]

    template = _TEMPLATES[plugin_type]
    code = template.replace("{{ name }}", name).replace("{{ class_name }}", class_name)
    test_code = _TEST_TEMPLATE.replace("{{ name }}", name)

    base = Path(output_dir) if output_dir else Path(".")

    # Write plugin file
    plugin_dir = base / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "__init__.py").write_text("")

    plugin_file = plugin_dir / f"{name}.py"
    plugin_file.write_text(code)

    # Write test file
    test_file = base / f"test_{name}.py"
    test_file.write_text(test_code)

    console.print("[green]Plugin created![/green]\n")
    console.print(f"  Plugin:  {plugin_file}")
    console.print(f"  Test:    {test_file}")
    console.print(f"  Class:   {class_name}")
    console.print("\n[dim]Register in sentinelai.yaml:[/dim]")

    type_config_keys = {"source": "alert_source", "triage": "triage_engine", "ticket": "ticket_system"}
    config_key = type_config_keys[plugin_type]
    console.print(f"[dim]  pipeline.{config_key}: {name}.{name}[/dim]")
