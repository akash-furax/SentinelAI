# Contributing to SentinelAI

Thank you for your interest in contributing. This guide covers everything you need to get started.

---

## Getting Started

### Prerequisites

- Python 3.12+
- An Anthropic API key (for running the Claude triage plugin)

### Setup

```bash
git clone https://github.com/your-org/sentinelai.git
cd sentinelai
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Verify

```bash
pytest                          # Run tests (41 tests, all should pass)
ruff check src/ tests/          # Lint
sentinelai doctor               # Validate setup
```

---

## Development Workflow

1. **Read [CODING-STANDARDS.md](CODING-STANDARDS.md) first.** It is the authoritative standard. Every action must be consistent with its 11 rules. If a task conflicts with a rule, stop and state which rule is in conflict.

2. **Read [ARCHITECTURE.md](ARCHITECTURE.md)** to understand the layer diagram and plugin contracts.

3. **Create a branch** for your change.

4. **Write tests alongside code.** Every new behavior needs a corresponding test. Bug fixes need a regression test that would have caught the bug.

5. **Run the full check suite before submitting:**
   ```bash
   ruff check src/ tests/       # Lint
   ruff format src/ tests/      # Format
   pytest                        # Tests
   pip-audit                     # Dependency security audit
   ```

6. **Open a pull request** with a clear description of what changed and why.

---

## Project Structure

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full directory structure and layer diagram. The key concept:

```
Domain (events, errors)     — pure data, no infrastructure imports
    ↓
Application (pipeline, config, plugin loader)
    ↓
Infrastructure (contract ABCs)
    ↓
Plugins (implementations)   — depend on contracts, never on each other
    ↓
Transport (CLI)             — imports application layer only
```

Dependencies flow **downward only**.

---

## Writing a Plugin

The most common contribution is a new plugin. SentinelAI has two plugin types today:

### Alert Source

Implement `sentinelai.contracts.alert_source.AlertSource`:

```python
from collections.abc import AsyncIterator
from sentinelai.contracts.alert_source import AlertSource
from sentinelai.core.events import AlertDetected
from sentinelai.core.errors import AlertSourceError

class DatadogAlertSource(AlertSource):
    """Reads alerts from Datadog's API."""

    async def read_alerts(self) -> AsyncIterator[AlertDetected]:
        # Your implementation here
        # Must raise AlertSourceError on failure — never generic exceptions
        ...
```

### Triage Engine

Implement `sentinelai.contracts.triage_engine.TriageEngine`:

```python
from sentinelai.contracts.triage_engine import TriageEngine
from sentinelai.core.events import AlertDetected, TriageComplete
from sentinelai.core.errors import TriageError, TriageTimeoutError

class GeminiTriageEngine(TriageEngine):
    """Triage engine using Google Gemini."""

    async def triage(self, alert: AlertDetected) -> TriageComplete:
        # Your implementation here
        # Must raise TriageError subtypes on failure
        ...
```

### Plugin Rules

1. **One public class per module** that implements the contract ABC
2. **Raise named errors** from `sentinelai.core.errors` — never generic exceptions
3. **No imports from other plugins** — plugins are independent
4. **No imports from the pipeline** — plugins depend on contracts and domain only
5. **Include tests** — unit tests for your plugin go in `tests/unit/test_<plugin_name>.py`

### Testing Your Plugin

```bash
# Register your plugin in sentinelai.yaml
pipeline:
  triage_engine: my_package.my_triage_engine

# Verify it loads
sentinelai doctor

# Run against a test alert
sentinelai triage --file tests/fixtures/demo_alert.json
```

---

## Coding Standards Summary

The full standards are in [CODING-STANDARDS.md](CODING-STANDARDS.md). The most commonly relevant for contributors:

| Rule | What it means |
|------|--------------|
| **No dead code** | Remove unused imports, functions, and variables. No commented-out code. |
| **No mocks outside tests** | Use interfaces for flexibility, not mocks. Mocks live in `tests/` only. |
| **Dependency direction** | Domain never imports infrastructure. Plugins never import other plugins. |
| **Named errors** | Every failure has a specific error class. No `catch Exception`. |
| **Structured logs** | Key-value pairs with trace_id, timestamp, severity. No interpolated strings. |
| **Bounded external calls** | Every API call needs a configurable timeout and retry with backoff. |
| **Config is external** | No hardcoded values. Everything comes from `sentinelai.yaml` or env vars. |
| **Tests required** | Every new behavior gets a test. Every bug fix gets a regression test. |

---

## Test Structure

```
tests/
├── unit/              # Fast tests, no external dependencies
│   ├── test_events.py
│   ├── test_errors.py
│   ├── test_config.py
│   ├── test_plugin.py
│   ├── test_pipeline.py
│   └── test_file_source.py
├── integration/       # Tests that call external APIs (mocked in CI)
└── fixtures/          # JSON alert files for testing
```

**Test naming convention:** `test_<module>.py` → `class Test<Feature>` → `def test_<behavior>()`

**Run a single test:**
```bash
pytest tests/unit/test_config.py::TestConfigLoad::test_loads_valid_config -v
```

---

## Commit Messages

Write commit messages that explain **why**, not just **what**:

```
Add Gemini triage plugin with retry logic

Claude plugin worked well but users requested Gemini support.
Uses the same TriageEngine contract. Adds Gemini-specific
response parsing and rate limit handling.
```

---

## Issue Labels

| Label | Meaning |
|-------|---------|
| `good first issue` | Great for new contributors |
| `plugin` | New plugin implementation |
| `bug` | Something is broken |
| `enhancement` | Improvement to existing functionality |
| `P1-todo` | Priority 1 — must fix before next release |
| `P2-todo` | Priority 2 — should fix soon |

---

## Questions?

Open an issue or start a discussion. We're happy to help new contributors get started.
