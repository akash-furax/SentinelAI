"""Tests for timeline, explain, and costs CLI commands."""

import json
import tempfile
from pathlib import Path

from click.testing import CliRunner

from sentinelai.cli.timeline import costs, explain, timeline


def _write_timeline(entries: list[dict]) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    for entry in entries:
        f.write(json.dumps(entry) + "\n")
    f.close()
    return Path(f.name)


_TS = "2026-03-25T12:"
_SAMPLE_ENTRIES = [
    {"event_type": "alert.detected", "timestamp": f"{_TS}00:00+00:00", "trace_id": "t1", "alert_id": "a1"},
    {
        "event_type": "triage.complete",
        "timestamp": f"{_TS}00:12+00:00",
        "trace_id": "t1",
        "alert_id": "a1",
        "severity": "P2",
        "confidence": 0.87,
    },
    {
        "event_type": "ticket.created",
        "timestamp": f"{_TS}00:15+00:00",
        "trace_id": "t1",
        "alert_id": "a1",
        "ticket_id": "JIRA-42",
        "ticket_url": "https://jira.example.com/JIRA-42",
    },
    {"event_type": "alert.detected", "timestamp": f"{_TS}01:00+00:00", "trace_id": "t2", "alert_id": "a2"},
    {"event_type": "alert.deduplicated", "timestamp": f"{_TS}01:05+00:00", "trace_id": "t2", "alert_id": "a2"},
]

runner = CliRunner()


class TestTimeline:
    def test_shows_all_events(self):
        path = _write_timeline(_SAMPLE_ENTRIES)
        try:
            result = runner.invoke(timeline, ["--path", str(path)])
            assert result.exit_code == 0
            assert "alert.detected" in result.output
            assert "triage.complete" in result.output
            assert "5 event(s) shown" in result.output
        finally:
            path.unlink()

    def test_filters_by_alert_id(self):
        path = _write_timeline(_SAMPLE_ENTRIES)
        try:
            result = runner.invoke(timeline, ["a1", "--path", str(path)])
            assert result.exit_code == 0
            assert "a1" in result.output
            assert "3 event(s) shown" in result.output
        finally:
            path.unlink()

    def test_empty_timeline(self):
        path = _write_timeline([])
        try:
            result = runner.invoke(timeline, ["--path", str(path)])
            assert result.exit_code == 0
            assert "No timeline events found" in result.output
        finally:
            path.unlink()


class TestExplain:
    def test_shows_triage_info(self):
        path = _write_timeline(_SAMPLE_ENTRIES)
        try:
            result = runner.invoke(explain, ["a1", "--path", str(path)])
            assert result.exit_code == 0
            assert "P2" in result.output
            assert "87%" in result.output
        finally:
            path.unlink()

    def test_unknown_alert_id(self):
        path = _write_timeline(_SAMPLE_ENTRIES)
        try:
            result = runner.invoke(explain, ["nonexistent", "--path", str(path)])
            assert result.exit_code == 0
            assert "No triage found" in result.output
        finally:
            path.unlink()


class TestCosts:
    def test_shows_summary(self):
        path = _write_timeline(_SAMPLE_ENTRIES)
        try:
            result = runner.invoke(costs, ["--path", str(path)])
            assert result.exit_code == 0
            assert "Alerts received" in result.output
            assert "Triage calls" in result.output
            assert "Tickets created" in result.output
        finally:
            path.unlink()

    def test_empty_timeline(self):
        path = _write_timeline([])
        try:
            result = runner.invoke(costs, ["--path", str(path)])
            assert result.exit_code == 0
            assert "0" in result.output
        finally:
            path.unlink()
