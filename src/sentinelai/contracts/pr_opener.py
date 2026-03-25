"""Abstract contract for PR opener plugins.

PR openers take a generated fix, commit it to a branch, and open
a pull request for human review. The human approval gate is enforced
here — AI cannot self-merge.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sentinelai.core.events import FixGenerated, PROpened, TriageComplete


class PROpener(ABC):
    """Base contract for all PR opener plugins."""

    @abstractmethod
    async def open_pr(
        self,
        fix: FixGenerated,
        triage: TriageComplete,
        repo_path: str,
    ) -> PROpened:
        """Create a branch, commit the fix, and open a pull request.

        Args:
            fix: The generated code fix with file changes and tests.
            triage: The triage result (used for PR description).
            repo_path: Path to the local repository root.

        Returns:
            PROpened event with PR number, URL, and branch name.

        Raises:
            PRCreationError on failure — never generic exceptions.
        """
        ...  # pragma: no cover
