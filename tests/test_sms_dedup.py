"""Tests for SMS within-batch dedup + body fingerprint suppression."""

from src import main
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


def test_signal_key_ignores_setup_type_and_price():
    # Same symbol + action yields the same dedup key regardless of which
    # setup triggered it or the reported entry price. This is the
    # user-facing contract the SMS dedup relies on.
    a = _S("JPM", "BUY", "ema_crossover", 316.99, 0.55)
    b = _S("JPM", "BUY", "breakout", 317.50, 0.70)
    c = _S("JPM", "SELL", "breakout", 317.50, 0.70)
    assert main.signal_key(a) == main.signal_key(b) == "JPM:BUY"
    assert main.signal_key(c) == "JPM:SELL"
    assert main.signal_key(a) != main.signal_key(c)


def test_signal_key_matches_dispatcher_dedup_key():
    # The main-loop signal_key and the dispatcher-level batch dedup key
    # must stay in lockstep; if they diverge, a signal can land in the
    # "seen" set but still emit a duplicate SMS within the same batch
    # (or vice versa). This test guards against one side being changed
    # without the other.
    sigs = [_S("JPM", "BUY", "ema_crossover", 316.99, 0.55)]
    deduped_keys = {f"{s.symbol}:{s.action.value}" for s in dispatcher._deduped_signals_for_sms(sigs)}
    main_keys = {main.signal_key(s) for s in sigs}
    assert deduped_keys == main_keys


def test_dedup_collapses_across_setup_types_for_same_symbol_action():
    # Regression: JPM fired twice within 77 minutes because the first
    # alert carried setup_type=EMA_CROSSOVER and the second had
    # setup_type=BREAKOUT. The SMS body was identical, so the user saw
    # duplicates. Dedup must collapse to symbol:action regardless of
    # which technical pattern triggered it.
    sigs = [
        _S("JPM", "BUY", "ema_crossover", 316.99, 0.55),
        _S("JPM", "BUY", "breakout", 316.99, 0.70),
        _S("JPM", "BUY", "rsi_pullback", 316.99, 0.62),
    ]
    deduped = dispatcher._deduped_signals_for_sms(sigs)
    assert len(deduped) == 1
    # Highest-confidence variant wins.
    assert deduped[0].confidence == 0.70


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
