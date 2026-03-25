"""Tests for file_source alert plugin."""

import json
import tempfile
from pathlib import Path

import pytest

from sentinelai.core.errors import AlertSourceError
from sentinelai.plugins.sources.file_source import FileAlertSource


async def _collect(source: FileAlertSource) -> list:
    results = []
    async for alert in source.read_alerts():
        results.append(alert)
    return results


class TestFileAlertSource:
    def _write_json(self, data) -> Path:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, f)
        f.close()
        return Path(f.name)

    @pytest.mark.asyncio
    async def test_reads_single_alert(self):
        path = self._write_json(
            {
                "service_name": "auth",
                "summary": "error spike",
            }
        )
        try:
            source = FileAlertSource(path)
            alerts = await _collect(source)
            assert len(alerts) == 1
            assert alerts[0].service_name == "auth"
        finally:
            path.unlink()

    @pytest.mark.asyncio
    async def test_reads_array_of_alerts(self):
        path = self._write_json(
            [
                {"service_name": "auth", "summary": "error A"},
                {"service_name": "payment", "summary": "error B"},
            ]
        )
        try:
            source = FileAlertSource(path)
            alerts = await _collect(source)
            assert len(alerts) == 2
        finally:
            path.unlink()

    @pytest.mark.asyncio
    async def test_generates_alert_id_if_missing(self):
        path = self._write_json({"service_name": "auth", "summary": "error"})
        try:
            source = FileAlertSource(path)
            alerts = await _collect(source)
            assert alerts[0].alert_id  # UUID generated
        finally:
            path.unlink()

    @pytest.mark.asyncio
    async def test_file_not_found_raises(self):
        source = FileAlertSource("/nonexistent/file.json")
        with pytest.raises(AlertSourceError, match="Alert file not found"):
            await _collect(source)

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        f.write("{invalid json")
        f.close()
        path = Path(f.name)
        try:
            source = FileAlertSource(path)
            with pytest.raises(AlertSourceError, match="Invalid JSON"):
                await _collect(source)
        finally:
            path.unlink()

    @pytest.mark.asyncio
    async def test_missing_required_fields_raises(self):
        path = self._write_json({"alert_id": "test"})  # Missing service_name and summary
        try:
            source = FileAlertSource(path)
            with pytest.raises(AlertSourceError, match="missing required fields"):
                await _collect(source)
        finally:
            path.unlink()

    @pytest.mark.asyncio
    async def test_no_file_configured_raises(self):
        source = FileAlertSource()
        with pytest.raises(AlertSourceError, match="no file path configured"):
            await _collect(source)
