"""Alert payload adapters — normalize monitoring provider payloads to AlertDetected.

Each adapter translates a specific monitoring tool's webhook payload format
into SentinelAI's AlertDetected schema.

Architecture:
    Datadog webhook ──► DatadogAdapter.normalize() ──► AlertDetected
    PagerDuty webhook ──► PagerDutyAdapter.normalize() ──► AlertDetected
    GCP Monitoring ──► GCPMonitoringAdapter.normalize() ──► AlertDetected
    Generic/unknown ──► GenericAdapter.normalize() ──► AlertDetected

The webhook source auto-detects the provider from request headers or
payload structure, then delegates to the appropriate adapter.
"""
