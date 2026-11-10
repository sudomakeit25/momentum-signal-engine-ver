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


        monkeypatch.setattr(mod.client, "get_multi_bars", fake_multi_bars)
        monkeypatch.setattr(mod.client, "get_intraday_multi_bars", fake_intraday_bars)
        monkeypatch.setattr(mod, "_earnings_lookup", lambda symbols: (set(), set(symbols)))
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


# ------------------------------------------------ all-session higher low

from src.scanner.intraday_movers import (  # noqa: E402
    _intraday_universe,
    detect_box_forming,
    detect_vwap_tag,
)


def _morning_higher_low(confirm_low: float = 101.3) -> pd.DataFrame:
    """Whole structure before noon: low 100, bounce to 105, pullback to 101,
    confirmation close back above the pivot bar's high."""
    rows = [(100.5, 100.8, 100.0, 100.4, 2000)] * 2          # day low 100
    rows += [(101.0, 105.0, 100.9, 104.5, 3000)] * 5         # bounce to 105
    rows += [(102.0, 102.1, 101.0, 101.2, 1200)] * 4         # pullback (higher low)
    rows.append((101.3, 102.3, confirm_low, 102.2, 2500))    # confirm
    return _bars(rows, start=datetime(2026, 11, 9, 9, 30, tzinfo=ET))


class TestHigherLowAllSession:
    def test_fires_before_noon(self):
        sdf = _morning_higher_low()
        assert sdf.index[-1].time() < datetime(2026, 1, 1, 12, 0).time()
        sig = detect_higher_low(sdf, "TEST")
        assert sig is not None
        assert sig.setup_type == SetupType.HIGHER_LOW
        assert sig.stop_loss == pytest.approx(101.0, abs=0.01)
        assert sig.target == pytest.approx(105.0, abs=0.01)
        assert sig.rr_ratio >= 1.5

    def test_confirmation_bar_undercuts_higher_low(self):
        assert detect_higher_low(_morning_higher_low(confirm_low=100.9), "TEST") is None

    def test_monotonic_rise_is_not_a_pullback(self):
        rows = [
            (100 + i * 0.2, 100.3 + i * 0.2, 100 + i * 0.2, 100.25 + i * 0.2, 1000)
            for i in range(15)
        ]
        assert detect_higher_low(_bars(rows), "TEST") is None

    def test_day_low_too_recent(self):
        rows = [(100, 100.2, 100.0, 100.1, 1000)] * 12
        rows += [(100, 100.1, 98.0, 98.5, 3000), (98.5, 99.0, 98.4, 98.9, 2000),
                 (98.9, 99.5, 98.8, 99.4, 2000)]
        assert detect_higher_low(_bars(rows), "TEST") is None

    def test_downtrend_day_targets_bounce_peak_not_day_high(self):
        rows = [
            (109, 110, 108, 108.5, 5000),                    # day high first
            (106, 106.5, 104, 104.5, 4000), (104, 104.5, 102, 102.5, 4000),
            (102, 102.5, 101, 101.2, 4000), (101, 101.3, 100.5, 100.8, 4000),
            (100.8, 101, 100.0, 100.6, 4000),                # day low 100
            (100.6, 102, 100.5, 101.8, 3000), (101.8, 103, 101.7, 102.8, 3000),
            (102.8, 103.0, 102.2, 102.4, 2000),              # bounce peak 103
            (102.4, 102.5, 101.5, 101.6, 1500), (101.6, 101.7, 101.0, 101.2, 1500),
            (101.2, 101.4, 101.05, 101.3, 1500),             # higher low 101
            (101.3, 101.9, 101.25, 101.75, 2500),            # confirm
        ]
        sig = detect_higher_low(_bars(rows), "TEST")
        assert sig is not None
        assert sig.target == pytest.approx(103.0, abs=0.01)
        assert sig.stop_loss == pytest.approx(101.0, abs=0.01)


# ------------------------------------------------------- box forming watch

def _forming_box(start: datetime | None = None) -> pd.DataFrame:
    """An hour of real move (96 -> 100) then an intact 8-bar box 100.0-100.4."""
    rows = [(96 + i * 0.35, 96.45 + i * 0.35, 96 + i * 0.35, 96.4 + i * 0.35, 3000)
            for i in range(12)]
    rows += [(100.2, 100.4, 100.0, 100.3, 1000)] * 8
    return _bars(rows, start=start or datetime(2026, 11, 9, 12, 50, tzinfo=ET))


