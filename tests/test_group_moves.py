"""Crypto miners moving together at the 10:30 checkpoint, logged to the
scorecard only. No network."""

import inspect
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.scanner import group_moves as gm

ET = ZoneInfo("America/New_York")
DAY = (2026, 11, 18)
NOW = datetime(*DAY, 10, 45, tzinfo=ET)
GROUP = {"crypto_miners": ["RIOT", "MARA", "CLSK", "HUT", "IREN"]}
PREV = {"RIOT": 10.0, "MARA": 20.0, "CLSK": 6.0, "HUT": 50.0, "IREN": 30.0}


def bars(prev, move_pct, until=(10, 25), day=DAY):
    """Session bars from 09:30 to `until` (bar start), drifting to `move_pct`
    from the previous close by the last bar."""
    t, idx = datetime(*day, 9, 30, tzinfo=ET), []
    end = datetime(*day, *until, tzinfo=ET)
    while t <= end:
        idx.append(t)
        t += timedelta(minutes=5)
    n = len(idx)
    closes = [prev * (1 + move_pct / 100 * (i + 1) / n) for i in range(n)]
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes,
                         "volume": 1000}, index=pd.DatetimeIndex(idx))


def market(moves, until=(10, 25)):
    return {s: bars(PREV[s], m, until) for s, m in moves.items()}


class TestDetect:
    def test_three_members_together_are_logged(self):
        out = gm.detect(market({"RIOT": 4.0, "MARA": 3.5, "CLSK": 6.2, "HUT": 1.0, "IREN": -0.5}),
                        PREV, now=NOW, group_map=GROUP)
        assert [o["symbol"] for o in out] == ["CLSK", "RIOT", "MARA"]          # biggest first
        assert {o["kind"] for o in out} == {"crypto_miners_move"} and {o["direction"] for o in out} == {"up"}
        clsk = out[0]
        assert clsk["price"] == pytest.approx(6.0 * 1.062, rel=1e-6) and clsk["move_pct"] == pytest.approx(6.2)

    def test_two_are_not_a_group_move(self):
        assert gm.detect(market({"RIOT": 4.0, "MARA": 3.5, "CLSK": 2.0, "HUT": 1.0, "IREN": 0.0}),
                         PREV, now=NOW, group_map=GROUP) == []

    def test_down_moves(self):
        out = gm.detect(market({"RIOT": -4.0, "MARA": -3.0, "CLSK": -7.0, "HUT": 5.0, "IREN": -1.0}),
                        PREV, now=NOW, group_map=GROUP)
        assert [o["symbol"] for o in out] == ["CLSK", "RIOT", "MARA"] and {o["direction"] for o in out} == {"down"}

    def test_the_threshold_is_inclusive(self):
        out = gm.detect(market({"RIOT": 3.0, "MARA": 3.0, "CLSK": 3.0, "HUT": 2.99, "IREN": 0.0}),
                        PREV, now=NOW, group_map=GROUP)
        assert sorted(o["symbol"] for o in out) == ["CLSK", "MARA", "RIOT"]

    @pytest.mark.parametrize("until,expected", [((10, 20), 0), ((10, 25), 3), ((10, 50), 3), ((10, 55), 0)])
    def test_only_at_the_10_30_checkpoint(self, until, expected):
        out = gm.detect(market({"RIOT": 4.0, "MARA": 4.0, "CLSK": 4.0, "HUT": 0.0, "IREN": 0.0}, until=until),
                        PREV, now=NOW, group_map=GROUP)
        assert len(out) == expected

    def test_members_without_a_previous_close_or_bars_are_skipped(self):
        moves = market({"RIOT": 4.0, "MARA": 4.0, "CLSK": 4.0})
        assert gm.detect(moves, {"RIOT": 10.0, "MARA": 20.0, "CLSK": 0.0}, now=NOW, group_map=GROUP) == []
        assert gm.detect({"RIOT": moves["RIOT"], "MARA": pd.DataFrame(), "CLSK": None}, PREV,
                         now=NOW, group_map=GROUP) == []

    def test_yesterdays_bars_do_not_count(self):
        old = {s: bars(PREV[s], 5.0, day=(2026, 11, 17)) for s in ("RIOT", "MARA", "CLSK")}
        assert gm.detect(old, PREV, now=NOW, group_map=GROUP) == []

    def test_input_order_does_not_matter(self):
        moves = market({"RIOT": 4.0, "MARA": 3.5, "CLSK": 6.2, "HUT": 1.0, "IREN": -0.5})
        flipped = dict(reversed(list(moves.items())))
        assert gm.detect(moves, PREV, now=NOW, group_map=GROUP) == gm.detect(flipped, PREV, now=NOW, group_map=GROUP)

    def test_empty(self):
        assert gm.detect({}, {}, now=NOW, group_map=GROUP) == []

    def test_default_group_is_the_ten_miners(self):
        assert set(gm.groups()["crypto_miners"]) >= {"RIOT", "MARA", "CLSK", "HUT", "IREN"}


