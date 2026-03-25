# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SentinelAI is an open-source AI-powered DevOps automation framework — autonomous incident response with pluggable providers. Users bring their own AI keys (Claude, Gemini).

**Status:** Phase 1 implemented. Core framework, file source, Claude triage, and CLI are working.

## Commands

```bash
# Development
pip install -e ".[dev]"        # Install with dev dependencies
pytest                          # Run all tests (41 tests)
pytest tests/unit/test_config.py -v  # Run a single test file
ruff check src/ tests/          # Lint
ruff format src/ tests/         # Format
pip-audit                       # Dependency security audit

# Usage
sentinelai demo                 # Simulated incident triage
sentinelai triage --file <path> # Triage from JSON file
sentinelai doctor               # Validate setup
sentinelai validate-config      # Check config only
```

## Architecture

Event-driven plugin architecture with clean layer separation:

```
Domain (events, errors) → Application (pipeline, config, plugin loader)
    → Infrastructure (contract ABCs) → Plugins → Transport (CLI)
```

Dependencies flow downward only. See [ARCHITECTURE.md](ARCHITECTURE.md) for full details.

### Key Files

| File | Purpose |
|------|---------|
| `src/sentinelai/core/pipeline.py` | Pipeline orchestrator — dedup, rate limit, retry, timeline |
| `src/sentinelai/core/events.py` | Domain events: AlertDetected, TriageComplete, Priority |
| `src/sentinelai/core/errors.py` | Named error hierarchy (10 types) |
| `src/sentinelai/core/config.py` | YAML config loading + startup validation |
| `src/sentinelai/core/plugin.py` | Plugin discovery via module path import |
| `src/sentinelai/contracts/` | AlertSource and TriageEngine ABCs |
| `src/sentinelai/plugins/triage/claude.py` | Claude triage with prompt injection mitigation |
| `src/sentinelai/plugins/sources/file_source.py` | JSON file alert source |
| `src/sentinelai/cli/main.py` | Click CLI commands |

### Plugin System

Plugins are loaded by module path from `sentinelai.yaml`. Each plugin module must contain one public class implementing the relevant ABC. Plugins depend on contracts and domain — never on each other or on the pipeline.

## Coding Standards

Read [CODING-STANDARDS.md](CODING-STANDARDS.md) before making any changes. The 11 rules are enforced:

- **Rule 3:** Domain never imports infrastructure. Dependency direction is strict.
- **Rule 4:** Every failure has a named error type. No generic catch-alls.
- **Rule 5:** Structured logging with trace_id on every entry.
- **Rule 6:** All external calls have configurable timeouts + bounded retries with jitter.
- **Rule 7:** All config is external (YAML + env vars), validated at startup.

## Testing

- Unit tests in `tests/unit/` — one file per module, no external dependencies
- Integration tests in `tests/integration/` — tests that call external APIs (mocked via respx)
- Test fixtures in `tests/fixtures/` — JSON alert files
- Run single test: `pytest tests/unit/test_pipeline.py::TestDedupStore::test_first_alert_passes -v`

## Phase Plan

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Core + file source + Claude triage + CLI | Done |
| 1.5 | Webhook source, Jira, GitHub Issues, Gemini, timeline commands | Next |
| 2 | AI code fix generation + PR automation | Planned |
| 3 | Deploy automation + Playwright validation | Planned |
