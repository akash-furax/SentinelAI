# SentinelAI — TODOS
Generated from /plan-ceo-review on 2026-03-25

## P1 — Must complete before Phase 1 ships

### Prompt injection sanitization
- **What:** Alert summaries flow directly into Claude/Gemini prompts. Sanitize or sandbox alert content before including in triage prompts.
- **Why:** A malicious alert can manipulate triage decisions. Highest-severity security gap.
- **Effort:** M (human: ~1 day / CC: ~30 min)
- **Depends on:** Triage plugin implementation
- **How to apply:** Implement input boundary between alert payload and LLM prompt. Consider: XML/JSON wrapping, explicit "this is user-controlled data" framing in prompt, or a sanitization pass that strips instruction-like patterns.

### Dependency pinning + security audit in CI
- **What:** Pin all dependencies in `pyproject.toml`. Add `pip-audit` to GitHub Actions.
- **Why:** OSS projects are supply chain attack targets.
- **Effort:** S (human: ~2 hours / CC: ~15 min)
- **Depends on:** Project scaffolding

### OpenAPI specification for webhook receiver
- **What:** Create `api-specification.yml` per CODING-STANDARDS.md rule 10. CI must verify contract matches implementation.
- **Why:** Required by coding standards. Drift between spec and code is a build failure.
- **Effort:** S (human: ~2 hours / CC: ~15 min)
- **Depends on:** Webhook plugin implementation

### SQLite outbox for event durability
- **What:** Events written to SQLite before dispatch. Replayed on restart. Resolves CODING-STANDARDS.md rule 9 compliance.
- **Why:** In-process event bus loses events on crash. Triage success + ticket failure = unrecoverable without outbox.
- **Effort:** S-M (~200 LOC, human: ~4 hours / CC: ~20 min)
- **Depends on:** Core event bus implementation

## P2 — Should complete before Phase 1.5

### Webhook body size limit
- **What:** Configurable max body size (default 1MB). Reject with 413 + WARN log.
- **Why:** Prevents OOM from arbitrarily large payloads.
- **Effort:** S (human: ~30 min / CC: ~5 min)

### CLI file input error handling
- **What:** Graceful FileNotFoundError and JSONDecodeError handling in `sentinelai triage --file`.
- **Why:** Per CODING-STANDARDS.md rule 4, every failure handled explicitly.
- **Effort:** S (human: ~30 min / CC: ~5 min)

### Per-provider cost configuration
- **What:** Extend rate_limits config with per-provider `cost_per_call` instead of single scalar.
- **Why:** Claude and Gemini have different pricing. Single scalar breaks when both are active.
- **Effort:** S (human: ~1 hour / CC: ~10 min)

### Dedup collision fallback
- **What:** On fingerprint hash match, fall back to full-string comparison before dropping.
- **Why:** False dedup silently drops a P1 alert — the exact failure this system prevents.
- **Effort:** S (human: ~30 min / CC: ~5 min)

### AlertContext intermediate type
- **What:** Structured type between raw_payload and triage prompt. Provider-specific parsing in a mapper layer, not in the triage plugin.
- **Why:** Prevents clean architecture violation (provider logic in provider-agnostic contract).
- **Effort:** M (human: ~1 day / CC: ~30 min)

### Phase 2 webhook router
- **What:** Design a multiplexed webhook listener that handles both alert events (Phase 1) and GitHub PR events (Phase 2).
- **Why:** Phase 2 approval gate requires a second webhook type that doesn't fit current plugin model.
- **Effort:** M (human: ~1 day / CC: ~30 min)

## P3 — Post Phase 2

### Demo mode rule 2 compliance
- **What:** Ensure `sentinelai demo` uses file_source + bundled fixtures, not a demo mode flag with fake responses.
- **Why:** CODING-STANDARDS.md rule 2 prohibits mocks/fakes in non-test code.
- **Effort:** S — design constraint, not implementation effort
