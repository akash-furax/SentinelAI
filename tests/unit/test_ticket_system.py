"""Tests for ticket system contract and plugins."""

import pytest

from sentinelai.contracts.ticket_system import TicketResult, TicketSystem
from sentinelai.core.errors import TicketCreationError
from sentinelai.core.events import Priority, TriageComplete
from sentinelai.core.plugin import load_plugin


def _make_triage() -> TriageComplete:
    return TriageComplete(
        alert_id="test-1",
        severity=Priority.P2,
        root_cause_hypothesis="Connection pool exhaustion",
        confidence=0.87,
        affected_services=["auth-service"],
        recommended_action="Increase pool size",
        ai_reasoning="Full reasoning chain",
        trace_id="trace-abc",
    )


class TestTicketResult:
    def test_creates_with_fields(self):
        result = TicketResult(
            alert_id="test-1",
            ticket_id="JIRA-123",
            ticket_url="https://jira.example.com/browse/JIRA-123",
            trace_id="trace-abc",
        )
        assert result.ticket_id == "JIRA-123"
        assert result.ticket_url.startswith("https://")


class TestJiraPlugin:
    def test_loads(self):
        plugin = load_plugin("sentinelai.plugins.tickets.jira", TicketSystem)
        assert isinstance(plugin, TicketSystem)

    @pytest.mark.asyncio
    async def test_missing_config_raises(self, monkeypatch):
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        monkeypatch.delenv("JIRA_PROJECT_KEY", raising=False)

        from sentinelai.plugins.tickets.jira import JiraTicketSystem

        plugin = JiraTicketSystem()
        with pytest.raises(TicketCreationError, match="Missing Jira configuration"):
            await plugin.create_ticket(_make_triage())


class TestGitHubIssuesPlugin:
    def test_loads(self):
        plugin = load_plugin("sentinelai.plugins.tickets.github_issues", TicketSystem)
        assert isinstance(plugin, TicketSystem)

    @pytest.mark.asyncio
    async def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_REPO", raising=False)

        from sentinelai.plugins.tickets.github_issues import GitHubIssuesTicketSystem

        plugin = GitHubIssuesTicketSystem()
        with pytest.raises(TicketCreationError, match="GITHUB_TOKEN not set"):
            await plugin.create_ticket(_make_triage())

    @pytest.mark.asyncio
    async def test_missing_repo_raises(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        monkeypatch.delenv("GITHUB_REPO", raising=False)

        from sentinelai.plugins.tickets.github_issues import GitHubIssuesTicketSystem

        plugin = GitHubIssuesTicketSystem()
        with pytest.raises(TicketCreationError, match="GITHUB_REPO not set"):
            await plugin.create_ticket(_make_triage())
