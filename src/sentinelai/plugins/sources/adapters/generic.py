"""Generic adapter — fallback for unknown or custom monitoring tools.

Expects the payload to contain at minimum: "service_name" and "summary".
Any additional fields are preserved in raw_payload.
"""

from __future__ import annotations

import uuid

from sentinelai.core.events import AlertDetected

from .base import AlertAdapter


class GenericAdapter(AlertAdapter):
    """Fallback adapter for payloads that don't match any known provider."""

    def normalize(self, payload: dict, headers: dict[str, str] | None = None) -> AlertDetected:
        return AlertDetected(
            alert_id=payload.get("alert_id", str(uuid.uuid4())),
            source=payload.get("source", "webhook"),
            service_name=payload.get("service_name", payload.get("service", "unknown-service")),
            summary=payload.get("summary", payload.get("title", payload.get("message", "No summary provided"))),
            raw_payload=payload,
        )
