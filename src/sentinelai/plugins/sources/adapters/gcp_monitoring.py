"""GCP Cloud Monitoring webhook adapter.

Normalizes GCP Monitoring alert payloads (from notification channels)
into SentinelAI AlertDetected events.

GCP Monitoring webhook reference:
    https://cloud.google.com/monitoring/alerts/using-channels-api#webhook

Typical GCP Monitoring payload:
    {
        "incident": {
            "incident_id": "...",
            "condition_name": "CPU > 90%",
            "resource_name": "auth-service-prod",
            "state": "open",
            "summary": "...",
            "url": "https://console.cloud.google.com/monitoring/..."
        },
        "policy_name": "Auth Service Health"
    }
"""

from __future__ import annotations

import uuid

from sentinelai.core.events import AlertDetected

from .base import AlertAdapter


class GCPMonitoringAdapter(AlertAdapter):
    """Translates GCP Cloud Monitoring webhook payloads to AlertDetected."""

    def normalize(self, payload: dict, headers: dict[str, str] | None = None) -> AlertDetected:
        incident = payload.get("incident", {})

        incident_id = incident.get("incident_id", str(uuid.uuid4()))
        condition = incident.get("condition_name", "")
        resource = incident.get("resource_name", incident.get("resource", {}).get("labels", {}).get("instance_id", ""))
        policy = payload.get("policy_name", "")
        state = incident.get("state", "open")

        # Derive service name from resource name or labels
        service_name = resource if resource else policy.lower().replace(" ", "-")
        if not service_name:
            service_name = "unknown-gcp-service"

        # Build summary
        summary_parts = []
        if condition:
            summary_parts.append(condition)
        if incident.get("summary"):
            summary_parts.append(incident["summary"])
        if state:
            summary_parts.append(f"(state: {state})")

        summary = " — ".join(summary_parts) if summary_parts else f"GCP alert on {service_name}"

        return AlertDetected(
            alert_id=f"gcp-{incident_id}",
            source="gcp_monitoring",
            service_name=service_name,
            summary=summary,
            raw_payload=payload,
        )
