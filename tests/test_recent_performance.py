"""Recent performance: the day-by-day table, peer comparison over the same
window, and big-day headlines. No network."""

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from src.scanner import recent_performance as rp


def _days(n, end=date(2026, 11, 10)):
    """The last n weekdays ending at `end`, oldest first."""
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def bars(closes, volumes=None, end=date(2026, 11, 10), tz=True):
    days = _days(len(closes), end)
    idx = pd.DatetimeIndex([datetime(d.year, d.month, d.day, 5, tzinfo=timezone.utc) for d in days])
    if not tz:
        idx = pd.DatetimeIndex([datetime(d.year, d.month, d.day) for d in days])
    vols = volumes or [1_000_000] * len(closes)
    return pd.DataFrame({
        "open": closes, "high": [c * 1.01 for c in closes], "low": [c * 0.99 for c in closes],
        "close": closes, "volume": vols,
    }, index=idx)


def flat_then(moves, base=100.0, lead=70, wiggle=0.5):
    """`lead` quiet sessions (alternating +/- wiggle %), then the given daily % moves."""
    closes = [base]
    for i in range(lead - 1):
        closes.append(closes[-1] * (1 + (wiggle if i % 2 else -wiggle) / 100))
    for m in moves:
        closes.append(closes[-1] * (1 + m / 100))
    return closes


class TestSummarize:
    def test_totals_match_the_closes(self):
        closes = flat_then([+5, -4, -6, -7, +14, -16, -16, +8, +12, -5])
        s = rp.summarize(bars(closes), 10)
        assert s["sessions"] == 10 and len(s["rows"]) == 10
        assert s["base_close"] == round(closes[-11], 2)
        assert s["last_close"] == round(closes[-1], 2)
        assert s["change_pct"] == pytest.approx((closes[-1] / closes[-11] - 1) * 100, abs=0.01)
        assert s["rows"][-1]["cum_pct"] == s["change_pct"]
        assert [r["change_pct"] for r in s["rows"]] == pytest.approx(
            [5, -4, -6, -7, 14, -16, -16, 8, 12, -5], abs=0.01)
        assert s["up_days"] == 4 and s["down_days"] == 6
        assert s["best_day"]["change_pct"] == pytest.approx(14, abs=0.01)
        assert s["worst_day"]["change_pct"] == pytest.approx(-16, abs=0.01)
        assert s["avg_abs_move"] == pytest.approx(9.3, abs=0.01)

    def test_dates_are_the_last_sessions_in_order(self):
        s = rp.summarize(bars(flat_then([1] * 10)), 10)
        dates = [r["date"] for r in s["rows"]]
        assert dates == sorted(dates) and dates[-1] == "2026-11-10" == s["last_date"]
        assert s["base_date"] < dates[0]
        assert all(date.fromisoformat(d).weekday() < 5 for d in dates)

    def test_reversed_and_shuffled_input_give_the_same_answer(self):
        df = bars(flat_then([+5, -4, -6, -7, +14, -16, -16, +8, +12, -5]))
        expected = rp.summarize(df, 10)
        assert rp.summarize(df.iloc[::-1], 10) == expected
        assert rp.summarize(df.sample(frac=1, random_state=7), 10) == expected

    def test_duplicate_dates_are_collapsed(self):
        df = bars(flat_then([1, 2, 3]))
        doubled = pd.concat([df, df.iloc[-2:]])
        assert rp.summarize(doubled, 3) == rp.summarize(df, 3)

    def test_timezone_naive_index_gives_the_same_dates(self):
        closes = flat_then([1, 2, 3])
        a, b = rp.summarize(bars(closes), 3), rp.summarize(bars(closes, tz=False), 3)
        assert [r["date"] for r in a["rows"]] == [r["date"] for r in b["rows"]]

    @pytest.mark.parametrize("df", [None, pd.DataFrame(), pd.DataFrame({"volume": [1, 2]})])
    def test_no_usable_bars_gives_none(self, df):
        assert rp.summarize(df, 10) is None

    def test_too_few_bars_gives_none(self):
        assert rp.summarize(bars([10.0, 11.0]), 10) is None

    def test_short_history_uses_what_exists_and_says_so(self):
        s = rp.summarize(bars([10.0, 11.0, 12.1, 12.1]), 10)
        assert s["sessions"] == 3 and s["sessions_requested"] == 10
        assert s["base_close"] == 10.0 and s["change_pct"] == pytest.approx(21.0, abs=0.01)
        assert s["typical_move"] is None and not any(r["big"] for r in s["rows"])

    @pytest.mark.parametrize("asked,used", [(0, 2), (-5, 2), (1, 2), (10, 10), (500, 30)])
    def test_session_count_is_clamped(self, asked, used):
        assert rp.summarize(bars(flat_then([1] * 40)), asked)["sessions"] == used

    def test_bad_rows_are_dropped_not_fatal(self):
        df = bars(flat_then([1, 2, 3]))
        df.iloc[-2, df.columns.get_loc("close")] = float("nan")
        df.iloc[-5, df.columns.get_loc("close")] = 0.0
        s = rp.summarize(df, 3)
        assert s is not None and all(r["close"] > 0 for r in s["rows"])

    def test_volume_is_compared_with_the_prior_twenty_sessions(self):
        closes = flat_then([1, 1])
        vols = [1_000_000] * (len(closes) - 1) + [3_000_000]
        s = rp.summarize(bars(closes, vols), 2)
        assert s["rows"][-1]["rvol"] == 3.0 and s["rows"][-2]["rvol"] == 1.0

    def test_missing_or_zero_volume_gives_no_ratio(self):
        closes = flat_then([1, 1])
        s = rp.summarize(bars(closes, [0] * len(closes)), 2)
        assert all(r["rvol"] is None for r in s["rows"])
        df = bars(closes).drop(columns=["volume"])
        s = rp.summarize(df, 2)
        assert all(r["rvol"] is None and r["volume"] is None for r in s["rows"])

    def test_range_position(self):
        s = rp.summarize(bars(flat_then([-10, -10, +5])), 3)
        assert 0 < s["range_pos"] < 50
        assert s["low_date"] <= s["last_date"] and s["high"] > s["low"]

    def test_flat_prices_do_not_divide_by_zero(self):
        df = bars([50.0] * 30)
        df["high"] = df["low"] = df["close"]
        s = rp.summarize(df, 5)
        assert s["change_pct"] == 0 and s["range_pos"] is None
        assert s["up_days"] == 0 and s["down_days"] == 0 and not any(r["big"] for r in s["rows"])


