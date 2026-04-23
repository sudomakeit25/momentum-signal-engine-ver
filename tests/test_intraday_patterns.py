"""Tests for the intraday pattern detectors.

Synthetic 5-min bar fixtures shaped to match the four real charts that
motivated the feature: CLSK (V-reversal), AMD (inverted-V), AST and
RKLB (sustained breakdown).
"""

from datetime import datetime, timedelta, timezone

import pandas as pd

from src.scanner import intraday_patterns as ip


def _bars(closes: list[float], volumes: list[int] | None = None) -> pd.DataFrame:
    """Build a 5-min OHLCV DataFrame from a list of closes."""
    if volumes is None:
        volumes = [100_000] * len(closes)
    assert len(closes) == len(volumes)
    base_ts = datetime(2026, 4, 23, 18, 0, tzinfo=timezone.utc)
    rows = []
    for i, (c, v) in enumerate(zip(closes, volumes)):
        # Simple OHLC: open at prior close, high/low ±0.1% of close.
        prev = closes[i - 1] if i > 0 else c
        rows.append({
            "open": prev,
            "high": max(prev, c) * 1.001,
            "low": min(prev, c) * 0.999,
            "close": c,
            "volume": v,
        })
    df = pd.DataFrame(rows, index=[base_ts + timedelta(minutes=5 * i) for i in range(len(closes))])
    return df


# --- V-reversal ---

def test_v_reversal_fires_on_clsk_shape():
    # 13.20 -> 11.42 -> 12.16 in 18 bars (CLSK 2026-04-23)
    drop = [13.20, 13.10, 13.00, 12.80, 12.55, 12.20, 11.85, 11.55, 11.42]
    recover = [11.55, 11.70, 11.85, 12.00, 12.10, 12.16, 12.16, 12.16, 12.16]
    df = _bars(drop + recover, volumes=[100] * len(drop) + [200] * len(recover))
    pat = ip.detect_v_reversal(df, "CLSK")
    assert pat is not None
    assert pat.action == "BUY"
    assert pat.pattern_type == "v_reversal"
    assert pat.move_pct < -10  # ~-13.5%
    assert pat.recovery_pct > 5
    assert pat.volume_confirmed is True


def test_v_reversal_skips_when_low_is_at_the_edge():
    # Lowest low is the very last bar -> not a V yet.
    closes = [10.0, 10.2, 10.4, 10.3, 10.1, 9.9, 9.7, 9.5, 9.3, 9.1, 8.9, 8.7]
    df = _bars(closes)
    assert ip.detect_v_reversal(df, "X") is None


def test_v_reversal_skips_when_drop_too_small():
    # Only ~1% drop and recovery — below default 3% threshold.
    closes = [100.0, 100.2, 100.1, 99.9, 99.5, 99.3, 99.5, 99.8, 100.0]
    df = _bars(closes)
    assert ip.detect_v_reversal(df, "X") is None


def test_v_reversal_skips_when_recovery_too_small():
    # Sharp drop of ~10%, but only ~10% of that recovered — under
    # the default 30% recovery threshold.
    drop = [100.0, 99.0, 97.0, 95.0, 93.0, 91.0, 90.0]
    weak = [90.2, 90.4, 90.6, 90.8, 91.0]
    df = _bars(drop + weak)
    assert ip.detect_v_reversal(df, "X") is None


# --- Inverted-V ---

def test_inverted_v_fires_on_pop_and_fade():
    # Flat -> rally -> fade most of the rally. AMD-ish pattern.
    rise = [100.0, 100.5, 101.0, 102.0, 103.5, 105.0, 106.5, 107.0]
    fade = [106.0, 105.0, 103.5, 102.0, 100.8, 100.5, 100.4, 100.3, 100.2, 100.1]
    df = _bars(rise + fade, volumes=[100] * len(rise) + [200] * len(fade))
    pat = ip.detect_inverted_v(df, "AMD")
    assert pat is not None
    assert pat.action == "SELL"
    assert pat.pattern_type == "inverted_v"
    assert pat.move_pct > 5
    assert pat.recovery_pct < 0
    assert pat.volume_confirmed is True


def test_inverted_v_skips_when_high_is_at_the_edge():
    closes = [100.0, 100.5, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0]
    df = _bars(closes)
    assert ip.detect_inverted_v(df, "X") is None


# --- Sustained breakdown / breakout ---

def test_sustained_breakdown_fires_on_ast_shape():
    # Window opens near high, then sustained drop with no recovery.
    closes = [
        100.0, 100.2, 99.8, 100.0,   # early-window high here
        99.5, 98.0, 96.5, 95.0,      # break down
        93.5, 92.0, 91.5, 91.0,      # continuation lower
        90.8, 90.5, 90.3, 90.5,      # consolidating near the low
    ]
    df = _bars(closes, volumes=[100] * 4 + [200] * 12)
    pat = ip.detect_sustained_move(df, "ASTS")
    assert pat is not None
    assert pat.action == "SELL"
    assert pat.pattern_type == "breakdown"
    assert pat.move_pct < -5
    assert pat.volume_confirmed is True


def test_sustained_breakout_fires_on_morning_pop():
    closes = [
        50.0, 50.5, 50.2, 50.1,      # early-window low here
        51.0, 53.0, 55.0, 56.0,      # breakout
        57.5, 58.0, 58.5, 59.0,      # continuation higher
        59.2, 59.1, 59.3, 59.0,      # holding gains
    ]
    df = _bars(closes, volumes=[100] * 4 + [200] * 12)
    pat = ip.detect_sustained_move(df, "X")
    assert pat is not None
    assert pat.action == "BUY"
    assert pat.pattern_type == "breakout"
    assert pat.move_pct > 5
    assert pat.volume_confirmed is True


def test_sustained_skips_on_chop():
    # Pure chop — no clear directional move.
    closes = [100.0, 100.2, 99.9, 100.1, 99.8, 100.3, 99.9, 100.1, 100.0, 99.9, 100.1, 100.0]
    df = _bars(closes)
    assert ip.detect_sustained_move(df, "X") is None


# --- Scan + priority ordering ---

def test_scan_returns_one_pattern_per_symbol(monkeypatch):
    # Two symbols, distinct patterns.
    drop = [13.20, 13.00, 12.50, 12.00, 11.60, 11.42]
    recover = [11.60, 11.80, 12.00, 12.10, 12.16, 12.16]
    clsk = _bars(drop + recover, volumes=[100] * 6 + [200] * 6)

    chop = [100.0, 100.2, 99.9, 100.1, 99.8, 100.3, 99.9, 100.1, 100.0, 99.9, 100.1, 100.0]
    flat = _bars(chop)

    fake_bars = {"CLSK": clsk, "FLAT": flat}
    monkeypatch.setattr(
        ip.client,
        "get_intraday_multi_bars",
        lambda symbols, **kw: {s: fake_bars[s] for s in symbols if s in fake_bars},
    )

    out = ip.scan_intraday_patterns(["CLSK", "FLAT"])
    assert len(out) == 1
    assert out[0].symbol == "CLSK"
    assert out[0].pattern_type == "v_reversal"
