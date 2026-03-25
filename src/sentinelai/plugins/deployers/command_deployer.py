"""Command-based deployer — runs shell commands for deployment and rollback.

The most generic deployer: configure any deploy/rollback workflow as shell commands.
Works with any CI/CD system, any cloud provider, any container orchestrator.

Configuration via environment variables:
    SENTINELAI_DEPLOY_COMMAND: Shell command to run for deployment
        Placeholders: {commit_sha}, {branch}, {alert_id}, {environment}
        Example: "cd /app && git pull && docker-compose up -d"
    SENTINELAI_ROLLBACK_COMMAND: Shell command to run for rollback
        Example: "cd /app && git revert HEAD --no-edit && docker-compose up -d"
    SENTINELAI_DEPLOY_ENVIRONMENT: Target environment (default: "production")
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

from sentinelai.contracts.deployer import Deployer
from sentinelai.core.errors import DeployError, DeployRollbackError
from sentinelai.core.events import DeployStarted, PRMerged

logger = logging.getLogger("sentinelai.deployers.command")


async def _run_command(cmd: str, timeout: int = 300) -> tuple[int, str, str]:
    """Run a shell command asynchronously. Returns (returncode, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, stdout.decode(), stderr.decode()
    except TimeoutError as e:
        raise DeployError(f"Deploy command timed out after {timeout}s: {cmd}") from e
    except OSError as e:
        raise DeployError(f"Failed to execute deploy command: {e}") from e


class CommandDeployer(Deployer):
    """Deploys by running configurable shell commands."""

    def __init__(self) -> None:
        self._deploy_cmd = os.environ.get("SENTINELAI_DEPLOY_COMMAND", "")
        self._rollback_cmd = os.environ.get("SENTINELAI_ROLLBACK_COMMAND", "")
        self._environment = os.environ.get("SENTINELAI_DEPLOY_ENVIRONMENT", "production")

    async def deploy(self, merge_event: PRMerged) -> DeployStarted:
        if not self._deploy_cmd:
            raise DeployError(
                "SENTINELAI_DEPLOY_COMMAND not set. Configure the deploy command. "
                "Example: export SENTINELAI_DEPLOY_COMMAND='./deploy.sh {commit_sha}'",
                trace_id=merge_event.trace_id,
            )

        cmd = self._deploy_cmd.format(
            commit_sha=merge_event.merge_commit_sha,
            branch=merge_event.branch_name,
            alert_id=merge_event.alert_id,
            environment=self._environment,
        )

        deploy_id = str(uuid.uuid4())[:8]

        logger.info(
            "Starting deployment",
            extra={
                "trace_id": merge_event.trace_id,
                "deploy_id": deploy_id,
                "command": cmd,
                "environment": self._environment,
                "event": "deploy.started",
            },
        )

        returncode, _stdout, stderr = await _run_command(cmd)

        if returncode != 0:
            raise DeployError(
                f"Deploy command failed (exit {returncode}): {stderr[:500]}",
                trace_id=merge_event.trace_id,
            )

        logger.info(
            "Deployment completed",
            extra={
                "trace_id": merge_event.trace_id,
                "deploy_id": deploy_id,
                "event": "deploy.completed",
            },
        )

        return DeployStarted(
            alert_id=merge_event.alert_id,
            deploy_id=deploy_id,
            environment=self._environment,
            strategy="command",
            trace_id=merge_event.trace_id,
        )

    async def rollback(self, deploy: DeployStarted) -> None:
        if not self._rollback_cmd:
            raise DeployRollbackError(
                "SENTINELAI_ROLLBACK_COMMAND not set. Manual rollback required.",
                trace_id=deploy.trace_id,
            )

        cmd = self._rollback_cmd.format(
            deploy_id=deploy.deploy_id,
            alert_id=deploy.alert_id,
            environment=deploy.environment,
        )

        logger.warning(
            "Starting rollback",
            extra={"trace_id": deploy.trace_id, "deploy_id": deploy.deploy_id, "event": "deploy.rollback"},
        )

        returncode, _stdout, stderr = await _run_command(cmd)

        if returncode != 0:
            raise DeployRollbackError(
                f"Rollback failed (exit {returncode}): {stderr[:500]}. MANUAL INTERVENTION REQUIRED.",
                trace_id=deploy.trace_id,
            )

        logger.info(
            "Rollback completed",
            extra={"trace_id": deploy.trace_id, "deploy_id": deploy.deploy_id, "event": "deploy.rolled_back"},
        )
