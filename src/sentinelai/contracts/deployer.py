"""Abstract contract for deployer plugins.

Deployers take a merged commit and deploy it to the target environment.
They must support rollback if the deployment or validation fails.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sentinelai.core.events import DeployStarted, PRMerged


class Deployer(ABC):
    """Base contract for all deployer plugins."""

    @abstractmethod
    async def deploy(self, merge_event: PRMerged) -> DeployStarted:
        """Deploy the merged commit to the target environment.

        Raises DeployError on failure — never generic exceptions.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def rollback(self, deploy: DeployStarted) -> None:
        """Roll back a deployment. Called when validation fails.

        Raises DeployError on failure.
        """
        ...  # pragma: no cover
