"""Today's most active stocks added to the intraday movers screen. The screen
had only seen about 90 large companies (watchlist plus the daily scan's top
names); it found 0 qualifying stocks on most cycles."""

import pytest

from src.data import most_actives as ma

REAL_FETCH = ma._fetch          # kept before conftest replaces it for every test


@pytest.fixture
def feed(monkeypatch):
    state = {"calls": 0, "symbols": [], "fail": False}

    def fetch(top):
        state["calls"] += 1
        if state["fail"]:
            raise RuntimeError("alpaca screener down")
        return list(state["symbols"])

    monkeypatch.setattr(ma, "_fetch", fetch)
    return state


T0 = 1_000_000.0


class TestList:
    def test_plain_tickers_only_busiest_first(self, feed):
        feed["symbols"] = ["NVDA", "SOXL", "BRK.B", "ABCDW", "AAPL", "NXXT", "TOOLONG", "AAPL", "lower", "SPY"]
        out = ma.most_active(top=100, now=T0)
        assert out == ["NVDA", "SOXL", "ABCDW", "AAPL", "NXXT", "SPY"]
        assert "BRK.B" not in out and "TOOLONG" not in out and out.count("AAPL") == 1

    def test_top_limits_and_clamps(self, feed):
        feed["symbols"] = [chr(65 + i) * 3 for i in range(20)]
        assert len(ma.most_active(top=5, now=T0)) == 5
        assert len(ma.most_active(top=500, now=T0)) == 20
        assert len(ma.most_active(top=0, now=T0)) == 1

    def test_cached_for_a_few_minutes(self, feed):
        feed["symbols"] = ["NVDA"]
        ma.most_active(now=T0)
        ma.most_active(now=T0 + ma.TTL - 1)
        assert feed["calls"] == 1
        ma.most_active(now=T0 + ma.TTL + 1)
        assert feed["calls"] == 2

    def test_a_failure_uses_the_last_good_list_for_a_while(self, feed):
        feed["symbols"] = ["NVDA", "AMD"]
        ma.most_active(now=T0)
        feed["fail"] = True
        assert ma.most_active(now=T0 + ma.TTL + 1) == ["NVDA", "AMD"]
        assert ma.most_active(now=T0 + ma.STALE_OK + 120) == []

    def test_a_failure_with_nothing_cached_gives_an_empty_list(self, feed):
        feed["fail"] = True
        assert ma.most_active(now=T0) == []

    def test_a_failing_endpoint_is_not_hammered(self, feed):
        feed["fail"] = True
        ma.most_active(now=T0)
        ma.most_active(now=T0 + 10)
        ma.most_active(now=T0 + 30)
        assert feed["calls"] == 1
        ma.most_active(now=T0 + 61)
        assert feed["calls"] == 2

    def test_ranked_by_trades_not_share_volume(self, monkeypatch):
        sent = {}

        class Client:
            def __init__(self, *a):
                pass

            def get_most_actives(self, req):
                sent["by"] = getattr(req.by, "value", req.by)
                sent["top"] = req.top
                return type("R", (), {"most_actives": [type("A", (), {"symbol": "NVDA"})()]})()

        import alpaca.data.historical.screener as scr
        monkeypatch.setattr(scr, "ScreenerClient", Client)
        assert REAL_FETCH(100) == ["NVDA"]
        assert sent == {"by": "trades", "top": 100}


class TestScreen:
    @pytest.fixture
    def capture(self, monkeypatch):
        from src.scanner import intraday_movers as m
        asked = {}

        def bars(universe, **kw):
            asked["universe"] = list(universe)
            return {}

        monkeypatch.setattr(m.client, "get_multi_bars", bars)
        monkeypatch.setattr(m.client, "get_intraday_multi_bars", lambda u, **kw: {})
        return m, asked

    def test_most_active_stocks_join_the_universe(self, capture, feed, monkeypatch):
        m, asked = capture
        monkeypatch.setattr(m.settings, "intraday_include_most_active", True)
        feed["symbols"] = ["SOFI", "NVDA", "HOOD"]
        m.scan_intraday(symbols=["NVDA", "AMD"])
        assert asked["universe"] == ["NVDA", "AMD", "SOFI", "HOOD"]   # given first, no repeats

    def test_can_be_switched_off(self, capture, feed, monkeypatch):
        m, asked = capture
        monkeypatch.setattr(m.settings, "intraday_include_most_active", False)
        feed["symbols"] = ["SOFI"]
        m.scan_intraday(symbols=["NVDA"])
        assert asked["universe"] == ["NVDA"] and feed["calls"] == 0

    def test_explicit_argument_wins_over_the_setting(self, capture, feed, monkeypatch):
        m, asked = capture
        monkeypatch.setattr(m.settings, "intraday_include_most_active", True)
        feed["symbols"] = ["SOFI"]
        m.scan_intraday(symbols=["NVDA"], include_most_active=False)
        assert asked["universe"] == ["NVDA"]

    def test_screen_still_runs_when_the_list_fails(self, capture, feed, monkeypatch):
        m, asked = capture
        monkeypatch.setattr(m.settings, "intraday_include_most_active", True)
        feed["fail"] = True
        assert m.scan_intraday(symbols=["NVDA"]) == []
        assert asked["universe"] == ["NVDA"]

    def test_settings_are_declared(self):
        from config.settings import Settings
        f = Settings.model_fields
        assert f["intraday_include_most_active"].default is True
        assert f["intraday_most_active_top"].default == 100
