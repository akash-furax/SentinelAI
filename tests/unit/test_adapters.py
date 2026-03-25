"""Tests for alert payload adapters — Datadog, PagerDuty, GCP, Generic."""

from sentinelai.plugins.sources.adapters.base import detect_provider
from sentinelai.plugins.sources.adapters.datadog import DatadogAdapter
from sentinelai.plugins.sources.adapters.gcp_monitoring import GCPMonitoringAdapter
from sentinelai.plugins.sources.adapters.generic import GenericAdapter
from sentinelai.plugins.sources.adapters.pagerduty import PagerDutyAdapter


class TestProviderDetection:
    def test_detects_datadog_by_header(self):
        assert detect_provider({}, {"dd-api-key": "abc"}) == "datadog"

    def test_detects_datadog_by_payload(self):
        assert detect_provider({"alertType": "error", "hostname": "web-1"}) == "datadog"

    def test_detects_pagerduty_by_payload(self):
        payload = {"event": {"event_type": "incident.triggered", "data": {"id": "P1"}}}
        assert detect_provider(payload, {"x-webhook-id": "wh_123"}) == "pagerduty"

    def test_detects_gcp_by_header(self):
        assert detect_provider({}, {"user-agent": "Google-Alerts"}) == "gcp_monitoring"

    def test_detects_gcp_by_payload(self):
        assert detect_provider({"policy_name": "CPU Alert"}) == "gcp_monitoring"

    def test_falls_back_to_generic(self):
        assert detect_provider({"foo": "bar"}) == "generic"


class TestDatadogAdapter:
    def test_normalizes_basic_payload(self):
        payload = {
            "id": "12345",
            "title": "High CPU on auth-api",
            "body": "CPU > 90% for 5 minutes",
            "alertType": "error",
            "hostname": "auth-api-prod-1",
            "tags": "service:auth-api,env:production",
        }
        alert = DatadogAdapter().normalize(payload)
        assert alert.alert_id == "dd-12345"
        assert alert.source == "datadog"
        assert alert.service_name == "auth-api"
        assert "High CPU" in alert.summary

    def test_extracts_service_from_tags(self):
        payload = {"id": "1", "title": "alert", "tags": "service:payment-svc,env:prod"}
        alert = DatadogAdapter().normalize(payload)
        assert alert.service_name == "payment-svc"

    def test_falls_back_to_hostname(self):
        payload = {"id": "1", "title": "alert", "hostname": "web-server-3", "tags": "env:prod"}
        alert = DatadogAdapter().normalize(payload)
        assert alert.service_name == "web-server-3"


class TestPagerDutyAdapter:
    def test_normalizes_v3_webhook(self):
        payload = {
            "event": {
                "id": "evt_1",
                "event_type": "incident.triggered",
                "data": {
                    "id": "P123ABC",
                    "title": "Database connection failures",
                    "urgency": "high",
                    "status": "triggered",
                    "service": {"id": "svc_1", "summary": "Auth Service"},
                },
            }
        }
        alert = PagerDutyAdapter().normalize(payload)
        assert alert.alert_id == "pd-P123ABC"
        assert alert.source == "pagerduty"
        assert alert.service_name == "Auth Service"
        assert "HIGH" in alert.summary
        assert "Database connection" in alert.summary


class TestGCPMonitoringAdapter:
    def test_normalizes_incident_payload(self):
        payload = {
            "incident": {
                "incident_id": "inc_abc",
                "condition_name": "CPU > 90%",
                "resource_name": "auth-service-prod",
                "state": "open",
                "summary": "CPU utilization exceeded threshold",
            },
            "policy_name": "Auth Service Health",
        }
        alert = GCPMonitoringAdapter().normalize(payload)
        assert alert.alert_id == "gcp-inc_abc"
        assert alert.source == "gcp_monitoring"
        assert alert.service_name == "auth-service-prod"
        assert "CPU > 90%" in alert.summary


class TestGenericAdapter:
    def test_normalizes_with_standard_fields(self):
        payload = {
            "alert_id": "custom-1",
            "service_name": "my-service",
            "summary": "Something broke",
            "extra_field": "preserved",
        }
        alert = GenericAdapter().normalize(payload)
        assert alert.alert_id == "custom-1"
        assert alert.service_name == "my-service"
        assert alert.raw_payload["extra_field"] == "preserved"

    def test_handles_minimal_payload(self):
        alert = GenericAdapter().normalize({"message": "error occurred"})
        assert alert.service_name == "unknown-service"
        assert alert.summary == "error occurred"

    def test_generates_alert_id_if_missing(self):
        alert = GenericAdapter().normalize({"service_name": "svc", "summary": "err"})
        assert alert.alert_id  # UUID generated
