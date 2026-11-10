"""Auto-trader: confirmed intraday setups -> Alpaca PAPER bracket orders.

Each new setup from the intraday movers screen (entry / stop / target) is
checked against a fixed set of limits and, if it passes, sent as a market
bracket order: entry now, stop-loss and take-profit attached.

Safety properties, all enforced in code:
  * Off by default. `settings.auto_trade_enabled` is the master switch; the
    API can pause and resume, but cannot enable what the owner has not.
  * Paper only. Refuses to do anything unless the Alpaca endpoint is the
    paper one.
  * Sized by risk: shares = dollars at risk / (entry - stop), capped by a
    maximum position value and buying power.
  * Daily caps: trades per day, open positions, and a day-loss halt.
  * No entries late in the session, and the bot's own positions are closed
    before the close. It only ever closes symbols it opened itself.
  * Every decision (trade or skip, with the reason) is logged per day.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dtime
from typing import Protocol
from zoneinfo import ZoneInfo

from config.settings import settings
from src.data.models import IntradayResult, Signal, SignalAction
from src.data.redis_store import _get_redis

logger = logging.getLogger("mse.auto_trader")

ET = ZoneInfo("America/New_York")
SESSION_OPEN = dtime(9, 35)   # matches the intraday loop's gate
SESSION_CLOSE = dtime(16, 0)

_STATE_KEY = "mse:auto_trade_state"
_PAUSED_KEY = "mse:auto_trade_paused"
_MAX_LOG = 200

# Fallback store when Redis is not configured (local runs, tests)
_MEM: dict[str, str] = {}


# ----------------------------------------------------------------- config

def _parse_hhmm(value: str, default: dtime) -> dtime:
    try:
        hh, mm = value.strip().split(":")
        return dtime(int(hh), int(mm))
    except Exception:
        return default


@dataclass
class AutoTradeConfig:
    enabled: bool = False
    risk_per_trade_usd: float = 50.0
    max_position_usd: float = 5000.0
    max_trades_per_day: int = 5
    max_open_positions: int = 3
    daily_loss_limit_usd: float = 150.0
    allow_shorts: bool = False
    min_confidence: float = 0.6
    max_chase_frac: float = 0.25
    min_rr_at_quote: float = 1.2
    last_entry: dtime = dtime(15, 30)
    flatten_at: dtime = dtime(15, 45)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["last_entry"] = self.last_entry.strftime("%H:%M")
        d["flatten_at"] = self.flatten_at.strftime("%H:%M")
        return d


def get_config() -> AutoTradeConfig:
    s = settings
    return AutoTradeConfig(
        enabled=bool(s.auto_trade_enabled),
        risk_per_trade_usd=float(s.auto_trade_risk_per_trade_usd),
        max_position_usd=float(s.auto_trade_max_position_usd),
        max_trades_per_day=int(s.auto_trade_max_trades_per_day),
        max_open_positions=int(s.auto_trade_max_open_positions),
        daily_loss_limit_usd=float(s.auto_trade_daily_loss_limit_usd),
        allow_shorts=bool(s.auto_trade_allow_shorts),
        min_confidence=float(s.auto_trade_min_confidence),
        max_chase_frac=float(s.auto_trade_max_chase_frac),
        min_rr_at_quote=float(s.auto_trade_min_rr_at_quote),
        last_entry=_parse_hhmm(s.auto_trade_last_entry_et, dtime(15, 30)),
        flatten_at=_parse_hhmm(s.auto_trade_flatten_et, dtime(15, 45)),
    )


# ----------------------------------------------------------------- broker

class Broker(Protocol):
    """The small surface the auto-trader needs. A second broker can be
    added by implementing this, without touching the decision logic."""

    def is_paper(self) -> bool: ...
    def account(self) -> dict: ...                 # equity, last_equity, buying_power
    def positions(self) -> dict[str, float]: ...   # symbol -> signed qty
    def quote(self, symbol: str) -> tuple[float, float]: ...  # (bid, ask)
    def open_order_ids(self, symbol: str) -> list[str]: ...
    def submit_bracket(
        self, symbol: str, side: str, qty: int, stop: float, target: float,
        client_order_id: str,
    ) -> dict: ...
    def cancel_order(self, order_id: str) -> None: ...
    def close_position(self, symbol: str) -> None: ...


class AlpacaPaperBroker:
    """Alpaca implementation. `is_paper` is derived from the configured
    endpoint; the trader refuses to act when it is False."""

    def is_paper(self) -> bool:
        return "paper" in (settings.alpaca_base_url or "")

    def _client(self):
        from src.data.client import _get_trading_client
        return _get_trading_client()

    def account(self) -> dict:
        a = self._client().get_account()
        return {
            "equity": float(a.equity),
            "last_equity": float(a.last_equity),
            "buying_power": float(a.buying_power),
        }

    def positions(self) -> dict[str, float]:
        return {p.symbol: float(p.qty) for p in self._client().get_all_positions()}

    def quote(self, symbol: str) -> tuple[float, float]:
        from src.data import client as data_client
        q = data_client.get_latest_quote(symbol)
        return float(q["bid"]), float(q["ask"])

    def open_order_ids(self, symbol: str) -> list[str]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest
        orders = self._client().get_orders(
            GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
        )
        return [str(o.id) for o in orders]

    def submit_bracket(
        self, symbol: str, side: str, qty: int, stop: float, target: float,
        client_order_id: str,
    ) -> dict:
        from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
        from alpaca.trading.requests import (
            MarketOrderRequest, StopLossRequest, TakeProfitRequest,
        )
        order = self._client().submit_order(
            MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=round(target, 2)),
                stop_loss=StopLossRequest(stop_price=round(stop, 2)),
                client_order_id=client_order_id,
            )
        )
        return {"order_id": str(order.id), "status": order.status.value}

    def cancel_order(self, order_id: str) -> None:
        self._client().cancel_order_by_id(order_id)

    def close_position(self, symbol: str) -> None:
        self._client().close_position(symbol)


# ------------------------------------------------------------------ state

@dataclass
class DayState:
    date: str = ""
    trades: list[dict] = field(default_factory=list)
    skips: list[dict] = field(default_factory=list)
    halted: str = ""       # reason the bot stopped for the day, "" if running
    flattened: bool = False

    def traded_symbols(self) -> set[str]:
        return {t["symbol"] for t in self.trades}


def _store_get(key: str) -> str | None:
    redis = _get_redis()
    if redis is None:
        return _MEM.get(key)
    try:
        raw = redis.get(key)
        if raw is None:
            return None
        return raw if isinstance(raw, str) else json.dumps(raw)
    except Exception as e:
        logger.warning("Auto-trade state read failed: %s", e)
        return _MEM.get(key)


def _store_set(key: str, value: str) -> None:
    _MEM[key] = value
    redis = _get_redis()
    if redis is None:
        return
    try:
        redis.set(key, value)
    except Exception as e:
        logger.warning("Auto-trade state write failed: %s", e)


def load_state() -> DayState:
    raw = _store_get(_STATE_KEY)
    if not raw:
        return DayState()
    try:
        d = json.loads(raw)
        return DayState(
            date=str(d.get("date", "")),
            trades=list(d.get("trades", [])),
            skips=list(d.get("skips", [])),
            halted=str(d.get("halted", "")),
            flattened=bool(d.get("flattened", False)),
        )
    except Exception as e:
        logger.warning("Auto-trade state unreadable, starting empty: %s", e)
        return DayState()


def save_state(state: DayState) -> None:
    state.skips = state.skips[-_MAX_LOG:]
    _store_set(_STATE_KEY, json.dumps(asdict(state)))


def is_paused() -> bool:
    return _store_get(_PAUSED_KEY) == "1"


def set_paused(paused: bool) -> None:
    _store_set(_PAUSED_KEY, "1" if paused else "0")


# --------------------------------------------------------------- decisions

@dataclass
class Decision:
    trade: bool
    reason: str
    qty: int = 0
    ref_price: float = 0.0
    halt: bool = False   # this reason should stop the bot for the rest of the day


def _now_et(now: datetime | None) -> datetime:
    return (now or datetime.now(tz=ET)).astimezone(ET)


def in_entry_window(cfg: AutoTradeConfig, now: datetime | None = None) -> bool:
    n = _now_et(now)
    if n.weekday() >= 5:
        return False
    return SESSION_OPEN <= n.time() < cfg.last_entry


def size_position(
    entry: float, stop: float, cfg: AutoTradeConfig, buying_power: float
) -> int:
    """Whole shares such that a stop-out loses about `risk_per_trade_usd`,
    capped by the position-value limit and available buying power."""
    risk_per_share = abs(entry - stop)
    if entry <= 0 or risk_per_share <= 0:
        return 0
    by_risk = cfg.risk_per_trade_usd / risk_per_share
    by_value = cfg.max_position_usd / entry
    by_power = max(buying_power, 0.0) / entry
    qty = math.floor(min(by_risk, by_value, by_power))
    return max(qty, 0)


def evaluate(
    signal: Signal,
    row: IntradayResult | None,
    cfg: AutoTradeConfig,
    state: DayState,
    account: dict,
    positions: dict[str, float],
    quote: tuple[float, float] | None,
    now: datetime | None = None,
    has_open_orders: bool = False,
) -> Decision:
    """Decide whether one signal becomes an order. Pure: no I/O."""
    if state.halted:
        return Decision(False, f"halted: {state.halted}")
    if not in_entry_window(cfg, now):
        return Decision(False, "outside entry window")

    day_pnl = float(account.get("equity", 0)) - float(account.get("last_equity", 0))
    if day_pnl <= -abs(cfg.daily_loss_limit_usd):
        return Decision(False, f"daily loss limit hit ({day_pnl:.2f})", halt=True)

    if len(state.trades) >= cfg.max_trades_per_day:
        return Decision(False, "max trades per day reached")

    is_buy = signal.action == SignalAction.BUY
    if not is_buy and not cfg.allow_shorts:
        return Decision(False, "shorts disabled")
    if signal.confidence < cfg.min_confidence:
        return Decision(False, f"confidence {signal.confidence:.2f} below minimum")
    if row is not None and row.earnings_soon:
        return Decision(False, "earnings within a day")

    sym = signal.symbol
    if sym in state.traded_symbols():
        return Decision(False, "already traded this symbol today")
    if abs(positions.get(sym, 0.0)) > 0:
        return Decision(False, "position already open in this symbol")
    if has_open_orders:
        return Decision(False, "open orders already exist for this symbol")

    open_bot = sum(1 for s in state.traded_symbols() if abs(positions.get(s, 0.0)) > 0)
    if open_bot >= cfg.max_open_positions:
        return Decision(False, "max open positions reached")

    if not quote or quote[0] <= 0 or quote[1] <= 0 or quote[1] < quote[0]:
        return Decision(False, "no usable quote")
    ref = quote[1] if is_buy else quote[0]   # what a market order would pay / receive

    entry, stop, target = signal.entry, signal.stop_loss, signal.target
    risk_signal = (entry - stop) if is_buy else (stop - entry)
    if risk_signal <= 0:
        return Decision(False, "signal has no risk distance")

    drift = (ref - entry) if is_buy else (entry - ref)
    if drift > cfg.max_chase_frac * risk_signal:
        return Decision(False, f"price moved past entry ({ref:.2f} vs {entry:.2f})")

    risk_now = (ref - stop) if is_buy else (stop - ref)
    reward_now = (target - ref) if is_buy else (ref - target)
    # Alpaca rejects a bracket whose legs are not at least a cent beyond the price
    if risk_now < 0.02 or reward_now < 0.02:
        return Decision(False, "quote is at or beyond stop/target")
    if reward_now / risk_now < cfg.min_rr_at_quote:
        return Decision(False, f"reward:risk at quote {reward_now / risk_now:.2f} too low")

    qty = size_position(ref, stop, cfg, float(account.get("buying_power", 0)))
    if qty < 1:
        return Decision(False, "position size rounds to zero")

    return Decision(True, "ok", qty=qty, ref_price=ref)


# ------------------------------------------------------------------ actions

def _roll_day(state: DayState, today: str) -> DayState:
    """Start a fresh day's log."""
    if state.date == today:
        return state
    return DayState(date=today)


