"""Configuration loading and validation.

Per CODING-STANDARDS.md rule 7: all configuration is external, validated at startup,
and the service refuses to start if required values are absent or invalid.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from sentinelai.core.errors import ConfigValidationError

_DEFAULT_CONFIG_PATH = "sentinelai.yaml"


@dataclass
class TimeoutConfig:
    triage_timeout_seconds: int = 60
    alert_source_timeout_seconds: int = 10


@dataclass
class RetryConfig:
    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 30.0
    jitter: bool = True


@dataclass
class RateLimitConfig:
    ai_calls_per_minute: int = 20
    max_tickets_per_hour: int = 10


@dataclass
class PipelineConfig:
    alert_source: str = ""
    triage_engine: str = ""


@dataclass
class SentinelConfig:
    """Top-level configuration for SentinelAI."""

    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)
    dedup_window_minutes: int = 5

    @classmethod
    def load(cls, path: str | Path | None = None) -> SentinelConfig:
        """Load config from YAML file and validate.

        Raises ConfigValidationError if the file is missing, unparseable,
        or contains invalid/missing required values.
        """
        config_path = Path(path) if path else Path(_DEFAULT_CONFIG_PATH)

        if not config_path.exists():
            raise ConfigValidationError(
                f"Config file not found: {config_path}. Create {_DEFAULT_CONFIG_PATH} or pass --config path."
            )

        try:
            raw = yaml.safe_load(config_path.read_text())
        except yaml.YAMLError as e:
            raise ConfigValidationError(f"Invalid YAML in {config_path}: {e}") from e

        if not isinstance(raw, dict):
            raise ConfigValidationError(
                f"Config file {config_path} must be a YAML mapping, got {type(raw).__name__}"
            )

        config = cls()

        pipeline_raw = raw.get("pipeline", {})
        if isinstance(pipeline_raw, dict):
            config.pipeline = PipelineConfig(
                alert_source=pipeline_raw.get("alert_source", ""),
                triage_engine=pipeline_raw.get("triage_engine", ""),
            )

        timeouts_raw = raw.get("timeouts", {})
        if isinstance(timeouts_raw, dict):
            config.timeouts = TimeoutConfig(
                triage_timeout_seconds=int(timeouts_raw.get("triage_timeout_seconds", 60)),
                alert_source_timeout_seconds=int(timeouts_raw.get("alert_source_timeout_seconds", 10)),
            )

        retry_raw = raw.get("retry", {})
        if isinstance(retry_raw, dict):
            config.retry = RetryConfig(
                max_retries=int(retry_raw.get("max_retries", 3)),
                backoff_base_seconds=float(retry_raw.get("backoff_base_seconds", 1.0)),
                backoff_max_seconds=float(retry_raw.get("backoff_max_seconds", 30.0)),
                jitter=bool(retry_raw.get("jitter", True)),
            )

        rate_raw = raw.get("rate_limits", {})
        if isinstance(rate_raw, dict):
            config.rate_limits = RateLimitConfig(
                ai_calls_per_minute=int(rate_raw.get("ai_calls_per_minute", 20)),
                max_tickets_per_hour=int(rate_raw.get("max_tickets_per_hour", 10)),
            )

        settings_raw = raw.get("settings", {})
        if isinstance(settings_raw, dict):
            config.dedup_window_minutes = int(settings_raw.get("dedup_window_minutes", 5))

        config.validate()
        return config

    def validate(self) -> None:
        """Validate that all required configuration is present and valid.

        Raises ConfigValidationError with a specific description of what's wrong.
        """
        errors: list[str] = []

        if not self.pipeline.alert_source:
            errors.append("pipeline.alert_source is required (module path to alert source plugin)")

        if not self.pipeline.triage_engine:
            errors.append("pipeline.triage_engine is required (module path to triage engine plugin)")

        if self.timeouts.triage_timeout_seconds <= 0:
            errors.append("timeouts.triage_timeout_seconds must be > 0")

        if self.retry.max_retries < 0:
            errors.append("retry.max_retries must be >= 0")

        if self.dedup_window_minutes < 0:
            errors.append("settings.dedup_window_minutes must be >= 0")

        if errors:
            raise ConfigValidationError("Configuration validation failed:\n  - " + "\n  - ".join(errors))

    def validate_api_keys(self) -> list[str]:
        """Check that required API keys are present in environment.

        Returns list of issues found (empty = all good).
        Does NOT raise — used by `sentinelai doctor`.
        """
        issues: list[str] = []

        if "claude" in self.pipeline.triage_engine:
            key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                issues.append(
                    "ANTHROPIC_API_KEY is not set. Required for Claude triage plugin. "
                    "Set it: export ANTHROPIC_API_KEY=sk-ant-..."
                )
            elif not key.startswith("sk-ant-"):
                issues.append(
                    "ANTHROPIC_API_KEY doesn't look like a valid Anthropic key (expected prefix: sk-ant-)"
                )

        return issues
