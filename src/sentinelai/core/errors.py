"""Named error hierarchy for SentinelAI.

Per CODING-STANDARDS.md rule 4: every failure is named and handled explicitly.
No catch-all handlers. Each error carries trace_id, timestamp, and message.

Error tree:
    SentinelAIError
    ├── AlertSourceError
    │   └── WebhookAuthError
    ├── TriageError
    │   ├── TriageTimeoutError
    │   ├── TriageRateLimitError
    │   └── TriageMalformedResponse
    ├── TicketCreationError
    ├── ConfigValidationError
    ├── PluginLoadError
    └── RateLimitExceeded
"""

from __future__ import annotations

from datetime import UTC, datetime


class SentinelAIError(Exception):
    """Base error for all SentinelAI exceptions."""

    def __init__(
        self,
        message: str,
        trace_id: str = "",
        timestamp: datetime | None = None,
    ) -> None:
        self.trace_id = trace_id
        self.timestamp = timestamp or datetime.now(UTC)
        super().__init__(message)


class AlertSourceError(SentinelAIError):
    """Alert source connection or parsing failed."""


class WebhookAuthError(AlertSourceError):
    """Webhook request failed HMAC signature verification."""


class TriageError(SentinelAIError):
    """AI triage call failed."""


class TriageTimeoutError(TriageError):
    """AI triage call exceeded the configured timeout."""


class TriageRateLimitError(TriageError):
    """AI provider returned HTTP 429 — rate limited."""


class TriageMalformedResponse(TriageError):
    """AI provider returned an unparseable or empty response."""


class TicketCreationError(SentinelAIError):
    """Ticket system is unreachable or rejected the request."""


class ConfigValidationError(SentinelAIError):
    """Configuration is missing required keys or has invalid values."""


class PluginLoadError(SentinelAIError):
    """Plugin module not found or does not implement the required contract."""


class RateLimitExceeded(SentinelAIError):
    """Max tickets/hour or AI calls/minute threshold exceeded."""
