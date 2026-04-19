"""Tests for SMS within-batch dedup + body fingerprint suppression."""

from src.notifications import dispatcher


class _S:
    def __init__(self, sym, action, setup, entry, conf):
        self.symbol = sym
        self.action = type("A", (), {"value": action})()
        self.setup_type = type("ST", (), {"value": setup})()
        self.entry = entry
        self.confidence = conf


def test_within_batch_dedup_keeps_highest_confidence():
    sigs = [
        _S("PFE", "BUY", "breakout", 27.54, 0.60),
        _S("PFE", "BUY", "breakout", 27.54, 0.70),
        _S("NFLX", "SELL", "rejection", 97.31, 0.75),
    ]
    deduped = dispatcher._deduped_signals_for_sms(sigs)
    by_sym = {s.symbol: s for s in deduped}
    assert len(deduped) == 2
    assert by_sym["PFE"].confidence == 0.70


def test_format_body_omits_duplicates():
    sigs = [
        _S("PFE", "BUY", "breakout", 27.54, 0.60),
        _S("PFE", "BUY", "breakout", 27.54, 0.70),
    ]
    body = dispatcher._format_sms_body(sigs)
    # PFE should appear exactly once
    assert body.count("PFE") == 1


def test_fingerprint_stable_for_same_body():
    body1 = "MSE Alert\n+PFE BUY $27.54 70%"
    body2 = "MSE Alert\n+PFE BUY $27.54 70%"
    assert dispatcher._fingerprint_of_body(body1) == dispatcher._fingerprint_of_body(body2)


def test_fingerprint_differs_for_different_body():
    assert (
        dispatcher._fingerprint_of_body("MSE Alert\n+PFE BUY $27.54 70%")
        != dispatcher._fingerprint_of_body("MSE Alert\n+PFE BUY $27.55 70%")
    )
