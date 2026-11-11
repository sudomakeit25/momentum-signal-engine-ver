"""Auto-trader history: each paper trade rebuilt from broker orders, how it
ended, profit or loss, and totals. No network."""

import random
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from src.trading import auto_trader as at
from src.trading import trade_history as th

_ids = iter(range(1, 10_000))


def order(coid, side, qty, filled, price=None, *, status="filled", sym="NVDA", ts=1000.0,
          fill_ts=None, legs=None, order_type="market", limit=None, stop=None):
    return {
        "order_id": f"O{next(_ids)}", "client_order_id": coid, "symbol": sym, "side": side,
        "status": status, "qty": float(qty), "filled_qty": float(filled), "ts": ts,
        "fill_ts": fill_ts if fill_ts is not None else ts + 1, "date": "2026-11-11",
        "legs": legs or [], "filled_avg_price": price, "limit_price": limit,
        "stop_price": stop, "order_type": order_type,
    }


def tp(qty, filled, price=None, limit=110.0, side="sell", ts=2000.0, status=None):
    return order("", side, qty, filled, price, ts=ts, order_type="limit", limit=limit,
                 status=status or ("filled" if filled else "canceled"))


def sl(qty, filled, price=None, stop=95.0, side="sell", ts=2000.0, status=None):
    return order("", side, qty, filled, price, ts=ts, order_type="stop", stop=stop,
                 status=status or ("filled" if filled else "canceled"))


ENTRY = "mse-auto-2026-11-11-NVDA-higher_low"


def entry(legs, qty=10, filled=10, price=100.0, coid=ENTRY, side="buy", sym="NVDA", ts=1000.0, **kw):
    return order(coid, side, qty, filled, price, sym=sym, ts=ts, legs=legs, **kw)


def flat(coid_entry, qty, price, n=1, side="sell", sym="NVDA", ts=3000.0):
    suffix = coid_entry[len(at.BOT_PREFIX):]
    return order(f"{at.FLAT_PREFIX}{suffix}-{n}", side, qty, qty, price, sym=sym, ts=ts)


def one(orders, positions=None):
    trades, unfilled = th.build_trades(orders, positions)
    assert len(trades) == 1, trades
    return trades[0]


class TestParse:
    def test_normal_id(self):
        assert th.parse_coid(ENTRY) == ("2026-11-11", "NVDA", "higher_low")

    @pytest.mark.parametrize("bad", ["", None, "manual", "mse-auto-", "mse-auto-garbage",
                                     "mse-auto-20261111-NVDA-x", "other-2026-11-11-NVDA-x"])
    def test_malformed_ids_never_raise(self, bad):
        assert th.parse_coid(bad) == ("", "", "")

    def test_setup_with_underscores_and_missing_setup(self):
        assert th.parse_coid("mse-auto-2026-11-11-AMD-range_breakout")[2] == "range_breakout"
        assert th.parse_coid("mse-auto-2026-11-11-AMD") == ("2026-11-11", "AMD", "")


