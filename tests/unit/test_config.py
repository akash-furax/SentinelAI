"""Tests for configuration loading and validation."""

import tempfile
from pathlib import Path

import pytest

from sentinelai.core.config import SentinelConfig
from sentinelai.core.errors import ConfigValidationError

_VALID_CONFIG = """\
pipeline:
  alert_source: sentinelai.plugins.sources.file_source
  triage_engine: sentinelai.plugins.triage.claude

settings:
  dedup_window_minutes: 5

timeouts:
  triage_timeout_seconds: 60
"""


def _write_config(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


class TestConfigLoad:
    def test_loads_valid_config(self):
        path = _write_config(_VALID_CONFIG)
        try:
            config = SentinelConfig.load(path)
            assert config.pipeline.alert_source == "sentinelai.plugins.sources.file_source"
            assert config.pipeline.triage_engine == "sentinelai.plugins.triage.claude"
            assert config.dedup_window_minutes == 5
        finally:
            path.unlink()

    def test_missing_file_raises(self):
        with pytest.raises(ConfigValidationError, match="Config file not found"):
            SentinelConfig.load("/nonexistent/path.yaml")

    def test_invalid_yaml_raises(self):
        path = _write_config("{{invalid yaml: [")
        try:
            with pytest.raises(ConfigValidationError, match="Invalid YAML"):
                SentinelConfig.load(path)
        finally:
            path.unlink()

    def test_non_mapping_yaml_raises(self):
        path = _write_config("- just\n- a\n- list")
        try:
            with pytest.raises(ConfigValidationError, match="must be a YAML mapping"):
                SentinelConfig.load(path)
        finally:
            path.unlink()

    def test_missing_alert_source_raises(self):
        path = _write_config("pipeline:\n  triage_engine: foo")
        try:
            with pytest.raises(ConfigValidationError, match="alert_source is required"):
                SentinelConfig.load(path)
        finally:
            path.unlink()

    def test_missing_triage_engine_raises(self):
        path = _write_config("pipeline:\n  alert_source: foo")
        try:
            with pytest.raises(ConfigValidationError, match="triage_engine is required"):
                SentinelConfig.load(path)
        finally:
            path.unlink()

    def test_defaults_applied(self):
        path = _write_config(_VALID_CONFIG)
        try:
            config = SentinelConfig.load(path)
            assert config.timeouts.triage_timeout_seconds == 60
            assert config.retry.max_retries == 3
            assert config.retry.jitter is True
            assert config.rate_limits.ai_calls_per_minute == 20
        finally:
            path.unlink()


class TestValidateApiKeys:
    def test_missing_anthropic_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = SentinelConfig()
        config.pipeline.triage_engine = "sentinelai.plugins.triage.claude"
        issues = config.validate_api_keys()
        assert len(issues) == 1
        assert "ANTHROPIC_API_KEY" in issues[0]

    def test_invalid_anthropic_key_format(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "invalid-key")
        config = SentinelConfig()
        config.pipeline.triage_engine = "sentinelai.plugins.triage.claude"
        issues = config.validate_api_keys()
        assert len(issues) == 1
        assert "doesn't look like" in issues[0]

    def test_valid_anthropic_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test123")
        config = SentinelConfig()
        config.pipeline.triage_engine = "sentinelai.plugins.triage.claude"
        issues = config.validate_api_keys()
        assert len(issues) == 0
