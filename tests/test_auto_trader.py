"""Tests for the paper auto-trader (src/trading/auto_trader.py).

A fake broker records every call, so nothing here reaches Alpaca, and the
state store is forced to the in-memory fallback so nothing reaches Redis.
"""

from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import pytest

from src.data.models import IntradayResult, SetupType, Signal, SignalAction
from src.trading import auto_trader as at

ET = ZoneInfo("America/New_York")
MON_11 = datetime(2026, 11, 9, 11, 0, tzinfo=ET)       # Monday, mid-session
MON_1546 = datetime(2026, 11, 9, 15, 46, tzinfo=ET)    # past the flatten time
TUE_10 = datetime(2026, 11, 10, 10, 0, tzinfo=ET)


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch):
    monkeypatch.setattr(at, "_get_redis", lambda: None)
    at._MEM.clear()
    yield
    at._MEM.clear()


class FakeBroker:
    def __init__(self, paper=True, equity=100_000.0, last_equity=100_000.0,
                 buying_power=200_000.0, positions=None, quotes=None,
                 open_orders=None, reject=None):
        self.paper = paper
        self._account = {"equity": equity, "last_equity": last_equity,
                         "buying_power": buying_power}
        self._positions = dict(positions or {})
        self._quotes = dict(quotes or {})
        self._open_orders = {k: list(v) for k, v in (open_orders or {}).items()}
        self._reject = set(reject or [])
        self.submitted = []
        self.cancelled = []
        self.closed = []
        self.calls = 0

    def is_paper(self):
        return self.paper

    def account(self):
        self.calls += 1
        return dict(self._account)

    def positions(self):
        self.calls += 1
        return dict(self._positions)

    def quote(self, symbol):
        self.calls += 1
        return self._quotes[symbol]

    def open_order_ids(self, symbol):
        self.calls += 1
        return list(self._open_orders.get(symbol, []))

    def submit_bracket(self, symbol, side, qty, stop, target, client_order_id):
        self.calls += 1
        if symbol in self._reject:
            raise RuntimeError("insufficient buying power")
        self.submitted.append(dict(symbol=symbol, side=side, qty=qty, stop=stop,
                                   target=target, client_order_id=client_order_id))
        self._positions[symbol] = qty if side == "buy" else -qty
        self._open_orders[symbol] = [f"{symbol}-tp", f"{symbol}-sl"]
        return {"order_id": f"oid-{symbol}", "status": "accepted"}

    def cancel_order(self, order_id):
        self.calls += 1
        self.cancelled.append(order_id)
        for ids in self._open_orders.values():
            if order_id in ids:
                ids.remove(order_id)

    def close_position(self, symbol):
        self.calls += 1
        self.closed.append(symbol)
        self._positions.pop(symbol, None)


def _sig(symbol="NVDA", action=SignalAction.BUY, entry=100.0, stop=99.0,
         target=102.0, confidence=0.65, setup=SetupType.HIGHER_LOW):
    return Signal(symbol=symbol, action=action, setup_type=setup, reason="t",
                  entry=entry, stop_loss=stop, target=target,
                  rr_ratio=abs(target - entry) / abs(entry - stop),
                  confidence=confidence, timestamp=MON_11)


def _row(symbol="NVDA", earnings_soon=False):
    return IntradayResult(symbol=symbol, price=100.0, change_pct=3.0, atr_pct=4.0,
                          rvol=2.0, volume=1, avg_volume=1, day_high=102.0,
                          day_low=98.0, vwap_dist_pct=0.1, score=50.0,
                          earnings_soon=earnings_soon)


def _cfg(**kw):
    base = dict(enabled=True, risk_per_trade_usd=50.0, max_position_usd=5000.0,
                max_trades_per_day=5, max_open_positions=3,
                daily_loss_limit_usd=150.0, allow_shorts=False, min_confidence=0.6,
                max_chase_frac=0.25, min_rr_at_quote=1.2,
                last_entry=dtime(15, 30), flatten_at=dtime(15, 45))
    base.update(kw)
    return at.AutoTradeConfig(**base)