class TestBigDays:
    def test_flags_moves_of_twice_a_normal_day(self):
        # A normal day is 0.5%; 3% and -4% are big, 0.6% is not.
        s = rp.summarize(bars(flat_then([0.6, 3, -4, 0.4])), 4)
        assert [r["big"] for r in s["rows"]] == [False, True, True, False]
        assert s["typical_move"] == pytest.approx(0.5, abs=0.01)

    def test_at_most_five_and_the_largest_win(self):
        s = rp.summarize(bars(flat_then([5, -9, 6, -7, 8, -3, 4])), 7)
        flagged = [r["change_pct"] for r in s["rows"] if r["big"]]
        assert len(flagged) == 5
        assert sorted(abs(x) for x in flagged) == pytest.approx([5, 6, 7, 8, 9], abs=0.01)

    def test_a_volatile_stock_needs_a_bigger_move(self):
        # A normal day is 5%, so a 6% day is ordinary for this stock.
        s = rp.summarize(bars(flat_then([6, -6], wiggle=5)), 2)
        assert not any(r["big"] for r in s["rows"])

    def test_normal_day_is_measured_before_the_window_only(self):
        # Ten wild days inside the window must not raise their own bar.
        s = rp.summarize(bars(flat_then([10, -10] * 5)), 10)
        assert s["typical_move"] == pytest.approx(0.5, abs=0.01)
        assert sum(r["big"] for r in s["rows"]) == 5


class TestChangeBetween:
    def test_same_window_as_the_main_symbol(self):
        closes = flat_then([1] * 10)
        df = bars(closes)
        days = _days(len(closes))
        assert rp.change_between(df, days[-11], days[-1]) == pytest.approx(
            (closes[-1] / closes[-11] - 1) * 100, abs=0.01)

    def test_a_missing_session_uses_the_close_before_it(self):
        closes = flat_then([1] * 10)
        df = bars(closes)
        days = _days(len(closes))
        gap = df.drop(df.index[-11])               # peer did not trade on the base date
        assert rp.change_between(gap, days[-11], days[-1]) == pytest.approx(
            (closes[-1] / closes[-12] - 1) * 100, abs=0.01)

    def test_stale_peer_is_left_out(self):
        df = bars(flat_then([1] * 10), end=date(2026, 9, 30))
        assert rp.change_between(df, date(2026, 10, 27), date(2026, 11, 10)) is None

    def test_reversed_dates_and_empty_input(self):
        df = bars(flat_then([1] * 10))
        assert rp.change_between(df, date(2026, 11, 10), date(2026, 10, 27)) is None
        assert rp.change_between(None, date(2026, 10, 27), date(2026, 11, 10)) is None
        assert rp.change_between(pd.DataFrame(), date(2026, 10, 27), date(2026, 11, 10)) is None

    def test_window_before_the_data_starts(self):
        df = bars([10.0, 11.0, 12.0])
        assert rp.change_between(df, date(2020, 1, 2), date(2020, 1, 10)) is None


