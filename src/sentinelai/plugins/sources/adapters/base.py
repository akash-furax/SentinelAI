"""Base adapter and auto-detection logic.

Provider detection flow:
    1. Check request headers for provider signatures
    2. Check payload structure for known fields
    3. Fall back to GenericAdapter
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sentinelai.core.events import AlertDetected


class AlertAdapter(ABC):
    """Base class for alert payload adapters."""

    @abstractmethod
    def normalize(self, payload: dict, headers: dict[str, str] | None = None) -> AlertDetected:
        """Convert a provider-specific payload to AlertDetected.

        Args:
            payload: The parsed JSON body from the webhook request.
            headers: HTTP request headers (lowercased keys).

        Returns:
            AlertDetected event with normalized fields.
        """
        ...  # pragma: no cover

    def _safe_get(self, data: dict, *keys: str, default: str = "") -> str:
        """Safely traverse nested dicts."""
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key, default)
            else:
                return default
        return str(current) if current is not None else default


def detect_provider(payload: dict, headers: dict[str, str] | None = None) -> str:
    """Detect the monitoring provider from headers or payload structure.

    Returns: "datadog", "pagerduty", "gcp_monitoring", or "generic"
    """
    headers = headers or {}

    # Header-based detection
    if "x-datadog-signature" in headers or "dd-api-key" in headers:
        return "datadog"
    if "x-pagerduty-signature" in headers or "x-webhook-id" in headers:
        # PagerDuty sends x-webhook-id
        if isinstance(payload.get("event"), dict) and "incident" in str(payload.get("event", {}).get("event_type", "")):
            return "pagerduty"
    if headers.get("user-agent", "").startswith("Google-Alerts"):
        return "gcp_monitoring"

    # Payload structure detection
    if "alertType" in payload and "hostname" in payload:
        return "datadog"
    if "incident" in payload and "service" in payload.get("incident", {}):
        return "pagerduty"
    if "incident" in payload and "condition_name" in payload.get("incident", {}):
        return "gcp_monitoring"
    if "policy_name" in payload or "condition" in payload:
        return "gcp_monitoring"

    return "generic"