class TestOneTrade:
    def test_target_hit(self):
        t = one([entry([tp(10, 10, 110.0), sl(10, 0)])])
        assert (t["outcome"], t["exit_reason"]) == ("closed", "target")
        assert t["entry_price"] == 100.0 and t["exit_price"] == 110.0
        assert t["pnl"] == 100.0 and t["r_multiple"] == 2.0
        assert (t["stop"], t["target"], t["setup"], t["symbol"]) == (95.0, 110.0, "higher_low", "NVDA")

    def test_stop_hit(self):
        t = one([entry([tp(10, 0), sl(10, 10, 95.0)])])
        assert (t["exit_reason"], t["pnl"], t["r_multiple"]) == ("stop", -50.0, -1.0)

    def test_stop_with_slippage_is_worse_than_one_r(self):
        t = one([entry([tp(10, 0), sl(10, 10, 94.5)])])
        assert t["pnl"] == -55.0 and t["r_multiple"] == -1.1

    def test_end_of_day_close(self):
        t = one([entry([tp(10, 0), sl(10, 0)]), flat(ENTRY, 10, 102.0)])
        assert (t["exit_reason"], t["pnl"], t["r_multiple"]) == ("end of day close", 20.0, 0.4)

    def test_part_target_then_close(self):
        t = one([entry([tp(10, 4, 110.0), sl(10, 0)]), flat(ENTRY, 6, 101.0)])
        assert t["outcome"] == "closed" and t["exit_qty"] == 10
        assert t["exit_price"] == pytest.approx(104.6) and t["pnl"] == 46.0
        assert t["exit_reasons"] == {"target": 4.0, "end of day close": 6.0}
        assert t["exit_reason"] == "end of day close"            # the larger part

    def test_short_trade(self):
        legs = [tp(10, 10, 90.0, limit=90.0, side="buy"), sl(10, 0, stop=105.0, side="buy")]
        t = one([entry(legs, side="sell")])
        assert t["side"] == "sell" and t["pnl"] == 100.0 and t["r_multiple"] == 2.0

    def test_short_trade_stopped(self):
        legs = [tp(10, 0, limit=90.0, side="buy"), sl(10, 10, 105.0, stop=105.0, side="buy")]
        t = one([entry(legs, side="sell")])
        assert t["pnl"] == -50.0 and t["r_multiple"] == -1.0

    def test_partly_filled_entry_counts_what_filled(self):
        t = one([entry([tp(6, 6, 110.0), sl(6, 0)], qty=10, filled=6, status="canceled")])
        assert t["qty"] == 6 and t["pnl"] == 60.0

    def test_open_trade(self):
        t = one([entry([tp(10, 0, status="new"), sl(10, 0, status="new")])], {"NVDA": 10.0})
        assert t["outcome"] == "open" and t["pnl"] is None and t["open_qty"] == 10

    def test_open_after_part_target(self):
        t = one([entry([tp(10, 4, 110.0, status="partially_filled"), sl(10, 0, status="new")])],
                {"NVDA": 6.0})
        assert t["outcome"] == "open" and t["open_qty"] == 6 and t["pnl"] == 40.0

    def test_sold_by_hand(self):
        t = one([entry([tp(10, 0), sl(10, 0)])], {})
        assert t["outcome"] == "closed outside the bot" and t["pnl"] is None

    def test_short_open_is_judged_by_a_negative_position(self):
        legs = [tp(10, 0, limit=90.0, side="buy", status="new"), sl(10, 0, stop=105.0, side="buy", status="new")]
        assert one([entry(legs, side="sell")], {"NVDA": -10.0})["outcome"] == "open"
        assert one([entry(legs, side="sell")], {"NVDA": 10.0})["outcome"] == "closed outside the bot"

    def test_missing_prices_give_no_result_rather_than_a_wrong_one(self):
        t = one([entry([tp(10, 10, None), sl(10, 0)])])
        assert t["outcome"] == "closed" and t["pnl"] is None and t["r_multiple"] is None
        t = one([entry([tp(10, 10, 110.0), sl(10, 0)], price=None)])
        assert t["pnl"] is None

    def test_no_stop_leg_gives_no_r(self):
        t = one([entry([tp(10, 10, 110.0)])])
        assert t["pnl"] == 100.0 and t["r_multiple"] is None

    def test_leg_without_order_type_is_told_apart_by_its_prices(self):
        a = tp(10, 0)
        b = sl(10, 10, 95.0)
        a["order_type"] = b["order_type"] = ""
        t = one([entry([a, b])])
        assert t["exit_reason"] == "stop" and t["stop"] == 95.0 and t["target"] == 110.0


