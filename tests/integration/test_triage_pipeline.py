"""Integration test — full triage pipeline with mocked AI responses.

Proves the end-to-end flow works without an API key:
    file_source → dedup → triage (mocked Claude) → console output + timeline

This test validates that all components wire together correctly —
config loading, plugin discovery, pipeline orchestration, dedup,
retry logic, timeline logging, and rich CLI output.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from sentinelai.cli.main import cli
from sentinelai.core.config import SentinelConfig
from sentinelai.core.events import AlertDetected, Priority, TriageComplete
from sentinelai.core.pipeline import Pipeline
from sentinelai.plugins.sources.file_source import FileAlertSource


def _write_file(data, suffix=".json") -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False)
    if isinstance(data, str):
        f.write(data)
    else:
        json.dump(data, f)
    f.close()
    return Path(f.name)


_MOCK_TRIAGE_RESPONSE = TriageComplete(
    alert_id="test-e2e-1",
    severity=Priority.P2,
    root_cause_hypothesis="Connection pool exhaustion due to traffic spike",
    confidence=0.87,
    affected_services=["auth-service"],
    recommended_action="Increase max_connections from 10 to 100",
    ai_reasoning="The error logs show 10/10 connections in use. The traffic spike "
    "from the marketing campaign increased login attempts 3x. The pool "
    "max_connections=10 is too low for this load. Recommend increasing to 100.",
    trace_id="",  # pipeline assigns this
)

_TEST_ALERT = {
    "alert_id": "test-e2e-1",
    "service_name": "auth-service",
    "summary": "Connection pool exhausted: 10/10 connections in use",
    "raw_payload": {"error_count": 847, "active_connections": 10, "max_connections": 10},
}

_TEST_CONFIG = """\
pipeline:
  alert_source: sentinelai.plugins.sources.file_source
  triage_engine: sentinelai.plugins.triage.claude

settings:
  dedup_window_minutes: 5

timeouts:
  triage_timeout_seconds: 60
"""


class TestTriagePipelineE2E:
    """End-to-end pipeline test with mocked AI responses."""

    @pytest.mark.asyncio
    async def test_full_pipeline_triage(self, tmp_path):
        """Alert file → pipeline → triage result with timeline."""
        alert_file = tmp_path / "alert.json"
        alert_file.write_text(json.dumps(_TEST_ALERT))

        config_file = tmp_path / "sentinelai.yaml"
        config_file.write_text(_TEST_CONFIG)

        timeline_file = tmp_path / "timeline.jsonl"

        config = SentinelConfig.load(config_file)
        source = FileAlertSource(alert_file)

        # Mock the Claude triage engine
        mock_engine = AsyncMock()
        mock_engine.triage = AsyncMock(return_value=_MOCK_TRIAGE_RESPONSE)

        pipeline = Pipeline(config, source, mock_engine, timeline_path=timeline_file)
        results = await pipeline.run()

        # Verify triage result
        assert len(results) == 1
        result = results[0]
        assert result.severity == Priority.P2
        assert result.confidence == 0.87
        assert "Connection pool" in result.root_cause_hypothesis

        # Verify triage was called with an alert that has a trace_id assigned by pipeline
        mock_engine.triage.assert_called_once()
        call_arg = mock_engine.triage.call_args[0][0]
        assert isinstance(call_arg, AlertDetected)
        assert call_arg.service_name == "auth-service"
        assert call_arg.trace_id  # pipeline assigned a UUID

        # Verify timeline was written
        assert timeline_file.exists()
        entries = [json.loads(line) for line in timeline_file.read_text().strip().split("\n")]
        event_types = [e["event_type"] for e in entries]
        assert "alert.detected" in event_types
        assert "triage.complete" in event_types

    @pytest.mark.asyncio
    async def test_dedup_blocks_duplicate(self, tmp_path):
        """Two identical alerts → only one triage call."""
        alerts = [_TEST_ALERT, _TEST_ALERT]  # Same alert twice
        alert_file = tmp_path / "alerts.json"
        alert_file.write_text(json.dumps(alerts))

        config_file = tmp_path / "sentinelai.yaml"
        config_file.write_text(_TEST_CONFIG)

        config = SentinelConfig.load(config_file)
        source = FileAlertSource(alert_file)

        mock_engine = AsyncMock()
        mock_engine.triage = AsyncMock(return_value=_MOCK_TRIAGE_RESPONSE)

        pipeline = Pipeline(config, source, mock_engine, timeline_path=tmp_path / "timeline.jsonl")
        results = await pipeline.run()

        # Only one triage — second alert was deduped
        assert len(results) == 1
        assert mock_engine.triage.call_count == 1

    @pytest.mark.asyncio
    async def test_different_alerts_both_triaged(self, tmp_path):
        """Two different alerts → two triage calls."""
        alerts = [
            _TEST_ALERT,
            {
                "alert_id": "test-e2e-2",
                "service_name": "payment-service",
                "summary": "Latency p99 exceeded SLO: 4200ms",
                "raw_payload": {"latency_p99_ms": 4200},
            },
        ]
        alert_file = tmp_path / "alerts.json"
        alert_file.write_text(json.dumps(alerts))

        config_file = tmp_path / "sentinelai.yaml"
        config_file.write_text(_TEST_CONFIG)

        config = SentinelConfig.load(config_file)
        source = FileAlertSource(alert_file)

        mock_engine = AsyncMock()
        mock_engine.triage = AsyncMock(return_value=_MOCK_TRIAGE_RESPONSE)

        pipeline = Pipeline(config, source, mock_engine, timeline_path=tmp_path / "timeline.jsonl")
        results = await pipeline.run()

        assert len(results) == 2
        assert mock_engine.triage.call_count == 2


class TestCLITriageE2E:
    """Test the CLI triage command end-to-end with mocked AI."""

    def test_triage_cli_renders_output(self, tmp_path):
        """sentinelai triage --file → rich output with severity + RCA."""
        alert_file = tmp_path / "alert.json"
        alert_file.write_text(json.dumps(_TEST_ALERT))

        config_file = tmp_path / "sentinelai.yaml"
        config_file.write_text(_TEST_CONFIG)

        runner = CliRunner()

        with patch("sentinelai.cli.main.load_plugin") as mock_load:
            mock_engine = AsyncMock()
            mock_engine.triage = AsyncMock(return_value=_MOCK_TRIAGE_RESPONSE)
            mock_load.return_value = mock_engine

            result = runner.invoke(cli, ["triage", "--file", str(alert_file), "--config", str(config_file)])

        assert result.exit_code == 0
        assert "P2" in result.output
        assert "Connection pool" in result.output
        assert "87%" in result.output
        assert "Triaged 1 alert" in result.output

    def test_doctor_passes_with_valid_config(self, tmp_path, monkeypatch):
        """sentinelai doctor → all checks pass."""
        config_file = tmp_path / "sentinelai.yaml"
        config_file.write_text(_TEST_CONFIG)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-for-doctor")

        runner = CliRunner()
        result = runner.invoke(cli, ["doctor", "--config", str(config_file)])

        assert result.exit_code == 0
        assert "checks passed" in result.output