def _skip(state: DayState, signal: Signal, reason: str, now: datetime) -> dict:
    rec = {
        "time": now.strftime("%H:%M:%S"),
        "symbol": signal.symbol,
        "setup": signal.setup_type.value,
        "action": signal.action.value,
        "reason": reason,
    }
    state.skips.append(rec)
    return rec


def handle_new_setups(
    signals: list[Signal],
    rows: dict[str, IntradayResult] | None = None,
    broker: Broker | None = None,
    cfg: AutoTradeConfig | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Evaluate each new setup and place bracket orders for those that pass.

    Returns the list of decision records (trades and skips) for this call.
    Does nothing, and touches no broker, when disabled or paused.
    """
    cfg = cfg or get_config()
    if not signals or not cfg.enabled or is_paused():
        return []

    broker = broker or AlpacaPaperBroker()
    if not broker.is_paper():
        logger.error("Auto-trader refused: Alpaca endpoint is not the paper one")
        return []

    n = _now_et(now)
    today = n.date().isoformat()
    prior = load_state()
    if prior.date and prior.date != today and prior.trades and not prior.flattened:
        # Yesterday's positions were never closed (server down at the close).
        # Keep that record until maybe_flatten succeeds; rolling the day now
        # would forget which symbols the bot owns.
        logger.warning(
            "Auto-trader: %s positions not flattened yet, no new entries", prior.date
        )
        return []
    state = _roll_day(prior, today)
    rows = rows or {}
    records: list[dict] = []

    try:
        account = broker.account()
        positions = dict(broker.positions())
    except Exception as e:
        logger.warning("Auto-trader: account/positions unavailable, skipping cycle: %s", e)
        return []

    for signal in sorted(signals, key=lambda s: s.confidence, reverse=True):
        sym = signal.symbol
        quote = None
        has_orders = False
        try:
            quote = broker.quote(sym)
            has_orders = bool(broker.open_order_ids(sym))
        except Exception as e:
            logger.debug("Auto-trader: quote/orders lookup failed for %s: %s", sym, e)

        decision = evaluate(
            signal, rows.get(sym), cfg, state, account, positions, quote,
            now=n, has_open_orders=has_orders,
        )
        if decision.halt:
            state.halted = decision.reason
        if not decision.trade:
            records.append({"type": "skip", **_skip(state, signal, decision.reason, n)})
            continue

        side = "buy" if signal.action == SignalAction.BUY else "sell"
        coid = f"mse-auto-{today}-{sym}-{signal.setup_type.value}"
        try:
            result = broker.submit_bracket(
                sym, side, decision.qty, signal.stop_loss, signal.target, coid
            )
        except Exception as e:
            logger.warning("Auto-trader: order rejected for %s: %s", sym, e)
            records.append(
                {"type": "skip", **_skip(state, signal, f"order rejected: {e}"[:200], n)}
            )
            continue

        trade = {
            "time": n.strftime("%H:%M:%S"),
            "symbol": sym,
            "setup": signal.setup_type.value,
            "side": side,
            "qty": decision.qty,
            "signal_entry": signal.entry,
            "quote_at_order": round(decision.ref_price, 2),
            "stop": signal.stop_loss,
            "target": signal.target,
            "risk_usd": round(abs(decision.ref_price - signal.stop_loss) * decision.qty, 2),
            "order_id": result.get("order_id", ""),
            "client_order_id": coid,
            "status": result.get("status", ""),
        }
        state.trades.append(trade)
        positions[sym] = float(decision.qty if side == "buy" else -decision.qty)
        records.append({"type": "trade", **trade})
        logger.info(
            "Auto-trade (paper): %s %d %s stop %.2f target %.2f",
            side.upper(), decision.qty, sym, signal.stop_loss, signal.target,
        )

    save_state(state)
    return records


def _wait_orders_cleared(
    broker: Broker, symbol: str, tries: int = 10, delay: float = 0.5
) -> bool:
    """Poll until the symbol has no open orders (about 5 seconds at most)."""
    for attempt in range(tries):
        if not broker.open_order_ids(symbol):
            return True
        if attempt < tries - 1:
            time.sleep(delay)
    return False


def maybe_flatten(
    broker: Broker | None = None,
    cfg: AutoTradeConfig | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Close the bot's own positions late in the session.

    Runs when it is past the flatten time on a weekday, or when the saved
    state is from an earlier day and was never flattened (server was down
    at the close). Runs even when paused or disabled, so a pause never
    strands a position overnight. Only symbols the bot opened are touched.
    Returns the symbols it closed.
    """
    cfg = cfg or get_config()
    state = load_state()
    if not state.trades or state.flattened:
        return []

    n = _now_et(now)
    today = n.date().isoformat()
    stale = bool(state.date) and state.date != today
    due = n.weekday() < 5 and cfg.flatten_at <= n.time() < SESSION_CLOSE
    if not (stale or due):
        return []

    broker = broker or AlpacaPaperBroker()
    if not broker.is_paper():
        logger.error("Auto-trader flatten refused: Alpaca endpoint is not the paper one")
        return []

    try:
        positions = broker.positions()
    except Exception as e:
        logger.warning("Auto-trader flatten: positions unavailable: %s", e)
        return []

    closed: list[str] = []
    failed = False
    for sym in sorted(state.traded_symbols()):
        try:
            # Bracket legs hold the shares; cancel them before closing
            for oid in broker.open_order_ids(sym):
                broker.cancel_order(oid)
            if abs(positions.get(sym, 0.0)) > 0:
                # Cancels are asynchronous at the broker: closing while a leg
                # is still pending-cancel is rejected for reserved shares.
                if not _wait_orders_cleared(broker, sym):
                    raise RuntimeError("bracket legs still open after cancel")
                broker.close_position(sym)
                closed.append(sym)
        except Exception as e:
            failed = True
            logger.warning("Auto-trader flatten failed for %s: %s", sym, e)

    # Leave `flattened` False on any failure so the next cycle retries
    state.flattened = not failed
    save_state(state)
    if closed:
        logger.info("Auto-trader flattened: %s", ", ".join(closed))
    return closed


def status() -> dict:
    """Snapshot for the API: config, switches, and today's log."""
    cfg = get_config()
    state = load_state()
    paper = AlpacaPaperBroker().is_paper()
    paused = is_paused()
    if not cfg.enabled:
        mode = "off"
    elif not paper:
        mode = "refusing (not a paper endpoint)"
    elif paused:
        mode = "paused"
    elif state.halted:
        mode = "halted"
    else:
        mode = "running"
    return {
        "mode": mode,
        "enabled": cfg.enabled,
        "paused": paused,
        "paper": paper,
        "config": cfg.to_dict(),
        "date": state.date,
        "halted": state.halted,
        "flattened": state.flattened,
        "trades": state.trades,
        "skips": state.skips[-50:],
    }
