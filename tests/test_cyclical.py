"""Tests for the cyclical / mean-reversion detector."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pandas as pd

from src.scanner import cyclical as cy


def _series(closes: list[float]) -> pd.Series:
    base = datetime(2026, 4, 14, tzinfo=timezone.utc)
    idx = [base + timedelta(hours=i) for i in range(len(closes))]
    return pd.Series(closes, index=idx)


def _bars(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"close": closes}, index=_series(closes).index)


# --- Zigzag helper ---

def test_zigzag_filters_noise_below_threshold():
    # 3% wiggles below the default 5% filter should produce no extremes.
    closes = [100.0, 101.0, 99.5, 100.5, 99.0, 100.2, 99.8, 100.5]
    extremes = cy.find_zigzag_extremes(_series(closes), threshold_pct=5.0)
    assert extremes == []


def test_zigzag_captures_10_percent_swings():
    # Clean alternation: 100 -> 112 -> 100 -> 112 -> 100. Three swings.
    closes = [100, 104, 108, 112, 108, 104, 100, 104, 108, 112, 108, 104, 100]
    extremes = cy.find_zigzag_extremes(_series(closes), threshold_pct=5.0)
    kinds = [e.kind for e in extremes]
    # Expect alternating kinds, at least two peaks and two troughs
    assert kinds.count("peak") >= 2
    assert kinds.count("trough") >= 2
    # And the pattern must alternate (no two peaks back-to-back)
    for a, b in zip(kinds, kinds[1:]):
        assert a != b


# --- detect_cyclical positive cases ---

def _sine_prices(cycles: int = 4, bars_per_cycle: int = 12,
                 amplitude_pct: float = 10.0, base: float = 100.0) -> list[float]:
    closes: list[float] = []
    total = cycles * bars_per_cycle
    for i in range(total):
        phase = 2 * math.pi * i / bars_per_cycle
        closes.append(base * (1 + amplitude_pct / 200 * math.sin(phase)))
    return closes


def test_detect_sine_wave_passes_all_gates():
    bars = _bars(_sine_prices(cycles=4, bars_per_cycle=12, amplitude_pct=12.0))
    r = cy.detect_cyclical(bars, "SINE")
    assert r is not None
    assert r.cycles >= 3
    assert r.mean_amplitude_pct >= 8.0
    assert r.amplitude_cv < 0.1   # synthetic sine => near zero
    assert r.period_cv < 0.1
    assert 0.0 <= r.range_position <= 1.0
    assert r.cyclical_score > 0.85


def test_near_trough_tags_buy():
    # Ensure the last bar lands at the low end of the range.
    closes = _sine_prices(cycles=4, bars_per_cycle=12, amplitude_pct=12.0)
    # Walk forward phase until close-to-zero (sine minimum). Append
    # a trough sample as the final bar.
    closes.append(88.0)
    bars = _bars(closes)
    r = cy.detect_cyclical(bars, "X")
    assert r is not None
    assert r.bias == "BUY"
    assert r.range_position < 0.3


def test_near_peak_tags_sell():
    closes = _sine_prices(cycles=4, bars_per_cycle=12, amplitude_pct=12.0)
    closes.append(112.0)
    bars = _bars(closes)
    r = cy.detect_cyclical(bars, "X")
    assert r is not None
    assert r.bias == "SELL"
    assert r.range_position > 0.7


# --- Negative / reject cases ---

def test_pure_noise_fails():
    # Small random-looking moves <5% each direction, no real cycles.
    closes = [100, 101, 100.5, 101.2, 100.8, 101.5, 101.0, 100.7,
              101.3, 100.9, 101.1, 100.6, 101.0, 100.8, 101.2, 100.9,
              101.3, 100.7, 101.0, 100.8, 101.2, 100.9, 101.0, 100.8]
    bars = _bars(closes)
    assert cy.detect_cyclical(bars, "X") is None


def test_trending_stock_fails():
    # Monotonic uptrend — no oscillation.
    closes = [100 * (1 + 0.02 * i) for i in range(40)]
    bars = _bars(closes)
    assert cy.detect_cyclical(bars, "X") is None


def test_irregular_amplitudes_fail_cv():
    # 4 cycles but amplitudes vary wildly (5%, 30%, 6%, 28%). High CV.
    closes = [
        100, 103, 105, 102, 100,        # ~5% up, then down
        105, 115, 125, 130, 115, 100,   # ~30% up, then down
        103, 105, 102, 100,             # ~6% swing
        110, 120, 128, 118, 100,        # ~28% swing
    ]
    bars = _bars(closes)
    r = cy.detect_cyclical(bars, "X")
    # Either detector returns None OR the amplitude CV is >= cap
    if r is not None:
        assert r.amplitude_cv > 0.4 or r.period_cv > 0.4


def test_short_window_returns_none():
    closes = [100, 105, 95, 105, 95, 105, 95, 105, 95, 105]  # only 10 bars
    bars = _bars(closes)
    assert cy.detect_cyclical(bars, "X") is None


# --- scan_cyclicals ---

def test_scan_sorts_by_score_and_excludes_non_cyclicals(monkeypatch):
    clean_sine = _bars(_sine_prices(cycles=4, bars_per_cycle=12, amplitude_pct=12.0))
    trend = _bars([100 * (1 + 0.02 * i) for i in range(48)])
    noisy_cycle = _bars([
        100, 112, 100, 108, 100, 115, 100, 107, 100, 113,
        100, 106, 100, 114, 100, 109, 100, 111, 100, 110,
        100, 112, 100, 108, 100, 115, 100, 107, 100, 113,
        100, 106, 100, 114, 100, 109, 100, 111, 100, 110,
        100, 112, 100, 108, 100, 115, 100, 107,
    ])

    fake = {"SINE": clean_sine, "TREND": trend, "NOISE": noisy_cycle}
    monkeypatch.setattr(
        cy.client,
        "get_multi_bars",
        lambda symbols, **kw: {s: fake[s] for s in symbols if s in fake},
    )

    out = cy.scan_cyclicals(["SINE", "TREND", "NOISE"])
    symbols = [r.symbol for r in out]
    assert "TREND" not in symbols
    # SINE is the cleanest; it should rank first if both pass, or be
    # the only one that passes.
    assert symbols[0] == "SINE"
