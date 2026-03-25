# SentinelAI

**AI-powered DevOps automation framework** — autonomous incident response with pluggable providers.

SentinelAI triages production alerts with AI, generates root cause analyses, and (in future phases) writes code fixes and opens pull requests — all autonomously. You bring your own AI keys (Claude, Gemini). The framework handles the rest.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

---

## Why SentinelAI?

Existing open-source tools each solve one piece of incident response:

| Tool | What it does | What's missing |
|------|-------------|---------------|
| [HolmesGPT](https://github.com/robusta-dev/holmesgpt) | AI alert investigation / RCA | No code fixes, no PR automation |
| [k8sgpt](https://github.com/k8sgpt-ai/k8sgpt) | Kubernetes diagnostics with AI | K8s-only, no remediation |
| [StackStorm](https://github.com/StackStorm/st2) | Event-driven automation | Pre-AI, no intelligent triage |
| [Keep](https://github.com/keephq/keep) | Alert management | Consolidation only, no AI triage |

**SentinelAI does the full loop:** Alert → AI Triage → Ticket → Code Fix → PR → Deploy → Validate. And it's pluggable — swap any provider without changing your pipeline.

---

## Quick Start

### 1. Install

```bash
pip install sentinelai
```

Or from source:

```bash
git clone https://github.com/your-org/sentinelai.git
cd sentinelai
pip install -e ".[dev]"
```

### 2. Configure

Create `sentinelai.yaml` in your project root (or copy the default from the repo):

```yaml
pipeline:
  alert_source: sentinelai.plugins.sources.file_source
  triage_engine: sentinelai.plugins.triage.claude

settings:
  dedup_window_minutes: 5

timeouts:
  triage_timeout_seconds: 60

retry:
  max_retries: 3
  backoff_base_seconds: 1.0
  jitter: true

rate_limits:
  ai_calls_per_minute: 20
  max_tickets_per_hour: 10
```

### 3. Set your API key

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 4. Validate your setup

```bash
sentinelai doctor
```

```
SentinelAI Doctor — checking your setup

✔ Config file loaded and valid
✔ API keys configured
✔ Alert source plugin: sentinelai.plugins.sources.file_source
✔ Triage engine plugin: sentinelai.plugins.triage.claude

All 4 checks passed! You're ready to go.
```

### 5. Run

```bash
# Run the demo — simulated incident against Claude
sentinelai demo

# Triage your own alerts
sentinelai triage --file alerts.json
```

---

## How It Works

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Alert Source  │────▶│ AI Triage    │────▶│ Output       │
│ (plugin)     │     │ (plugin)     │     │ (console/    │
│              │     │              │     │  ticket)     │
│ file_source  │     │ Claude       │     │              │
│ webhook      │     │ Gemini       │     │ Jira         │
│ your own...  │     │ your own...  │     │ GitHub Issues│
└──────────────┘     └──────────────┘     └──────────────┘
```

1. **Alert sources** read alerts from files, webhooks, or any custom source
2. **Deduplication** collapses duplicate alerts within a configurable time window
3. **AI triage** classifies severity (P1–P4), generates root cause hypotheses, and produces confidence scores
4. **Output** displays rich terminal results (Phase 1) or creates tickets (Phase 1.5+)
5. **Incident timeline** records every event as an append-only JSONL audit log

All components are **pluggable** — implement an interface, drop it in your config, done.

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `sentinelai demo` | Run a simulated incident triage with a bundled demo alert |
| `sentinelai triage --file <path>` | Triage alerts from a JSON file |
| `sentinelai doctor` | Validate setup — config, API keys, plugins |
| `sentinelai validate-config` | Check config validity without running the pipeline |

### Alert File Format

JSON file containing a single alert object or an array of alert objects:

```json
[
  {
    "alert_id": "optional-custom-id",
    "service_name": "auth-service",
    "summary": "Error rate spike: 500 errors up 340% in 5 minutes",
    "raw_payload": {
      "error_rate": 0.34,
      "latency_p99_ms": 12400
    }
  }
]
```

**Required fields:** `service_name`, `summary`
**Optional fields:** `alert_id` (auto-generated UUID if omitted), `source`, `raw_payload`, `trace_id`

---

## Configuration Reference

All configuration lives in `sentinelai.yaml`. API keys are read from environment variables — never put secrets in the config file.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `pipeline.alert_source` | string | *required* | Module path to alert source plugin |
| `pipeline.triage_engine` | string | *required* | Module path to triage engine plugin |
| `settings.dedup_window_minutes` | int | `5` | Duplicate alert suppression window |
| `timeouts.triage_timeout_seconds` | int | `60` | Max time for a single AI triage call |
| `timeouts.alert_source_timeout_seconds` | int | `10` | Max time to connect to alert source |
| `retry.max_retries` | int | `3` | Global retry limit (triage overrides to 2) |
| `retry.backoff_base_seconds` | float | `1.0` | Exponential backoff base |
| `retry.backoff_max_seconds` | float | `30.0` | Max backoff cap |
| `retry.jitter` | bool | `true` | Add randomness to backoff |
| `rate_limits.ai_calls_per_minute` | int | `20` | Max AI API calls per minute |
| `rate_limits.max_tickets_per_hour` | int | `10` | Max tickets per service per hour |

### Environment Variables

| Variable | Required For | Description |
|----------|-------------|-------------|
| `ANTHROPIC_API_KEY` | Claude triage plugin | Your Anthropic API key (`sk-ant-...`) |

---

## Writing Plugins

SentinelAI uses a plugin architecture. Each pipeline stage has an abstract contract — implement it to add support for your tools.

### Alert Source Plugin

```python
from sentinelai.contracts.alert_source import AlertSource
from sentinelai.core.events import AlertDetected
from sentinelai.core.errors import AlertSourceError

class MyAlertSource(AlertSource):
    async def read_alerts(self):
        # Yield AlertDetected events from your source
        yield AlertDetected(
            alert_id="my-alert-1",
            source="my_source",
            service_name="api-gateway",
            summary="Latency spike on /api/v1/users",
            raw_payload={"latency_p99_ms": 5000},
        )
```

### Triage Engine Plugin

```python
from sentinelai.contracts.triage_engine import TriageEngine
from sentinelai.core.events import AlertDetected, TriageComplete, Priority
from sentinelai.core.errors import TriageError

class MyTriageEngine(TriageEngine):
    async def triage(self, alert: AlertDetected) -> TriageComplete:
        # Call your AI provider, parse the response
        return TriageComplete(
            alert_id=alert.alert_id,
            severity=Priority.P2,
            root_cause_hypothesis="Database connection pool exhaustion",
            confidence=0.85,
            affected_services=["api-gateway", "user-db"],
            recommended_action="Increase connection pool max_size to 200",
            ai_reasoning="Full reasoning chain here...",
            trace_id=alert.trace_id,
        )
```

### Register Your Plugin

Point your `sentinelai.yaml` at your module:

```yaml
pipeline:
  alert_source: my_package.my_alert_source
  triage_engine: my_package.my_triage_engine
```

The module must contain exactly one public class that implements the contract ABC.

---

## Built-in Plugins

### Alert Sources

| Plugin | Module Path | Description |
|--------|------------|-------------|
| File Source | `sentinelai.plugins.sources.file_source` | Reads alerts from JSON files. For local dev, testing, and demos. |

**Coming in Phase 1.5:** Webhook source (HMAC-SHA256 authenticated HTTP endpoint)

### Triage Engines

| Plugin | Module Path | Requires |
|--------|------------|----------|
| Claude | `sentinelai.plugins.triage.claude` | `ANTHROPIC_API_KEY` |

**Coming in Phase 1.5:** Gemini triage engine

---

## Error Handling

SentinelAI uses a named error hierarchy — no catch-all handlers, no silent failures. Every error carries a `trace_id` and `timestamp` for debugging.

```
SentinelAIError
├── AlertSourceError
│   └── WebhookAuthError
├── TriageError
│   ├── TriageTimeoutError
│   ├── TriageRateLimitError
│   └── TriageMalformedResponse
├── TicketCreationError
├── ConfigValidationError
├── PluginLoadError
└── RateLimitExceeded
```

When triage fails, the pipeline creates a fallback result with `severity=UNKNOWN` and flags it for manual review — alerts are never silently dropped.

---

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| **Phase 1** | Core framework + file source + Claude triage + CLI | **Current** |
| **Phase 1.5** | Webhook source, Jira/GitHub Issues, Gemini, timeline, costs | Planned |
| **Phase 2** | AI code fix generation + PR automation (the differentiator) | Planned |
| **Phase 3** | Deployment automation + Playwright validation + auto-close | Planned |

---

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/ tests/

# Format code
ruff format src/ tests/

# Security audit
pip-audit
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor guide.
See [ARCHITECTURE.md](ARCHITECTURE.md) for the system design and plugin contracts.

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [Anthropic Claude](https://anthropic.com) — AI triage engine
- [bubus](https://github.com/browser-use/bubus) — Event bus with WAL persistence
- [Rich](https://github.com/Textualize/rich) — Terminal formatting
