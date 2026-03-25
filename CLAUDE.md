# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SentinelAI is an open-source AI-powered DevOps automation framework — autonomous incident response with pluggable providers. Users bring their own AI keys (Claude, Gemini). The full pipeline: alert → triage → code fix → PR → deploy → validate → auto-rollback.

**Status:** All phases implemented (1, 1.5, 2, 3). 105 tests passing. 11 CLI commands.

## Commands

```bash
# Development
pip install -e ".[dev]"                    # Install with dev dependencies
pytest                                      # Run all tests
pytest tests/unit/test_config.py -v         # Run a single test file
ruff check src/ tests/                      # Lint
ruff format src/ tests/                     # Format
pip-audit                                   # Dependency security audit

# Usage
sentinelai run                              # Start pipeline (webhook listener)
sentinelai triage --file alert.json         # One-shot triage
sentinelai fix --file alert.json --repo .   # Triage + code fix + PR
sentinelai deploy --commit abc123           # Deploy + validate + auto-rollback
sentinelai demo                             # Simulated incident demo
sentinelai doctor                           # Validate setup
sentinelai timeline [alert_id]              # Browse incident timeline
sentinelai explain <alert_id>               # Show AI reasoning
sentinelai costs                            # API cost summary
sentinelai plugin new --type triage --name x # Generate plugin skeleton
sentinelai validate-config                  # Config check
```

## Architecture

Event-driven plugin architecture with clean layer separation:

```
Domain (events, errors) → Application (pipeline, config, plugin loader)
    → Infrastructure (contract ABCs) → Plugins → Transport (CLI)
```

Dependencies flow downward only. 7 plugin contracts, 9 built-in plugins.

### Key Files

| File | Purpose |
|------|---------|
| `src/sentinelai/core/pipeline.py` | Pipeline orchestrator — dedup, rate limit, retry, timeline, ticket creation |
| `src/sentinelai/core/events.py` | Domain events: AlertDetected → TriageComplete → FixGenerated → PROpened → DeployStarted → ValidationResult → TicketClosed |
| `src/sentinelai/core/errors.py` | Named error hierarchy (14 types) |
| `src/sentinelai/core/config.py` | YAML config loading + startup validation |
| `src/sentinelai/core/plugin.py` | Plugin discovery via module path import |
| `src/sentinelai/contracts/` | 7 ABCs: AlertSource, TriageEngine, TicketSystem, CodeFixer, PROpener, Deployer, Validator |
| `src/sentinelai/plugins/triage/claude.py` | Claude triage with prompt injection mitigation |
| `src/sentinelai/plugins/fixers/claude_fixer.py` | Claude code fixer — fault-domain discovery + fix generation |
| `src/sentinelai/plugins/pr_openers/github_pr.py` | GitHub PR creation with full context |
| `src/sentinelai/plugins/sources/webhook.py` | Webhook server with HMAC auth + provider auto-detection |
| `src/sentinelai/plugins/sources/adapters/` | Datadog, PagerDuty, GCP Monitoring, Generic adapters |
| `src/sentinelai/cli/main.py` | CLI entry point (11 commands) |

## Coding Standards

Read [CODING-STANDARDS.md](CODING-STANDARDS.md) before making any changes. Key rules:

- **Rule 3:** Domain never imports infrastructure. Strict dependency direction.
- **Rule 4:** Every failure has a named error type. No generic catch-alls.
- **Rule 5:** Structured logging with trace_id on every entry.
- **Rule 6:** All external calls have configurable timeouts + bounded retries with jitter.
- **Rule 7:** All config is external (YAML + env vars), validated at startup.
- **Rule 10:** Formal API contracts. Code and contract must not diverge.

## Testing

- Unit tests in `tests/unit/` — one file per module
- Integration tests in `tests/integration/` — end-to-end with mocked AI responses
- Fixtures in `tests/fixtures/` — JSON alert files
- Run single test: `pytest tests/unit/test_pipeline.py::TestDedupStore -v`
