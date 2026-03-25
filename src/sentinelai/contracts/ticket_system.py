"""Abstract contract for ticket system plugins.

Ticket systems create tickets/issues from triage results.
Implementations must raise TicketCreationError (not generic exceptions) on failure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sentinelai.core.events import TriageComplete


@dataclass
class TicketResult:
    """Result of creating a ticket in an external system."""

    alert_id: str
    ticket_id: str  # Provider-defined (e.g., "JIRA-123", "42" for GitHub Issues)
    ticket_url: str
    trace_id: str = ""


class TicketSystem(ABC):
    """Base contract for all ticket system plugins."""

    @abstractmethod
    async def create_ticket(self, triage: TriageComplete) -> TicketResult:
        """Create a ticket from a triage result.

        Must raise TicketCreationError (not a generic exception) on failure.
        Must complete within the configured timeout.
        """
        ...  # pragma: no cover