Q = {"NVDA": (99.98, 100.02)}   # tight quote right at the signal entry


# ------------------------------------------------------------------ sizing

class TestSizing:
    def test_risk_based(self):
        # $50 risk / $1.00 per share = 50 shares ($5,000, at the value cap)
        assert at.size_position(100.0, 99.0, _cfg(), 1e9) == 50

    def test_capped_by_position_value(self):
        # tiny stop distance would mean 5,000 shares; value cap allows 50
        assert at.size_position(100.0, 99.99, _cfg(), 1e9) == 50

    def test_capped_by_buying_power(self):
        assert at.size_position(100.0, 99.0, _cfg(), 1234.0) == 12

    def test_zero_risk_distance(self):
        assert at.size_position(100.0, 100.0, _cfg(), 1e9) == 0

    def test_negative_or_zero_inputs(self):
        assert at.size_position(0.0, -1.0, _cfg(), 1e9) == 0
        assert at.size_position(100.0, 99.0, _cfg(), -500.0) == 0

    def test_expensive_stock_rounds_to_zero(self):
        # one share of a $9,000 stock exceeds the $5,000 cap
        assert at.size_position(9000.0, 8990.0, _cfg(), 1e9) == 0


# ---------------------------------------------------------------- evaluate

def _eval(signal=None, row=None, cfg=None, state=None, account=None,
          positions=None, quote=Q["NVDA"], now=MON_11, has_open_orders=False):
    return at.evaluate(
        signal or _sig(), row, cfg or _cfg(), state or at.DayState(date="2026-11-09"),
        account or {"equity": 100_000.0, "last_equity": 100_000.0, "buying_power": 200_000.0},
        positions or {}, quote, now=now, has_open_orders=has_open_orders,
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

    def test_daily_loss_limit_halts(self):
        d = _eval(account={"equity": 99_850.0, "last_equity": 100_000.0,
                           "buying_power": 1e6})
        assert not d.trade and d.halt and "daily loss limit" in d.reason

    def test_just_inside_loss_limit_still_trades(self):
        d = _eval(account={"equity": 99_851.0, "last_equity": 100_000.0,
                           "buying_power": 1e6})
        assert d.trade

    def test_already_halted(self):
        st = at.DayState(date="2026-11-09", halted="daily loss limit hit")
        assert not _eval(state=st).trade

    def test_max_trades_per_day(self):
        st = at.DayState(date="2026-11-09",
                         trades=[{"symbol": f"S{i}"} for i in range(5)])
        assert _eval(state=st).reason == "max trades per day reached"

    def test_short_blocked_by_default(self):
        s = _sig(action=SignalAction.SELL, entry=100.0, stop=101.0, target=98.0)
        assert _eval(signal=s).reason == "shorts disabled"

    def test_short_allowed_uses_bid(self):
        s = _sig(action=SignalAction.SELL, entry=100.0, stop=101.0, target=98.0)
        d = _eval(signal=s, cfg=_cfg(allow_shorts=True))
        assert d.trade and d.ref_price == pytest.approx(99.98)

    def test_low_confidence(self):
        assert not _eval(signal=_sig(confidence=0.5)).trade

    def test_earnings_soon(self):
        assert _eval(row=_row(earnings_soon=True)).reason == "earnings within a day"

    def test_already_traded_symbol_today(self):
        st = at.DayState(date="2026-11-09", trades=[{"symbol": "NVDA"}])
        assert _eval(state=st).reason == "already traded this symbol today"

    def test_existing_position_not_opened_by_bot(self):
        assert _eval(positions={"NVDA": 10.0}).reason == "position already open in this symbol"

    def test_existing_short_position_counts(self):
        assert not _eval(positions={"NVDA": -10.0}).trade

    def test_existing_open_orders(self):
        assert not _eval(has_open_orders=True).trade

    def test_max_open_positions_counts_only_bot_positions(self):
        st = at.DayState(date="2026-11-09",
                         trades=[{"symbol": "A"}, {"symbol": "B"}, {"symbol": "C"}])
        # three bot symbols still open -> blocked
        assert _eval(state=st, positions={"A": 1, "B": 1, "C": 1}).reason == \
            "max open positions reached"
        # one of them already exited -> allowed, unrelated holdings ignored
        assert _eval(state=st, positions={"A": 1, "B": 1, "ZZZ": 500}).trade

    def test_no_quote(self):
        assert _eval(quote=None).reason == "no usable quote"

    def test_zero_or_crossed_quote(self):
        assert not _eval(quote=(0.0, 100.0)).trade
        assert not _eval(quote=(100.5, 100.0)).trade

    def test_price_ran_past_entry(self):
        # risk is 1.00; ask 100.30 is 30% of risk past the entry
        d = _eval(quote=(100.28, 100.30))
        assert not d.trade and "moved past entry" in d.reason

    def test_price_below_entry_is_fine_if_above_stop(self):
        assert _eval(quote=(99.58, 99.60)).trade

    def test_quote_at_or_through_stop(self):
        assert _eval(quote=(98.98, 99.00)).reason == "quote is at or beyond stop/target"

    def test_reward_to_risk_at_quote_too_low(self):
        # entry 100, stop 99, target 101.5; at ask 100.24 reward 1.26 / risk 1.24
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
        assert at.handle_new_setups([_sig()], broker=b, cfg=_cfg(enabled=False), now=MON_11) == []
        assert b.calls == 0 and at.load_state().trades == []

    def test_paused_touches_nothing(self):
        at.set_paused(True)
        b = FakeBroker(quotes=Q)
        assert at.handle_new_setups([_sig()], broker=b, cfg=_cfg(), now=MON_11) == []
        assert b.calls == 0

    def test_empty_signal_list(self):
        b = FakeBroker(quotes=Q)
        assert at.handle_new_setups([], broker=b, cfg=_cfg(), now=MON_11) == []
        assert b.calls == 0

    def test_refuses_non_paper_endpoint(self):
        b = FakeBroker(paper=False, quotes=Q)
        assert at.handle_new_setups([_sig()], broker=b, cfg=_cfg(), now=MON_11) == []
        assert b.submitted == [] and b.calls == 0

    def test_places_bracket_with_signal_levels(self):
        b = FakeBroker(quotes=Q)
        recs = at.handle_new_setups([_sig()], {"NVDA": _row()}, broker=b, cfg=_cfg(), now=MON_11)
        assert [r["type"] for r in recs] == ["trade"]
        assert b.submitted == [dict(symbol="NVDA", side="buy", qty=49, stop=99.0,
                                    target=102.0,
                                    client_order_id="mse-auto-2026-11-09-NVDA-higher_low")]
        st = at.load_state()
        assert st.date == "2026-11-09" and len(st.trades) == 1
        assert st.trades[0]["risk_usd"] == pytest.approx(49 * 1.02, abs=0.01)

    def test_same_symbol_twice_in_one_call_trades_once(self):
        b = FakeBroker(quotes=Q)
        sigs = [_sig(setup=SetupType.HIGHER_LOW), _sig(setup=SetupType.VWAP_RECLAIM, confidence=0.7)]
        recs = at.handle_new_setups(sigs, broker=b, cfg=_cfg(), now=MON_11)
        assert len(b.submitted) == 1
        assert b.submitted[0]["client_order_id"].endswith("vwap_reclaim")  # higher confidence first
        assert [r["type"] for r in recs] == ["trade", "skip"]

    def test_second_call_does_not_retrade_symbol(self):
        b = FakeBroker(quotes=Q)
        at.handle_new_setups([_sig()], broker=b, cfg=_cfg(), now=MON_11)
        at.handle_new_setups([_sig(setup=SetupType.RANGE_BREAKOUT)], broker=b, cfg=_cfg(), now=MON_11)
        assert len(b.submitted) == 1

    def test_stops_at_max_trades_per_day(self):
        syms = ["A", "B", "C"]
        b = FakeBroker(quotes={s: Q["NVDA"] for s in syms})
        recs = at.handle_new_setups([_sig(symbol=s) for s in syms], broker=b,
                                    cfg=_cfg(max_trades_per_day=2), now=MON_11)
        assert len(b.submitted) == 2
        assert recs[-1]["reason"] == "max trades per day reached"

    def test_loss_limit_halts_for_rest_of_day(self):
        b = FakeBroker(equity=99_800.0, quotes={"NVDA": Q["NVDA"], "AMD": Q["NVDA"]})
        at.handle_new_setups([_sig()], broker=b, cfg=_cfg(), now=MON_11)
        assert at.load_state().halted
        # account recovers, but the halt holds until the next day
        b._account["equity"] = 100_500.0
        at.handle_new_setups([_sig(symbol="AMD")], broker=b, cfg=_cfg(), now=MON_11)
        assert b.submitted == []

    def test_broker_rejection_is_logged_not_raised(self):
        b = FakeBroker(quotes=Q, reject={"NVDA"})
        recs = at.handle_new_setups([_sig()], broker=b, cfg=_cfg(), now=MON_11)
        assert recs[0]["type"] == "skip" and "order rejected" in recs[0]["reason"]
        assert at.load_state().trades == []

    def test_missing_quote_skips_without_crashing(self):
        b = FakeBroker(quotes={})
        recs = at.handle_new_setups([_sig()], broker=b, cfg=_cfg(), now=MON_11)
        assert recs[0]["reason"] == "no usable quote" and b.submitted == []

    def test_account_failure_skips_cycle(self):
        b = FakeBroker(quotes=Q)
        b.account = lambda: (_ for _ in ()).throw(RuntimeError("503"))
        assert at.handle_new_setups([_sig()], broker=b, cfg=_cfg(), now=MON_11) == []
        assert b.submitted == []

    def test_new_day_resets_counts(self):
        b = FakeBroker(quotes=Q)
        at.handle_new_setups([_sig()], broker=b, cfg=_cfg(), now=MON_11)
        at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546)
        at.handle_new_setups([_sig()], broker=b, cfg=_cfg(), now=TUE_10)
        st = at.load_state()
        assert st.date == "2026-11-10" and len(st.trades) == 1 and not st.flattened
        assert len(b.submitted) == 2

    def test_no_entries_while_yesterday_is_unflattened(self):
        b = FakeBroker(quotes=Q)
        at.handle_new_setups([_sig()], broker=b, cfg=_cfg(), now=MON_11)
        # server was down at the close: Tuesday arrives with Monday still open
        recs = at.handle_new_setups([_sig(symbol="AMD")], broker=b, cfg=_cfg(), now=TUE_10)
        assert recs == [] and len(b.submitted) == 1
        assert at.load_state().date == "2026-11-09"   # record of ownership kept