class TestBoxForming:
    def test_box_after_real_move(self):
        w = detect_box_forming(_forming_box(), "TEST", atr_pct=4.0)
        assert w is not None
        assert w.watch_type == "box_forming"
        assert w.upper == pytest.approx(100.4)
        assert w.lower == pytest.approx(100.0)
        assert "100.40" in w.detail and "100.00" in w.detail

    def test_opening_range_is_not_a_box(self):
        # Same tight box, but only 6 bars of session before it
        sdf = _forming_box().iloc[6:]
        assert len(sdf) == 14
        assert detect_box_forming(sdf, "TEST", atr_pct=4.0) is None

    def test_high_atr_name_capped_at_one_percent(self):
        rows = [(90 + i * 0.8, 90.9 + i * 0.8, 90 + i * 0.8, 90.8 + i * 0.8, 3000)
                for i in range(12)]
        rows += [(100.4, 101.05, 100.0, 100.5, 1000)] * 8    # 1.04% tall
        assert detect_box_forming(_bars(rows), "TEST", atr_pct=9.0) is None

    def test_quiet_stock_without_a_move(self):
        assert detect_box_forming(_flat(20), "TEST", atr_pct=4.0) is None

    def test_box_too_wide_for_low_atr_name(self):
        assert detect_box_forming(_forming_box(), "TEST", atr_pct=1.0) is None

    def test_insufficient_empty_none(self):
        assert detect_box_forming(_flat(6), "TEST", atr_pct=4.0) is None
        assert detect_box_forming(pd.DataFrame(), "TEST", atr_pct=4.0) is None
        assert detect_box_forming(None, "TEST", atr_pct=4.0) is None


# ------------------------------------------------------------ VWAP tag watch

def _vwap_tag_frame() -> pd.DataFrame:
    from src.signals.indicators import vwap as _vwap
    rise = [100 + i * 0.2 for i in range(16)]                 # 100 -> 103
    fade = [103 - i * 0.15 for i in range(1, 10)]             # back toward VWAP
    rows = [(c, c + 0.05, c - 0.05, c, 1000) for c in rise + fade]
    sdf = _bars(rows)
    v = float(_vwap(sdf).iloc[-1])                            # snap last bar onto VWAP
    sdf.iloc[-1] = [v, v + 0.05, v - 0.05, v, 1000]
    return sdf


class TestVwapTag:
    def test_tag_after_trending_away(self):
        w = detect_vwap_tag(_vwap_tag_frame(), "TEST")
        assert w is not None
        assert w.watch_type == "vwap_tag"
        assert "VWAP" in w.detail

    def test_never_far_from_vwap(self):
        assert detect_vwap_tag(_flat(25), "TEST") is None

    def test_still_far_from_vwap(self):
        rows = [(100 + i * 0.3, 100.35 + i * 0.3, 100 + i * 0.3, 100.3 + i * 0.3, 1000)
                for i in range(25)]
        assert detect_vwap_tag(_bars(rows), "TEST") is None

    def test_insufficient_empty_none(self):
        assert detect_vwap_tag(_flat(10), "TEST") is None
        assert detect_vwap_tag(pd.DataFrame(), "TEST") is None
        assert detect_vwap_tag(None, "TEST") is None


# ------------------------------------------------------ universe + scan wiring

class TestUniverse:
    def test_fallback_adds_high_beta_and_drops_crypto(self):
        uni = _intraday_universe(None)
        assert "SNDK" in uni and "ASTS" in uni
        assert all("/" not in s for s in uni)
        assert len(uni) == len(set(uni))

    def test_explicit_symbols_are_not_extended(self):
        assert _intraday_universe(["MU", "BTC/USD"]) == ["MU"]


class TestScanWatches:
    reporting: set = set()
    known: bool = True

    def _run(self, monkeypatch, five_min):
        from src.scanner import intraday_movers as mod
        day_idx = pd.DatetimeIndex(
            [datetime(2026, 9, 1, tzinfo=UTC) + timedelta(days=i) for i in range(40)]
        )
        daily = pd.DataFrame({
            "open": 98.0, "high": 102.0, "low": 95.0, "close": 97.0,
            "volume": 5_000_000,
        }, index=day_idx)
        monkeypatch.setattr(mod.client, "get_multi_bars",
                            lambda symbols, timeframe=None, days=200: {"MOVR": daily.copy()})
        monkeypatch.setattr(mod.client, "get_intraday_multi_bars",
                            lambda symbols, minutes_back=400, timeframe_minutes=5: {"MOVR": five_min})
        monkeypatch.setattr(
            mod, "_earnings_lookup",
            lambda symbols: (self.reporting, set(symbols) if self.known else set()))
        return mod.scan_intraday(symbols=["MOVR"], check_spread=False, now=NOW)

    def test_intact_box_surfaces_as_watch(self, monkeypatch):
        five_min = _forming_box()
        five_min["volume"] = 2_000_000
        results = self._run(monkeypatch, five_min)
        assert len(results) == 1
        assert [w.watch_type for w in results[0].watches] == ["box_forming"]
        assert SetupType.RANGE_BREAKOUT not in results[0].setup_types

    def test_triggered_breakout_suppresses_box_watch(self, monkeypatch):
        five_min = _box_frame(100.55)
        five_min["volume"] = [2_000_000] * 8 + [4_000_000]
        results = self._run(monkeypatch, five_min)
        assert SetupType.RANGE_BREAKOUT in results[0].setup_types
        assert all(w.watch_type != "box_forming" for w in results[0].watches)


# ------------------------------------------------------------ watch dispatch

