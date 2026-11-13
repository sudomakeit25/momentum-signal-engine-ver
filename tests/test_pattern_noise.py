"""Pattern alerts must not come from pre-market bars or a single stray trade.
(Contradicting alerts are held back in src/notifications/alert_rules.py,
tested in tests/test_alert_rules.py.)

Regression case, from Alpaca's real 5-minute bars: on 2026-11-11 one AMD
pre-market print at 516.50 (bar 08:25 opened near 545, closed 543.92, 20,000
shares) produced a V-reversal BUY at 09:50 and an inverted-V SELL at 09:57.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.scanner import intraday_patterns as ip

ET = ZoneInfo("America/New_York")

# AMD, 2026-11-11, 5-minute bars as Alpaca reported them: (time, high, low, close, volume)
AMD_NOV11 = [
    ("08:05", 543.77, 541.27, 542.62, 52136), ("08:10", 543.91, 541.70, 543.90, 92980),
    ("08:15", 545.45, 543.09, 545.14, 58756), ("08:20", 545.25, 544.32, 545.00, 26484),
    ("08:25", 545.19, 516.50, 543.92, 20106), ("08:30", 544.60, 542.00, 542.00, 30970),
    ("08:35", 542.10, 540.09, 541.00, 36398), ("08:40", 542.50, 540.60, 540.67, 32676),
    ("08:45", 541.43, 540.07, 541.00, 195548), ("08:50", 542.42, 540.50, 542.00, 49283),
    ("08:55", 545.74, 541.79, 545.44, 79487), ("09:00", 545.94, 542.73, 544.48, 92006),
    ("09:05", 545.50, 543.98, 544.22, 45070), ("09:10", 544.44, 544.07, 544.23, 13315),
    ("09:15", 545.78, 544.11, 545.70, 45677), ("09:20", 546.36, 545.00, 546.36, 37547),
    ("09:25", 548.98, 542.84, 543.03, 132344), ("09:30", 543.40, 531.00, 532.23, 2166286),
    ("09:35", 532.55, 526.05, 528.43, 1238729), ("09:40", 531.80, 522.98, 524.46, 1023550),
    ("09:45", 527.62, 522.65, 526.70, 989991), ("09:50", 531.79, 525.35, 529.67, 840851),
    ("09:55", 534.71, 529.03, 534.20, 762948), ("10:00", 539.50, 532.80, 539.13, 866471),
    ("10:05", 546.45, 537.87, 543.17, 1401869), ("10:10", 543.60, 535.20, 535.70, 1004029),
]


def amd_bars(until: str) -> pd.DataFrame:
    rows, idx = [], []
    prev_close = 542.55
    for t, h, lo, c, v in AMD_NOV11:
        if t > until:
            break
        hh, mm = map(int, t.split(":"))
        idx.append(datetime(2026, 11, 11, hh, mm, tzinfo=ET))
        rows.append({"open": prev_close, "high": h, "low": lo, "close": c, "volume": v})
        prev_close = c
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


def run(df, now):
    for fn in ip._DETECTORS:
        p = fn(df, "AMD")
        if p is not None and p.volume_confirmed:
            return p
    return None


class TestAmdNov11:
    @pytest.mark.parametrize("sent,data_until", [("09:50", "09:30"), ("09:57", "09:35")])
    def test_the_window_is_session_only(self, sent, data_until):
        now = datetime(2026, 11, 11, *map(int, sent.split(":")), tzinfo=ET)
        df = amd_bars(data_until)
        old = ip._trim_window(df, 90, 5)
        assert sum(1 for t in old.index if t.hour * 60 + t.minute < 570) >= 16   # what fired: mostly pre-market
        window = ip.session_window(df, now=now)
        assert len(window) and all(t.hour * 60 + t.minute >= 570 for t in window.index)
        assert len(window) < 6                       # too little session data to judge yet

    def test_the_stray_print_alone_is_rejected_even_in_a_full_window(self):
        # The pre-market window exactly as the old scan saw it at 09:57.
        df = ip._trim_window(amd_bars("09:35"), 90, 5)
        assert ip.detect_v_reversal(df, "AMD") is None
        assert ip.detect_inverted_v(df, "AMD") is None

    def test_scan_sends_nothing_for_amd_that_morning(self, monkeypatch):
        for sent, until in (("09:50", "09:30"), ("09:57", "09:35"), ("10:15", "10:00")):
            df = amd_bars(until)
            monkeypatch.setattr(ip.client, "get_intraday_multi_bars", lambda s, **k: {"AMD": df})
            now = datetime(2026, 11, 11, *map(int, sent.split(":")), tzinfo=ET)
            assert ip.scan_intraday_patterns(["AMD"], now=now) == [], sent


def bars(lows_highs_closes, start="10:00", vol=None):
    """Session bars from (low, high, close) triples."""
    hh, mm = map(int, start.split(":"))
    t0 = datetime(2026, 11, 11, hh, mm, tzinfo=ET)
    rows, prev = [], lows_highs_closes[0][2]
    for i, (lo, hi, c) in enumerate(lows_highs_closes):
        rows.append({"open": prev, "high": hi, "low": lo, "close": c,
                     "volume": (vol[i] if vol else (100 if i < len(lows_highs_closes) // 2 else 300))})
        prev = c
    return pd.DataFrame(rows, index=pd.DatetimeIndex([t0 + timedelta(minutes=5 * i) for i in range(len(rows))]))


def v_shape(low_bar=None):
    """100 -> 95 -> 98 with a clean low unless low_bar replaces it."""
    seq = [(99.8, 100.2, 100.0), (99.0, 100.1, 99.2), (98.0, 99.3, 98.1), (96.8, 98.2, 97.0),
           (95.4, 97.1, 95.6), (95.0, 95.8, 95.3), (95.2, 96.4, 96.2), (96.0, 97.3, 97.1),
           (96.9, 98.1, 98.0)]
    if low_bar is not None:
        seq[5] = low_bar
    return bars(seq)


class TestStrayPrints:
    def test_a_real_v_still_fires(self):
        p = ip.detect_v_reversal(v_shape(), "X")
        assert p is not None and p.pattern_type == "v_reversal"

    def test_a_hammer_low_still_counts(self):
        # Long lower wick but the bar closed in the lower half of the move.
        p = ip.detect_v_reversal(v_shape(low_bar=(95.0, 95.9, 96.3)), "X")
        assert p is not None

    def test_a_one_trade_spike_down_does_not_make_a_v(self):
        # Flat around 100, one print at 94, back to 99.9: not a V.
        flat = [(99.7, 100.2, 100.0)] * 4 + [(94.0, 100.1, 99.9)] + [(99.6, 100.3, 100.0)] * 4
        assert ip.detect_v_reversal(bars(flat), "X") is None

    def test_a_one_trade_spike_up_does_not_make_an_inverted_v(self):
        flat = [(99.7, 100.2, 100.0)] * 4 + [(99.9, 106.0, 100.1)] + [(99.6, 100.3, 99.9)] * 4
        assert ip.detect_inverted_v(bars(flat), "X") is None

    def test_a_one_trade_print_cannot_fake_a_breakdown(self):
        # A stray high at the start, then a modest drift: no 3% move without it.
        seq = [(99.8, 104.0, 100.0)] + [(99.5 - i * 0.1, 100.1 - i * 0.1, 99.6 - i * 0.1) for i in range(8)]
        assert ip.detect_sustained_move(bars(seq), "X") is None

    def test_a_real_breakdown_still_fires(self):
        seq = [(99.8, 100.2, 100.0), (99.0, 100.0, 99.1), (98.0, 99.2, 98.1), (97.0, 98.2, 97.1),
               (96.2, 97.2, 96.3), (95.5, 96.4, 95.6), (95.0, 95.8, 95.1), (94.8, 95.3, 94.9),
               (94.6, 95.0, 94.7)]
        p = ip.detect_sustained_move(bars(seq), "X")
        assert p is not None and p.pattern_type == "breakdown"

    def test_neighbour_near_the_low_confirms_it(self):
        # The low bar closed far off its low (98.0, more than half the 5.2 move
        # away), but the bar before it traded down to 95.4: a real low.
        df = v_shape(low_bar=(95.0, 99.0, 98.0))
        assert ip._real_low(df, 5, 5.2) is True
        assert ip.detect_v_reversal(df, "X") is not None

    def test_without_a_close_or_neighbour_near_it_the_low_is_not_real(self):
        df = v_shape(low_bar=(95.0, 99.0, 98.0))
        df.iloc[4, df.columns.get_loc("low")] = 97.0        # neighbours far from 95.0
        df.iloc[6, df.columns.get_loc("low")] = 97.5
        assert ip._real_low(df, 5, 5.2) is False
        assert ip.detect_v_reversal(df, "X") is None

    @pytest.mark.parametrize("move", [0, -1])
    def test_no_move_is_never_a_real_extreme(self, move):
        df = v_shape()
        assert ip._real_low(df, 5, move) is False and ip._real_high(df, 0, move) is False

    def test_edge_bars_are_judged_on_their_one_neighbour(self):
        # First bar: a high of 105 with the close at 100 (5 away of a 5 move).
        df = bars([(99.5, 105.0, 100.0), (99.4, 104.0, 99.6), (99.0, 100.0, 99.1)])
        assert ip._real_high(df, 0, 5.0) is True             # next bar reached 104
        df.iloc[1, df.columns.get_loc("high")] = 100.0
        assert ip._real_high(df, 0, 5.0) is False             # nothing near 105
        last = len(df) - 1
        df.iloc[last, df.columns.get_loc("low")] = 94.0       # last bar: low 94, closed 99.1
        assert ip._real_low(df, last, 5.0) is False


class TestSessionWindow:
    def test_pre_market_and_other_days_are_left_out(self):
        df = amd_bars("10:10")
        other_day = df.copy()
        other_day.index = other_day.index - timedelta(days=1)
        both = pd.concat([other_day, df])
        w = ip.session_window(both, now=datetime(2026, 11, 11, 10, 30, tzinfo=ET))
        assert w.index[0] == datetime(2026, 11, 11, 9, 30, tzinfo=ET) and len(w) == 9
        assert all(t.date().isoformat() == "2026-11-11" for t in w.index)

    def test_keeps_only_the_most_recent_bars(self):
        long = bars([(99.8, 100.2, 100.0)] * 30, start="09:30")
        w = ip.session_window(long, now=datetime(2026, 11, 11, 13, 0, tzinfo=ET))
        assert len(w) == 18 and w.index[-1] == long.index[-1]

    def test_empty_input(self):
        assert ip.session_window(pd.DataFrame(), now=datetime(2026, 11, 11, 11, tzinfo=ET)).empty