# ------------------------------------------------------------------ flatten

class TestFlatten:
    def _open_trade(self, b):
        at.handle_new_setups([_sig()], broker=b, cfg=_cfg(), now=MON_11)

    def test_not_before_flatten_time(self):
        b = FakeBroker(quotes=Q)
        self._open_trade(b)
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_11) == []
        assert b.closed == []

    def test_cancels_legs_then_closes_only_bot_symbols(self):
        b = FakeBroker(quotes=Q, positions={"AAPL": 100.0})   # AAPL is not the bot's
        self._open_trade(b)
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546) == ["NVDA"]
        assert b.cancelled == ["NVDA-tp", "NVDA-sl"]
        assert b.closed == ["NVDA"]
        assert "AAPL" in b.positions()
        assert at.load_state().flattened

    def test_runs_once(self):
        b = FakeBroker(quotes=Q)
        self._open_trade(b)
        at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546)
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546) == []
        assert b.closed == ["NVDA"]

    def test_runs_even_when_paused_or_disabled(self):
        b = FakeBroker(quotes=Q)
        self._open_trade(b)
        at.set_paused(True)
        assert at.maybe_flatten(broker=b, cfg=_cfg(enabled=False), now=MON_1546) == ["NVDA"]

    def test_position_already_exited_by_bracket(self):
        b = FakeBroker(quotes=Q)
        self._open_trade(b)
        b._positions.pop("NVDA")
        b._open_orders["NVDA"] = []
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546) == []
        assert b.closed == [] and at.load_state().flattened

    def test_nothing_traded_touches_nothing(self):
        b = FakeBroker(quotes=Q, positions={"AAPL": 100.0})
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546) == []
        assert b.calls == 0

    def test_failure_retries_next_cycle(self):
        b = FakeBroker(quotes=Q)
        self._open_trade(b)
        real_close = b.close_position
        b.close_position = lambda s: (_ for _ in ()).throw(RuntimeError("timeout"))
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546) == []
        assert not at.load_state().flattened
        b.close_position = real_close
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546) == ["NVDA"]

    def test_waits_for_slow_cancels_before_closing(self, monkeypatch):
        monkeypatch.setattr(at.time, "sleep", lambda s: None)
        b = FakeBroker(quotes=Q)
        self._open_trade(b)
        b.cancel_order = lambda oid: b.cancelled.append(oid)   # cancel lags
        polls = {"n": 0}
        def slow_orders(sym):
            polls["n"] += 1
            return ["NVDA-tp"] if polls["n"] <= 3 else []
        b.open_order_ids = slow_orders
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546) == ["NVDA"]
        assert polls["n"] == 4

    def test_legs_never_clear_does_not_close_and_retries(self, monkeypatch):
        monkeypatch.setattr(at.time, "sleep", lambda s: None)
        b = FakeBroker(quotes=Q)
        self._open_trade(b)
        b.cancel_order = lambda oid: None                      # cancel never lands
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546) == []
        assert b.closed == [] and not at.load_state().flattened

    def test_stale_day_is_flattened_next_morning(self):
        b = FakeBroker(quotes=Q)
        self._open_trade(b)
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=TUE_10) == ["NVDA"]

    def test_refuses_non_paper_endpoint(self):
        b = FakeBroker(quotes=Q)
        self._open_trade(b)
        b.paper = False
        assert at.maybe_flatten(broker=b, cfg=_cfg(), now=MON_1546) == []
        assert b.closed == []