class TestWatchDispatch:
    def _watch(self, sym="SNDK", kind="box_forming"):
        from src.data.models import IntradayWatch
        return IntradayWatch(symbol=sym, watch_type=kind, detail="d",
                             upper=890.0, lower=884.0, timestamp=NOW)

    def test_body_fits_sms_limit(self):
        from src.notifications.dispatcher import _format_watch_body
        body = _format_watch_body([self._watch(f"SYM{i}") for i in range(12)])
        assert len(body) <= 155
        assert body.startswith("MSE Watch: 12")

    def test_single_watch_body(self):
        from src.notifications.dispatcher import _format_watch_body
        body = _format_watch_body([self._watch(kind="vwap_tag")])
        assert body == "MSE Watch\nSNDK at VWAP 890.00, watch hold/reject"

    def test_empty_list_sends_nothing(self):
        from src.notifications.dispatcher import dispatch_intraday_watches
        assert dispatch_intraday_watches([]) == {"sms": False, "push": False}

    def test_disabled_alerts_send_nothing(self, monkeypatch):
        from src.notifications import dispatcher as d
        sent = []
        monkeypatch.setattr(d, "load_config",
                            lambda: d.NotificationConfig(auto_alerts_enabled=False))
        monkeypatch.setattr(d, "_send_text_sms", lambda c, b: sent.append(b) or True)
        assert d.dispatch_intraday_watches([self._watch()]) == {"sms": False, "push": False}
        assert sent == []

    def test_enabled_sends_once_with_levels(self, monkeypatch):
        from src.notifications import dispatcher as d
        import src.data.redis_store as rs
        sent = []
        cfg = d.NotificationConfig(auto_alerts_enabled=True, sms_to="5551234567",
                                   sms_consent=True, sms_method="email_gateway",
                                   sms_carrier="tmobile")
        monkeypatch.setattr(d, "load_config", lambda: cfg)
        monkeypatch.setattr(d, "_recent_sms_fingerprints", lambda: {})
        monkeypatch.setattr(d, "_record_sms_fingerprint", lambda fp: None)
        monkeypatch.setattr(d, "_send_text_sms", lambda c, b: sent.append(b) or True)
        monkeypatch.setattr(rs, "get_push_tokens", lambda: {})
        result = d.dispatch_intraday_watches([self._watch()])
        assert result["sms"] is True
        assert sent == ["MSE Watch\nSNDK box 884.00-890.00, watch break"]

    def test_no_consent_no_sms(self, monkeypatch):
        from src.notifications import dispatcher as d
        import src.data.redis_store as rs
        sent = []
        cfg = d.NotificationConfig(auto_alerts_enabled=True, sms_to="5551234567",
                                   sms_consent=False)
        monkeypatch.setattr(d, "load_config", lambda: cfg)
        monkeypatch.setattr(d, "_send_text_sms", lambda c, b: sent.append(b) or True)
        monkeypatch.setattr(rs, "get_push_tokens", lambda: {})
        assert d.dispatch_intraday_watches([self._watch()])["sms"] is False
        assert sent == []


# ------------------------------------------------------- earnings + NaN guards

class TestEarningsFlag:
    def _scan(self, monkeypatch, reporting, known):
        helper = TestScanWatches()
        helper.reporting, helper.known = reporting, known
        five_min = _forming_box()
        five_min["volume"] = 2_000_000
        return helper._run(monkeypatch, five_min)[0]

    def test_reporting_symbol_is_flagged(self, monkeypatch):
        r = self._scan(monkeypatch, {"MOVR"}, True)
        assert r.earnings_soon is True and r.earnings_known is True

    def test_failed_lookup_is_marked_unknown_not_clear(self, monkeypatch):
        r = self._scan(monkeypatch, set(), False)
        assert r.earnings_soon is False and r.earnings_known is False

    def test_lookup_error_means_nothing_is_known(self, monkeypatch):
        from src.data import earnings_calendar
        from src.scanner import intraday_movers as mod
        def boom(symbols, now=None):
            raise RuntimeError("503")
        monkeypatch.setattr(earnings_calendar, "reporting_soon", boom)
        assert mod._earnings_lookup(["NVDA"]) == (set(), set())

    def test_lookup_passes_through_the_calendar_answer(self, monkeypatch):
        from src.data import earnings_calendar
        from src.scanner import intraday_movers as mod
        monkeypatch.setattr(earnings_calendar, "reporting_soon",
                            lambda symbols, now=None: ({"NVDA"}, {"NVDA", "AMD"}))
        assert mod._earnings_lookup(["NVDA", "AMD", "MU"]) == ({"NVDA"}, {"NVDA", "AMD"})


def test_make_signal_rejects_non_finite_levels():
    from src.scanner.intraday_movers import _make_signal
    nan = float("nan")
    for entry, stop, target in [(nan, 99.0, 102.0), (100.0, nan, 102.0), (100.0, 99.0, nan),
                                (100.0, 99.0, float("inf"))]:
        assert _make_signal("X", SignalAction.BUY, SetupType.HIGHER_LOW, "r", entry, stop,
                            target, 0.6, NOW, 1.5) is None
