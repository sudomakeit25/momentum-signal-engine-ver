"""Tests for the intraday movers screener (src/scanner/intraday_movers.py)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.data.models import SetupType, SignalAction
from src.scanner.intraday_movers import (
    ET,
    detect_higher_low,
    detect_range_breakout,
    detect_vwap_setup,
    is_market_hours,
    relative_volume,
    session_bars,
)

UTC = ZoneInfo("UTC")


def _bars(
    rows: list[tuple[float, float, float, float, int]],
    start: datetime | None = None,
    freq_min: int = 5,
) -> pd.DataFrame:
    """Build a 5-min bar frame from (open, high, low, close, volume) rows."""
    start = start or datetime(2026, 11, 9, 9, 30, tzinfo=ET)  # a Monday
    idx = [start + timedelta(minutes=freq_min * i) for i in range(len(rows))]
    return pd.DataFrame(
        rows, columns=["open", "high", "low", "close", "volume"],
        index=pd.DatetimeIndex(idx),
    )


def _flat(n: int, price: float = 100.0, vol: int = 1000, **kw) -> pd.DataFrame:
    return _bars([(price, price + 0.1, price - 0.1, price, vol)] * n, **kw)


NOW = datetime(2026, 11, 9, 14, 30, tzinfo=ET)  # Monday 2:30 PM ET


# ---------------------------------------------------------------- session_bars

class TestSessionBars:
    def test_empty_frame(self):
        assert session_bars(pd.DataFrame(), now=NOW).empty

    def test_none(self):
        assert session_bars(None, now=NOW).empty

    def test_filters_other_days_and_premarket(self):
        yesterday = _flat(5, start=datetime(2026, 11, 6, 10, 0, tzinfo=ET))
        premarket = _flat(3, start=datetime(2026, 11, 9, 8, 0, tzinfo=ET))
        session = _flat(4, start=datetime(2026, 11, 9, 9, 30, tzinfo=ET))
        df = pd.concat([yesterday, premarket, session])
        out = session_bars(df, now=NOW)
        assert len(out) == 4

    def test_reversed_input_is_sorted(self):
        df = _flat(6, start=datetime(2026, 11, 9, 9, 30, tzinfo=ET)).iloc[::-1]
        out = session_bars(df, now=NOW)
        assert list(out.index) == sorted(out.index)

    def test_naive_index_treated_as_utc(self):
        # 14:30 UTC == 9:30 ET in November (EST)
        idx = [datetime(2026, 11, 9, 14, 30) + timedelta(minutes=5 * i) for i in range(3)]
        df = pd.DataFrame(
            [(100, 100.1, 99.9, 100, 1000)] * 3,
            columns=["open", "high", "low", "close", "volume"],
            index=pd.DatetimeIndex(idx),
        )
        assert len(session_bars(df, now=NOW)) == 3


# ------------------------------------------------------------ relative_volume

class TestRelativeVolume:
    def test_zero_avg_volume(self):
        assert relative_volume(1_000_000, 0, now=NOW) == 0.0

    def test_half_day_double_volume(self):
        # 12:45 ET = 195 min elapsed = half the session; full-day avg traded
        # by midday means 2x pace
        halfday = datetime(2026, 11, 9, 12, 45, tzinfo=ET)
        rv = relative_volume(10_000_000, 10_000_000, now=halfday)
        assert rv == pytest.approx(2.0, rel=0.01)

    def test_before_open_clamps(self):
        early = datetime(2026, 11, 9, 9, 31, tzinfo=ET)
        assert relative_volume(1000, 1_000_000, now=early) > 0


# -------------------------------------------------------------- market hours

class TestMarketHours:
    def test_weekend(self):
        assert not is_market_hours(datetime(2026, 11, 8, 11, 0, tzinfo=ET))  # Sunday

    def test_midsession(self):
        assert is_market_hours(NOW)

    def test_after_close(self):
        assert not is_market_hours(datetime(2026, 11, 9, 16, 30, tzinfo=ET))


# ------------------------------------------------------- range-box breakout

def _box_frame(breakout_close: float, breakout_vol: int = 2000) -> pd.DataFrame:
    """8 tight box bars (100.0-100.5) then a breakout bar."""
    rows = [(100.2, 100.5, 100.0, 100.3, 1000)] * 8
    rows.append((100.4, max(100.6, breakout_close), min(99.9, breakout_close),
                 breakout_close, breakout_vol))
    return _bars(rows, start=datetime(2026, 11, 9, 13, 30, tzinfo=ET))


class TestRangeBreakout:
    def test_breakout_long(self):
        sig = detect_range_breakout(_box_frame(100.55), "TEST", atr_pct=4.0)
        assert sig is not None
        assert sig.action == SignalAction.BUY
        assert sig.setup_type == SetupType.RANGE_BREAKOUT
        assert sig.stop_loss == pytest.approx(100.25, abs=0.01)  # box midpoint
        assert sig.target == pytest.approx(101.0, abs=0.01)      # high + height
        assert sig.rr_ratio >= 1.5

    def test_breakdown_short(self):
        sig = detect_range_breakout(_box_frame(99.95), "TEST", atr_pct=4.0)
        assert sig is not None
        assert sig.action == SignalAction.SELL
        assert sig.target == pytest.approx(99.5, abs=0.01)

    def test_chased_entry_rejected_by_rr_floor(self):
        # 100.5 box high + 0.5 height: entry 100.9 is 0.8x height extended
        assert detect_range_breakout(_box_frame(100.9), "TEST", atr_pct=4.0) is None

    def test_no_volume_confirmation(self):
        assert detect_range_breakout(
            _box_frame(100.55, breakout_vol=1100), "TEST", atr_pct=4.0
        ) is None

    def test_box_too_wide_for_low_atr_name(self):
        # 0.5% box vs ATR 1.0% -> threshold max(0.3, 0.35) = 0.35% -> too wide
        assert detect_range_breakout(_box_frame(100.55), "TEST", atr_pct=1.0) is None

    def test_insufficient_bars(self):
        assert detect_range_breakout(_flat(3), "TEST", atr_pct=4.0) is None

    def test_empty_and_none(self):
        assert detect_range_breakout(pd.DataFrame(), "TEST", atr_pct=4.0) is None
        assert detect_range_breakout(None, "TEST", atr_pct=4.0) is None

    def test_still_inside_box(self):
        assert detect_range_breakout(_box_frame(100.3, 5000), "TEST", atr_pct=4.0) is None


# ------------------------------------------------------------- VWAP setups

class TestVwapSetup:
    def test_reclaim_long(self):
        # Heavy open spike anchors VWAP ~101.5 and the day high at 103.5;
        # price bases at 100 below VWAP, then reclaims it on volume with
        # room overhead to the day high.
        rows = [(101, 103.5, 100.8, 101, 50000)]           # heavy open, day high 103.5
        rows += [(100, 100.2, 99.8, 100, 1000)] * 8        # base below VWAP
        rows.append((100.5, 102.0, 100.4, 101.9, 9000))    # reclaim bar through VWAP
        sdf = _bars(rows, start=datetime(2026, 11, 9, 9, 30, tzinfo=ET))
        sig = detect_vwap_setup(sdf, "TEST")
        assert sig is not None
        assert sig.action == SignalAction.BUY
        assert sig.setup_type == SetupType.VWAP_RECLAIM
        assert sig.rr_ratio >= 1.5
        assert sig.target == pytest.approx(103.5, abs=0.01)  # day high

    def test_rejection_short(self):
        # VWAP ~100.5; price below it all session with the day low at 97.5,
        # pokes up to VWAP, fails, closes back down.
        rows = [(100.8, 101.2, 100.2, 100.6, 50000)]       # heavy open anchors VWAP
        rows += [(100, 100.2, 97.5, 100, 1000)]            # day low 97.5 early
        rows += [(99.9, 100.0, 99.7, 99.9, 1000)] * 6      # base below VWAP
        rows.append((99.9, 100.55, 99.8, 100.0, 1500))     # retest toward VWAP
        rows.append((100.0, 100.1, 99.6, 99.7, 2000))      # fail and roll over
        sdf = _bars(rows, start=datetime(2026, 11, 9, 9, 30, tzinfo=ET))
        sig = detect_vwap_setup(sdf, "TEST")
        assert sig is not None
        assert sig.action == SignalAction.SELL
        assert sig.setup_type == SetupType.VWAP_REJECTION
        assert sig.target == pytest.approx(97.5, abs=0.01)  # day low

    def test_chop_no_signal(self):
        assert detect_vwap_setup(_flat(20), "TEST") is None

    def test_insufficient_bars(self):
        assert detect_vwap_setup(_flat(5), "TEST") is None

    def test_empty_and_none(self):
        assert detect_vwap_setup(pd.DataFrame(), "TEST") is None
        assert detect_vwap_setup(None, "TEST") is None


# ------------------------------------------------------------- higher low

def _higher_low_frame(pullback_low: float = 101.0) -> pd.DataFrame:
    """Morning: low 100, run to day high 104. Afternoon: pull back to
    `pullback_low`, then confirm back up."""
    rows = [(100.5, 101.0, 100.0, 100.8, 2000)] * 3        # morning low 100
    rows += [(101.0, 104.0, 100.9, 103.5, 3000)] * 4       # run to day high 104
    rows += [(103.0, 103.2, 102.0, 102.2, 1500)] * 30      # drift into the afternoon
    rows += [(102.0, 102.1, pullback_low, pullback_low + 0.2, 1200)] * 3  # pullback
    rows.append((101.5, 102.2, 101.4, 102.15, 2500))       # confirm above pivot high
    return _bars(rows, start=datetime(2026, 11, 9, 9, 30, tzinfo=ET))


class TestHigherLow:
    def test_higher_low_continuation(self):
        sig = detect_higher_low(_higher_low_frame(), "TEST")
        assert sig is not None
        assert sig.action == SignalAction.BUY
        assert sig.setup_type == SetupType.HIGHER_LOW
        assert sig.stop_loss == pytest.approx(101.0, abs=0.01)
        assert sig.target == pytest.approx(104.0, abs=0.01)
        assert sig.rr_ratio >= 1.5

    def test_pullback_breaks_morning_low(self):
        assert detect_higher_low(_higher_low_frame(pullback_low=99.9), "TEST") is None

    def test_retest_of_morning_low_not_higher(self):
        # within 0.15% margin of the morning low -> not a higher low
        assert detect_higher_low(_higher_low_frame(pullback_low=100.05), "TEST") is None

    def test_morning_only_no_afternoon(self):
        sdf = _flat(10, start=datetime(2026, 11, 9, 9, 30, tzinfo=ET))
        assert detect_higher_low(sdf, "TEST") is None

    def test_empty_and_none(self):
        assert detect_higher_low(pd.DataFrame(), "TEST") is None
        assert detect_higher_low(None, "TEST") is None


# --------------------------------------------------------------- end to end

class TestScanIntraday:
    def test_scan_with_mocked_client(self, monkeypatch):
        """Full scan over a mocked two-symbol universe: one qualifying mover
        with a breakout, one quiet large cap that must be filtered out."""
        from src.scanner import intraday_movers as mod

        mover_5m = _box_frame(100.55)
        # Box bars 2M each, breakout bar 4M: clears both the 1.5x box-volume
        # confirmation and the cumulative RVOL gate.
        mover_5m["volume"] = [2_000_000] * 8 + [4_000_000]
        quiet_5m = _flat(9, price=100.0, vol=1000,
                         start=datetime(2026, 11, 9, 13, 30, tzinfo=ET))

        day_idx = pd.DatetimeIndex(
            [datetime(2026, 9, 1, tzinfo=UTC) + timedelta(days=i) for i in range(40)]
        )
        daily = pd.DataFrame({
            "open": 98.0, "high": 102.0, "low": 95.0, "close": 97.0,
            "volume": 5_000_000,
        }, index=day_idx)

        def fake_multi_bars(symbols, timeframe=None, days=200):
            return {"MOVR": daily.copy(), "QUIET": daily.copy()}

        def fake_intraday_bars(symbols, minutes_back=400, timeframe_minutes=5):
            return {"MOVR": mover_5m, "QUIET": quiet_5m}

        def fake_earnings(symbols, days_ahead=1):
            return []

        monkeypatch.setattr(mod.client, "get_multi_bars", fake_multi_bars)
        monkeypatch.setattr(mod.client, "get_intraday_multi_bars", fake_intraday_bars)
        import src.scanner.earnings_whisper as ew
        monkeypatch.setattr(ew, "get_upcoming_earnings", fake_earnings)
        results = mod.scan_intraday(
            symbols=["MOVR", "QUIET", "BTC/USD"],
            check_spread=False,
            now=NOW,
        )
        symbols = [r.symbol for r in results]
        assert "MOVR" in symbols       # +3.6% vs yesterday close 97, high RVOL
        assert "QUIET" not in symbols  # RVOL ~0 at 1000/bar
        movr = results[symbols.index("MOVR")]
        assert movr.atr_pct > 0
        assert SetupType.RANGE_BREAKOUT in movr.setup_types

    def test_empty_universe(self):
        from src.scanner.intraday_movers import scan_intraday
        assert scan_intraday(symbols=["BTC/USD"], now=NOW) == []
