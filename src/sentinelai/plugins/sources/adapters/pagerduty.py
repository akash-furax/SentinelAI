"""PagerDuty webhook adapter (Events API v2 / Webhooks v3).

Normalizes PagerDuty incident webhook payloads into SentinelAI AlertDetected events.

PagerDuty webhook reference:
    https://developer.pagerduty.com/docs/webhooks/v3-overview/

Typical PagerDuty v3 webhook payload:
    {
        "event": {
            "id": "...",
            "event_type": "incident.triggered",
            "resource_type": "incident",
            "occurred_at": "...",
            "data": {
                "id": "P123ABC",
                "title": "High CPU on auth-service",
                "urgency": "high",
                "status": "triggered",
                "service": {"id": "...", "summary": "Auth Service"},
                ...
            }
        }
    }
"""

from __future__ import annotations

import uuid

from sentinelai.core.events import AlertDetected

from .base import AlertAdapter


class PagerDutyAdapter(AlertAdapter):
    """Translates PagerDuty webhook payloads to AlertDetected."""

    def normalize(self, payload: dict, headers: dict[str, str] | None = None) -> AlertDetected:
        event = payload.get("event", {})
        data = event.get("data", payload.get("incident", payload))

        incident_id = data.get("id", str(uuid.uuid4()))
        title = data.get("title", data.get("summary", "PagerDuty incident"))

        # PagerDuty nests service info
        service = data.get("service", {})
        service_name = service.get("summary", service.get("name", "unknown-service"))

        # Build a rich summary from available fields
        urgency = data.get("urgency", "unknown")
        status = data.get("status", "triggered")
        summary = f"[{urgency.upper()}] {title} (status: {status})"

        return AlertDetected(
            alert_id=f"pd-{incident_id}",
            source="pagerduty",
            service_name=service_name,
            summary=summary,
            raw_payload=payload,
        )