# ------------------------------------------------------------ status / misc

class TestStatusAndConfig:
    def test_default_settings_are_off(self):
        from config.settings import Settings
        assert Settings.model_fields["auto_trade_enabled"].default is False
        assert Settings.model_fields["auto_trade_allow_shorts"].default is False

    def test_status_modes(self, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "auto_trade_enabled", False)
        assert at.status()["mode"] == "off"
        monkeypatch.setattr(settings, "auto_trade_enabled", True)
        monkeypatch.setattr(settings, "alpaca_base_url", "https://paper-api.alpaca.markets")
        assert at.status()["mode"] == "running"
        at.set_paused(True)
        assert at.status()["mode"] == "paused"
        at.set_paused(False)
        monkeypatch.setattr(settings, "alpaca_base_url", "https://api.alpaca.markets")
        assert at.status()["mode"].startswith("refusing")

    def test_resume_does_not_enable(self, monkeypatch):
        from config.settings import settings
        monkeypatch.setattr(settings, "auto_trade_enabled", False)
        at.set_paused(False)
        b = FakeBroker(quotes=Q)
        assert at.handle_new_setups([_sig()], broker=b, now=MON_11) == []
        assert b.calls == 0

    def test_bad_time_setting_falls_back(self):
        assert at._parse_hhmm("nonsense", dtime(15, 30)) == dtime(15, 30)
        assert at._parse_hhmm("14:05", dtime(15, 30)) == dtime(14, 5)

    def test_corrupt_state_starts_empty(self):
        at._MEM[at._STATE_KEY] = "{not json"
        assert at.load_state().trades == []
