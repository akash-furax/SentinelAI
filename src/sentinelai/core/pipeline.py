"""Pipeline orchestrator — wires plugins and manages alert flow.

Pipeline flow:
    AlertSource.read_alerts()
        │
        ▼
    dedup check (fingerprint + TTL)
        │
        ▼
    TriageEngine.triage()
        │
        ▼
    console output (Phase 1) / TicketSystem (Phase 1.5+)

All events are logged to the incident timeline (JSONL) for audit.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sentinelai.core.errors import (
    RateLimitExceeded,
    TriageError,
    TriageMalformedResponse,
    TriageRateLimitError,
    TriageTimeoutError,
)
from sentinelai.core.events import AlertDetected, Priority, TriageComplete

if TYPE_CHECKING:
    from sentinelai.contracts.alert_source import AlertSource
    from sentinelai.contracts.ticket_system import TicketSystem
    from sentinelai.contracts.triage_engine import TriageEngine
    from sentinelai.core.config import SentinelConfig

logger = logging.getLogger("sentinelai.pipeline")


def _fingerprint(summary: str) -> str:
    """Generate a dedup fingerprint from an alert summary.

    Algorithm (explicit ordered steps):
        1. Lowercase
        2. Strip all non-alphanumeric and non-space characters
        3. Collapse consecutive whitespace to single space
        4. Strip leading/trailing whitespace
        5. SHA-256
        6. First 16 hex chars
    """
    normalized = summary.lower()
    normalized = re.sub(r"[^a-z0-9 ]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


class DedupStore:
    """In-memory TTL-based deduplication store.

    v1 limitation: state is lost on process restart. Acceptable for Phase 1.
    Persistent store (SQLite-backed) is a Phase 2 enhancement if needed.
    """

    def __init__(self, window_minutes: int = 5) -> None:
        self._window_seconds = window_minutes * 60
        self._seen: dict[str, tuple[datetime, str]] = {}  # key -> (timestamp, original_summary)
        self._dedup_count = 0

    def is_duplicate(self, alert: AlertDetected) -> bool:
        """Check if this alert is a duplicate within the dedup window."""
        self._evict_expired()

        key = f"{alert.service_name}:{_fingerprint(alert.summary)}"
        now = datetime.now(UTC)

        if key in self._seen:
            _stored_ts, stored_summary = self._seen[key]
            # Collision fallback: full-string comparison on hash match
            if stored_summary != alert.summary:
                return False  # Hash collision — different alert, let it through
            self._dedup_count += 1
            logger.info(
                "Alert deduplicated",
                extra={
                    "alert_id": alert.alert_id,
                    "trace_id": alert.trace_id,
                    "service_name": alert.service_name,
                    "event": "alert.deduplicated",
                    "dedup_count": self._dedup_count,
                },
            )
            return True

        self._seen[key] = (now, alert.summary)
        return False

    def _evict_expired(self) -> None:
        now = datetime.now(UTC)
        expired = [k for k, (ts, _) in self._seen.items() if (now - ts).total_seconds() > self._window_seconds]
        for k in expired:
            del self._seen[k]


class Pipeline:
    """Orchestrates the alert → triage → output flow."""

    def __init__(
        self,
        config: SentinelConfig,
        alert_source: AlertSource,
        triage_engine: TriageEngine,
        ticket_system: TicketSystem | None = None,
        timeline_path: Path | None = None,
    ) -> None:
        self._config = config
        self._alert_source = alert_source
        self._triage_engine = triage_engine
        self._ticket_system = ticket_system
        self._dedup = DedupStore(config.dedup_window_minutes)
        self._timeline_path = timeline_path or Path("incidents/timeline.jsonl")
        self._ai_calls_this_minute = 0
        self._minute_start = datetime.now(UTC)

    async def run(self) -> list[TriageComplete]:
        """Run the pipeline: read alerts, dedup, triage, output.

        Returns list of triage results (for CLI display).
        """
        results: list[TriageComplete] = []

        async for alert in self._alert_source.read_alerts():
            alert = self._assign_trace_id(alert)
            self._log_timeline(alert, "alert.detected")

            if self._dedup.is_duplicate(alert):
                self._log_timeline(alert, "alert.deduplicated")
                continue

            try:
                self._check_rate_limit(alert.trace_id)
                triage_result = await self._triage_with_retry(alert)
            except RateLimitExceeded:
                self._log_timeline(alert, "alert.rate_limited")
                continue
            except TriageError as e:
                triage_result = self._fallback_triage(alert, e)

            self._log_timeline(triage_result, "triage.complete")
            results.append(triage_result)

            # Create ticket if a ticket system is configured
            if self._ticket_system is not None:
                try:
                    ticket = await self._ticket_system.create_ticket(triage_result)
                    self._log_timeline_raw(
                        {
                            "event_type": "ticket.created",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "trace_id": triage_result.trace_id,
                            "alert_id": triage_result.alert_id,
                            "ticket_id": ticket.ticket_id,
                            "ticket_url": ticket.ticket_url,
                        }
                    )
                except Exception as e:
                    logger.error(
                        "Ticket creation failed",
                        extra={
                            "trace_id": triage_result.trace_id,
                            "error": str(e),
                            "event": "ticket.creation_failed",
                        },
                    )

        return results

    async def _triage_with_retry(self, alert: AlertDetected) -> TriageComplete:
        """Triage with retry logic for transient failures.

        Retry policy: triage uses max 2 retries (override of global default 3).
        Backoff: exponential with jitter per config.
        """
        max_retries = min(2, self._config.retry.max_retries)
        last_error: TriageError | None = None

        for attempt in range(max_retries + 1):
            try:
                return await asyncio.wait_for(
                    self._triage_engine.triage(alert),
                    timeout=self._config.timeouts.triage_timeout_seconds,
                )
            except TimeoutError:
                last_error = TriageTimeoutError(
                    f"Triage timed out after {self._config.timeouts.triage_timeout_seconds}s "
                    f"(attempt {attempt + 1}/{max_retries + 1})",
                    trace_id=alert.trace_id,
                )
                logger.warning(
                    "Triage timeout",
                    extra={
                        "trace_id": alert.trace_id,
                        "attempt": attempt + 1,
                        "event": "triage.timeout",
                    },
                )
            except TriageRateLimitError as e:
                last_error = e
                logger.warning(
                    "Triage rate limited by provider",
                    extra={
                        "trace_id": alert.trace_id,
                        "attempt": attempt + 1,
                        "event": "triage.rate_limited",
                    },
                )
            except TriageMalformedResponse:
                raise  # Don't retry malformed responses — they won't improve
            except TriageError as e:
                last_error = e

            if attempt < max_retries:
                backoff = min(
                    self._config.retry.backoff_base_seconds * (2**attempt),
                    self._config.retry.backoff_max_seconds,
                )
                await asyncio.sleep(backoff)

        raise last_error  # type: ignore[misc]

    def _fallback_triage(self, alert: AlertDetected, error: TriageError) -> TriageComplete:
        """Create a fallback triage result when AI triage fails."""
        return TriageComplete(
            alert_id=alert.alert_id,
            severity=Priority.UNKNOWN,
            root_cause_hypothesis="AI triage failed — manual review required.",
            confidence=0.0,
            affected_services=[alert.service_name],
            recommended_action=f"Manual triage needed. Error: {error}",
            ai_reasoning=f"Triage failed after retries. Error type: {type(error).__name__}. Message: {error}",
            trace_id=alert.trace_id,
        )

    def _assign_trace_id(self, alert: AlertDetected) -> AlertDetected:
        """Assign a trace_id if one wasn't provided by the source."""
        if not alert.trace_id:
            alert.trace_id = str(uuid.uuid4())
        return alert

    def _check_rate_limit(self, trace_id: str) -> None:
        """Enforce AI calls per minute rate limit."""
        now = datetime.now(UTC)
        if (now - self._minute_start).total_seconds() >= 60:
            self._ai_calls_this_minute = 0
            self._minute_start = now

        if self._ai_calls_this_minute >= self._config.rate_limits.ai_calls_per_minute:
            raise RateLimitExceeded(
                f"AI call rate limit exceeded: {self._config.rate_limits.ai_calls_per_minute}/min",
                trace_id=trace_id,
            )

        self._ai_calls_this_minute += 1

    def _log_timeline(self, event: AlertDetected | TriageComplete, event_type: str) -> None:
        """Append event to the incident timeline (JSONL audit log)."""
        self._timeline_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "trace_id": event.trace_id,
            "alert_id": event.alert_id,
        }

        if isinstance(event, TriageComplete):
            entry["severity"] = event.severity.value
            entry["confidence"] = event.confidence

        with open(self._timeline_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _log_timeline_raw(self, entry: dict) -> None:
        """Append a pre-built entry to the timeline."""
        self._timeline_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._timeline_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
