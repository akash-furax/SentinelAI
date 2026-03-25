"""Abstract contract for triage engine plugins.

Triage engines analyze alerts and produce severity classifications
with root cause hypotheses. Implementations must raise TriageError
subtypes (not generic exceptions) on failure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sentinelai.core.events import AlertDetected, TriageComplete


class TriageEngine(ABC):
    """Base contract for all triage engine plugins."""

    @abstractmethod
    async def triage(self, alert: AlertDetected) -> TriageComplete:
        """Analyze an alert and produce a triage result.

        Must raise TriageError subtypes on failure:
        - TriageTimeoutError if the AI call exceeds the configured timeout
        - TriageRateLimitError if the AI provider returns 429
        - TriageMalformedResponse if the response cannot be parsed

        Must complete within the configured timeout (default: 60s).
        """
        ...  # pragma: no cover
