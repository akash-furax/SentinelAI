"""Abstract contract for code fixer plugins.

Code fixers analyze triaged alerts against a codebase and generate
targeted fixes with tests. This is the differentiating capability
of SentinelAI — no other OSS tool does this.

Implementations must raise CodeFixError (not generic exceptions) on failure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sentinelai.core.events import FixGenerated, TriageComplete


class CodeFixer(ABC):
    """Base contract for all code fixer plugins."""

    @abstractmethod
    async def generate_fix(
        self,
        triage: TriageComplete,
        repo_path: str,
    ) -> FixGenerated:
        """Generate a code fix based on the triage result and codebase.

        Args:
            triage: The completed triage with RCA hypothesis and affected files.
            repo_path: Path to the local repository root.

        Returns:
            FixGenerated event with file changes, test code, and rationale.

        Raises:
            CodeFixError subtypes on failure — never generic exceptions.
        """
        ...  # pragma: no cover
