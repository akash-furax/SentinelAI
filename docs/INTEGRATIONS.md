# Integrations Guide

How to connect SentinelAI to your monitoring, ticketing, and deployment tools.

---

## How Alerts Flow Into SentinelAI

```
Your Monitoring Tool                    SentinelAI
┌──────────────────┐     webhook POST   ┌─────────────────────────────┐
│ Datadog          │ ──────────────────► │ Webhook Server (port 8090)  │
│ PagerDuty        │                     │   │                         │
│ GCP Monitoring   │                     │   ▼                         │
│ Grafana          │                     │ Auto-detect provider        │
│ Custom           │                     │   │                         │
└──────────────────┘                     │   ▼                         │
                                         │ Adapter normalizes payload  │
                                         │   │                         │
                                         │   ▼                         │
                                         │ Pipeline: triage → ticket   │
                                         └─────────────────────────────┘
```

SentinelAI **auto-detects** which monitoring tool sent the alert by checking HTTP headers and payload structure. It then normalizes the payload into a standard format. You don't need to write any glue code.

**Supported providers (auto-detected):**
| Provider | Detection Method | Adapter |
|----------|-----------------|---------|
| Datadog | `dd-api-key` header or `alertType` + `hostname` in payload | `DatadogAdapter` |
| PagerDuty | `x-webhook-id` header or `event.data.incident` structure | `PagerDutyAdapter` |
| GCP Monitoring | `Google-Alerts` user-agent or `policy_name` in payload | `GCPMonitoringAdapter` |
| Any other | Falls back to generic format | `GenericAdapter` |

---

## Quick Setup (5 minutes)

### 1. Configure SentinelAI

Create `sentinelai.yaml`:

```yaml
pipeline:
  alert_source: sentinelai.plugins.sources.webhook
  triage_engine: sentinelai.plugins.triage.claude
  # ticket_system: sentinelai.plugins.tickets.jira   # optional
```

### 2. Set environment variables

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key
export SENTINELAI_WEBHOOK_SECRET=your-shared-secret   # for HMAC verification
export SENTINELAI_WEBHOOK_PORT=8090                    # default
```

### 3. Start the pipeline

```bash
sentinelai run
```

You'll see:
```
SentinelAI Pipeline Started
  Alert source:  sentinelai.plugins.sources.webhook
  Triage engine: sentinelai.plugins.triage.claude

Webhook server listening on port 8090
Send alerts to: POST http://localhost:8090/
Press Ctrl+C to stop.
```

### 4. Point your monitoring tool at SentinelAI

Configure a webhook notification in your monitoring tool that sends to `http://your-server:8090/`.

---

## Datadog Setup

1. Go to **Integrations → Webhooks** in Datadog
2. Create a new webhook:
   - **Name:** `sentinelai`
   - **URL:** `http://your-server:8090/`
   - **Custom Headers:**
     ```json
     {"X-Sentinel-Signature": "sha256=<computed>"}
     ```
3. Add the webhook to your monitor's notification: `@webhook-sentinelai`

**Payload mapping (automatic):**
| Datadog field | SentinelAI field |
|--------------|-----------------|
| `id` | `alert_id` |
| `title` | `summary` |
| `tags: service:X` | `service_name` |
| Full payload | `raw_payload` |

---

## PagerDuty Setup

1. Go to **Integrations → Generic Webhooks (v3)** in PagerDuty
2. Add a webhook subscription:
   - **Endpoint URL:** `http://your-server:8090/`
   - **Events:** `incident.triggered`
3. Note: PagerDuty signs webhooks with `X-PagerDuty-Signature` — configure your `SENTINELAI_WEBHOOK_SECRET` to match.

**Payload mapping (automatic):**
| PagerDuty field | SentinelAI field |
|----------------|-----------------|
| `event.data.id` | `alert_id` |
| `event.data.title` | `summary` |
| `event.data.service.summary` | `service_name` |
| Full payload | `raw_payload` |

---

## GCP Cloud Monitoring Setup

1. Go to **Monitoring → Alerting → Notification Channels** in GCP Console
2. Add a **Webhook** channel:
   - **Endpoint URL:** `http://your-server:8090/`
3. Attach the channel to your alerting policies

**Payload mapping (automatic):**
| GCP field | SentinelAI field |
|-----------|-----------------|
| `incident.incident_id` | `alert_id` |
| `incident.condition_name + summary` | `summary` |
| `incident.resource_name` | `service_name` |
| Full payload | `raw_payload` |

---

## Grafana Setup

Grafana alerts can be sent as webhooks:

1. Go to **Alerting → Contact Points** in Grafana
2. Add a **Webhook** contact point:
   - **URL:** `http://your-server:8090/`
   - **HTTP Method:** POST
3. Grafana's payload will be handled by the Generic adapter

---

## Custom / Any Monitoring Tool

If your tool can send HTTP webhooks, it works with SentinelAI. Send a POST request:

```bash
# Compute HMAC signature
BODY='{"service_name":"auth-service","summary":"Error rate spike"}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SENTINELAI_WEBHOOK_SECRET" | awk '{print $2}')

# Send alert
curl -X POST http://localhost:8090/ \
  -H "Content-Type: application/json" \
  -H "X-Sentinel-Signature: sha256=$SIG" \
  -d "$BODY"
```

**Minimum required fields:**
```json
{
  "service_name": "your-service",
  "summary": "What happened"
}
```

**Full payload (all optional fields):**
```json
{
  "alert_id": "custom-id-123",
  "source": "my-monitoring-tool",
  "service_name": "auth-service",
  "summary": "Error rate spike: 500 errors in 5 minutes",
  "raw_payload": {
    "any": "additional",
    "context": "you want the AI to see"
  }
}
```

---

## Testing Your Integration

Send a test alert without a real monitoring tool:

```bash
# Set your secret
export SENTINELAI_WEBHOOK_SECRET=test-secret

# Start the pipeline in one terminal
sentinelai run

# In another terminal, send a test alert
BODY='{"service_name":"auth-service","summary":"Test alert: connection pool exhaustion","raw_payload":{"error_count":42}}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "test-secret" | awk '{print $2}')

curl -X POST http://localhost:8090/ \
  -H "Content-Type: application/json" \
  -H "X-Sentinel-Signature: sha256=$SIG" \
  -d "$BODY"
```

You should see SentinelAI triage the alert in real-time.

---

## Ticket System Integrations

After triage, SentinelAI can auto-create tickets:

### Jira

```yaml
pipeline:
  ticket_system: sentinelai.plugins.tickets.jira
```

```bash
export JIRA_URL=https://your-org.atlassian.net
export JIRA_EMAIL=you@example.com
export JIRA_API_TOKEN=your-token
export JIRA_PROJECT_KEY=OPS
```

### GitHub Issues

```yaml
pipeline:
  ticket_system: sentinelai.plugins.tickets.github_issues
```

```bash
export GITHUB_TOKEN=ghp_your-token
export GITHUB_REPO=your-org/your-repo
```
