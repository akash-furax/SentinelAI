"""Tests for code fixer contract, events, and plugin loading."""

import tempfile
from pathlib import Path

import pytest

from sentinelai.contracts.code_fixer import CodeFixer
from sentinelai.core.errors import CodeFixError, CodeFixNoFilesError, CodeFixTimeoutError, PRCreationError
from sentinelai.core.events import CodeFix, FixGenerated, Priority, PROpened, TriageComplete
from sentinelai.core.plugin import load_plugin


def _make_triage(affected_files: list[str] | None = None) -> TriageComplete:
    return TriageComplete(
        alert_id="test-fix-1",
        severity=Priority.P2,
        root_cause_hypothesis="Connection pool exhaustion in auth service",
        confidence=0.87,
        affected_services=["auth-service"],
        recommended_action="Increase pool max_size from 50 to 200",
        ai_reasoning="The error logs show all 50 connections are in use...",
        affected_files=affected_files or [],
        trace_id="trace-fix-1",
    )


class TestCodeFixEvent:
    def test_creates_code_fix(self):
        fix = CodeFix(
            file_path="src/auth/pool.py",
            original_content="MAX_POOL = 50",
            fixed_content="MAX_POOL = 200",
            description="Increase connection pool max size",
        )
        assert fix.file_path == "src/auth/pool.py"
        assert fix.original_content != fix.fixed_content

    def test_creates_fix_generated(self):
        fix = FixGenerated(
            alert_id="test-1",
            fixes=[
                CodeFix("src/pool.py", "old", "new", "fix pool"),
            ],
            test_code="def test_pool(): assert MAX_POOL == 200",
            test_file_path="tests/test_fix_test-1.py",
            rationale="Pool was undersized",
            confidence=0.85,
            rollback_instructions="git revert HEAD",
            trace_id="trace-1",
        )
        assert len(fix.fixes) == 1
        assert fix.confidence == 0.85

    def test_creates_pr_opened(self):
        pr = PROpened(
            alert_id="test-1",
            pr_number=42,
            pr_url="https://github.com/org/repo/pull/42",
            branch_name="sentinelai/fix-test-1-20260325",
            trace_id="trace-1",
        )
        assert pr.pr_number == 42
        assert "pull/42" in pr.pr_url


class TestCodeFixErrors:
    def test_code_fix_error_hierarchy(self):
        assert issubclass(CodeFixTimeoutError, CodeFixError)
        assert issubclass(CodeFixNoFilesError, CodeFixError)

    def test_pr_creation_error(self):
        err = PRCreationError("push failed", trace_id="t1")
        assert err.trace_id == "t1"


class TestClaudeFixerPlugin:
    def test_loads(self):
        plugin = load_plugin("sentinelai.plugins.fixers.claude_fixer", CodeFixer)
        assert isinstance(plugin, CodeFixer)

    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from sentinelai.plugins.fixers.claude_fixer import ClaudeCodeFixer

        fixer = ClaudeCodeFixer()
        with pytest.raises(CodeFixError, match="ANTHROPIC_API_KEY not set"):
            await fixer.generate_fix(_make_triage(), "/tmp")


class TestFaultDomainDiscovery:
    def test_finds_files_by_triage_affected_files(self):
        from sentinelai.plugins.fixers.claude_fixer import _find_fault_domain_files

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file matching affected_files
            (Path(tmpdir) / "src" / "auth").mkdir(parents=True)
            target = Path(tmpdir) / "src" / "auth" / "pool.py"
            target.write_text("MAX_POOL = 50")

            triage = _make_triage(affected_files=["src/auth/pool.py"])
            files = _find_fault_domain_files(tmpdir, triage)
            assert len(files) == 1
            assert files[0].name == "pool.py"

    def test_finds_files_by_service_name(self):
        from sentinelai.plugins.fixers.claude_fixer import _find_fault_domain_files

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "auth_service").mkdir()
            target = Path(tmpdir) / "auth_service" / "handler.py"
            target.write_text("def handle(): pass")

            triage = _make_triage()  # affected_services=["auth-service"]
            files = _find_fault_domain_files(tmpdir, triage)
            assert len(files) >= 1

    def test_returns_empty_for_no_matches(self):
        from sentinelai.plugins.fixers.claude_fixer import _find_fault_domain_files

        with tempfile.TemporaryDirectory() as tmpdir:
            triage = _make_triage()
            files = _find_fault_domain_files(tmpdir, triage)
            assert len(files) == 0


class TestGitHubPROpener:
    def test_loads(self):
        from sentinelai.contracts.pr_opener import PROpener

        plugin = load_plugin("sentinelai.plugins.pr_openers.github_pr", PROpener)
        assert isinstance(plugin, PROpener)

    @pytest.mark.asyncio
    async def test_missing_token_raises(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        from sentinelai.plugins.pr_openers.github_pr import GitHubPROpener

        opener = GitHubPROpener()
        fix = FixGenerated(
            alert_id="t1",
            fixes=[],
            test_code="",
            test_file_path="",
            rationale="",
            confidence=0.5,
            rollback_instructions="",
            trace_id="t1",
        )
        triage = _make_triage()
        with pytest.raises(PRCreationError, match="GITHUB_TOKEN not set"):
            await opener.open_pr(fix, triage, "/tmp")