class TestManyTrades:
    def _book(self):
        e1 = "mse-auto-2026-11-10-AMD-range_breakout"
        e2 = "mse-auto-2026-11-11-NVDA-higher_low"
        e3 = "mse-auto-2026-11-11-TSM-higher_low"
        e4 = "mse-auto-2026-11-11-MU-vwap_reclaim"
        return [
            entry([tp(10, 10, 110.0), sl(10, 0)], coid=e1, sym="AMD", ts=100.0),        # +100, 2R
            entry([tp(10, 0), sl(10, 10, 95.0)], coid=e2, sym="NVDA", ts=200.0),        # -50, -1R
            entry([tp(10, 0), sl(10, 0)], coid=e3, sym="TSM", ts=300.0),
            flat(e3, 10, 103.0, sym="TSM", ts=400.0),                                   # +30, 0.6R
            entry([], coid=e4, sym="MU", filled=0, price=None, status="rejected"),      # never filled
            order("manual-1", "buy", 50, 50, 99.0, sym="NVDA"),                          # by hand
            order(None or "", "sell", 50, 50, 101.0, sym="NVDA"),
        ]

    def test_totals(self):
        trades, unfilled = th.build_trades(self._book())
        s = th.summarize(trades, unfilled)["totals"]
        assert (s["trades"], s["closed"], s["wins"], s["losses"], s["not_filled"]) == (3, 3, 2, 1, 1)
        assert s["pnl"] == 80.0 and s["win_rate"] == pytest.approx(66.7)
        assert s["avg_r"] == pytest.approx(round((2.0 - 1.0 + 0.6) / 3, 2))
        assert s["best"] == {"symbol": "AMD", "date": "2026-11-10", "pnl": 100.0}
        assert s["worst"]["symbol"] == "NVDA"

    def test_by_setup_and_by_day(self):
        trades, _ = th.build_trades(self._book())
        out = th.summarize(trades)
        setups = {g["setup"]: g for g in out["by_setup"]}
        assert setups["higher_low"]["trades"] == 2 and setups["higher_low"]["pnl"] == -20.0
        assert setups["higher_low"]["win_rate"] == 50.0
        assert setups["range_breakout"]["avg_r"] == 2.0
        assert [d["date"] for d in out["by_day"]] == ["2026-11-11", "2026-11-10"]
        assert out["by_day"][0]["pnl"] == -20.0

    def test_hand_orders_are_ignored(self):
        trades, _ = th.build_trades(self._book())
        assert all(t["client_order_id"].startswith(at.BOT_PREFIX) for t in trades)

    def test_newest_first(self):
        trades, _ = th.build_trades(self._book())
        assert [t["symbol"] for t in trades] == ["TSM", "NVDA", "AMD"]

    def test_any_input_order_gives_the_same_answer(self):
        book = self._book()
        expected = th.build_trades(book)
        rnd = random.Random(3)
        for _ in range(5):
            shuffled = book[:]
            rnd.shuffle(shuffled)
            assert th.build_trades(shuffled) == expected
        assert th.build_trades(list(reversed(book))) == expected

    def test_a_close_belongs_only_to_its_own_entry(self):
        e1 = "mse-auto-2026-11-11-NVDA-higher_low"
        e2 = "mse-auto-2026-11-11-NVDA-vwap_reclaim"
        trades, _ = th.build_trades([
            entry([tp(10, 0), sl(10, 0)], coid=e1, ts=100.0),
            entry([tp(10, 0), sl(10, 0)], coid=e2, ts=200.0),
            flat(e2, 10, 104.0),
        ], {})
        by = {t["setup"]: t for t in trades}
        assert by["vwap_reclaim"]["pnl"] == 40.0
        assert by["higher_low"]["outcome"] == "closed outside the bot"

    def test_retried_close_is_counted_once_per_fill(self):
        t = one([entry([tp(10, 0), sl(10, 0)]),
                 order(f"{at.FLAT_PREFIX}2026-11-11-NVDA-higher_low-1", "sell", 10, 0, None, status="canceled"),
                 flat(ENTRY, 10, 101.0, n=2)])
        assert t["exit_qty"] == 10 and t["pnl"] == 10.0

    def test_open_and_outside_trades_stay_out_of_the_totals(self):
        e2 = "mse-auto-2026-11-11-AMD-vwap_reclaim"
        trades, _ = th.build_trades([
            entry([tp(10, 10, 110.0), sl(10, 0)]),
            entry([tp(10, 4, 110.0, status="partially_filled"), sl(10, 0, status="new")], coid=e2, sym="AMD"),
        ], {"AMD": 6.0})
        s = th.summarize(trades)["totals"]
        assert (s["trades"], s["closed"], s["open"], s["pnl"]) == (2, 1, 1, 100.0)

    @pytest.mark.parametrize("orders", [[], [order("manual", "buy", 1, 1, 10.0)]])
    def test_nothing_traded(self, orders):
        trades, unfilled = th.build_trades(orders)
        s = th.summarize(trades, unfilled)
        assert trades == [] and s["totals"]["trades"] == 0
        assert s["totals"]["win_rate"] is None and s["totals"]["avg_r"] is None
        assert s["totals"]["best"] is None and s["by_day"] == [] and s["by_setup"] == []

    def test_malformed_bot_id_is_kept_under_unknown(self):
        t = one([entry([tp(10, 10, 110.0), sl(10, 0)], coid="mse-auto-garbage", sym="XYZ")])
        assert t["symbol"] == "XYZ" and t["setup"] == ""
        assert th.summarize([t])["by_setup"][0]["setup"] == "unknown"


class _Broker:
    def __init__(self, orders=None, positions=None, fail=False):
        self.orders, self.pos, self.fail, self.calls = orders or [], positions or {}, fail, 0

    def account_orders(self, since):
        self.calls += 1
        if self.fail:
            raise RuntimeError("alpaca down")
        return self.orders

    def positions(self):
        return self.pos


class TestHistory:
    @pytest.fixture(autouse=True)
    def clean(self):
        th._cache.clear()

    def test_answer(self):
        r = th.history(30, broker=_Broker([entry([tp(10, 10, 110.0), sl(10, 0)])]))
        assert r["data_ok"] is True and r["days"] == 30 and r["totals"]["pnl"] == 100.0
        assert len(r["trades"]) == 1 and r["since"] <= r["as_of"][:10]

    def test_broker_failure_is_reported_not_raised(self):
        r = th.history(30, broker=_Broker(fail=True))
        assert r["data_ok"] is False and "alpaca" not in r["note"].lower()

    @pytest.mark.parametrize("asked,used", [(0, 1), (-3, 1), (7, 7), (500, 90)])
    def test_days_are_clamped(self, asked, used):
        assert th.history(asked, broker=_Broker())["days"] == used

    def test_default_broker_answer_is_cached_and_failures_are_not(self, monkeypatch):
        b = _Broker(fail=True)
        monkeypatch.setattr(at, "AlpacaPaperBroker", lambda: b)
        assert th.history(30)["data_ok"] is False
        b.fail = False
        assert th.history(30)["data_ok"] is True
        th.history(30)
        assert b.calls == 2

    def test_route(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routes import router
        monkeypatch.setattr(at, "AlpacaPaperBroker",
                            lambda: _Broker([entry([tp(10, 0), sl(10, 10, 95.0)])]))
        app = FastAPI()
        app.include_router(router)
        c = TestClient(app)
        r = c.get("/trading/auto/history?days=7")
        assert r.status_code == 200 and r.json()["totals"]["pnl"] == -50.0
        assert c.get("/trading/auto/history?days=0").status_code == 422
        assert c.get("/trading/auto/history?days=91").status_code == 422


class TestOrderDictPrices:
    def _o(self, **kw):
        t = datetime(2026, 11, 11, 15, tzinfo=timezone.utc)
        base = dict(id="X", client_order_id=ENTRY, symbol="NVDA", side=NS(value="buy"),
                    status=NS(value="filled"), qty="10", filled_qty="10", created_at=t,
                    submitted_at=t, filled_at=t, updated_at=t, legs=None,
                    filled_avg_price="100.25", limit_price=None, stop_price=None,
                    order_type=NS(value="market"))
        base.update(kw)
        return NS(**base)

    def test_prices_are_read_from_alpaca_strings(self):
        d = at._order_dict(self._o(legs=[self._o(id="L", order_type=NS(value="stop"),
                                                 stop_price="95.5", filled_avg_price=None)]))
        assert d["filled_avg_price"] == 100.25 and d["order_type"] == "market"
        assert d["legs"][0]["stop_price"] == 95.5 and d["legs"][0]["filled_avg_price"] is None
        assert d["legs"][0]["order_type"] == "stop"

    @pytest.mark.parametrize("bad", [None, "", "0", "-1", "nan", "inf", "abc"])
    def test_unusable_prices_become_none(self, bad):
        assert at._order_dict(self._o(filled_avg_price=bad))["filled_avg_price"] is None

    def test_objects_without_price_fields_still_work(self):
        o = self._o()
        for name in ("filled_avg_price", "limit_price", "stop_price", "order_type"):
            delattr(o, name)
        d = at._order_dict(o)
        assert d["filled_avg_price"] is None and d["order_type"] == ""
