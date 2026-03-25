"""Tests for Phase 3: deploy, validate, and close events + plugins."""

import pytest

from sentinelai.contracts.deployer import Deployer
from sentinelai.contracts.validator import Validator
from sentinelai.core.errors import (
    DeployError,
    DeployRollbackError,
    SentinelAIError,
    ValidationError,
)
from sentinelai.core.events import (
    DeployStarted,
    PRMerged,
    TicketClosed,
    ValidationResult,
)
from sentinelai.core.plugin import load_plugin


class TestPhase3Events:
    def test_pr_merged(self):
        event = PRMerged(
            alert_id="a1",
            pr_number=42,
            merge_commit_sha="abc123def456",
            branch_name="sentinelai/fix-a1",
            trace_id="t1",
        )
        assert event.merge_commit_sha == "abc123def456"

    def test_deploy_started(self):
        event = DeployStarted(
            alert_id="a1",
            deploy_id="d-123",
            environment="production",
            strategy="command",
            trace_id="t1",
        )
        assert event.environment == "production"
        assert event.strategy == "command"

    def test_validation_result_pass(self):
        result = ValidationResult(
            alert_id="a1",
            passed=True,
            total_checks=3,
            passed_checks=3,
            failed_checks=[],
            duration_seconds=12.5,
            trace_id="t1",
        )
        assert result.passed is True
        assert result.total_checks == result.passed_checks

    def test_validation_result_fail(self):
        result = ValidationResult(
            alert_id="a1",
            passed=False,
            total_checks=3,
            passed_checks=1,
            failed_checks=["Check 2 failed: health check returned 503", "Check 3 timed out"],
            duration_seconds=45.0,
        )
        assert result.passed is False
        assert len(result.failed_checks) == 2

    def test_ticket_closed(self):
        event = TicketClosed(
            alert_id="a1",
            ticket_id="JIRA-42",
            resolution="auto-closed: all validation checks passed",
            trace_id="t1",
        )
        assert "auto-closed" in event.resolution


class TestPhase3Errors:
    def test_deploy_error_hierarchy(self):
        assert issubclass(DeployError, SentinelAIError)
        assert issubclass(DeployRollbackError, DeployError)
        assert issubclass(ValidationError, SentinelAIError)

    def test_deploy_rollback_carries_context(self):
        err = DeployRollbackError("rollback failed", trace_id="t1")
        assert err.trace_id == "t1"
        assert isinstance(err, DeployError)


class TestCommandDeployer:
    def test_loads(self):
        plugin = load_plugin("sentinelai.plugins.deployers.command_deployer", Deployer)
        assert isinstance(plugin, Deployer)

    @pytest.mark.asyncio
    async def test_missing_command_raises(self, monkeypatch):
        monkeypatch.delenv("SENTINELAI_DEPLOY_COMMAND", raising=False)
        from sentinelai.plugins.deployers.command_deployer import CommandDeployer

        deployer = CommandDeployer()
        merge = PRMerged(alert_id="a1", pr_number=1, merge_commit_sha="abc", branch_name="b", trace_id="t1")
        with pytest.raises(DeployError, match="SENTINELAI_DEPLOY_COMMAND not set"):
            await deployer.deploy(merge)

    @pytest.mark.asyncio
    async def test_deploy_success(self, monkeypatch):
        monkeypatch.setenv("SENTINELAI_DEPLOY_COMMAND", "echo deployed {commit_sha}")
        monkeypatch.setenv("SENTINELAI_DEPLOY_ENVIRONMENT", "staging")
        from sentinelai.plugins.deployers.command_deployer import CommandDeployer

        deployer = CommandDeployer()
        merge = PRMerged(alert_id="a1", pr_number=1, merge_commit_sha="abc123", branch_name="b", trace_id="t1")
        result = await deployer.deploy(merge)
        assert result.environment == "staging"
        assert result.strategy == "command"
        assert result.alert_id == "a1"

    @pytest.mark.asyncio
    async def test_deploy_failure(self, monkeypatch):
        monkeypatch.setenv("SENTINELAI_DEPLOY_COMMAND", "exit 1")
        from sentinelai.plugins.deployers.command_deployer import CommandDeployer

        deployer = CommandDeployer()
        merge = PRMerged(alert_id="a1", pr_number=1, merge_commit_sha="abc", branch_name="b", trace_id="t1")
        with pytest.raises(DeployError, match="Deploy command failed"):
            await deployer.deploy(merge)


class TestCommandValidator:
    def test_loads(self):
        plugin = load_plugin("sentinelai.plugins.validators.command_validator", Validator)
        assert isinstance(plugin, Validator)

    @pytest.mark.asyncio
    async def test_missing_commands_raises(self, monkeypatch):
        monkeypatch.delenv("SENTINELAI_VALIDATE_COMMANDS", raising=False)
        from sentinelai.plugins.validators.command_validator import CommandValidator

        validator = CommandValidator()
        deploy = DeployStarted(alert_id="a1", deploy_id="d1", environment="prod", strategy="cmd", trace_id="t1")
        with pytest.raises(ValidationError, match="SENTINELAI_VALIDATE_COMMANDS not set"):
            await validator.validate(deploy)

    @pytest.mark.asyncio
    async def test_all_checks_pass(self, monkeypatch):
        monkeypatch.setenv("SENTINELAI_VALIDATE_COMMANDS", "echo check1;echo check2")
        from sentinelai.plugins.validators.command_validator import CommandValidator

        validator = CommandValidator()
        deploy = DeployStarted(alert_id="a1", deploy_id="d1", environment="prod", strategy="cmd", trace_id="t1")
        result = await validator.validate(deploy)
        assert result.passed is True
        assert result.total_checks == 2
        assert result.passed_checks == 2

    @pytest.mark.asyncio
    async def test_partial_failure(self, monkeypatch):
        monkeypatch.setenv("SENTINELAI_VALIDATE_COMMANDS", "echo ok;exit 1;echo ok2")
        from sentinelai.plugins.validators.command_validator import CommandValidator

        validator = CommandValidator()
        deploy = DeployStarted(alert_id="a1", deploy_id="d1", environment="prod", strategy="cmd", trace_id="t1")
        result = await validator.validate(deploy)
        assert result.passed is False
        assert result.passed_checks == 2
        assert result.total_checks == 3
        assert len(result.failed_checks) == 1
