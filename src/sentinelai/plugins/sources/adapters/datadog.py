"""Datadog webhook adapter.

Normalizes Datadog webhook payloads (from Monitor Alerts and Events)
into SentinelAI AlertDetected events.

Datadog webhook payload reference:
    https://docs.datadoghq.com/integrations/webhooks/

Typical Datadog payload fields:
    - id: alert ID
    - title: alert title
    - body: alert body/description
    - alertType: "error" | "warning" | "info" | "success"
    - hostname: affected host
    - tags: comma-separated tags
    - priority: "normal" | "low"
"""

from __future__ import annotations

import uuid

from sentinelai.core.events import AlertDetected

from .base import AlertAdapter


class DatadogAdapter(AlertAdapter):
    """Translates Datadog webhook payloads to AlertDetected."""

    def normalize(self, payload: dict, headers: dict[str, str] | None = None) -> AlertDetected:
        alert_id = str(payload.get("id", payload.get("alert_id", str(uuid.uuid4()))))

        # Datadog uses "hostname" or tags to identify the service
        hostname = payload.get("hostname", "")
        tags = payload.get("tags", "")
        service_name = self._extract_service(hostname, tags)

        # Title is the best summary — body has the full context
        title = payload.get("title", "")
        body = payload.get("body", "")
        summary = title if title else body[:200]

        return AlertDetected(
            alert_id=f"dd-{alert_id}",
            source="datadog",
            service_name=service_name,
            summary=summary,
            raw_payload=payload,
        )

    def _extract_service(self, hostname: str, tags: str) -> str:
        """Extract service name from Datadog hostname or tags.

        Datadog tags format: "service:auth-api,env:production,team:platform"
        """
        # Check tags for service tag
        if isinstance(tags, str):
            for tag in tags.split(","):
                tag = tag.strip()
                if tag.startswith("service:"):
                    return tag.split(":", 1)[1]

        # Fall back to hostname
        if hostname:
            return hostname

        return "unknown-service"
