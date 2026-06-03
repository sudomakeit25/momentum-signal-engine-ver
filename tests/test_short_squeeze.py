"""Tests for the short-squeeze detector.

Covers the composite score function directly, and the scan logic with
FINRA / Alpaca calls mocked so no network access is needed.
"""

import json

import numpy as np
import pandas as pd

from src.scanner import advanced_signals as adv


# --- compute_squeeze_score ---

def test_score_rewards_high_days_to_cover_and_rising_price():
    ideal = adv.compute_squeeze_score(
        days_to_cover=8, price_change_5d=12, si_change_pct=5, recent_short_vol_pct=55
    )
    assert ideal > 80  # both fuel and trigger present


def test_score_drops_without_fuel():
    # Rising hard but only 1 day to cover — no squeeze fuel.
    weak_fuel = adv.compute_squeeze_score(
        days_to_cover=1, price_change_5d=12, si_change_pct=5, recent_short_vol_pct=55
    )
    strong = adv.compute_squeeze_score(
        days_to_cover=8, price_change_5d=12, si_change_pct=5, recent_short_vol_pct=55
    )
    assert weak_fuel < strong


def test_score_drops_without_trigger():
    # Lots of fuel but price flat — nothing forcing covers.
    no_trigger = adv.compute_squeeze_score(
        days_to_cover=8, price_change_5d=0, si_change_pct=5, recent_short_vol_pct=55
    )
    strong = adv.compute_squeeze_score(
        days_to_cover=8, price_change_5d=12, si_change_pct=5, recent_short_vol_pct=55
    )
    assert no_trigger < strong


def test_score_is_native_float():
    s = adv.compute_squeeze_score(8, 12, 5, 55)
    assert type(s) is float  # not numpy
    assert 0 <= s <= 100


def test_score_building_short_interest_adds_points():
    building = adv.compute_squeeze_score(5, 8, +10, 50)
    covering = adv.compute_squeeze_score(5, 8, -10, 50)
    assert building == covering + 10  # the 10-pt "SI building" component


# --- scan_short_squeeze (mocked) ---

def _bars(closes):
    idx = pd.date_range("2026-05-01", periods=len(closes), freq="D")
    return pd.DataFrame({"close": closes}, index=idx)


def _patch_scan(monkeypatch, si_cycle, price_map, vol_map=None, universe=None):
    universe = universe or list(si_cycle.keys())
    monkeypatch.setattr(adv, "get_default_universe", lambda: universe)

    import src.data.finra_client as fc
    monkeypatch.setattr(fc, "get_short_interest", lambda: si_cycle)
    monkeypatch.setattr(
        fc, "get_short_volume_batch", lambda syms, days=10: (vol_map or {})
    )

    def fake_bars(sym, days=20):
        closes = price_map.get(sym)
        return _bars(closes) if closes else None
    monkeypatch.setattr(adv.alpaca_client, "get_bars", fake_bars)

    # Bypass the on-disk cache so each test starts clean.
    monkeypatch.setattr(adv._cache, "get", lambda key: None)
    monkeypatch.setattr(adv._cache, "set", lambda key, val: None)


SI = {
    "SQUEEZE": {"shares_short": 50_000_000, "prev_shares_short": 45_000_000,
                "avg_daily_volume": 6_000_000, "days_to_cover": 8.3,
                "change_pct": 11.1, "settlement_date": "2026-05-15"},
    "MOMENTUM": {"shares_short": 8_000_000, "prev_shares_short": 8_100_000,
                 "avg_daily_volume": 9_000_000, "days_to_cover": 0.9,
                 "change_pct": -1.2, "settlement_date": "2026-05-15"},
    "FALLING": {"shares_short": 40_000_000, "prev_shares_short": 38_000_000,
                "avg_daily_volume": 5_000_000, "days_to_cover": 8.0,
                "change_pct": 5.0, "settlement_date": "2026-05-15"},
}


def test_scan_surfaces_real_squeeze_over_momentum(monkeypatch):
    prices = {
        "SQUEEZE": [100, 102, 105, 110, 118, 120],   # +14% over 5d, high dtc
        "MOMENTUM": [50, 55, 60, 70, 80, 85],         # +70% but dtc 0.9 — no fuel
        "FALLING": [100, 99, 97, 95, 92, 90],         # high dtc but price falling
    }
    _patch_scan(monkeypatch, SI, prices)
    out = adv.scan_short_squeeze()
    syms = [r["symbol"] for r in out]

    # MOMENTUM excluded — days_to_cover 0.9 < gate of 3.0
    assert "MOMENTUM" not in syms
    # FALLING excluded — price not rising
    assert "FALLING" not in syms
    # SQUEEZE is the real candidate
    assert syms == ["SQUEEZE"]


def test_scan_output_is_json_serializable(monkeypatch):
    prices = {"SQUEEZE": [100, 102, 105, 110, 118, 120]}
    _patch_scan(monkeypatch, {"SQUEEZE": SI["SQUEEZE"]}, prices)
    out = adv.scan_short_squeeze()
    # Must not raise — guards against the numpy-float64 500 in prod.
    json.dumps(out)
    row = out[0]
    assert type(row["squeeze_score"]) is float
    assert type(row["shares_short"]) is int
    assert type(row["days_to_cover"]) is float


def test_scan_empty_when_no_short_interest(monkeypatch):
    _patch_scan(monkeypatch, {}, {})
    assert adv.scan_short_squeeze() == []


def test_scan_handles_missing_price_data(monkeypatch):
    # SI says SQUEEZE qualifies, but Alpaca returns no bars for it.
    _patch_scan(monkeypatch, {"SQUEEZE": SI["SQUEEZE"]}, {})
    assert adv.scan_short_squeeze() == []


def test_scan_short_volume_confirmation_feeds_score(monkeypatch):
    prices = {"SQUEEZE": [100, 102, 105, 110, 118, 120]}
    vol = {"SQUEEZE": [{"short_pct": 60.0}, {"short_pct": 62.0}, {"short_pct": 64.0}]}
    _patch_scan(monkeypatch, {"SQUEEZE": SI["SQUEEZE"]}, prices, vol_map=vol)
    out = adv.scan_short_squeeze()
    assert out[0]["recent_short_vol_pct"] == 62.0  # mean of last 3
    # numpy mean must have been cast to native float
    assert type(out[0]["recent_short_vol_pct"]) is float
