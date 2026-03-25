"""Tests for pipeline orchestrator and dedup logic."""

from sentinelai.core.events import AlertDetected
from sentinelai.core.pipeline import DedupStore, _fingerprint


class TestFingerprint:
    def test_basic_fingerprint(self):
        fp = _fingerprint("Error rate spike on auth-service")
        assert len(fp) == 16
        assert fp.isalnum()

    def test_case_insensitive(self):
        assert _fingerprint("Error Rate SPIKE") == _fingerprint("error rate spike")

    def test_strips_special_chars(self):
        assert _fingerprint("Error: 500!") == _fingerprint("Error 500")

    def test_collapses_whitespace(self):
        assert _fingerprint("Error   rate    spike") == _fingerprint("Error rate spike")

    def test_different_summaries_different_fingerprints(self):
        fp1 = _fingerprint("Error rate spike on auth")
        fp2 = _fingerprint("Memory leak in payment service")
        assert fp1 != fp2


class TestDedupStore:
    def _make_alert(self, alert_id: str = "test-1", summary: str = "error spike") -> AlertDetected:
        return AlertDetected(
            alert_id=alert_id,
            source="test",
            service_name="auth",
            summary=summary,
            raw_payload={},
            trace_id="trace-1",
        )

    def test_first_alert_passes(self):
        store = DedupStore(window_minutes=5)
        alert = self._make_alert()
        assert store.is_duplicate(alert) is False

    def test_duplicate_within_window_blocked(self):
        store = DedupStore(window_minutes=5)
        alert1 = self._make_alert(alert_id="a1")
        alert2 = self._make_alert(alert_id="a2")  # Same summary = duplicate
        assert store.is_duplicate(alert1) is False
        assert store.is_duplicate(alert2) is True

    def test_different_summary_passes(self):
        store = DedupStore(window_minutes=5)
        alert1 = self._make_alert(alert_id="a1", summary="error A")
        alert2 = self._make_alert(alert_id="a2", summary="error B")
        assert store.is_duplicate(alert1) is False
        assert store.is_duplicate(alert2) is False

    def test_different_service_same_summary_passes(self):
        store = DedupStore(window_minutes=5)
        alert1 = self._make_alert()
        alert2 = AlertDetected(
            alert_id="a2",
            source="test",
            service_name="payment",  # Different service
            summary="error spike",  # Same summary
            raw_payload={},
            trace_id="trace-2",
        )
        assert store.is_duplicate(alert1) is False
        assert store.is_duplicate(alert2) is False

    def test_expired_entries_evicted(self):
        store = DedupStore(window_minutes=0)  # 0 minutes = immediate expiry
        alert = self._make_alert()
        assert store.is_duplicate(alert) is False
        # With 0 window, next check should evict and allow through
        assert store.is_duplicate(alert) is False
