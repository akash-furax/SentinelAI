# Architecture

This document describes SentinelAI's system design, plugin contracts, and data flow. It is the technical reference for contributors — read the [README](README.md) first for an overview.

---

## Design Principles

SentinelAI follows [CODING-STANDARDS.md](CODING-STANDARDS.md) — 11 golden rules that govern every line of code. The most architecturally significant:

- **Clean architecture** (rule 3): Domain → Application → Infrastructure → Transport. Domain never imports infrastructure.
- **Named errors** (rule 4): Every failure has a specific error type. No catch-all handlers.
- **Structured observability** (rule 5): Every log entry is key-value with trace_id, timestamp, severity.
- **Bounded external calls** (rule 6): All API calls have configurable timeouts, retries with jitter, and circuit breaker patterns.
- **Formal contracts** (rule 10): Plugin interfaces are the source of truth.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        sentinelai CLI                           │
│    triage | demo | doctor | validate-config                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    Pipeline Orchestrator                         │
│                                                                 │
│  1. Assigns trace_id (UUID4) to each alert                      │
│  2. Deduplicates (fingerprint + TTL window)                     │
│  3. Enforces rate limits (AI calls/min, tickets/hour)           │
│  4. Dispatches to triage engine with retry + timeout            │
│  5. Logs every event to incident timeline (JSONL)               │
└─────────┬────────────────────┬──────────────────┬───────────────┘
          │                    │                  │
          ▼                    ▼                  ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐
│  Alert Source    │  │  Triage Engine   │  │  Incident Timeline  │
│  (Plugin ABC)    │  │  (Plugin ABC)    │  │  (JSONL audit log)  │
├─────────────────┤  ├─────────────────┤  └─────────────────────┘
│ file_source     │  │ claude          │
│ [webhook]       │  │ [gemini]        │
│ [your own]      │  │ [your own]      │
└─────────────────┘  └─────────────────┘

    [ ] = planned, not yet implemented
```

---

## Layer Diagram (Dependency Direction)

```
  ┌─────────────────────────────────────────────────────┐
  │                   DOMAIN LAYER                       │
  │  core/events.py — AlertDetected, TriageComplete      │
  │  core/errors.py — Named error hierarchy               │
  │  (No infrastructure imports. Pure data + types.)      │
  └───────────────────────┬─────────────────────────────┘
                          │ imports
  ┌───────────────────────▼─────────────────────────────┐
  │                APPLICATION LAYER                      │
  │  core/pipeline.py — Orchestrator, dedup, rate limit   │
  │  core/config.py   — YAML config loading + validation  │
  │  core/plugin.py   — Plugin discovery (module path)    │
  │  (Imports domain only.)                                │
  └───────────────────────┬─────────────────────────────┘
                          │ imports
  ┌───────────────────────▼─────────────────────────────┐
  │              INFRASTRUCTURE LAYER                     │
  │  contracts/alert_source.py  — AlertSource ABC         │
  │  contracts/triage_engine.py — TriageEngine ABC        │
  │  (Defines interfaces. Implemented by plugins.)        │
  └───────────────────────┬─────────────────────────────┘
                          │ implements
  ┌───────────────────────▼─────────────────────────────┐
  │                 PLUGIN LAYER                          │
  │  plugins/sources/file_source.py — FileAlertSource     │
  │  plugins/triage/claude.py       — ClaudeTriageEngine  │
  │  (Depends on contracts + domain, never on other       │
  │   plugins or on the pipeline.)                        │
  └───────────────────────┬─────────────────────────────┘
                          │ used by
  ┌───────────────────────▼─────────────────────────────┐
  │                TRANSPORT LAYER                        │
  │  cli/main.py — Click CLI commands                     │
  │  (Imports application layer only. Converts user       │
  │   input to domain objects and back.)                  │
  └─────────────────────────────────────────────────────┘
```

**Rule:** Dependencies flow downward only. A plugin never imports another plugin. The CLI never imports a plugin directly (it uses the plugin loader).

---

## Data Flow

### Alert → Triage Pipeline

```
Alert JSON File
      │
      ▼
FileAlertSource.read_alerts()
      │  yields AlertDetected events
      ▼
Pipeline._assign_trace_id()
      │  assigns UUID4 if missing
      ▼
Pipeline._log_timeline()          ──► incidents/timeline.jsonl
      │
      ▼
DedupStore.is_duplicate()
      │
      ├── YES (duplicate within window) ──► logged, dropped
      │
      ▼ NO
Pipeline._check_rate_limit()
      │
      ├── EXCEEDED ──► RateLimitExceeded, alert dropped
      │
      ▼ OK
