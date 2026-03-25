# SentinelAI — Leadership Demo

A live demonstration of the full AI-powered incident response pipeline.

## What you'll show

1. **AI Triage** — Feed a production alert, watch Claude classify severity and generate root cause analysis in seconds
2. **AI Code Fix** — Watch Claude read the broken source code, identify the bug, and generate a targeted fix with tests
3. **Incident Timeline** — Show the full audit trail of what happened and why

Total demo time: **3-5 minutes** (depends on API response time).

---

## Prerequisites

```bash
# 1. You need an Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-your-key-here

# 2. Install SentinelAI (if not already installed)
cd /path/to/SentinelAI
pip install -e ".[dev]"

# 3. Verify setup
sentinelai doctor --config demo/sentinelai-demo.yaml
```

You should see all checks pass (green checkmarks).

---

## Demo Script

### Act 1: "We have a production incident" (30 seconds)

**Say:** *"It's 3am. Your monitoring fires an alert: auth-service is down. Error rate spiked 340%. Users can't log in. Here's what the alert looks like."*

Show the alert file:
```bash
cat demo/alert-connection-pool.json | python -m json.tool
```

**Key points to highlight:**
- 847 errors in 5 minutes
- Connection pool exhausted (10/10)
- Traffic spike from marketing campaign

---

### Act 2: "SentinelAI triages it instantly" (60 seconds)

```bash
sentinelai triage --file demo/alert-connection-pool.json --config demo/sentinelai-demo.yaml
```

**What happens:** Claude analyzes the alert in ~5-10 seconds and produces:
- Severity classification (likely P1 or P2)
- Root cause hypothesis ("connection pool max_connections too low")
- Confidence score
- Recommended action
- Full AI reasoning chain

**Say:** *"In under 10 seconds, we have a severity classification, root cause, and recommended fix — with full reasoning that any engineer can audit."*

---

### Act 3: "Now it writes the fix" (90 seconds — the wow moment)

```bash
sentinelai fix --file demo/alert-connection-pool.json \
    --repo demo/broken-app \
    --config demo/sentinelai-demo.yaml \
    --no-pr --write-files
```

**What happens:** Claude:
1. Triages the alert (same as Act 2)
2. Reads the actual source code in `demo/broken-app/src/`
3. Identifies the bug (`max_connections = 10`)
4. Generates a targeted fix (increases pool size, adds configuration)
5. Generates a test that would have caught this
6. Writes the fixed files to disk

**Say:** *"The AI read our codebase, found the exact line causing the outage, wrote a fix, and generated a regression test. This took 15 seconds. A human engineer would take 30-60 minutes."*

Show the diff:
```bash
git diff demo/broken-app/
```

---

### Act 4: "Full audit trail" (30 seconds)

```bash
sentinelai timeline --path incidents/timeline.jsonl
sentinelai costs --path incidents/timeline.jsonl
```

**Say:** *"Every action is logged. We can see exactly what the AI decided and why. This is the audit trail compliance teams need."*

---

### Act 5: "Try the second bug" (optional — 60 seconds)

Reset the first fix and run the rate limiter alert:
```bash
git checkout demo/broken-app/
sentinelai fix --file demo/alert-rate-limiter.json \
    --repo demo/broken-app \
    --config demo/sentinelai-demo.yaml \
    --no-pr --write-files
```

**Say:** *"Different bug, different service. Same pipeline. It found the memory leak in the rate limiter — the sliding window never cleans up expired entries."*

---

## Talking Points

**For engineering leadership:**
- "This replaces the 30-60 minute manual triage + fix cycle with a 15-second automated one"
- "Every action is auditable — the AI shows its reasoning, not just the answer"
- "It's pluggable — works with any AI provider (Claude, Gemini), any ticketing system (Jira, GitHub Issues), any cloud"
- "The human approval gate is non-negotiable — AI proposes, humans approve"

**For non-technical leadership:**
- "Think of it as an AI SRE that never sleeps and responds in seconds instead of hours"
- "MTTR (mean time to resolution) drops from 4+ hours to under 25 minutes"
- "It's open source — teams use their own AI keys, no vendor lock-in"

**Handling questions:**
- *"What if the AI fix is wrong?"* — "The fix goes through a PR that requires human approval. The AI also generates tests. Wrong fixes get caught at code review, just like any other PR."
- *"What does this cost?"* — "API costs are $0.01-0.05 per triage. For a team handling 100 incidents/month, that's $1-5/month in AI costs."
- *"Can it handle our stack?"* — "The plugin architecture supports any language, any cloud, any CI/CD. You write a plugin once, it works forever."

---

## Cleanup

Reset demo state after presenting:
```bash
git checkout demo/broken-app/
rm -rf incidents/
```
