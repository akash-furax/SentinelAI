"""Tests for error hierarchy."""

from sentinelai.core.errors import (
    AlertSourceError,
    ConfigValidationError,
    PluginLoadError,
    RateLimitExceeded,
    SentinelAIError,
    TicketCreationError,
    TriageError,
    TriageMalformedResponse,
    TriageRateLimitError,
    TriageTimeoutError,
    WebhookAuthError,
)


class TestErrorHierarchy:
    def test_all_errors_inherit_from_base(self):
        errors = [
            AlertSourceError,
            WebhookAuthError,
            TriageError,
            TriageTimeoutError,
            TriageRateLimitError,
            TriageMalformedResponse,
            TicketCreationError,
            ConfigValidationError,
            PluginLoadError,
            RateLimitExceeded,
        ]
        for error_cls in errors:
            assert issubclass(error_cls, SentinelAIError)

    def test_webhook_auth_is_alert_source_error(self):
        assert issubclass(WebhookAuthError, AlertSourceError)

    def test_triage_subtypes(self):
        assert issubclass(TriageTimeoutError, TriageError)
        assert issubclass(TriageRateLimitError, TriageError)
        assert issubclass(TriageMalformedResponse, TriageError)

    def test_error_carries_trace_id(self):
        err = TriageTimeoutError("timeout", trace_id="abc-123")
        assert err.trace_id == "abc-123"
        assert str(err) == "timeout"

    def test_error_carries_timestamp(self):
        err = SentinelAIError("test")
        assert err.timestamp is not None