class TestScan:
    @pytest.fixture
    def feed(self, monkeypatch):
        calls = []
        moves = market({"RIOT": 4.0, "MARA": 3.5, "CLSK": 6.2, "HUT": 1.0, "IREN": -0.5})

        def intraday(symbols, **kw):
            calls.append("intraday")
            return moves

        def daily(symbols, days=10, **kw):
            calls.append("daily")
            out = {}
            for s in symbols:
                if s in PREV:
                    out[s] = pd.DataFrame({"close": [PREV[s] * 0.9, PREV[s], PREV[s] * 1.05]},
                                          index=pd.DatetimeIndex([datetime(2026, 11, 16, 5, tzinfo=ET),
                                                                  datetime(2026, 11, 17, 5, tzinfo=ET),
                                                                  datetime(2026, 11, 18, 5, tzinfo=ET)]))
            return out

        monkeypatch.setattr(gm.client, "get_intraday_multi_bars", intraday)
        monkeypatch.setattr(gm.client, "get_multi_bars", daily)
        monkeypatch.setattr(gm, "groups", lambda: GROUP)
        return calls

    def test_uses_the_close_before_today(self, feed):
        out = gm.scan(now=NOW)
        assert [o["symbol"] for o in out] == ["CLSK", "RIOT", "MARA"]
        assert out[0]["move_pct"] == pytest.approx(6.2)              # from 6.0, not today's 6.3

    @pytest.mark.parametrize("when", [datetime(*DAY, 10, 29, tzinfo=ET), datetime(*DAY, 11, 30, tzinfo=ET),
                                      datetime(2026, 11, 21, 10, 45, tzinfo=ET)])          # Saturday
    def test_outside_the_window_it_fetches_nothing(self, feed, when):
        assert gm.scan(now=when) == [] and feed == []

    def test_a_data_failure_is_not_raised(self, feed, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("alpaca down")

        monkeypatch.setattr(gm.client, "get_intraday_multi_bars", boom)
        assert gm.scan(now=NOW) == []


class TestScorecard:
    def test_records_are_accepted_by_the_scorecard(self, monkeypatch):
        from src.scanner import scorecard as sc
        monkeypatch.setattr(sc, "_get_redis", lambda: None)
        monkeypatch.setattr(sc, "_mem", None)
        alerts = gm.detect(market({"RIOT": 4.0, "MARA": 3.5, "CLSK": 6.2}), PREV, now=NOW, group_map=GROUP)
        assert sc.log_alerts(alerts, now=NOW) == 3
        assert sc.log_alerts(alerts, now=NOW) == 0                         # once per stock per day
        assert {r["kind"] for r in sc._load()} == {"crypto_miners_move"}

    def test_wired_into_the_intraday_loop_without_alerts(self):
        from src import main
        src = inspect.getsource(main._intraday_scan_loop)
        block = src[src.index("group_moves.scan"):src.index("Group move check failed")]
        assert "_score(scorecard, moved)" in block
        assert "dispatch" not in block and "telegram" not in block.lower()
