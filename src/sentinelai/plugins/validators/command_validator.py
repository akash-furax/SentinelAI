"""Command-based validator — runs shell commands for post-deploy validation.

The generic validator: any test suite, health check, or verification script.
Works with pytest, Playwright, curl health checks, or custom scripts.

Configuration via environment variables:
    SENTINELAI_VALIDATE_COMMANDS: Semicolon-separated list of validation commands.
        Each command is run independently. ALL must pass (exit 0) for validation to pass.
        Placeholders: {deploy_id}, {alert_id}, {environment}
        Example: "pytest tests/smoke/;curl -sf http://localhost:8080/health"
    SENTINELAI_VALIDATE_TIMEOUT: Max seconds per validation command (default: 120)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from sentinelai.contracts.validator import Validator
from sentinelai.core.errors import ValidationError
from sentinelai.core.events import DeployStarted, ValidationResult

logger = logging.getLogger("sentinelai.validators.command")


class CommandValidator(Validator):
    """Validates deployments by running configurable shell commands."""

    def __init__(self) -> None:
        self._commands_str = os.environ.get("SENTINELAI_VALIDATE_COMMANDS", "")
        self._timeout = int(os.environ.get("SENTINELAI_VALIDATE_TIMEOUT", "120"))

    async def validate(self, deploy: DeployStarted) -> ValidationResult:
        if not self._commands_str:
            raise ValidationError(
                "SENTINELAI_VALIDATE_COMMANDS not set. "
                "Example: export SENTINELAI_VALIDATE_COMMANDS='pytest tests/smoke/;curl -sf http://localhost/health'",
                trace_id=deploy.trace_id,
            )

        commands = [
            cmd.strip().format(
                deploy_id=deploy.deploy_id,
                alert_id=deploy.alert_id,
                environment=deploy.environment,
            )
            for cmd in self._commands_str.split(";")
            if cmd.strip()
        ]

        if not commands:
            raise ValidationError("No validation commands found after parsing", trace_id=deploy.trace_id)

        start = time.monotonic()
        total = len(commands)
        passed = 0
        failures: list[str] = []

        for i, cmd in enumerate(commands, 1):
            logger.info(
                f"Running validation check {i}/{total}",
                extra={
                    "trace_id": deploy.trace_id,
                    "deploy_id": deploy.deploy_id,
                    "command": cmd,
                    "event": "validation.check_started",
                },
            )

            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
                returncode = proc.returncode or 0
            except TimeoutError:
                failures.append(f"Check {i} timed out ({self._timeout}s): {cmd}")
                logger.warning(
                    f"Validation check {i} timed out",
                    extra={"trace_id": deploy.trace_id, "command": cmd, "event": "validation.check_timeout"},
                )
                continue
            except OSError as e:
                failures.append(f"Check {i} failed to execute: {cmd} — {e}")
                continue

            if returncode == 0:
                passed += 1
                logger.info(
                    f"Validation check {i} passed",
                    extra={"trace_id": deploy.trace_id, "command": cmd, "event": "validation.check_passed"},
                )
            else:
                error_output = stderr.decode()[:200] if stderr else stdout.decode()[:200]
                failures.append(f"Check {i} failed (exit {returncode}): {cmd} — {error_output}")
                logger.warning(
                    f"Validation check {i} failed",
                    extra={
                        "trace_id": deploy.trace_id,
                        "command": cmd,
                        "exit_code": returncode,
                        "event": "validation.check_failed",
                    },
                )

        duration = time.monotonic() - start
        all_passed = passed == total

        logger.info(
            "Validation complete",
            extra={
                "trace_id": deploy.trace_id,
                "passed": all_passed,
                "checks": f"{passed}/{total}",
                "duration_s": f"{duration:.1f}",
                "event": "validation.complete",
            },
        )

        return ValidationResult(
            alert_id=deploy.alert_id,
            passed=all_passed,
            total_checks=total,
            passed_checks=passed,
            failed_checks=failures,
            duration_seconds=duration,
            trace_id=deploy.trace_id,
        )
