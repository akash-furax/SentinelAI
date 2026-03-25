"""Tests for webhook alert source."""

import hashlib
import hmac

import pytest

from sentinelai.contracts.alert_source import AlertSource
from sentinelai.core.errors import AlertSourceError, WebhookAuthError
from sentinelai.core.plugin import load_plugin
from sentinelai.plugins.sources.webhook import WebhookAlertSource


class TestWebhookSignature:
    def test_valid_signature(self, monkeypatch):
        monkeypatch.setenv("SENTINELAI_WEBHOOK_SECRET", "test-secret")
        source = WebhookAlertSource()

        body = b'{"service_name": "auth", "summary": "error"}'
        sig = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

        # Should not raise
        source._verify_signature(body, sig)

    def test_invalid_signature_raises(self, monkeypatch):
        monkeypatch.setenv("SENTINELAI_WEBHOOK_SECRET", "test-secret")
        source = WebhookAlertSource()

        body = b'{"service_name": "auth", "summary": "error"}'
        with pytest.raises(WebhookAuthError, match="HMAC signature verification failed"):
            source._verify_signature(body, "sha256=invalid")

    def test_missing_prefix_raises(self, monkeypatch):
        monkeypatch.setenv("SENTINELAI_WEBHOOK_SECRET", "test-secret")
        source = WebhookAlertSource()

        with pytest.raises(WebhookAuthError, match="Invalid signature format"):
            source._verify_signature(b"body", "no-prefix-here")

    def test_missing_secret_raises(self, monkeypatch):
        monkeypatch.delenv("SENTINELAI_WEBHOOK_SECRET", raising=False)
        source = WebhookAlertSource()

        with pytest.raises(WebhookAuthError, match="SENTINELAI_WEBHOOK_SECRET not set"):
            source._verify_signature(b"body", "sha256=test")


class TestWebhookPlugin:
    def test_loads(self):
        plugin = load_plugin("sentinelai.plugins.sources.webhook", AlertSource)
        assert isinstance(plugin, AlertSource)

    @pytest.mark.asyncio
    async def test_missing_secret_in_read_alerts_raises(self, monkeypatch):
        monkeypatch.delenv("SENTINELAI_WEBHOOK_SECRET", raising=False)
        source = WebhookAlertSource()
        with pytest.raises(AlertSourceError, match="SENTINELAI_WEBHOOK_SECRET not set"):
            async for _ in source.read_alerts():
                pass