class TestPeers:
    def test_narrow_group_wins(self):
        group, peers = rp.peers_for("CLSK")
        assert group == "crypto_miners" and "CLSK" not in peers
        assert peers[:2] == ["RIOT", "MARA"] and len(peers) == 4

    def test_unknown_symbol_has_no_peers(self):
        assert rp.peers_for("ZZZZZ") == (None, [])

    def test_survives_the_sector_list_failing(self, monkeypatch):
        from src.scanner import spike_reversal as sr

        def boom():
            raise RuntimeError("no sectors")

        monkeypatch.setattr(sr, "peer_groups", boom)
        assert rp.peers_for("CLSK")[0] == "crypto_miners"

    @pytest.mark.parametrize("raw,expected", [
        ("riot, mara", ["RIOT", "MARA"]),
        ("RIOT;MARA RIOT", ["RIOT", "MARA"]),
        ("CLSK,RIOT", ["RIOT"]),                       # never itself
        ("BRK-B, ../etc, DROP TABLE, A1, TOOLONG", ["DROP", "TABLE"]),
        ("", []), (None, []), (",,,", []),
    ])
    def test_caller_peers_are_cleaned(self, raw, expected):
        assert rp.parse_peers(raw, "CLSK") == expected

    def test_caller_peers_are_capped(self):
        assert len(rp.parse_peers("A,B,C,D,E,F,G,H,I,J", "CLSK")) == rp.MAX_PEERS


class TestInProgress:
    ET = rp.ET

    def test_today_before_the_close_is_in_progress(self):
        now = datetime(2026, 11, 11, 11, 0, tzinfo=self.ET)
        assert rp._in_progress(date(2026, 11, 11), now) is True

    def test_today_after_the_close_is_final(self):
        now = datetime(2026, 11, 11, 16, 15, tzinfo=self.ET)
        assert rp._in_progress(date(2026, 11, 11), now) is False

    def test_an_earlier_bar_is_final(self):
        now = datetime(2026, 11, 11, 11, 0, tzinfo=self.ET)
        assert rp._in_progress(date(2026, 11, 10), now) is False

    def test_now_in_another_zone_is_converted(self):
        now = datetime(2026, 11, 11, 16, 0, tzinfo=timezone.utc)   # 11:00 New York
        assert rp._in_progress(date(2026, 11, 11), now) is True


