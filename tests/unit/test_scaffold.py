"""Tests for plugin scaffold generator."""

import tempfile
from pathlib import Path

from click.testing import CliRunner

from sentinelai.cli.scaffold import plugin

runner = CliRunner()


class TestScaffold:
    def test_creates_triage_plugin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(plugin, ["new", "--type", "triage", "--name", "my_ai", "--output", tmpdir])
            assert result.exit_code == 0
            assert "Plugin created!" in result.output

            plugin_file = Path(tmpdir) / "my_ai" / "my_ai.py"
            assert plugin_file.exists()
            content = plugin_file.read_text()
            assert "class MyAiTriageEngine" in content
            assert "TriageEngine" in content

            test_file = Path(tmpdir) / "test_my_ai.py"
            assert test_file.exists()

    def test_creates_source_plugin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(plugin, ["new", "--type", "source", "--name", "datadog", "--output", tmpdir])
            assert result.exit_code == 0
            plugin_file = Path(tmpdir) / "datadog" / "datadog.py"
            assert plugin_file.exists()
            assert "class DatadogAlertSource" in plugin_file.read_text()

    def test_creates_ticket_plugin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(plugin, ["new", "--type", "ticket", "--name", "linear", "--output", tmpdir])
            assert result.exit_code == 0
            plugin_file = Path(tmpdir) / "linear" / "linear.py"
            assert plugin_file.exists()
            assert "class LinearTicketSystem" in plugin_file.read_text()

    def test_invalid_type_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(plugin, ["new", "--type", "invalid", "--name", "foo", "--output", tmpdir])
            assert result.exit_code != 0
