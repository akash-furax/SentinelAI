"""GitHub Issues ticket system plugin — creates GitHub issues from triage results.

Requires environment variables:
    GITHUB_TOKEN: GitHub personal access token (or fine-grained token with issues:write)
    GITHUB_REPO: Repository in owner/repo format (e.g., acme/api-server)
"""

from __future__ import annotations

import json
import logging
import os

import httpx

from sentinelai.contracts.ticket_system import TicketResult, TicketSystem
from sentinelai.core.errors import TicketCreationError
from sentinelai.core.events import TriageComplete

logger = logging.getLogger("sentinelai.tickets.github_issues")

_SEVERITY_LABELS = {
    "P1": "priority: critical",
    "P2": "priority: high",
    "P3": "priority: medium",
    "P4": "priority: low",
    "UNKNOWN": "needs-triage",
}


class GitHubIssuesTicketSystem(TicketSystem):
    """Creates GitHub Issues from triage results via the GitHub REST API."""

    def __init__(self) -> None:
        self._token = os.environ.get("GITHUB_TOKEN", "")
        self._repo = os.environ.get("GITHUB_REPO", "")

    async def create_ticket(self, triage: TriageComplete) -> TicketResult:
        if not self._token:
            raise TicketCreationError("GITHUB_TOKEN not set", trace_id=triage.trace_id)
        if not self._repo:
            raise TicketCreationError("GITHUB_REPO not set (expected: owner/repo)", trace_id=triage.trace_id)

        severity_label = _SEVERITY_LABELS.get(triage.severity.value, "needs-triage")
        labels = ["sentinelai", severity_label]

        body = (
            f"## Root Cause Hypothesis\n{triage.root_cause_hypothesis}\n\n"
            f"**Confidence:** {triage.confidence:.0%}\n"
            f"**Affected Services:** {', '.join(triage.affected_services)}\n"
            f"**Recommended Action:** {triage.recommended_action}\n\n"
            f"---\n"
            f"### AI Reasoning\n{triage.ai_reasoning}\n\n"
            f"---\n"
            f"*Created by SentinelAI | Alert: {triage.alert_id} | Trace: {triage.trace_id}*"
        )

        payload = {
            "title": f"[{triage.severity.value}] {triage.root_cause_hypothesis[:100]}",
            "body": body,
            "labels": labels,
        }

        api_url = f"https://api.github.com/repos/{self._repo}/issues"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    api_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Accept": "application/vnd.github.v3+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
            except httpx.TimeoutException as e:
                raise TicketCreationError(f"GitHub API timeout: {e}", trace_id=triage.trace_id) from e
            except httpx.HTTPError as e:
                raise TicketCreationError(f"GitHub API error: {e}", trace_id=triage.trace_id) from e

        if resp.status_code == 422:
            raise TicketCreationError(
                f"GitHub rejected the issue (422): {resp.text[:300]}. "
                f"Check that GITHUB_REPO={self._repo} exists and labels are valid.",
                trace_id=triage.trace_id,
            )

        if resp.status_code not in (200, 201):
            raise TicketCreationError(
                f"GitHub API error {resp.status_code}: {resp.text[:300]}",
                trace_id=triage.trace_id,
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise TicketCreationError(f"GitHub returned non-JSON response: {e}", trace_id=triage.trace_id) from e

        issue_number = str(data.get("number", "unknown"))
        issue_url = data.get("html_url", f"https://github.com/{self._repo}/issues/{issue_number}")

        logger.info(
            "GitHub issue created",
            extra={
                "trace_id": triage.trace_id,
                "ticket_id": issue_number,
                "ticket_url": issue_url,
                "event": "ticket.created",
            },
        )

        return TicketResult(
            alert_id=triage.alert_id,
            ticket_id=issue_number,
            ticket_url=issue_url,
            trace_id=triage.trace_id,
        )
