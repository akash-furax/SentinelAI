"""Abstract contract for alert source plugins.

Alert sources produce AlertDetected events from external systems.
Implementations must raise AlertSourceError (not generic exceptions) on failure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from sentinelai.core.events import AlertDetected


class AlertSource(ABC):
    """Base contract for all alert source plugins."""

    @abstractmethod
    async def read_alerts(self) -> AsyncIterator[AlertDetected]:
        """Yield alerts from the source.

        For streaming sources (webhooks), this yields indefinitely.
        For batch sources (files), this yields all alerts then returns.

        Must raise AlertSourceError on failure — never a generic exception.
        """
        ...  # pragma: no cover
        yield  # type: ignore[misc]  # pragma: no cover
