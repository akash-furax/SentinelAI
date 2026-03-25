"""Abstract contract for validator plugins.

Validators run post-deployment checks to verify the fix works in production.
Generic by design: implementations can run shell commands, Playwright tests,
HTTP health checks, or any custom validation logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sentinelai.core.events import DeployStarted, ValidationResult


class Validator(ABC):
    """Base contract for all validator plugins."""

    @abstractmethod
    async def validate(self, deploy: DeployStarted) -> ValidationResult:
        """Run post-deployment validation checks.

        Returns ValidationResult with pass/fail status and check details.
        Raises ValidationError on infrastructure failure (not test failure —
        a test failure is a ValidationResult with passed=False).
        """
        ...  # pragma: no cover
