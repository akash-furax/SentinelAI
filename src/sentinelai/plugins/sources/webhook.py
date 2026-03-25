"""Webhook alert source — receives alerts via authenticated HTTP POST.

Runs an async HTTP server that accepts alert payloads. Each request is
verified with HMAC-SHA256 signature before processing.

Requires environment variables:
    SENTINELAI_WEBHOOK_SECRET: Shared secret for HMAC signature verification
    SENTINELAI_WEBHOOK_PORT: Port to listen on (default: 8090)

Signature format:
    Header: X-Sentinel-Signature: sha256=<hex_digest>
    Computed: HMAC-SHA256(secret, request_body)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from collections.abc import AsyncIterator

from sentinelai.contracts.alert_source import AlertSource
from sentinelai.core.errors import AlertSourceError, WebhookAuthError
from sentinelai.core.events import AlertDetected

logger = logging.getLogger("sentinelai.sources.webhook")

_MAX_BODY_SIZE = 1_048_576  # 1 MB


class WebhookAlertSource(AlertSource):
    """HTTP webhook alert source with HMAC-SHA256 authentication.

    Starts an HTTP server and yields AlertDetected events as requests arrive.
    """

    def __init__(self) -> None:
        self._secret = os.environ.get("SENTINELAI_WEBHOOK_SECRET", "")
        self._port = int(os.environ.get("SENTINELAI_WEBHOOK_PORT", "8090"))
        self._queue: asyncio.Queue[AlertDetected] = asyncio.Queue()

    def _verify_signature(self, body: bytes, signature_header: str) -> None:
        """Verify HMAC-SHA256 signature. Raises WebhookAuthError on failure."""
        if not self._secret:
            raise WebhookAuthError("SENTINELAI_WEBHOOK_SECRET not set — cannot verify webhook signatures")

        if not signature_header.startswith("sha256="):
            raise WebhookAuthError("Invalid signature format. Expected: sha256=<hex_digest>")

        expected = "sha256=" + hmac.new(self._secret.encode(), body, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected, signature_header):
            raise WebhookAuthError("HMAC signature verification failed")

    async def _handle_request(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle a single HTTP request."""
        try:
            # Read request line
            request_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not request_line:
                writer.close()
                return

            # Read headers
            headers: dict[str, str] = {}
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=10.0)
                if line == b"\r\n" or line == b"\n" or not line:
                    break
                if b":" in line:
                    key, val = line.decode().split(":", 1)
                    headers[key.strip().lower()] = val.strip()

            # Read body
            content_length = int(headers.get("content-length", "0"))
            if content_length > _MAX_BODY_SIZE:
                self._send_response(writer, 413, "Payload too large")
                return

            body = await asyncio.wait_for(reader.read(content_length), timeout=10.0) if content_length > 0 else b""

            # Verify signature
            signature = headers.get("x-sentinel-signature", "")
            try:
                self._verify_signature(body, signature)
            except WebhookAuthError as e:
                logger.warning("Webhook auth failed", extra={"event": "webhook.auth_failed", "error": str(e)})
                self._send_response(writer, 401, str(e))
                return

            # Parse body
            try:
                data = json.loads(body)
            except json.JSONDecodeError as e:
                self._send_response(writer, 400, f"Invalid JSON: {e}")
                return

            if not isinstance(data, dict):
                self._send_response(writer, 400, "Expected JSON object")
                return

            # Auto-detect provider and normalize payload
            alert = self._normalize_payload(data, headers)

            await self._queue.put(alert)
            self._send_response(writer, 202, json.dumps({"status": "accepted", "alert_id": alert.alert_id}))

        except TimeoutError:
            self._send_response(writer, 408, "Request timeout")
        except Exception as e:
            logger.error("Webhook handler error", extra={"event": "webhook.error", "error": str(e)})
            self._send_response(writer, 500, "Internal error")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def _normalize_payload(self, data: dict, headers: dict[str, str]) -> AlertDetected:
        """Auto-detect monitoring provider and normalize to AlertDetected.

        Detection flow:
            1. Check headers for provider signatures (Datadog, PagerDuty, GCP)
            2. Check payload structure for known fields
            3. Fall back to generic adapter (requires service_name + summary)
        """
        from sentinelai.plugins.sources.adapters.base import detect_provider
        from sentinelai.plugins.sources.adapters.datadog import DatadogAdapter
        from sentinelai.plugins.sources.adapters.gcp_monitoring import GCPMonitoringAdapter
        from sentinelai.plugins.sources.adapters.generic import GenericAdapter
        from sentinelai.plugins.sources.adapters.pagerduty import PagerDutyAdapter

        provider = detect_provider(data, headers)

        adapters = {
            "datadog": DatadogAdapter(),
            "pagerduty": PagerDutyAdapter(),
            "gcp_monitoring": GCPMonitoringAdapter(),
            "generic": GenericAdapter(),
        }

        adapter = adapters.get(provider, GenericAdapter())
        alert = adapter.normalize(data, headers)

        logger.info(
            "Alert normalized",
            extra={
                "provider": provider,
                "alert_id": alert.alert_id,
                "service_name": alert.service_name,
                "event": "webhook.normalized",
            },
        )

        return alert

    def _send_response(self, writer: asyncio.StreamWriter, status: int, body: str) -> None:
        status_text = {
            200: "OK",
            201: "Created",
            202: "Accepted",
            400: "Bad Request",
            401: "Unauthorized",
            408: "Timeout",
            413: "Payload Too Large",
            500: "Internal Server Error",
        }
        writer.write(
            f"HTTP/1.1 {status} {status_text.get(status, 'Error')}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"\r\n{body}".encode()
        )

    async def read_alerts(self) -> AsyncIterator[AlertDetected]:
        if not self._secret:
            raise AlertSourceError(
                "SENTINELAI_WEBHOOK_SECRET not set. Required for webhook authentication. "
                "Set it: export SENTINELAI_WEBHOOK_SECRET=your-secret-here"
            )

        server = await asyncio.start_server(self._handle_request, "0.0.0.0", self._port)
        logger.info(
            "Webhook server started",
            extra={"event": "webhook.started", "port": self._port},
        )

        async with server:
            server_task = asyncio.create_task(server.serve_forever())
            try:
                while True:
                    alert = await self._queue.get()
                    yield alert
            finally:
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass
