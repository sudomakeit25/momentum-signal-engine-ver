"""Tests for the paper auto-trader (src/trading/auto_trader.py).

A fake broker keeps an order history the way Alpaca does (entry orders with
bracket legs, closing orders, client order ids), so ownership and caps are
exercised the way production derives them. Nothing reaches Alpaca. The
state store is the in-memory fallback unless a test installs FakeRedis.
"""

from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import pytest

from src.data.models import IntradayResult, SetupType, Signal, SignalAction
from src.trading import auto_trader as at

ET = ZoneInfo("America/New_York")
MON_11 = datetime(2026, 11, 9, 11, 0, tzinfo=ET)       # Monday, mid-session
MON_1546 = datetime(2026, 11, 9, 15, 46, tzinfo=ET)    # inside the flatten window
MON_1601 = datetime(2026, 11, 9, 16, 1, tzinfo=ET)
TUE_10 = datetime(2026, 11, 10, 10, 0, tzinfo=ET)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(at, "_get_redis", lambda: None)
    monkeypatch.setattr(at.time, "sleep", lambda s: None)
    at._MEM.clear()
    at._UNSYNCED.clear()
    at._last_stale_check = float("-inf")
    yield
    at._MEM.clear()
    at._UNSYNCED.clear()


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.fail_get = False
        self.fail_set = False

    def get(self, key):
        if self.fail_get:
            raise TimeoutError("upstash timeout")
        return self.data.get(key)

    def set(self, key, value):
        if self.fail_set:
            raise TimeoutError("upstash timeout")
        self.data[key] = value


class FakeBroker:
    """Order-history fake. `today` is the date stamped on new orders."""

    def __init__(self, today="2026-11-09", paper=True, equity=100_000.0,
                 last_equity=100_000.0, buying_power=200_000.0, positions=None,
                 quotes=None, is_open=True, minutes_to_close=300.0):
        self.today = today
        self.paper = paper
        self._account = {"equity": equity, "last_equity": last_equity,
                         "buying_power": buying_power}
        self._positions = dict(positions or {})
        self._quotes = dict(quotes or {})
        self.is_open = is_open
        self.minutes_to_close = minutes_to_close
        self.orders = []          # the bot's orders (entries with legs, closes)
        self.user_orders = {}     # symbol -> [open order ids not placed by the bot]
        self.reject = set()
        self.timeout_after_accept = set()
        self.fail = set()         # method names that raise
        self.cancel_lag = False   # cancels accepted but not yet effective
        self.submitted = []
        self.market_orders = []
        self.cancelled = []
        self.calls = 0
        self._n = 0
        self._ts = 1000.0
        self.on_cancel = None     # hook run inside cancel_order (race tests)

    def _hit(self, name):
        self.calls += 1
        if name in self.fail:
            raise RuntimeError(f"{name} unavailable")

    def _id(self, tag):
        self._n += 1
        return f"{tag}-{self._n}"

    def _tick(self):
        self._ts += 1.0
        return self._ts

    def is_paper(self):
        return self.paper

    def account(self):
        self._hit("account")
        return dict(self._account)

    def clock(self):
        self._hit("clock")
        return {"is_open": self.is_open, "minutes_to_close": self.minutes_to_close}

    def positions(self):
        self._hit("positions")
        return dict(self._positions)

    def quote(self, symbol):
        self._hit("quote")
        return self._quotes[symbol]

    def open_order_ids(self, symbol):
        self._hit("open_order_ids")
        ids = list(self.user_orders.get(symbol, []))
        for o in self.orders:
            if o["symbol"] != symbol:
                continue
            for x in [o] + o["legs"]:
                if x["status"] not in at._TERMINAL:
                    ids.append(x["order_id"])
        return ids

    def account_orders(self, since):
        self._hit("account_orders")
        cutoff = since.astimezone(ET).date().isoformat()
        return [dict(o, legs=[dict(l) for l in o["legs"]])
                for o in self.orders if o["date"] >= cutoff]

    def submit_bracket(self, symbol, side, qty, stop, target, client_order_id):
        self._hit("submit_bracket")
        if any(o["client_order_id"] == client_order_id for o in self.orders):
            raise RuntimeError("client_order_id must be unique")
        if symbol in self.reject:
            raise RuntimeError("insufficient buying power")
        self.submitted.append(dict(symbol=symbol, side=side, qty=qty, stop=stop,
                                   target=target, client_order_id=client_order_id))
        leg = lambda tag: {"order_id": self._id(f"{symbol}-{tag}"), "client_order_id": "",
                           "symbol": symbol, "side": "sell" if side == "buy" else "buy",
                           "status": "new", "qty": float(qty), "filled_qty": 0.0,
                           "ts": 0.0, "date": self.today, "legs": []}
        order = {"order_id": self._id(f"{symbol}-entry"), "client_order_id": client_order_id,
                 "symbol": symbol, "side": side, "status": "filled", "qty": float(qty),
                 "filled_qty": float(qty), "ts": self._tick(), "date": self.today,
                 "legs": [leg("tp"), leg("sl")]}
        self.orders.append(order)
        self._positions[symbol] = self._positions.get(symbol, 0.0) + (qty if side == "buy" else -qty)
        if symbol in self.timeout_after_accept:
            raise TimeoutError("read timed out")
        return {"order_id": order["order_id"], "status": "accepted"}

    def submit_market(self, symbol, side, qty, client_order_id):
        self._hit("submit_market")
        if any(o["client_order_id"] == client_order_id for o in self.orders):
            raise RuntimeError("client_order_id must be unique")
        self.market_orders.append(dict(symbol=symbol, side=side, qty=qty,
                                       client_order_id=client_order_id))
        self.orders.append({"order_id": self._id(f"{symbol}-flat"),
                            "client_order_id": client_order_id, "symbol": symbol,
                            "side": side, "status": "filled", "qty": float(qty),
                            "filled_qty": float(qty), "ts": self._tick(),
                            "date": self.today, "legs": []})
        left = self._positions.get(symbol, 0.0) + (qty if side == "buy" else -qty)
        if abs(left) < 1e-9:
            self._positions.pop(symbol, None)
        else:
            self._positions[symbol] = left
        return {"order_id": "flat", "status": "accepted"}

    def cancel_order(self, order_id):
        self._hit("cancel_order")
        self.cancelled.append(order_id)
        if self.on_cancel:
            hook, self.on_cancel = self.on_cancel, None
            hook()
        if self.cancel_lag:
            return
        for o in self.orders:
            for x in [o] + o["legs"]:
                if x["order_id"] == order_id:
                    if x["status"] in at._TERMINAL:
                        raise RuntimeError("422 order is not cancelable")
                    x["status"] = "canceled"

    # test helpers -------------------------------------------------------
    def bracket_exit(self, symbol, which="tp"):
        """The bracket's target (or stop) fills, its sibling is cancelled."""
        for o in self.orders:
            if o["symbol"] == symbol and o["legs"]:
                for leg in o["legs"]:
                    if leg["status"] in at._TERMINAL:
                        continue
                    hit = f"-{which}-" in leg["order_id"]
                    leg["status"] = "filled" if hit else "canceled"
                    leg["filled_qty"] = leg["qty"] if hit else 0.0
                    leg["ts"] = self._tick() if hit else 0.0
                    if hit:
                        self._move(symbol, leg["side"], leg["qty"])

    def _move(self, symbol, side, qty):
        left = self._positions.get(symbol, 0.0) + (qty if side == "buy" else -qty)
        if abs(left) < 1e-9:
            self._positions.pop(symbol, None)
        else:
            self._positions[symbol] = left

    def user_trade(self, symbol, side, qty):
        """A manual order (or another feature's), filled, not tagged as the bot's."""
        self.orders.append({"order_id": self._id(f"{symbol}-manual"),
                            "client_order_id": f"manual-{self._n}", "symbol": symbol,
                            "side": side, "status": "filled", "qty": float(qty),
                            "filled_qty": float(qty), "ts": self._tick(),
                            "date": self.today, "legs": []})
        self._move(symbol, side, qty)

    def cancel_all_legs(self, symbol):
        for o in self.orders:
            if o["symbol"] == symbol:
                for leg in o["legs"]:
                    if leg["status"] not in at._TERMINAL:
                        leg["status"] = "canceled"

    def expire_legs(self):
        for o in self.orders:
            for leg in o["legs"]:
                if leg["status"] not in at._TERMINAL:
                    leg["status"] = "expired"


def _sig(symbol="NVDA", action=SignalAction.BUY, entry=100.0, stop=99.0,
         target=102.0, confidence=0.65, setup=SetupType.HIGHER_LOW):
    return Signal(symbol=symbol, action=action, setup_type=setup, reason="t",
                  entry=entry, stop_loss=stop, target=target,
                  rr_ratio=abs(target - entry) / abs(entry - stop),
                  confidence=confidence, timestamp=MON_11)


def _row(symbol="NVDA", earnings_soon=False, earnings_known=True):
    return IntradayResult(symbol=symbol, price=100.0, change_pct=3.0, atr_pct=4.0,
                          rvol=2.0, volume=1, avg_volume=1, day_high=102.0,
                          day_low=98.0, vwap_dist_pct=0.1, score=50.0,
                          earnings_soon=earnings_soon, earnings_known=earnings_known)


def _cfg(**kw):
    base = dict(enabled=True, risk_per_trade_usd=50.0, max_position_usd=5000.0,
                max_trades_per_day=5, max_open_positions=3,
                daily_loss_limit_usd=150.0, allow_shorts=False, min_confidence=0.6,
                max_chase_frac=0.25, min_rr_at_quote=1.2, require_earnings_check=True,
                require_persistent_store=False,
                last_entry=dtime(15, 30), flatten_at=dtime(15, 45))
    base.update(kw)
    return at.AutoTradeConfig(**base)


QUOTE = (99.98, 100.02)   # tight quote right at the signal entry
Q = {"NVDA": QUOTE}


def _rows(*symbols):
    return {s: _row(s) for s in (symbols or ("NVDA",))}


def _run(b, signals=None, cfg=None, now=MON_11, rows=None):
    signals = signals if signals is not None else [_sig()]
    rows = rows if rows is not None else {s.symbol: _row(s.symbol) for s in signals}
    return at.handle_new_setups(signals, rows, broker=b, cfg=cfg or _cfg(), now=now)


# ------------------------------------------------------------------ sizing

class TestSizing:
    def test_risk_based(self):
        assert at.size_position(100.0, 99.0, _cfg(), 1e9) == 50

    def test_capped_by_position_value(self):
        assert at.size_position(100.0, 99.99, _cfg(), 1e9) == 50

    def test_capped_by_buying_power(self):
        assert at.size_position(100.0, 99.0, _cfg(), 1234.0) == 12

    def test_zero_risk_distance(self):
        assert at.size_position(100.0, 100.0, _cfg(), 1e9) == 0

    def test_negative_or_zero_inputs(self):
        assert at.size_position(0.0, -1.0, _cfg(), 1e9) == 0
        assert at.size_position(100.0, 99.0, _cfg(), -500.0) == 0

    def test_non_finite_inputs(self):
        nan = float("nan")
        assert at.size_position(nan, 99.0, _cfg(), 1e9) == 0
        assert at.size_position(100.0, nan, _cfg(), 1e9) == 0
        assert at.size_position(100.0, 99.0, _cfg(), nan) == 0
        assert at.size_position(float("inf"), 99.0, _cfg(), 1e9) == 0

    def test_expensive_stock_rounds_to_zero(self):
        assert at.size_position(9000.0, 8990.0, _cfg(), 1e9) == 0


# ---------------------------------------------------------------- evaluate

ACCT = {"equity": 100_000.0, "last_equity": 100_000.0, "buying_power": 200_000.0}


def _eval(signal=None, row="default", cfg=None, halted="", counts=None,
          account=None, positions=None, quote=QUOTE, now=MON_11,
          has_open_orders=False, minutes_to_close=300.0):
    return at.evaluate(
        signal or _sig(), _row() if row == "default" else row, cfg or _cfg(),
        halted, counts or at.DayCounts(), ACCT if account is None else account,
        positions or {}, quote,
        now=now, has_open_orders=has_open_orders, minutes_to_close=minutes_to_close,
    )


class TestEvaluate:
    def test_accepts_clean_signal(self):
        d = _eval()
        assert d.trade and d.qty == 49          # $50 / (100.02 - 99.00)
        assert d.ref_price == pytest.approx(100.02)

    def test_weekend(self):
        assert not _eval(now=datetime(2026, 11, 8, 11, 0, tzinfo=ET)).trade

    def test_before_open_gate(self):
        assert not _eval(now=datetime(2026, 11, 9, 9, 32, tzinfo=ET)).trade

    def test_at_last_entry_time_is_too_late(self):
        d = _eval(now=datetime(2026, 11, 9, 15, 30, tzinfo=ET))
        assert not d.trade and d.reason == "outside entry window"

    def test_half_day_blocks_entry_near_early_close(self):
        # 12:40 on a 13:00-close day: wall clock says fine, exchange says 20 min left
        d = _eval(now=datetime(2026, 11, 27, 12, 40, tzinfo=ET), minutes_to_close=20.0)
        assert not d.trade and d.reason == "outside entry window"

    def test_half_day_morning_still_trades(self):
        assert _eval(now=datetime(2026, 11, 27, 10, 0, tzinfo=ET), minutes_to_close=180.0).trade

    def test_daily_loss_limit_halts(self):
        d = _eval(account={"equity": 99_850.0, "last_equity": 100_000.0, "buying_power": 1e6})
        assert not d.trade and d.halt and "daily loss limit" in d.reason

    def test_just_inside_loss_limit_still_trades(self):
        assert _eval(account={"equity": 99_851.0, "last_equity": 100_000.0,
                              "buying_power": 1e6}).trade

    def test_missing_or_nan_account_values(self):
        assert _eval(account={}).reason == "account values unavailable"
        assert not _eval(account={"equity": float("nan"), "last_equity": 1.0,
                                  "buying_power": 1.0}).trade

    def test_already_halted(self):
        assert not _eval(halted="daily loss limit hit").trade

    def test_max_trades_per_day(self):
        assert _eval(counts=at.DayCounts(trades=5)).reason == "max trades per day reached"

    def test_short_blocked_by_default(self):
        s = _sig(action=SignalAction.SELL, entry=100.0, stop=101.0, target=98.0)
        assert _eval(signal=s).reason == "shorts disabled"

    def test_short_allowed_uses_bid(self):
        s = _sig(action=SignalAction.SELL, entry=100.0, stop=101.0, target=98.0)
        d = _eval(signal=s, cfg=_cfg(allow_shorts=True))
        assert d.trade and d.ref_price == pytest.approx(99.98)

    def test_short_chase_is_mirrored(self):
        s = _sig(action=SignalAction.SELL, entry=100.0, stop=101.0, target=98.0)
        d = _eval(signal=s, cfg=_cfg(allow_shorts=True), quote=(99.70, 99.72))
        assert not d.trade and "moved past entry" in d.reason

    def test_low_confidence(self):
        assert not _eval(signal=_sig(confidence=0.5)).trade

    def test_earnings_soon(self):
        assert _eval(row=_row(earnings_soon=True)).reason == "earnings within a day"

    def test_earnings_unknown_fails_closed(self):
        assert _eval(row=_row(earnings_known=False)).reason == "earnings status unknown"
        assert _eval(row=None).reason == "earnings status unknown"

    def test_earnings_check_can_be_waived(self):
        assert _eval(row=None, cfg=_cfg(require_earnings_check=False)).trade

    def test_already_traded_symbol_today(self):
        assert _eval(counts=at.DayCounts(trades=1, symbols={"NVDA"})).reason == \
            "already traded this symbol today"

    def test_existing_position_long_or_short(self):
        assert _eval(positions={"NVDA": 10.0}).reason == "position already open in this symbol"
        assert not _eval(positions={"NVDA": -10.0}).trade

    def test_existing_open_orders(self):
        assert not _eval(has_open_orders=True).trade

    def test_max_open_positions(self):
        assert _eval(counts=at.DayCounts(open_positions=3)).reason == "max open positions reached"
        assert _eval(counts=at.DayCounts(open_positions=2)).trade

    def test_no_quote(self):
        assert _eval(quote=None).reason == "no usable quote"

    def test_zero_crossed_or_nan_quote(self):
        assert not _eval(quote=(0.0, 100.0)).trade
        assert not _eval(quote=(100.5, 100.0)).trade
        assert _eval(quote=(float("nan"), 100.0)).reason == "no usable quote"

    def test_nan_signal_levels(self):
        assert _eval(signal=_sig(stop=float("nan"))).reason == "no usable quote"
        assert not _eval(signal=_sig(target=float("nan"))).trade

    def test_price_ran_past_entry(self):
        d = _eval(quote=(100.28, 100.30))
        assert not d.trade and "moved past entry" in d.reason

    def test_price_below_entry_is_fine_if_above_stop(self):
        assert _eval(quote=(99.58, 99.60)).trade

    def test_quote_at_or_through_stop(self):
        assert _eval(quote=(98.98, 99.00)).reason == "quote is at or beyond stop/target"

    def test_reward_to_risk_at_quote_too_low(self):
        d = _eval(signal=_sig(target=101.5), quote=(100.22, 100.24))
        assert not d.trade and "reward:risk at quote" in d.reason

    def test_signal_with_inverted_stop(self):
        assert _eval(signal=_sig(stop=100.5)).reason == "signal has no risk distance"

    def test_size_rounds_to_zero(self):
        assert _eval(account={"equity": 1.0, "last_equity": 1.0,
                              "buying_power": 50.0}).reason == "position size rounds to zero"


# -------------------------------------------------------- handle_new_setups

class TestHandleNewSetups:
    def test_disabled_touches_nothing(self):
        b = FakeBroker(quotes=Q)
        assert _run(b, cfg=_cfg(enabled=False)) == []
        assert b.calls == 0

    def test_paused_touches_nothing(self):
        at.set_paused(True)
        b = FakeBroker(quotes=Q)
        assert _run(b) == []
        assert b.calls == 0

    def test_empty_signal_list(self):
        b = FakeBroker(quotes=Q)
        assert _run(b, signals=[]) == []
        assert b.calls == 0

    def test_refuses_non_paper_endpoint(self):
        b = FakeBroker(paper=False, quotes=Q)
        assert _run(b) == []
        assert b.submitted == [] and b.calls == 0

    def test_market_closed_places_nothing(self):
        b = FakeBroker(quotes=Q, is_open=False)
        assert _run(b) == [] and b.submitted == []

    def test_places_bracket_with_signal_levels(self):
        b = FakeBroker(quotes=Q)
        recs = _run(b)
        assert [r["type"] for r in recs] == ["trade"]
        assert b.submitted == [dict(symbol="NVDA", side="buy", qty=49, stop=99.0,
                                    target=102.0,
                                    client_order_id="mse-auto-2026-11-09-NVDA-higher_low")]
        st = at.load_state()
        assert st.date == "2026-11-09" and len(st.trades) == 1
        assert st.trades[0]["risk_usd"] == pytest.approx(49 * 1.02, abs=0.01)

    def test_short_goes_out_as_sell_bracket(self):
        b = FakeBroker(quotes=Q)
        s = _sig(action=SignalAction.SELL, entry=100.0, stop=101.0, target=98.0)
        _run(b, [s], cfg=_cfg(allow_shorts=True))
        assert b.submitted[0]["side"] == "sell"
        assert (b.submitted[0]["stop"], b.submitted[0]["target"]) == (101.0, 98.0)

    def test_same_symbol_twice_in_one_call_trades_once(self):
        b = FakeBroker(quotes=Q)
        sigs = [_sig(setup=SetupType.HIGHER_LOW),
                _sig(setup=SetupType.VWAP_RECLAIM, confidence=0.7)]
        recs = _run(b, sigs)
        assert len(b.submitted) == 1
        assert b.submitted[0]["client_order_id"].endswith("vwap_reclaim")
        assert [r["type"] for r in recs] == ["trade", "skip"]

    def test_second_call_does_not_retrade_symbol(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        _run(b, [_sig(setup=SetupType.RANGE_BREAKOUT)])
        assert len(b.submitted) == 1

    def test_stops_at_max_trades_per_day(self):
        syms = ["A", "B", "C"]
        b = FakeBroker(quotes={s: QUOTE for s in syms})
        recs = _run(b, [_sig(symbol=s) for s in syms], cfg=_cfg(max_trades_per_day=2))
        assert len(b.submitted) == 2
        assert recs[-1]["reason"] == "max trades per day reached"

    def test_buying_power_is_shared_across_the_batch(self):
        syms = ["A", "B", "C"]
        b = FakeBroker(quotes={s: QUOTE for s in syms}, buying_power=6_000.0)
        _run(b, [_sig(symbol=s) for s in syms])
        qtys = [o["qty"] for o in b.submitted]
        assert qtys[0] == 49
        assert sum(q * 100.02 for q in qtys) <= 6_000.0

    def test_loss_limit_halts_for_rest_of_day(self):
        b = FakeBroker(equity=99_800.0, quotes={"NVDA": QUOTE, "AMD": QUOTE})
        _run(b)
        assert at.load_state().halted
        b._account["equity"] = 100_500.0     # recovers, the halt still holds
        _run(b, [_sig(symbol="AMD")])
        assert b.submitted == []

    def test_broker_rejection_is_logged_not_raised(self):
        b = FakeBroker(quotes=Q)
        b.reject.add("NVDA")
        recs = _run(b)
        assert recs[0]["type"] == "skip" and "order rejected" in recs[0]["reason"]
        assert at.load_state().trades == []

    def test_timeout_after_accept_is_recorded_as_a_trade(self):
        b = FakeBroker(quotes=Q)
        b.timeout_after_accept.add("NVDA")
        recs = _run(b)
        assert recs[0]["type"] == "trade"
        assert len(at.load_state().trades) == 1

    def test_missing_quote_skips_without_crashing(self):
        b = FakeBroker(quotes={})
        assert _run(b)[0]["reason"] == "no usable quote" and b.submitted == []

    def test_open_order_lookup_failure_fails_closed(self):
        b = FakeBroker(quotes=Q)
        b.fail.add("open_order_ids")
        recs = _run(b)
        assert recs[0]["reason"] == "could not check open orders" and b.submitted == []

    def test_pending_user_order_blocks_entry(self):
        b = FakeBroker(quotes=Q)
        b.user_orders["NVDA"] = ["user-limit-1"]
        assert _run(b)[0]["reason"] == "open orders already exist for this symbol"

    @pytest.mark.parametrize("method", ["account", "positions", "clock", "account_orders"])
    def test_any_broker_read_failure_skips_cycle(self, method):
        b = FakeBroker(quotes=Q)
        b.fail.add(method)
        assert _run(b) == [] and b.submitted == []

    def test_earlier_trade_is_saved_before_a_later_one_blows_up(self):
        b = FakeBroker(quotes={"A": QUOTE, "B": QUOTE})
        real_quote = b.quote
        def boom(symbol):
            if symbol == "B":
                raise KeyboardInterrupt        # process dies mid-batch
            return real_quote(symbol)
        b.quote = boom
        with pytest.raises(KeyboardInterrupt):
            _run(b, [_sig(symbol="A", confidence=0.9), _sig(symbol="B")])
        assert [t["symbol"] for t in at.load_state().trades] == ["A"]

    def test_pause_mid_batch_stops_remaining_orders(self):
        b = FakeBroker(quotes={"A": QUOTE, "B": QUOTE})
        real_submit = b.submit_bracket
        def submit_then_pause(*a, **k):
            out = real_submit(*a, **k)
            at.set_paused(True)
            return out
        b.submit_bracket = submit_then_pause
        recs = _run(b, [_sig(symbol="A", confidence=0.9), _sig(symbol="B")])
        assert len(b.submitted) == 1 and recs[-1]["reason"] == "paused"

    def test_new_day_starts_clean(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.bracket_exit("NVDA")
        b.today = "2026-11-10"
        _run(b, now=TUE_10)
        assert len(b.submitted) == 2 and at.load_state().date == "2026-11-10"

    def test_no_entries_while_an_earlier_day_is_still_open(self):
        b = FakeBroker(quotes={"NVDA": QUOTE, "AMD": QUOTE})
        _run(b)
        b.expire_legs()                       # close was missed on Monday
        b.today = "2026-11-10"
        assert _run(b, [_sig(symbol="AMD")], now=TUE_10) == []
        assert len(b.submitted) == 1


# ------------------------------------------- broker is the source of truth

class TestStateLossCannotBypassLimits:
    def test_caps_hold_after_state_is_wiped(self):
        b = FakeBroker(quotes={"NVDA": QUOTE, "AMD": QUOTE})
        _run(b, cfg=_cfg(max_trades_per_day=1))
        at._MEM.clear()                       # restart with no Redis
        recs = _run(b, [_sig(symbol="AMD")], cfg=_cfg(max_trades_per_day=1))
        assert len(b.submitted) == 1
        assert recs[0]["reason"] == "max trades per day reached"

    def test_one_per_symbol_holds_after_state_is_wiped(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.bracket_exit("NVDA")                # flat again, so only history blocks it
        at._MEM.clear()
        recs = _run(b, [_sig(setup=SetupType.RANGE_BREAKOUT)])
        assert recs[0]["reason"] == "already traded this symbol today"

    def test_flatten_still_closes_after_state_is_wiped(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        at._MEM.clear()
        b.minutes_to_close = 14.0
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546) == ["NVDA"]

    def test_rejected_entry_does_not_use_up_a_trade(self):
        orders = [{"client_order_id": "mse-auto-2026-11-09-X-higher_low", "status": "rejected",
                   "filled_qty": 0.0, "symbol": "X", "date": "2026-11-09", "legs": []}]
        assert not at._counts_as_trade(orders[0])


class TestRedisFailures:
    def _redis(self, monkeypatch):
        r = FakeRedis()
        monkeypatch.setattr(at, "_get_redis", lambda: r)
        return r

    def test_pause_survives_restart_via_redis(self, monkeypatch):
        r = self._redis(monkeypatch)
        at.set_paused(True)
        at._MEM.clear()                       # restart
        assert at.is_paused()
        b = FakeBroker(quotes=Q)
        assert _run(b) == [] and b.calls == 0
        assert r.data[at._PAUSED_KEY] == "1"

    def test_unreadable_pause_flag_means_paused(self, monkeypatch):
        r = self._redis(monkeypatch)
        at.set_paused(True)
        at._MEM.clear()
        r.fail_get = True                     # one Upstash timeout after a restart
        assert at.is_paused()
        b = FakeBroker(quotes=Q)
        assert _run(b) == [] and b.submitted == []

    def test_unreadable_state_places_nothing_and_does_not_overwrite(self, monkeypatch):
        r = self._redis(monkeypatch)
        at.save_state(at.DayState(date="2026-11-09", halted="daily loss limit hit"))
        saved = r.data[at._STATE_KEY]
        at._MEM.clear()
        real_get = r.get
        r.get = lambda k: (_ for _ in ()).throw(TimeoutError()) if k == at._STATE_KEY else real_get(k)
        b = FakeBroker(quotes=Q)
        assert _run(b) == [] and b.submitted == []
        assert r.data[at._STATE_KEY] == saved     # the halt is not wiped

    def test_failed_write_is_not_replaced_by_stale_redis_data(self, monkeypatch):
        r = self._redis(monkeypatch)
        at.save_state(at.DayState(date="2026-11-09"))
        r.fail_set = True
        at.save_state(at.DayState(date="2026-11-09", halted="daily loss limit hit"))
        assert at.load_state().halted == "daily loss limit hit"   # memory wins
        r.fail_set = False
        at.load_state()                                           # resync on next read
        assert "daily loss limit hit" in r.data[at._STATE_KEY]

    def test_status_reports_unreachable_store(self, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "auto_trade_enabled", True)
        monkeypatch.setattr(settings, "alpaca_base_url", "https://paper-api.alpaca.markets")
        r = self._redis(monkeypatch)
        r.fail_get = True
        s = at.status()
        assert s["store_ok"] is False and s["paused"] is True
        assert s["mode"].startswith("stopped")


# ------------------------------------------------------------------ flatten

def _due(b):
    b.minutes_to_close = 14.0
    return at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546)


class TestFlatten:
    def _open(self, b, **kw):
        _run(b, **kw)

    def test_not_before_the_flatten_window(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_11) == []
        assert b.market_orders == [] and b.cancelled == []

    def test_cancels_own_legs_then_sells_own_quantity(self):
        b = FakeBroker(quotes=Q, positions={"AAPL": 100.0})
        self._open(b)
        assert _due(b) == ["NVDA"]
        assert len(b.cancelled) == 2 and all(c.startswith("NVDA-") for c in b.cancelled)
        assert b.market_orders == [dict(symbol="NVDA", side="sell", qty=49.0,
                                        client_order_id="mse-auto-flat-2026-11-09-NVDA-higher_low-1")]
        assert b.positions() == {"AAPL": 100.0}

    def test_shares_the_user_added_are_left_alone(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        b.user_trade("NVDA", "buy", 100)       # user buys 100 more by hand
        b.user_orders["NVDA"] = ["user-stop-1"]
        _due(b)
        assert b.market_orders[0]["qty"] == 49.0
        assert b.positions()["NVDA"] == 100.0
        assert "user-stop-1" not in b.cancelled

    def test_user_position_opened_after_bot_exit_is_left_alone(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        b.bracket_exit("NVDA", "tp")           # bot is out at 12:00
        b.user_trade("NVDA", "buy", 75)        # user opens their own at 13:00
        b.user_orders["NVDA"] = ["user-stop-1"]
        assert _due(b) == []
        assert b.market_orders == [] and b.cancelled == []
        assert b.positions()["NVDA"] == 75.0

    def test_user_sold_some_of_the_bot_shares(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        b.cancel_all_legs("NVDA")
        b.user_trade("NVDA", "sell", 29)
        _due(b)
        assert b.market_orders[0]["qty"] == 20.0 and b.positions() == {}

    def test_short_is_bought_back(self):
        b = FakeBroker(quotes=Q)
        s = _sig(action=SignalAction.SELL, entry=100.0, stop=101.0, target=98.0)
        _run(b, [s], cfg=_cfg(allow_shorts=True))
        _due(b)
        assert b.market_orders[0]["side"] == "buy" and b.positions() == {}

    def test_does_not_close_twice(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        _due(b)
        assert _due(b) == [] and len(b.market_orders) == 1

    def test_runs_even_when_paused_or_disabled(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        at.set_paused(True)
        b.minutes_to_close = 14.0
        assert at.maybe_flatten(broker=b, cfg=_cfg(enabled=False), now=MON_1546) == ["NVDA"]

    def test_nothing_to_do_when_bracket_already_exited(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        b.bracket_exit("NVDA", "sl")
        assert _due(b) == [] and b.market_orders == []

    def test_never_traded_closes_nothing(self):
        b = FakeBroker(quotes=Q, positions={"AAPL": 100.0})
        assert _due(b) == []
        assert b.market_orders == [] and b.cancelled == []

    def test_slow_cancel_waits_then_closes(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        real = b.open_order_ids
        polls = {"n": 0}
        def lagging(sym):
            polls["n"] += 1
            if polls["n"] <= 3:
                return ["NVDA-tp-2"]            # still pending-cancel
            return real(sym)
        b.open_order_ids = lagging
        assert _due(b) == ["NVDA"]

    def test_legs_never_clear_does_not_sell_and_retries(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        b.cancel_lag = True
        assert _due(b) == [] and b.market_orders == []
        b.cancel_lag = False
        assert _due(b) == ["NVDA"]             # next 30s cycle

    def test_sibling_cancel_error_does_not_block_the_close(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        real_cancel = b.cancel_order
        def oco(order_id):
            if "-sl-" in order_id:
                raise RuntimeError("422 order is already canceled")
            real_cancel(order_id)
            for o in b.orders:                 # cancelling one leg cancels its sibling
                for leg in o["legs"]:
                    leg["status"] = "canceled"
        b.cancel_order = oco
        assert _due(b) == ["NVDA"]

    def test_close_order_failure_is_retried(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        b.fail.add("submit_market")
        assert _due(b) == []
        b.fail.clear()
        assert _due(b) == ["NVDA"] and b.positions() == {}

    def test_rejected_close_gets_a_new_order_id(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        _due(b)
        b.orders[-1].update(status="rejected", filled_qty=0.0, ts=0.0)   # broker bounced it
        b._positions["NVDA"] = 49.0
        assert _due(b) == ["NVDA"]
        assert b.market_orders[-1]["client_order_id"].endswith("-2")

    def test_one_symbol_failing_does_not_stop_the_others(self):
        b = FakeBroker(quotes={"A": QUOTE, "B": QUOTE})
        _run(b, [_sig(symbol="A"), _sig(symbol="B")])
        real = b.submit_market
        def flaky(symbol, *a, **k):
            if symbol == "A":
                raise RuntimeError("timeout")
            return real(symbol, *a, **k)
        b.submit_market = flaky
        assert _due(b) == ["B"]

    def test_after_the_bell_sends_nothing(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        b.is_open = False
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1601) == []
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546) == []   # clock says closed
        assert b.market_orders == []

    def test_half_day_flattens_before_the_early_close(self):
        b = FakeBroker(quotes=Q, today="2026-11-27")
        _run(b, now=datetime(2026, 11, 27, 10, 0, tzinfo=ET))
        b.minutes_to_close = 12.0              # 12:48 on a 13:00-close day
        closed = at.maybe_flatten(broker=b, cfg=_cfg(),
                                  now=datetime(2026, 11, 27, 12, 48, tzinfo=ET))
        assert closed == ["NVDA"]

    def test_missed_close_is_caught_next_morning(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        b.expire_legs()                        # DAY legs died at the bell
        b.today = "2026-11-10"
        b.minutes_to_close = 360.0
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=TUE_10) == ["NVDA"]
        assert b.positions() == {}

    def test_todays_position_is_not_closed_early(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        b.minutes_to_close = 200.0
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_11) == []

    def test_stale_check_is_throttled_away_from_the_close(self):
        b = FakeBroker(quotes=Q)
        at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_11)
        before = b.calls
        at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_11)
        assert b.calls == before + 1           # just the clock

    def test_no_broker_calls_outside_session_hours(self):
        b = FakeBroker(quotes=Q)
        assert at.maybe_flatten(broker=b, cfg=_cfg(),
                                now=datetime(2026, 11, 9, 20, 0, tzinfo=ET)) == []
        assert at.maybe_flatten(broker=b, cfg=_cfg(),
                                now=datetime(2026, 11, 8, 11, 0, tzinfo=ET)) == []
        assert b.calls == 0

    def test_refuses_non_paper_endpoint(self):
        b = FakeBroker(quotes=Q)
        self._open(b)
        b.paper = False
        assert _due(b) == [] and b.market_orders == []

    @pytest.mark.parametrize("method", ["clock", "positions", "account_orders"])
    def test_broker_read_failure_sends_nothing(self, method):
        b = FakeBroker(quotes=Q)
        self._open(b)
        b.fail.add(method)
        assert _due(b) == [] and b.market_orders == []


# ------------------------------------------------------------------ config

class TestConfig:
    def test_default_settings_are_off(self):
        from config.settings import Settings
        f = Settings.model_fields
        assert f["auto_trade_enabled"].default is False
        assert f["auto_trade_allow_shorts"].default is False
        assert f["auto_trade_require_earnings_check"].default is True

    def test_get_config_reads_every_setting(self, monkeypatch):
        from config.settings import settings
        values = dict(
            auto_trade_enabled=True, auto_trade_risk_per_trade_usd=11.0,
            auto_trade_max_position_usd=222.0, auto_trade_max_trades_per_day=3,
            auto_trade_max_open_positions=2, auto_trade_daily_loss_limit_usd=44.0,
            auto_trade_allow_shorts=True, auto_trade_min_confidence=0.71,
            auto_trade_max_chase_frac=0.1, auto_trade_min_rr_at_quote=1.9,
            auto_trade_require_earnings_check=False,
            auto_trade_last_entry_et="14:00", auto_trade_flatten_et="15:00",
        )
        for k, v in values.items():
            monkeypatch.setattr(settings, k, v)
        c = at.get_config()
        assert (c.enabled, c.risk_per_trade_usd, c.max_position_usd) == (True, 11.0, 222.0)
        assert (c.max_trades_per_day, c.max_open_positions) == (3, 2)
        assert (c.daily_loss_limit_usd, c.allow_shorts, c.min_confidence) == (44.0, True, 0.71)
        assert (c.max_chase_frac, c.min_rr_at_quote, c.require_earnings_check) == (0.1, 1.9, False)
        assert (c.last_entry, c.flatten_at) == (dtime(14, 0), dtime(15, 0))
        assert (c.entry_lead_min, c.flatten_lead_min) == (120, 60)

    def test_last_entry_after_flatten_is_clamped(self):
        c = _cfg(last_entry=dtime(15, 30), flatten_at=dtime(15, 0))
        assert c.last_entry == dtime(15, 0)

    def test_flatten_at_or_after_the_bell_falls_back(self):
        assert _cfg(flatten_at=dtime(16, 0)).flatten_at == dtime(15, 45)
        assert _cfg(flatten_at=dtime(17, 30)).flatten_at == dtime(15, 45)

    def test_time_parsing(self):
        assert at._parse_hhmm("nonsense", dtime(15, 30)) == dtime(15, 30)
        assert at._parse_hhmm("14:05", dtime(15, 30)) == dtime(14, 5)
        assert at._parse_hhmm("14:05:00", dtime(15, 30)) == dtime(14, 5)
        assert at._parse_hhmm("", dtime(15, 30)) == dtime(15, 30)


# ------------------------------------------------------------------ status

class TestStatus:
    def _on(self, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "auto_trade_enabled", True)
        monkeypatch.setattr(settings, "auto_trade_require_persistent_store", False)
        monkeypatch.setattr(settings, "alpaca_base_url", "https://paper-api.alpaca.markets")
        return settings

    def test_modes(self, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "auto_trade_enabled", False)
        assert at.status()["mode"] == "off"
        settings = self._on(monkeypatch)
        assert at.status()["mode"] == "running"
        at.set_paused(True)
        assert at.status()["mode"] == "paused"
        at.set_paused(False)
        monkeypatch.setattr(settings, "alpaca_base_url", "https://api.alpaca.markets")
        assert at.status()["mode"].startswith("refusing")
        monkeypatch.setattr(settings, "alpaca_base_url", "")
        assert at.status()["mode"].startswith("refusing")

    def test_yesterdays_log_is_not_shown_as_today(self, monkeypatch):
        self._on(monkeypatch)
        at.save_state(at.DayState(date="2000-01-03", trades=[{"symbol": "OLD"}],
                                  halted="daily loss limit hit"))
        s = at.status()
        assert s["trades"] == [] and s["halted"] == "" and s["mode"] == "running"

    def test_resume_does_not_enable(self, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "auto_trade_enabled", False)
        at.set_paused(False)
        b = FakeBroker(quotes=Q)
        assert at.handle_new_setups([_sig()], _rows(), broker=b, now=MON_11) == []
        assert b.calls == 0

    def test_corrupt_state_starts_empty(self):
        at._MEM[at._STATE_KEY] = "{not json"
        assert at.load_state().trades == []


# ------------------------------------------------------------------- routes

class TestRoutes:
    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.routes import router
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_status_and_pause_are_open(self):
        c = self._client()
        assert c.get("/trading/auto/status").status_code == 200
        r = c.post("/trading/auto/pause")
        assert r.status_code == 200 and r.json()["paused"] is True

    def test_resume_without_a_key_is_refused(self, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "auto_trade_resume_key", "k" * 24)
        c = self._client()
        c.post("/trading/auto/pause")
        assert c.post("/trading/auto/resume").status_code == 403
        assert c.post("/trading/auto/resume",
                      headers={"X-Resume-Key": "nope"}).status_code == 403
        assert at.is_paused()

    def test_no_route_can_enable(self):
        from config.settings import settings
        from src.api.routes import router
        paths = {r.path for r in router.routes if "/trading/auto" in r.path}
        assert paths == {"/trading/auto/status", "/trading/auto/pause", "/trading/auto/resume"}
        c = self._client()
        c.post("/trading/auto/pause")
        assert settings.auto_trade_enabled is False


# --------------------------------------------------- Alpaca adapter (no I/O)

class TestAlpacaAdapter:
    def _capture(self, monkeypatch):
        sent = {}
        class Client:
            def submit_order(self, req):
                sent["req"] = req
                class S: value = "accepted"
                class O: id = "x1"; status = S
                return O
        b = at.AlpacaPaperBroker()
        monkeypatch.setattr(b, "_client", lambda: Client())
        return b, sent

    def test_bracket_request(self, monkeypatch):
        b, sent = self._capture(monkeypatch)
        out = b.submit_bracket("NVDA", "buy", 10, 98.999, 102.004, "mse-auto-x")
        r = sent["req"]
        assert out == {"order_id": "x1", "status": "accepted"}
        assert (r.symbol, r.qty, r.side.value, r.time_in_force.value) == ("NVDA", 10, "buy", "day")
        assert r.order_class.value == "bracket" and r.client_order_id == "mse-auto-x"
        assert (r.take_profit.limit_price, r.stop_loss.stop_price) == (102.0, 99.0)

    def test_closing_order_request(self, monkeypatch):
        b, sent = self._capture(monkeypatch)
        b.submit_market("NVDA", "sell", 49.0, "mse-auto-flat-x-1")
        r = sent["req"]
        assert (r.side.value, r.qty, r.client_order_id) == ("sell", 49.0, "mse-auto-flat-x-1")
        assert r.order_class is None

    def test_paper_gate(self, monkeypatch):
        from config.settings import settings
        b = at.AlpacaPaperBroker()
        monkeypatch.setattr(settings, "alpaca_base_url", "https://paper-api.alpaca.markets")
        assert b.is_paper()
        monkeypatch.setattr(settings, "alpaca_base_url", "https://api.alpaca.markets")
        assert not b.is_paper()
        monkeypatch.setattr(settings, "alpaca_base_url", "")
        assert not b.is_paper()

    def _order(self, oid, coid, when, legs=None, filled_at=None):
        from types import SimpleNamespace as NS
        return NS(id=oid, client_order_id=coid, symbol="NVDA", side=NS(value="buy"),
                  status=NS(value="filled"), qty="5", filled_qty="5", created_at=when,
                  submitted_at=when, filled_at=filled_at, updated_at=None, legs=legs)

    def test_account_orders_returns_everything_with_legs(self, monkeypatch):
        when = datetime(2026, 11, 9, 15, 0, tzinfo=ZoneInfo("UTC"))
        filled = datetime(2026, 11, 9, 15, 5, tzinfo=ZoneInfo("UTC"))
        reqs = []
        outer = self
        class Client:
            def get_orders(self, req):
                reqs.append(req)
                return [outer._order("1", "mse-auto-2026-11-09-NVDA-higher_low", when,
                                     legs=[outer._order("2", None, when)], filled_at=filled),
                        outer._order("3", "my-manual-order", when)]
        b = at.AlpacaPaperBroker()
        monkeypatch.setattr(b, "_client", lambda: Client())
        out = b.account_orders(MON_11)
        r = reqs[0]
        assert (r.status.value, r.nested, r.limit, r.direction.value) == ("all", True, 500, "desc")
        assert r.after == MON_11.astimezone(ZoneInfo("UTC")) and r.until is None
        # manual orders are included: a manual sale must be visible
        assert [o["client_order_id"] for o in out] == \
            ["mse-auto-2026-11-09-NVDA-higher_low", "my-manual-order"]
        assert out[0]["date"] == "2026-11-09" and out[0]["filled_qty"] == 5.0
        assert out[0]["ts"] == when.timestamp() and out[0]["fill_ts"] == filled.timestamp()
        assert len(out[0]["legs"]) == 1
        assert out[1]["fill_ts"] == when.timestamp()   # no fill time: falls back

    def test_account_orders_pages_until_history_is_complete(self, monkeypatch):
        from datetime import timedelta
        base = datetime(2026, 11, 9, 15, 0, tzinfo=ZoneInfo("UTC"))
        everything = [self._order(str(i), f"c{i}", base - timedelta(seconds=i))
                      for i in range(1200)]          # newest first
        reqs = []
        class Client:
            def get_orders(self, req):
                reqs.append(req)
                pool = [o for o in everything if req.until is None or o.created_at < req.until]
                return pool[:req.limit]
        b = at.AlpacaPaperBroker()
        monkeypatch.setattr(b, "_client", lambda: Client())
        out = b.account_orders(MON_11)
        assert len(out) == 1200 and len({o["order_id"] for o in out}) == 1200
        assert len(reqs) == 3

    def test_paging_steps_on_submission_time_not_creation_time(self, monkeypatch):
        from datetime import timedelta
        base = datetime(2026, 11, 9, 15, 0, tzinfo=ZoneInfo("UTC"))
        lag = timedelta(seconds=2)                   # submitted later than created
        everything = []
        for i in range(1100):
            o = self._order(str(i), f"c{i}", base - timedelta(seconds=i))
            o.submitted_at = o.created_at + lag
            everything.append(o)
        class Client:
            def get_orders(self, req):               # Alpaca filters on submitted_at
                pool = [o for o in everything
                        if req.until is None or o.submitted_at < req.until]
                return pool[:req.limit]
        b = at.AlpacaPaperBroker()
        monkeypatch.setattr(b, "_client", lambda: Client())
        assert len(b.account_orders(MON_11)) == 1100

    def test_partly_filled_leg_without_filled_at_still_counts(self):
        """Alpaca-shaped objects through _order_dict: a leg that sold 20 and
        has no filled_at must still reduce the bot's lot."""
        from types import SimpleNamespace as NS
        t0 = datetime(2026, 11, 9, 15, 0, 0, tzinfo=ZoneInfo("UTC"))
        t1 = datetime(2026, 11, 9, 15, 0, 1, tzinfo=ZoneInfo("UTC"))
        t2 = datetime(2026, 11, 9, 16, 0, 0, tzinfo=ZoneInfo("UTC"))
        def o(oid, coid, side, status, qty, filled, created, filled_at, updated, legs=None):
            return NS(id=oid, client_order_id=coid, symbol="NVDA", side=NS(value=side),
                      status=NS(value=status), qty=str(qty), filled_qty=str(filled),
                      created_at=created, submitted_at=created, filled_at=filled_at,
                      updated_at=updated, legs=legs)
        leg = o("L1", None, "sell", "canceled", 49, 20, t0, None, t2)     # partial, no filled_at
        entry = o("E1", "mse-auto-2026-11-09-NVDA-higher_low", "buy", "filled", 49, 49,
                  t0, t1, t1, legs=[leg])
        user = o("U1", "manual", "buy", "filled", 100, 100, t0, t1, t1)
        orders = [at._order_dict(x) for x in (entry, user)]
        held = at.owned_holdings(orders, {"NVDA": 129.0})
        assert [h.qty for h in held] == [29.0]       # not 49: 20 of them were sold

    def test_account_orders_refuses_a_history_it_cannot_finish(self, monkeypatch):
        when = datetime(2026, 11, 9, 15, 0, tzinfo=ZoneInfo("UTC"))
        outer = self
        class Client:
            n = 0
            def get_orders(self, req):
                Client.n += 1
                return [outer._order(f"{Client.n}-{i}", "x", when) for i in range(req.limit)]
        b = at.AlpacaPaperBroker()
        monkeypatch.setattr(b, "_client", lambda: Client())
        with pytest.raises(RuntimeError, match="too large"):
            b.account_orders(MON_11)

    def test_clock_minutes_to_close(self, monkeypatch):
        from types import SimpleNamespace as NS
        ts = datetime(2026, 11, 27, 12, 40, tzinfo=ET)
        class Client:
            def get_clock(self):
                return NS(is_open=True, timestamp=ts, next_close=ts.replace(hour=13, minute=0))
        b = at.AlpacaPaperBroker()
        monkeypatch.setattr(b, "_client", lambda: Client())
        assert b.clock() == {"is_open": True, "minutes_to_close": 20.0}

    def test_open_order_ids_queries_open_orders_for_the_symbol(self, monkeypatch):
        from types import SimpleNamespace as NS
        reqs = []
        class Client:
            def get_orders(self, req):
                reqs.append(req)
                return [NS(id="a"), NS(id="b")]
        b = at.AlpacaPaperBroker()
        monkeypatch.setattr(b, "_client", lambda: Client())
        assert b.open_order_ids("NVDA") == ["a", "b"]
        assert reqs[0].status.value == "open" and reqs[0].symbols == ["NVDA"]


# --------------------------------------------- ownership (second review round)

class TestOwnership:
    def test_position_closed_by_hand_is_no_longer_owned(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.cancel_all_legs("NVDA")
        b.user_trade("NVDA", "sell", 49)        # user closes the bot's position
        b.user_trade("NVDA", "buy", 75)         # then opens their own
        assert _due(b) == []
        assert b.market_orders == [] and b.positions() == {"NVDA": 75.0}

    def test_hand_closed_leftover_does_not_sell_a_later_user_position(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.expire_legs()
        b.today = "2026-11-10"
        b.user_trade("NVDA", "sell", 49)        # Tuesday: leftover closed by hand
        b.today = "2026-11-11"
        b.user_trade("NVDA", "buy", 100)        # Wednesday: user's own shares
        b.minutes_to_close = 360.0
        wed = datetime(2026, 11, 11, 10, 0, tzinfo=ET)
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=wed) == []
        assert b.market_orders == [] and b.positions() == {"NVDA": 100.0}

    def test_reentry_after_hand_closed_leftover(self):
        b = FakeBroker(quotes={"NVDA": QUOTE, "AMD": QUOTE})
        _run(b)
        b.expire_legs()
        b.today = "2026-11-10"
        b.user_trade("NVDA", "sell", 49)
        # the old entry no longer blocks anything
        recs = _run(b, [_sig(), _sig(symbol="AMD")], now=TUE_10)
        assert [r["type"] for r in recs] == ["trade", "trade"]
        b.minutes_to_close = 14.0
        tue_close = datetime(2026, 11, 10, 15, 46, tzinfo=ET)
        assert sorted(at.maybe_flatten(broker=b, cfg=_cfg(), now=tue_close)) == ["AMD", "NVDA"]
        assert b.positions() == {}
        assert all(m["qty"] == 49.0 for m in b.market_orders)

    def test_bracket_fill_racing_the_close_does_not_open_a_short(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.on_cancel = lambda: b.bracket_exit("NVDA", "tp")   # target fills mid-cancel
        assert _due(b) == []
        assert b.market_orders == [] and b.positions() == {}
        assert _due(b) == []                                  # and nothing later either

    def test_disowned_shares_lose_the_bots_legs_and_raise_a_notice(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.user_trade("NVDA", "buy", 100)
        b.user_trade("NVDA", "sell", 100)       # ambiguous: could be the bot's shares
        assert _due(b) == []
        assert b.market_orders == []            # never sells what it does not claim
        assert len(b.cancelled) == 2            # but its own legs must not keep selling
        assert b.positions() == {"NVDA": 49.0}
        notices = at.load_notices("2026-11-09")
        assert len(notices) == 1 and notices[0]["symbol"] == "NVDA"
        assert "49" in notices[0]["text"] and "by hand" in notices[0]["text"]
        _due(b)
        assert len(at.load_notices("2026-11-09")) == 1      # not repeated

    def test_disowning_is_caught_mid_session_not_only_at_the_close(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.user_trade("NVDA", "buy", 100)
        b.user_trade("NVDA", "sell", 49)        # ledger: the remaining 100 are the user's
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_11) == []
        assert len(b.cancelled) == 2 and b.market_orders == []
        assert b.positions() == {"NVDA": 100.0}

    def test_notices_appear_in_status(self, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "auto_trade_require_persistent_store", False)
        today = datetime.now(tz=ET).date().isoformat()
        at.add_notice("NVDA", "check this", today)
        at.add_notice("OLD", "ancient", "2000-01-01")
        assert [n["symbol"] for n in at.status()["notices"]] == ["NVDA"]

    def test_orphan_legs_with_no_position_are_cancelled(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.user_trade("NVDA", "sell", 49)        # position gone, legs somehow still live
        assert _due(b) == []
        assert len(b.cancelled) == 2 and b.market_orders == []

    def test_recount_after_cancel_survives_one_failed_read(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        real, n = b.account_orders, {"n": 0}
        def flaky(since):
            n["n"] += 1
            if n["n"] == 2:                      # the read right after the cancels
                raise RuntimeError("alpaca 503")
            return real(since)
        b.account_orders = flaky
        assert _due(b) == ["NVDA"] and b.positions() == {}

    def test_recount_that_keeps_failing_is_retried_on_the_next_tick(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        real, n = b.account_orders, {"n": 0}
        def down_after_first(since):
            n["n"] += 1
            if n["n"] > 1:
                raise RuntimeError("alpaca 503")
            return real(since)
        b.account_orders = down_after_first
        assert _due(b) == [] and b.market_orders == []
        b.account_orders = real
        assert _due(b) == ["NVDA"] and b.positions() == {}

    def test_partial_entry_fill(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.orders[0].update(status="partially_filled", filled_qty=30.0)
        b._positions["NVDA"] = 30.0
        assert _due(b) == ["NVDA"]
        assert b.market_orders[0]["qty"] == 30.0
        assert b.orders[0]["order_id"] in b.cancelled        # the unfilled remainder

    def test_working_close_is_not_sent_twice(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        _due(b)
        b.orders[-1].update(status="new", filled_qty=0.0, ts=0.0)   # accepted, not filled yet
        b._positions["NVDA"] = 49.0
        assert _due(b) == [] and len(b.market_orders) == 1

    def test_partly_filled_then_cancelled_close_resends_the_rest(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        _due(b)
        b.orders[-1].update(status="canceled", filled_qty=20.0)
        b._positions["NVDA"] = 29.0
        assert _due(b) == ["NVDA"]
        assert b.market_orders[-1]["qty"] == 29.0
        assert b.market_orders[-1]["client_order_id"].endswith("-2")

    def test_held_and_pending_cancel_legs_are_the_bots_to_cancel(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.orders[0]["legs"][0]["status"] = "held"
        b.orders[0]["legs"][1]["status"] = "pending_cancel"
        h = at.owned_holdings(b.account_orders(MON_11), b.positions())[0]
        assert len(h.cancel_ids) == 2 and h.qty == 49.0

    def test_short_leftover_is_bought_back_next_morning(self):
        b = FakeBroker(quotes=Q)
        s = _sig(action=SignalAction.SELL, entry=100.0, stop=101.0, target=98.0)
        _run(b, [s], cfg=_cfg(allow_shorts=True))
        b.expire_legs()
        b.today = "2026-11-10"
        b.minutes_to_close = 360.0
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=TUE_10) == ["NVDA"]
        assert b.market_orders[0]["side"] == "buy" and b.positions() == {}

    def test_user_net_short_means_nothing_to_sell(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.cancel_all_legs("NVDA")
        b.user_trade("NVDA", "sell", 149)
        assert _due(b) == [] and b.market_orders == []

    def test_sale_before_the_entry_does_not_count_against_it(self):
        b = FakeBroker(quotes=Q, positions={"NVDA": 0.0})
        b.user_trade("NVDA", "buy", 60)
        b.user_trade("NVDA", "sell", 60)
        b._positions.pop("NVDA", None)
        _run(b)
        assert _due(b) == ["NVDA"] and b.market_orders[0]["qty"] == 49.0

    def test_leftover_within_lookback_is_tracked_and_beyond_is_not(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.expire_legs()
        b.minutes_to_close = 360.0
        day8 = datetime(2026, 11, 17, 10, 0, tzinfo=ET)
        b.today = "2026-11-17"
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=day8) == ["NVDA"]
        # documented limit: past the lookback the entry is out of view
        b2 = FakeBroker(quotes=Q)
        _run(b2)
        b2.expire_legs()
        b2.minutes_to_close = 360.0
        far = datetime(2026, 12, 21, 10, 0, tzinfo=ET)
        assert at.maybe_flatten(broker=b2, cfg=_cfg(), now=far) == []

    def test_max_open_positions_counts_broker_holdings(self):
        syms = ["A", "B", "C"]
        b = FakeBroker(quotes={s: QUOTE for s in syms})
        _run(b, [_sig(symbol="A"), _sig(symbol="B")], cfg=_cfg(max_open_positions=2))
        at._MEM.clear()
        recs = _run(b, [_sig(symbol="C")], cfg=_cfg(max_open_positions=2))
        assert recs[0]["reason"] == "max open positions reached"
        b.bracket_exit("A", "tp")
        assert _run(b, [_sig(symbol="C")], cfg=_cfg(max_open_positions=2))[0]["type"] == "trade"


class TestThrottleAndGuard:
    def test_failed_read_does_not_use_up_the_leftover_check(self):
        b = FakeBroker(quotes=Q)
        _run(b)
        b.expire_legs()
        b.today = "2026-11-10"
        b.minutes_to_close = 360.0
        b.fail.add("positions")
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=TUE_10) == []
        b.fail.clear()
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=TUE_10) == ["NVDA"]   # next tick

    def test_guard_loop_cadence_and_survives_errors(self, monkeypatch):
        import src.main as main
        from src.trading import auto_trader

        class Stop:
            def __init__(self, ticks):
                self.left = ticks
            def is_set(self):
                return self.left <= 0
            def wait(self, seconds):
                self.left -= 1
                clock["now"] += seconds

        def run(enabled, ticks):
            calls["n"] = 0
            clock["now"] = 10_000.0
            monkeypatch.setattr(main, "_stop_event", Stop(ticks))
            monkeypatch.setattr(auto_trader, "get_config", lambda: _cfg(enabled=enabled))
            main._auto_trade_guard_loop()
            return calls["n"]

        calls, clock = {"n": 0}, {"now": 0.0}
        def flaky():
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("alpaca 503")
            return []
        monkeypatch.setattr(main.time, "monotonic", lambda: clock["now"])
        monkeypatch.setattr(auto_trader, "maybe_flatten", flaky)
        assert run(enabled=True, ticks=20) == 20      # every 30s tick, despite one error
        assert run(enabled=False, ticks=20) == 20     # same when the switch is off


class TestPersistence:
    def test_refuses_without_a_persistent_store(self):
        b = FakeBroker(quotes=Q)
        assert _run(b, cfg=_cfg(require_persistent_store=True)) == []
        assert b.calls == 0

    def test_status_says_no_persistent_store(self, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "auto_trade_enabled", True)
        monkeypatch.setattr(settings, "auto_trade_require_persistent_store", True)
        monkeypatch.setattr(settings, "alpaca_base_url", "https://paper-api.alpaca.markets")
        assert at.status()["mode"] == "stopped (no persistent store configured)"

    def test_pause_reports_when_it_was_not_saved(self, monkeypatch):
        r = FakeRedis()
        monkeypatch.setattr(at, "_get_redis", lambda: r)
        assert at.set_paused(True) is True
        r.fail_set = True
        assert at.set_paused(False) is False          # not durable
        assert at.is_paused() is False                # but effective in this process
        assert r.data[at._PAUSED_KEY] == "1"          # Redis still says paused

    def test_pause_endpoint_returns_503_when_not_saved(self, monkeypatch):
        r = FakeRedis()
        r.fail_set = True
        monkeypatch.setattr(at, "_get_redis", lambda: r)
        c = TestRoutes()._client()
        resp = c.post("/trading/auto/pause")
        assert resp.status_code == 503 and "restart" in resp.json()["detail"]
        assert at.is_paused()                         # still paused for now

    def test_pause_write_is_retried(self, monkeypatch):
        r = FakeRedis()
        real_set, n = r.set, {"n": 0}
        def flaky(k, v):
            n["n"] += 1
            if n["n"] < 3:
                raise TimeoutError()
            real_set(k, v)
        r.set = flaky
        monkeypatch.setattr(at, "_get_redis", lambda: r)
        assert at.set_paused(True) is True and r.data[at._PAUSED_KEY] == "1"


class TestResumeKey:
    KEY = "correct-horse-battery-staple"

    def _setup(self, monkeypatch, key=KEY):
        from config.settings import settings
        monkeypatch.setattr(settings, "auto_trade_resume_key", key)

    def test_rules(self, monkeypatch):
        self._setup(monkeypatch, key="")
        assert at.can_resume(self.KEY)[0] is False and at.resume_available()[0] is False
        self._setup(monkeypatch, key="short")
        assert at.can_resume("short")[0] is False          # too weak to count as set
        self._setup(monkeypatch)
        assert at.can_resume(None)[0] is False
        assert at.can_resume("")[0] is False
        assert at.can_resume(self.KEY + "x")[0] is False
        assert at.can_resume(self.KEY) == (True, "")

    def test_a_site_login_is_not_enough(self, monkeypatch):
        """Accounts are self-registered: a valid token for any email, even the
        owner's, must not clear the pause."""
        from config.settings import settings
        from src.auth.users import _create_token
        self._setup(monkeypatch)
        monkeypatch.setattr(settings, "jwt_secret", "x" * 40)
        c = TestRoutes()._client()
        c.post("/trading/auto/pause")
        token = _create_token("u1", "owner@example.com")
        r = c.post("/trading/auto/resume", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403 and at.is_paused()

    def test_right_key_resumes(self, monkeypatch):
        self._setup(monkeypatch)
        c = TestRoutes()._client()
        c.post("/trading/auto/pause")
        r = c.post("/trading/auto/resume", headers={"X-Resume-Key": self.KEY})
        assert r.status_code == 200 and r.json()["paused"] is False

    def test_disabled_until_a_key_is_configured(self, monkeypatch):
        self._setup(monkeypatch, key="")
        c = TestRoutes()._client()
        c.post("/trading/auto/pause")
        r = c.post("/trading/auto/resume", headers={"X-Resume-Key": self.KEY})
        assert r.status_code == 403 and "AUTO_TRADE_RESUME_KEY" in r.json()["detail"]
        assert at.is_paused() and "AUTO_TRADE_RESUME_KEY" in at.status()["resume_hint"]


class TestHaltDurability:
    def test_halt_write_is_retried(self, monkeypatch):
        r = FakeRedis()
        real_set, n = r.set, {"n": 0}
        def flaky(k, v):
            if k == at._STATE_KEY:
                n["n"] += 1
                if n["n"] < 3:
                    raise TimeoutError()
            real_set(k, v)
        r.set = flaky
        monkeypatch.setattr(at, "_get_redis", lambda: r)
        b = FakeBroker(equity=99_800.0, quotes=Q)
        _run(b, cfg=_cfg(require_persistent_store=True))
        assert "daily loss limit" in r.data[at._STATE_KEY]
        at._MEM.clear(); at._UNSYNCED.clear()               # restart
        assert at.load_state().halted

    def test_save_state_reports_durability(self, monkeypatch):
        r = FakeRedis()
        monkeypatch.setattr(at, "_get_redis", lambda: r)
        assert at.save_state(at.DayState(date="2026-11-09")) is True
        r.fail_set = True
        assert at.save_state(at.DayState(date="2026-11-09", halted="x")) is False