Pipeline._triage_with_retry()
      │
      ├── SUCCESS ──► TriageComplete event
      │
      ├── TIMEOUT (after 2 retries) ──► fallback TriageComplete (severity=UNKNOWN)
      │
      ├── RATE_LIMITED (429) ──► backoff + retry
      │
      └── MALFORMED_RESPONSE ──► no retry (won't improve), fallback TriageComplete
```

### Event Schemas

**AlertDetected:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `alert_id` | str | yes | Unique identifier |
| `source` | str | yes | Plugin that produced this alert |
| `service_name` | str | yes | Affected service |
| `summary` | str | yes | One-line description |
| `raw_payload` | dict | yes | Provider-specific raw data |
| `timestamp` | datetime | auto | UTC ingestion time |
| `trace_id` | str | auto | UUID4, assigned by pipeline |

**TriageComplete:**
| Field | Type | Description |
|-------|------|-------------|
| `alert_id` | str | Links back to AlertDetected |
| `severity` | Priority | P1, P2, P3, P4, or UNKNOWN |
| `root_cause_hypothesis` | str | AI-generated RCA |
| `confidence` | float | 0.0–1.0 confidence score |
| `affected_services` | list[str] | Services impacted |
| `recommended_action` | str | Suggested remediation |
| `ai_reasoning` | str | Full reasoning chain for audit |
| `trace_id` | str | Propagated from AlertDetected |

---

## Deduplication

Alerts are deduplicated using a fingerprint-based TTL store:

1. **Fingerprint algorithm:** lowercase → strip non-alphanumeric (keep spaces) → collapse whitespace → SHA-256 → first 16 hex chars
2. **Dedup key:** `(service_name, fingerprint)`
3. **Window:** Configurable via `settings.dedup_window_minutes` (default: 5)
4. **Collision handling:** On hash match, full-string comparison of the original summary before dropping

**Limitation (v1):** Dedup state is in-memory. Process restart clears the window.

---

## Error Handling

```
SentinelAIError              ← base (carries trace_id + timestamp)
├── AlertSourceError         ← source connection/parsing failed
│   └── WebhookAuthError     ← HMAC signature verification failed
├── TriageError              ← AI triage call failed
│   ├── TriageTimeoutError   ← exceeded configured timeout
│   ├── TriageRateLimitError ← provider returned 429
│   └── TriageMalformedResponse ← unparseable/empty response
├── TicketCreationError      ← ticket system unreachable
├── ConfigValidationError    ← missing/invalid config at startup
├── PluginLoadError          ← module not found or bad implementation
└── RateLimitExceeded        ← internal rate limit threshold hit
```

**Failure behavior:**
| Stage | Failure | Action | User sees |
|-------|---------|--------|-----------|
| Alert source | Connection lost | Retry 3x with backoff | Error in console |
| Triage | AI timeout | Retry 2x, then fallback | `severity=UNKNOWN`, manual review flag |
| Triage | Malformed response | No retry (won't improve) | Fallback with raw alert data |
| Triage | Rate limit (429) | Backoff per retry-after | Delayed (transparent) |
| Config | Missing key | Exit immediately | Actionable error message |

---

## Plugin Discovery

**v1: Module path only.** Plugins are loaded by dotted Python import path from `sentinelai.yaml`:

```yaml
pipeline:
  triage_engine: sentinelai.plugins.triage.claude
```

The plugin loader (`core/plugin.py`):
1. Imports the module via `importlib.import_module()`
2. Finds the single public class that subclasses the expected ABC
3. Instantiates it with no arguments

**For third-party plugins:** Install your package (`pip install sentinelai-my-plugin`), then reference its module path in config. `entry_points` discovery is planned for v2.

---

## Prompt Injection Mitigation

Alert content is user-controlled text that flows into AI prompts. The Claude triage plugin mitigates prompt injection by:

1. Wrapping alert data in explicit `<alert_data>` XML delimiters
2. System prompt instructs the model to treat delimited content as **untrusted data**, not instructions
3. System prompt requires severity classification based on **technical content**, not claims within the alert

This is defense-in-depth — the human approval gate (Phase 2+) provides the final safety net.

---

## Incident Timeline

Every pipeline event is appended to `incidents/timeline.jsonl`:

```json
{"event_type": "alert.detected", "timestamp": "2026-03-25T12:00:00+00:00", "trace_id": "abc-123", "alert_id": "alert-001"}
{"event_type": "triage.complete", "timestamp": "2026-03-25T12:00:12+00:00", "trace_id": "abc-123", "alert_id": "alert-001", "severity": "P2", "confidence": 0.87}
```

Used by `sentinelai timeline` (Phase 1.5) and `sentinelai explain` (Phase 1.5) for post-hoc investigation.

---

## Directory Structure

```
sentinelai/
├── src/sentinelai/
│   ├── core/
│   │   ├── events.py        # Domain events (AlertDetected, TriageComplete)
│   │   ├── errors.py        # Named error hierarchy
│   │   ├── config.py        # YAML config loading + validation
│   │   ├── plugin.py        # Plugin discovery (module path import)
│   │   └── pipeline.py      # Orchestrator, dedup, rate limiting, timeline
│   ├── contracts/
│   │   ├── alert_source.py  # AlertSource ABC
│   │   └── triage_engine.py # TriageEngine ABC
│   ├── plugins/
│   │   ├── sources/
│   │   │   └── file_source.py  # File-based alert source
│   │   └── triage/
│   │       └── claude.py       # Claude AI triage engine
│   └── cli/
│       └── main.py          # Click CLI (triage, demo, doctor)
├── tests/
│   ├── unit/                # 41 tests covering all core modules
│   ├── integration/         # (planned)
│   └── fixtures/            # Demo alert JSON files
├── idea/
│   ├── AI_DevOps_Automation_System.pdf  # Original design document
│   └── ceo-review/          # CEO review outputs
├── docs/designs/            # Promoted design documents
├── sentinelai.yaml          # Default configuration
├── pyproject.toml           # Package config, dependencies, tooling
├── CODING-STANDARDS.md      # 11 golden rules for this codebase
└── ARCHITECTURE.md          # This file
```