class TestFullAnswer:
    @pytest.fixture(autouse=True)
    def wire(self, monkeypatch):
        rp._cache.clear()
        self.sym = flat_then([+5, -4, -6, -7, +14, -16, -16, +8, +12, -5])
        self.data = {
            "CLSK": bars(self.sym),
            "RIOT": bars(flat_then([3] * 10)),
            "MARA": bars(flat_then([0.3] * 10)),
            "SPY": bars(flat_then([-0.2] * 10)),
        }
        self.asked = []
        from src.data import client, news

        def fake_bars(symbols, days=200, **kw):
            self.asked.append(list(symbols))
            return {s: self.data[s] for s in symbols if s in self.data}

        self.news_calls = []

        def fake_news(symbol, start, end, limit=3):
            self.news_calls.append((symbol, start, end))
            return [{"headline": f"{symbol} news", "source": "x", "time": end.isoformat(),
                     "url": "https://x/y", "specific": True}]

        monkeypatch.setattr(client, "get_multi_bars", fake_bars)
        monkeypatch.setattr(news, "headlines_between", fake_news)

    def test_table_peers_and_market(self):
        r = rp.recent_performance("clsk", 10)
        assert r["data_ok"] is True and r["symbol"] == "CLSK" and len(r["rows"]) == 10
        assert r["peer_group"] == "crypto_miners"
        got = {c["symbol"]: c for c in r["compared"]}
        assert set(got) == {"RIOT", "MARA", "SPY"}       # peers with no data are left out
        assert got["SPY"]["is_market"] is True and got["RIOT"]["is_market"] is False
        assert got["RIOT"]["change_pct"] == pytest.approx((1.03 ** 10 - 1) * 100, abs=0.01)
        assert got["SPY"]["change_pct"] < 0

    def test_headlines_cover_previous_close_to_that_days_close(self):
        r = rp.recent_performance("CLSK", 10)
        assert len(r["big_days"]) == 5
        assert sorted(abs(round(e["change_pct"])) for e in r["big_days"]) == [8, 12, 14, 16, 16]
        rows = r["rows"]
        for symbol, start, end in self.news_calls:
            assert symbol == "CLSK" and start < end
            day = end.date().isoformat()
            i = next(k for k, row in enumerate(rows) if row["date"] == day)
            assert start.date().isoformat() == rows[i - 1]["date"]
            assert (start.hour, end.hour) == (16, 16) and start.tzinfo is not None
        assert all(e["headlines"][0]["headline"] == "CLSK news" for e in r["big_days"])

    def test_big_day_on_the_first_row_starts_from_the_base_date(self, monkeypatch):
        self.data["CLSK"] = bars(flat_then([+15, 0.1, 0.1]))
        r = rp.recent_performance("CLSK", 3)
        assert r["big_days"][0]["date"] == r["rows"][0]["date"]
        assert self.news_calls[0][1].date().isoformat() == r["base_date"]

    def test_news_failure_keeps_the_table(self, monkeypatch):
        from src.data import news

        def boom(*a, **k):
            raise RuntimeError("feed down")

        monkeypatch.setattr(news, "headlines_between", boom)
        r = rp.recent_performance("CLSK", 10)
        assert r["data_ok"] is True and len(r["rows"]) == 10
        assert all(e["headlines"] is None for e in r["big_days"])

    def test_custom_peers_replace_the_group(self):
        r = rp.recent_performance("CLSK", 10, ["MARA"])
        assert r["peer_group"] == "custom"
        assert [c["symbol"] for c in r["compared"]] == ["MARA", "SPY"]

    def test_market_is_not_compared_with_itself(self):
        r = rp.recent_performance("SPY", 5)
        assert all(c["symbol"] != "SPY" for c in r["compared"])

    def test_symbol_without_bars(self):
        r = rp.recent_performance("ZZZZ", 10)
        assert r["data_ok"] is False and "ZZZZ" in r["note"]

    @pytest.mark.parametrize("bad", ["", "BRK-B", "BTC/USD", "toolongsym", "A1", "../x"])
    def test_malformed_symbol_is_refused_without_a_request(self, bad):
        r = rp.recent_performance(bad, 10)
        assert r["data_ok"] is False and self.asked == []

    def test_bar_failure_is_reported_not_raised(self, monkeypatch):
        from src.data import client

        def boom(*a, **k):
            raise RuntimeError("alpaca down")

        monkeypatch.setattr(client, "get_multi_bars", boom)
        r = rp.recent_performance("CLSK", 10)
        assert r["data_ok"] is False and "alpaca" not in r["note"].lower()

    def test_failed_answer_is_not_cached(self, monkeypatch):
        from src.data import client
        good = client.get_multi_bars

        def boom(*a, **k):
            raise RuntimeError("down")

        monkeypatch.setattr(client, "get_multi_bars", boom)
        assert rp.recent_performance("CLSK", 10)["data_ok"] is False
        monkeypatch.setattr(client, "get_multi_bars", good)
        assert rp.recent_performance("CLSK", 10)["data_ok"] is True

    def test_good_answer_is_cached(self):
        rp.recent_performance("CLSK", 10)
        rp.recent_performance("CLSK", 10)
        assert len(self.asked) == 1
        rp.recent_performance("CLSK", 5)             # another window is another request
        assert len(self.asked) == 2

    def test_cache_is_bounded(self, monkeypatch):
        # Found in review: the route is public and every new symbol, window
        # or peer list added an entry that was never evicted.
        monkeypatch.setattr(rp, "_CACHE_MAX", 3)
        for n in range(2, 9):
            rp.recent_performance("CLSK", n)
        assert len(rp._cache) == 3
        assert {k[1] for k in rp._cache} == {6, 7, 8}  # the newest survive

    def test_route(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routes import router
        app = FastAPI()
        app.include_router(router)
        c = TestClient(app)
        r = c.get("/recent-performance/clsk?sessions=5&peers=mara,brk-b")
        assert r.status_code == 200
        body = r.json()
        assert body["symbol"] == "CLSK" and body["sessions"] == 5
        assert [x["symbol"] for x in body["compared"]] == ["MARA", "SPY"]
        assert c.get("/recent-performance/CLSK?sessions=0").status_code == 422
        assert c.get("/recent-performance/CLSK?sessions=31").status_code == 422


class TestHeadlinesBetween:
    @pytest.fixture(autouse=True)
    def clean(self):
        from src.data import news
        news._range_cache.clear()

    def _item(self, headline, symbols, hour=10):
        from types import SimpleNamespace as NS
        return NS(headline=headline, symbols=symbols, source="benzinga", url="https://x/y",
                  created_at=datetime(2026, 11, 4, hour, tzinfo=timezone.utc))

    def _window(self):
        return (datetime(2026, 11, 3, 21, tzinfo=timezone.utc), datetime(2026, 11, 4, 21, tzinfo=timezone.utc))

    def test_specific_first_then_newest_and_only_this_symbol(self, monkeypatch):
        from src.data import news
        monkeypatch.setattr(news, "_fetch_range", lambda s, a, b: [
            self._item("Market wrap", ["CLSK", "A", "B", "C", "D"], hour=15),
            self._item("CleanSpark reports results", ["CLSK"], hour=9),
            self._item("CleanSpark prices offering", ["CLSK"], hour=12),
            self._item("Someone else", ["RIOT"], hour=13),
            self._item("", ["CLSK"], hour=14),
        ])
        out = news.headlines_between("clsk", *self._window())
        assert [h["headline"] for h in out] == [
            "CleanSpark prices offering", "CleanSpark reports results", "Market wrap"]

    def test_failure_is_none_and_not_cached(self, monkeypatch):
        from src.data import news

        def boom(*a):
            raise RuntimeError("down")

        monkeypatch.setattr(news, "_fetch_range", boom)
        assert news.headlines_between("CLSK", *self._window()) is None
        monkeypatch.setattr(news, "_fetch_range", lambda s, a, b: [self._item("Back", ["CLSK"])])
        assert news.headlines_between("CLSK", *self._window())[0]["headline"] == "Back"

    def test_no_news_is_an_empty_list_and_cached(self, monkeypatch):
        from src.data import news
        calls = []
        monkeypatch.setattr(news, "_fetch_range", lambda s, a, b: calls.append(s) or [])
        assert news.headlines_between("CLSK", *self._window()) == []
        assert news.headlines_between("CLSK", *self._window()) == []
        assert len(calls) == 1

    def test_reversed_window_and_crypto_pair_ask_nothing(self, monkeypatch):
        from src.data import news
        calls = []
        monkeypatch.setattr(news, "_fetch_range", lambda s, a, b: calls.append(s) or [])
        start, end = self._window()
        assert news.headlines_between("CLSK", end, start) == []
        assert news.headlines_between("BTC/USD", start, end) == []
        assert calls == []

    def test_limit(self, monkeypatch):
        from src.data import news
        monkeypatch.setattr(news, "_fetch_range", lambda s, a, b: [
            self._item(f"h{i}", ["CLSK"], hour=i) for i in range(1, 9)])
        assert len(news.headlines_between("CLSK", *self._window(), limit=2)) == 2

    def test_cache_is_bounded(self, monkeypatch):
        from src.data import news
        monkeypatch.setattr(news, "_RANGE_CACHE_MAX", 4)
        monkeypatch.setattr(news, "_fetch_range", lambda s, a, b: [])
        start, end = self._window()
        for sym in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"):
            news.headlines_between(sym, start, end)
        assert len(news._range_cache) == 4
        assert {k[0] for k in news._range_cache} == {"CCC", "DDD", "EEE", "FFF"}

    def test_a_window_still_open_is_refreshed_sooner(self, monkeypatch):
        # Today's big day keeps gaining headlines until the close.
        from src.data import news
        calls = []
        monkeypatch.setattr(news, "_fetch_range", lambda s, a, b: calls.append(s) or [])
        clock = [1_000_000.0]
        monkeypatch.setattr(news.time, "time", lambda: clock[0])
        now = datetime.now(timezone.utc)
        open_window = (now - timedelta(hours=20), now + timedelta(hours=4))
        closed_window = self._window()
        news.headlines_between("CLSK", *open_window)
        news.headlines_between("CLSK", *closed_window)
        clock[0] += 10 * 60                          # ten minutes later
        news.headlines_between("CLSK", *open_window)
        news.headlines_between("CLSK", *closed_window)
        assert len(calls) == 3                       # open refetched, closed still cached
