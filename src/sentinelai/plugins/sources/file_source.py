"""File-based alert source — reads alerts from JSON files.

Used for local development, testing, and `sentinelai demo`.
Per CODING-STANDARDS.md rule 2: this is NOT a mock — it reads real
alert data from real files. The file_source is a legitimate alert
source for offline/batch processing.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from sentinelai.contracts.alert_source import AlertSource
from sentinelai.core.errors import AlertSourceError
from sentinelai.core.events import AlertDetected


class FileAlertSource(AlertSource):
    """Reads AlertDetected events from a JSON file.

    Expected file format: JSON array of alert objects, or a single alert object.
    Required fields per alert: alert_id, source, service_name, summary, raw_payload.
    Optional fields: timestamp, trace_id (auto-generated if absent).
    """

    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file_path = Path(file_path) if file_path else None

    def configure(self, file_path: str | Path) -> None:
        self._file_path = Path(file_path)

    async def read_alerts(self) -> AsyncIterator[AlertDetected]:
        if self._file_path is None:
            raise AlertSourceError("FileAlertSource: no file path configured")

        if not self._file_path.exists():
            raise AlertSourceError(f"Alert file not found: {self._file_path}. Check the file path and try again.")

        try:
            raw_text = self._file_path.read_text()
        except OSError as e:
            raise AlertSourceError(f"Failed to read alert file {self._file_path}: {e}") from e

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise AlertSourceError(f"Invalid JSON in alert file {self._file_path}: {e}") from e

        alerts = data if isinstance(data, list) else [data]

        for i, alert_data in enumerate(alerts):
            if not isinstance(alert_data, dict):
                raise AlertSourceError(f"Alert #{i} in {self._file_path} is not a JSON object")

            required_fields = ["service_name", "summary"]
            missing = [f for f in required_fields if f not in alert_data]
            if missing:
                raise AlertSourceError(
                    f"Alert #{i} in {self._file_path} is missing required fields: {missing}. "
                    f"Required: {required_fields}"
                )

            yield AlertDetected(
                alert_id=alert_data.get("alert_id", str(uuid.uuid4())),
                source=alert_data.get("source", "file_source"),
                service_name=alert_data["service_name"],
                summary=alert_data["summary"],
                raw_payload=alert_data.get("raw_payload", alert_data),
                trace_id=alert_data.get("trace_id", ""),
            )
