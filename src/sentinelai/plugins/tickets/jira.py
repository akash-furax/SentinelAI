"""Jira ticket system plugin — creates Jira issues from triage results.

Requires environment variables:
    JIRA_URL: Base URL of your Jira instance (e.g., https://your-org.atlassian.net)
    JIRA_EMAIL: Email for Jira API authentication
    JIRA_API_TOKEN: Jira API token
    JIRA_PROJECT_KEY: Project key for ticket creation (e.g., OPS)
"""

from __future__ import annotations

import json
import logging
import os

import httpx

from sentinelai.contracts.ticket_system import TicketResult, TicketSystem
from sentinelai.core.errors import TicketCreationError
from sentinelai.core.events import TriageComplete

logger = logging.getLogger("sentinelai.tickets.jira")


class JiraTicketSystem(TicketSystem):
    """Creates Jira issues from triage results via the Jira REST API."""

    def __init__(self) -> None:
        self._url = os.environ.get("JIRA_URL", "").rstrip("/")
        self._email = os.environ.get("JIRA_EMAIL", "")
        self._token = os.environ.get("JIRA_API_TOKEN", "")
        self._project = os.environ.get("JIRA_PROJECT_KEY", "")

    async def create_ticket(self, triage: TriageComplete) -> TicketResult:
        if not all([self._url, self._email, self._token, self._project]):
            missing = []
            if not self._url:
                missing.append("JIRA_URL")
            if not self._email:
                missing.append("JIRA_EMAIL")
            if not self._token:
                missing.append("JIRA_API_TOKEN")
            if not self._project:
                missing.append("JIRA_PROJECT_KEY")
            raise TicketCreationError(
                f"Missing Jira configuration: {', '.join(missing)}",
                trace_id=triage.trace_id,
            )

        priority_map = {"P1": "Highest", "P2": "High", "P3": "Medium", "P4": "Low", "UNKNOWN": "Medium"}
        jira_priority = priority_map.get(triage.severity.value, "Medium")

        description = (
            f"*Root Cause Hypothesis:*\n{triage.root_cause_hypothesis}\n\n"
            f"*Confidence:* {triage.confidence:.0%}\n"
            f"*Affected Services:* {', '.join(triage.affected_services)}\n"
            f"*Recommended Action:* {triage.recommended_action}\n\n"
            f"----\n"
            f"*AI Reasoning:*\n{triage.ai_reasoning}\n\n"
            f"_Created by SentinelAI | Alert ID: {triage.alert_id} | Trace: {triage.trace_id}_"
        )

        payload = {
            "fields": {
                "project": {"key": self._project},
                "summary": f"[{triage.severity.value}] {triage.root_cause_hypothesis[:100]}",
                "description": description,
                "issuetype": {"name": "Bug"},
                "priority": {"name": jira_priority},
                "labels": ["sentinelai", f"severity-{triage.severity.value.lower()}"],
            }
        }

        api_url = f"{self._url}/rest/api/2/issue"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    api_url,
                    json=payload,
                    auth=(self._email, self._token),
                    headers={"Content-Type": "application/json"},
                )
            except httpx.TimeoutException as e:
                raise TicketCreationError(f"Jira API timeout: {e}", trace_id=triage.trace_id) from e
            except httpx.HTTPError as e:
                raise TicketCreationError(f"Jira API connection error: {e}", trace_id=triage.trace_id) from e

        if resp.status_code == 429:
            raise TicketCreationError("Jira API rate limited (429)", trace_id=triage.trace_id)

        if resp.status_code not in (200, 201):
            raise TicketCreationError(
                f"Jira API error {resp.status_code}: {resp.text[:300]}",
                trace_id=triage.trace_id,
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise TicketCreationError(f"Jira returned non-JSON response: {e}", trace_id=triage.trace_id) from e

        ticket_key = data.get("key", "UNKNOWN")
        ticket_url = f"{self._url}/browse/{ticket_key}"

        logger.info(
            "Jira ticket created",
            extra={
                "trace_id": triage.trace_id,
                "ticket_id": ticket_key,
                "ticket_url": ticket_url,
                "severity": triage.severity.value,
                "event": "ticket.created",
            },
        )

        return TicketResult(
            alert_id=triage.alert_id,
            ticket_id=ticket_key,
            ticket_url=ticket_url,
            trace_id=triage.trace_id,
        )
