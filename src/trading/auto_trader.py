"""Auto-trader: confirmed intraday setups -> Alpaca PAPER bracket orders.

Each new setup from the intraday movers screen (entry / stop / target) is
checked against a fixed set of limits and, if it passes, sent as a market
bracket order: entry now, stop-loss and take-profit attached.

Safety properties, all enforced in code:
  * Off by default. `settings.auto_trade_enabled` is the master switch; the
    API can pause and resume, but cannot enable what the owner has not.
  * Paper only. Refuses to act unless the Alpaca endpoint is the paper one.
  * The broker is the source of truth. What the bot owns, and how many
    trades it has made today, are derived from Alpaca orders carrying the
    bot's client_order_id prefix, never from saved state. A lost or stale
    state store therefore cannot reset a cap or orphan a position.
  * Fails closed. If the pause flag, the day state, the clock, the account,
    the order history, or a symbol's open orders cannot be read, no order
    is placed that cycle.
  * Sized by risk: shares = dollars at risk / (entry - stop), capped by a
    maximum position value and by buying power across the whole batch.
  * Daily caps: trades per day, open positions, one trade per symbol, and a
    day-loss halt.
  * Uses the exchange clock, so entry cut-off and the end-of-day close
    follow half-days and holidays.
  * Closes only its own shares: the quantity its entry order filled, minus
    what its bracket already sold. It never cancels or sells anything else.
"""

from __future__ import annotations

import hmac
import json
import logging
import math
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

from config.settings import settings
from src.data.models import IntradayResult, Signal, SignalAction
from src.data.redis_store import _get_redis

logger = logging.getLogger("mse.auto_trader")

ET = ZoneInfo("America/New_York")
SESSION_OPEN = dtime(9, 35)   # matches the intraday loop's gate
SESSION_CLOSE = dtime(16, 0)

BOT_PREFIX = "mse-auto-"            # every order the bot places
FLAT_PREFIX = "mse-auto-flat-"      # its end-of-day closing orders
_TERMINAL = {"filled", "canceled", "cancelled", "expired", "rejected",
             "replaced", "done_for_day"}
_DEAD = {"canceled", "cancelled", "expired", "rejected"}
_LOOKBACK_DAYS = 30      # how far back an unclosed bot entry is still tracked
_PAGE_SIZE = 500         # Alpaca's maximum per order query
_MAX_PAGES = 20          # beyond this the history is too large to trust

_STATE_KEY = "mse:auto_trade_state"
_PAUSED_KEY = "mse:auto_trade_paused"
_NOTICE_KEY = "mse:auto_trade_notices"
_MAX_LOG = 200

# Process-local copy. It is the store when Redis is not configured, and the
# authoritative copy for any key whose last Redis write failed.
_MEM: dict[str, str] = {}
_UNSYNCED: set[str] = set()
# The scan loop, the flatten guard and API requests run on different threads.
_STORE_LOCK = threading.RLock()


class StoreError(RuntimeError):
    """Redis is configured but could not be read."""


# ----------------------------------------------------------------- config

def _parse_hhmm(value: str, default: dtime, name: str = "") -> dtime:
    try:
        parts = str(value).strip().split(":")
        if len(parts) not in (2, 3):
            raise ValueError(value)
        return dtime(int(parts[0]), int(parts[1]))
    except Exception:
        logger.warning("Auto-trader: bad time %r for %s, using %s", value, name, default)
        return default


def _minutes_before_close(t: dtime) -> int:
    return (SESSION_CLOSE.hour * 60 + SESSION_CLOSE.minute) - (t.hour * 60 + t.minute)


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
    require_earnings_check: bool = True
    require_persistent_store: bool = True
    last_entry: dtime = dtime(15, 30)
    flatten_at: dtime = dtime(15, 45)

    def __post_init__(self) -> None:
        # The close must be reachable: before the bell, and not before the
        # last entry (otherwise a late entry would never be flattened).
        if not (dtime(9, 35) < self.flatten_at < SESSION_CLOSE):
            logger.warning("Auto-trader: flatten time %s invalid, using 15:45", self.flatten_at)
            self.flatten_at = dtime(15, 45)
        if self.last_entry > self.flatten_at:
            logger.warning(
                "Auto-trader: last entry %s is after flatten %s, clamping",
                self.last_entry, self.flatten_at,
            )
            self.last_entry = self.flatten_at

    @property
    def flatten_lead_min(self) -> int:
        """Minutes before the actual close at which the bot flattens."""
        return _minutes_before_close(self.flatten_at)

    @property
    def entry_lead_min(self) -> int:
        """Minutes before the actual close after which no entry is taken."""
        return _minutes_before_close(self.last_entry)

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
        require_earnings_check=bool(s.auto_trade_require_earnings_check),
        require_persistent_store=bool(s.auto_trade_require_persistent_store),
        last_entry=_parse_hhmm(s.auto_trade_last_entry_et, dtime(15, 30), "last entry"),
        flatten_at=_parse_hhmm(s.auto_trade_flatten_et, dtime(15, 45), "flatten"),
    )


# ----------------------------------------------------------------- broker

class Broker(Protocol):
    """The small surface the auto-trader needs. A second broker can be
    added by implementing this, without touching the decision logic.

    Order dicts (from `account_orders`) have: order_id, client_order_id,
    symbol, side ("buy"/"sell"), status, qty, filled_qty, ts (epoch seconds
    of submission), fill_ts (of the fill), date (ET, ISO), and legs (a list of the
    same shape for bracket children). `account_orders` returns EVERY order
    on the account, not only the bot's: a manual sale has to be visible for
    the bot to know it no longer owns those shares.
    """

    def is_paper(self) -> bool: ...
    def account(self) -> dict: ...                 # equity, last_equity, buying_power
    def clock(self) -> dict: ...                   # is_open, minutes_to_close
    def positions(self) -> dict[str, float]: ...   # symbol -> signed qty
    def quote(self, symbol: str) -> tuple[float, float]: ...  # (bid, ask)
    def open_order_ids(self, symbol: str) -> list[str]: ...
    def account_orders(self, since: datetime) -> list[dict]: ...
    def submit_bracket(
        self, symbol: str, side: str, qty: int, stop: float, target: float,
        client_order_id: str,
    ) -> dict: ...
    def submit_market(
        self, symbol: str, side: str, qty: float, client_order_id: str
    ) -> dict: ...
    def cancel_order(self, order_id: str) -> None: ...


def _order_dict(o) -> dict:
    created = getattr(o, "created_at", None) or getattr(o, "submitted_at", None)
    date = created.astimezone(ET).date().isoformat() if created else ""
    # A partly filled order may have no filled_at; updated_at then marks the
    # fill. Falling back to created_at would date a bracket leg's fill before
    # its own entry and the ledger would ignore it.
    filled = (getattr(o, "filled_at", None) or getattr(o, "updated_at", None)
              or created)
    status = getattr(o.status, "value", o.status)
    side = getattr(o.side, "value", o.side)
    return {
        "order_id": str(o.id),
        "client_order_id": o.client_order_id or "",
        "symbol": o.symbol,
        "side": str(side),
        "status": str(status),
        "qty": float(o.qty or 0),
        "filled_qty": float(o.filled_qty or 0),
        "ts": created.timestamp() if created else 0.0,
        "fill_ts": filled.timestamp() if filled else 0.0,
        "date": date,
        "legs": [_order_dict(leg) for leg in (getattr(o, "legs", None) or [])],
    }


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

    def clock(self) -> dict:
        c = self._client().get_clock()
        minutes = (c.next_close - c.timestamp).total_seconds() / 60.0
        return {"is_open": bool(c.is_open), "minutes_to_close": minutes}

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

    def account_orders(self, since: datetime) -> list[dict]:
        """Every order since `since`, newest first, bracket legs nested.

        Pages through the history: one query returns at most 500 orders, and
        a truncated history would silently hide an entry or a sale. Raises
        if the history is too large to read completely, so callers refuse to
        act instead of acting on a partial picture.
        """
        from alpaca.common.enums import Sort
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest
        client = self._client()
        after = since.astimezone(timezone.utc)
        until = None
        seen: dict[str, dict] = {}
        for _ in range(_MAX_PAGES):
            page = client.get_orders(
                GetOrdersRequest(
                    status=QueryOrderStatus.ALL, after=after, until=until,
                    nested=True, limit=_PAGE_SIZE, direction=Sort.DESC,
                )
            )
            for o in page:
                seen.setdefault(str(o.id), _order_dict(o))
            if len(page) < _PAGE_SIZE:
                return list(seen.values())
            # Alpaca filters and sorts on submission time, so step on that.
            oldest = min(
                (getattr(o, "submitted_at", None) or o.created_at) for o in page
                if (getattr(o, "submitted_at", None) or o.created_at)
            )
            # `until` is exclusive; step a microsecond past the oldest so
            # orders sharing its timestamp are fetched again (deduped by id).
            until = oldest + timedelta(microseconds=1)
        raise RuntimeError("order history too large to establish ownership")

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

    def submit_market(
        self, symbol: str, side: str, qty: float, client_order_id: str
    ) -> dict:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest
        order = self._client().submit_order(
            MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                client_order_id=client_order_id,
            )
        )
        return {"order_id": str(order.id), "status": order.status.value}

    def cancel_order(self, order_id: str) -> None:
        self._client().cancel_order_by_id(order_id)


# ------------------------------------------------------------------ store

def _store_get(key: str) -> str | None:
    """Read a key. Raises StoreError if Redis is configured but unreadable:
    callers must then refuse to trade, not assume an empty value."""
    with _STORE_LOCK:
        redis = _get_redis()
        if redis is None:
            return _MEM.get(key)
        if key in _UNSYNCED:
            # Our last write did not reach Redis: memory is newer. Try to resync.
            try:
                redis.set(key, _MEM[key])
                _UNSYNCED.discard(key)
            except Exception:
                pass
            return _MEM.get(key)
        try:
            raw = redis.get(key)
        except Exception as e:
            raise StoreError(f"read of {key} failed: {e}") from e
        if raw is None:
            return None
        return raw if isinstance(raw, str) else json.dumps(raw)


def _store_set(key: str, value: str, attempts: int = 1) -> bool:
    """Write a key. Returns True only if the value is durable: it reached
    Redis. With no Redis, or after a failed write, the value still holds in
    this process but would not survive a restart."""
    with _STORE_LOCK:
        _MEM[key] = value
        redis = _get_redis()
        if redis is None:
            return False
        last: Exception | None = None
        for _ in range(max(attempts, 1)):
            try:
                redis.set(key, value)
                _UNSYNCED.discard(key)
                return True
            except Exception as e:
                last = e
        _UNSYNCED.add(key)
        logger.warning("Auto-trade state write failed (kept in memory): %s", last)
        return False


def has_persistent_store() -> bool:
    return _get_redis() is not None


@dataclass
class DayState:
    """Per-day log. For display and for the day-loss halt only: caps and
    ownership come from the broker."""
    date: str = ""
    trades: list[dict] = field(default_factory=list)
    skips: list[dict] = field(default_factory=list)
    halted: str = ""       # reason the bot stopped for the day, "" if running


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
        )
    except Exception as e:
        logger.warning("Auto-trade state unreadable, starting empty: %s", e)
        return DayState()


def save_state(state: DayState) -> bool:
    """Save the day log. Returns False if it is not durable (see _store_set)."""
    state.skips = state.skips[-_MAX_LOG:]
    return _store_set(_STATE_KEY, json.dumps(asdict(state)), attempts=3)


def add_notice(symbol: str, text: str, date: str) -> None:
    """Record something the owner needs to look at (shown by status())."""
    try:
        raw = _store_get(_NOTICE_KEY)
        notices = json.loads(raw) if raw else []
    except Exception:
        notices = []
    if any(x.get("date") == date and x.get("symbol") == symbol for x in notices):
        return
    notices.append({"date": date, "symbol": symbol, "text": text})
    _store_set(_NOTICE_KEY, json.dumps(notices[-50:]), attempts=3)


def load_notices(since_date: str) -> list[dict]:
    try:
        raw = _store_get(_NOTICE_KEY)
        notices = json.loads(raw) if raw else []
    except Exception:
        return []
    return [x for x in notices if str(x.get("date", "")) >= since_date]


def is_paused() -> bool:
    """True when paused, and also when the flag cannot be read."""
    try:
        return _store_get(_PAUSED_KEY) == "1"
    except StoreError as e:
        logger.warning("Auto-trader: pause flag unreadable, treating as paused: %s", e)
        return True


def set_paused(paused: bool) -> bool:
    """Set the pause flag. It takes effect in this process immediately.
    Returns False if it could not be saved durably, in which case a restart
    would lose it and the caller must be told."""
    return _store_set(_PAUSED_KEY, "1" if paused else "0", attempts=3)


def resume_available() -> tuple[bool, str]:
    key = settings.auto_trade_resume_key or ""
    if len(key) < 16:
        return False, ("resume is disabled until AUTO_TRADE_RESUME_KEY "
                       "(16+ characters) is set on the server")
    return True, ""


def can_resume(key: str | None) -> tuple[bool, str]:
    """Clearing the pause through the API needs a secret only the owner has.

    It is deliberately not tied to a site login: accounts are self-registered
    and unverified, so "logged in as the owner's email" proves nothing.
    """
    ok, why = resume_available()
    if not ok:
        return False, why
    if not key or not hmac.compare_digest(str(key), settings.auto_trade_resume_key):
        return False, "wrong resume key"
    return True, ""


# -------------------------------------------------------- broker-derived view

def _is_open(order: dict) -> bool:
    return order.get("status", "") not in _TERMINAL


def _entries(orders: list[dict]) -> list[dict]:
    return [
        o for o in orders
        if o["client_order_id"].startswith(BOT_PREFIX)
        and not o["client_order_id"].startswith(FLAT_PREFIX)
    ]


def _counts_as_trade(entry: dict) -> bool:
    """An entry that reached the market. A rejected or never-filled cancelled
    order did not use up one of the day's trades."""
    return not (entry["status"] in _DEAD and entry["filled_qty"] <= 0)


@dataclass
class Holding:
    symbol: str
    entry_coid: str
    entry_date: str
    side: str                 # side of the entry order
    qty: float                # shares the bot still owns from this entry
    cancel_ids: list[str]     # the bot's own still-open orders for this entry
    flat_attempts: int        # closing orders already sent for this entry
    position: float           # actual same-direction position in the symbol


def _fill_time(order: dict) -> float:
    return float(order.get("fill_ts") or order.get("ts") or 0.0)


def _flat_owner(coid: str) -> str:
    """Entry client id that a closing order's client id belongs to."""
    return BOT_PREFIX + coid[len(FLAT_PREFIX):].rsplit("-", 1)[0]


def owned_holdings(orders: list[dict], positions: dict[str, float]) -> list[Holding]:
    """What the bot still owns, from the account's full order history.

    Each bot entry starts as a lot of its filled quantity. Every later fill
    on the opposite side in that symbol reduces the bot's lots, WHOEVER
    placed it: the bot's own bracket legs and closing orders, but also a
    manual sale or a close from another feature. A bracket leg or closing
    order reduces its own entry first; anything else reduces oldest first.
    Closing orders of the bot's that are still working count as already
    sold, so they are not sent twice. The result is capped by the actual
    position, oldest lot first.

    The rule is deliberately conservative: if the symbol is also traded by
    hand, the bot gives up its claim to the affected shares (it would
    rather leave a share open than sell one that is not its own).
    """
    entries = sorted(_entries(orders), key=lambda e: e.get("ts", 0.0))
    if not entries:
        return []
    flats = [o for o in orders if o["client_order_id"].startswith(FLAT_PREFIX)]
    remaining = {e["client_order_id"]: float(e["filled_qty"]) for e in entries}
    by_coid = {e["client_order_id"]: e for e in entries}
    leg_owner = {
        leg["order_id"]: e["client_order_id"] for e in entries for leg in e["legs"]
    }
    fills = [
        x for o in orders for x in [o, *o.get("legs", [])]
        if float(x.get("filled_qty", 0) or 0) > 0
    ]

    out: list[Holding] = []
    for sym in sorted({e["symbol"] for e in entries}):
        for side in ("buy", "sell"):
            lots = [e for e in entries if e["symbol"] == sym and e["side"] == side]
            if not lots:
                continue
            opposite = sorted(
                (f for f in fills if f["symbol"] == sym and f["side"] != side),
                key=_fill_time,
            )
            for f in opposite:
                qty = float(f["filled_qty"])
                own_coid = leg_owner.get(f["order_id"])
                if own_coid is None and f["client_order_id"].startswith(FLAT_PREFIX):
                    own_coid = _flat_owner(f["client_order_id"])
                own = by_coid.get(own_coid) if own_coid else None
                order = ([own] if own in lots else []) + [l for l in lots if l is not own]
                for lot in order:
                    if qty <= 0:
                        break
                    if lot.get("ts", 0.0) > _fill_time(f):
                        continue    # sold before this entry existed
                    take = min(qty, remaining[lot["client_order_id"]])
                    remaining[lot["client_order_id"]] -= take
                    qty -= take

            pos = positions.get(sym, 0.0)
            same_side = max(pos, 0.0) if side == "buy" else max(-pos, 0.0)
            pos_left = same_side
            for e in lots:
                coid = e["client_order_id"]
                mine = [f for f in flats if _flat_owner(f["client_order_id"]) == coid]
                working = sum(
                    max(f["qty"] - f["filled_qty"], 0.0) for f in mine if _is_open(f)
                )
                owned = max(min(remaining[coid] - working, pos_left), 0.0)
                pos_left -= owned
                cancel_ids = [leg["order_id"] for leg in e["legs"] if _is_open(leg)]
                if _is_open(e):
                    cancel_ids.append(e["order_id"])
                if owned <= 0 and not cancel_ids:
                    continue
                out.append(Holding(
                    symbol=sym, entry_coid=coid, entry_date=e["date"], side=side,
                    qty=owned, cancel_ids=cancel_ids, flat_attempts=len(mine),
                    position=same_side,
                ))
    return out


# --------------------------------------------------------------- decisions

@dataclass
class DayCounts:
    """Today's activity, derived from the broker's order history."""
    trades: int = 0
    symbols: set[str] = field(default_factory=set)
    open_positions: int = 0


@dataclass
class Decision:
    trade: bool
    reason: str
    qty: int = 0
    ref_price: float = 0.0
    halt: bool = False   # this reason should stop the bot for the rest of the day


def _now_et(now: datetime | None) -> datetime:
    return (now or datetime.now(tz=ET)).astimezone(ET)


def in_entry_window(
    cfg: AutoTradeConfig, now: datetime | None = None,
    minutes_to_close: float | None = None,
) -> bool:
    n = _now_et(now)
    if n.weekday() >= 5:
        return False
    if not (SESSION_OPEN <= n.time() < cfg.last_entry):
        return False
    # Exchange clock: on a half-day the close is early, so the wall-clock
    # check above is not enough.
    if minutes_to_close is not None and minutes_to_close <= cfg.entry_lead_min:
        return False
    return True


def size_position(
    entry: float, stop: float, cfg: AutoTradeConfig, buying_power: float
) -> int:
    """Whole shares such that a stop-out loses about `risk_per_trade_usd`,
    capped by the position-value limit and available buying power."""
    if not all(math.isfinite(v) for v in (entry, stop, buying_power)):
        return 0
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
    halted: str,
    counts: DayCounts,
    account: dict,
    positions: dict[str, float],
    quote: tuple[float, float] | None,
    now: datetime | None = None,
    has_open_orders: bool = False,
    minutes_to_close: float | None = None,
) -> Decision:
    """Decide whether one signal becomes an order. Pure: no I/O."""
    if halted:
        return Decision(False, f"halted: {halted}")
    if not in_entry_window(cfg, now, minutes_to_close):
        return Decision(False, "outside entry window")

    equity = float(account.get("equity", float("nan")))
    last_equity = float(account.get("last_equity", float("nan")))
    buying_power = float(account.get("buying_power", float("nan")))
    if not all(math.isfinite(v) for v in (equity, last_equity, buying_power)):
        return Decision(False, "account values unavailable")
    day_pnl = equity - last_equity
    if day_pnl <= -abs(cfg.daily_loss_limit_usd):
        return Decision(False, f"daily loss limit hit ({day_pnl:.2f})", halt=True)

    if counts.trades >= cfg.max_trades_per_day:
        return Decision(False, "max trades per day reached")

    is_buy = signal.action == SignalAction.BUY
    if not is_buy and not cfg.allow_shorts:
        return Decision(False, "shorts disabled")
    if signal.confidence < cfg.min_confidence:
        return Decision(False, f"confidence {signal.confidence:.2f} below minimum")

    if row is not None and row.earnings_soon:
        return Decision(False, "earnings within a day")
    if cfg.require_earnings_check and (row is None or not row.earnings_known):
        return Decision(False, "earnings status unknown")

    sym = signal.symbol
    if sym in counts.symbols:
        return Decision(False, "already traded this symbol today")
    if abs(positions.get(sym, 0.0)) > 0:
        return Decision(False, "position already open in this symbol")
    if has_open_orders:
        return Decision(False, "open orders already exist for this symbol")
    if counts.open_positions >= cfg.max_open_positions:
        return Decision(False, "max open positions reached")

    entry, stop, target = signal.entry, signal.stop_loss, signal.target
    if not quote or not all(math.isfinite(v) for v in (*quote, entry, stop, target)):
        return Decision(False, "no usable quote")
    if quote[0] <= 0 or quote[1] <= 0 or quote[1] < quote[0]:
        return Decision(False, "no usable quote")
    ref = quote[1] if is_buy else quote[0]   # what a market order would pay / receive

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

    qty = size_position(ref, stop, cfg, buying_power)
    if qty < 1:
        return Decision(False, "position size rounds to zero")

    return Decision(True, "ok", qty=qty, ref_price=ref)


# ------------------------------------------------------------------ actions

def _skip(state: DayState, signal: Signal, reason: str, now: datetime) -> dict:
    rec = {
        "time": now.strftime("%H:%M:%S"),
        "symbol": signal.symbol,
        "setup": signal.setup_type.value,
        "action": signal.action.value,
        "reason": reason,
    }
    state.skips.append(rec)
    return {"type": "skip", **rec}


def _order_exists(broker: Broker, coid: str, since: datetime) -> bool:
    """After a failed submit: did the order reach the broker anyway?"""
    try:
        return any(o["client_order_id"] == coid for o in broker.account_orders(since))
    except Exception:
        return False


def handle_new_setups(
    signals: list[Signal],
    rows: dict[str, IntradayResult] | None = None,
    broker: Broker | None = None,
    cfg: AutoTradeConfig | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Evaluate each new setup and place bracket orders for those that pass.

    Returns the decision records (trades and skips) for this call. Does
    nothing, and touches no broker, when disabled or paused. Any failure to
    read the store or the broker ends the cycle without placing an order.
    """
    cfg = cfg or get_config()
    if not signals or not cfg.enabled or is_paused():
        return []

    if cfg.require_persistent_store and not has_persistent_store():
        # Without Redis a restart would forget a pause or a loss halt.
        logger.error("Auto-trader refused: no persistent store (Redis) configured")
        return []

    broker = broker or AlpacaPaperBroker()
    if not broker.is_paper():
        logger.error("Auto-trader refused: Alpaca endpoint is not the paper one")
        return []

    n = _now_et(now)
    today = n.date().isoformat()
    try:
        state = load_state()
    except StoreError as e:
        logger.warning("Auto-trader: day state unreadable, no entries this cycle: %s", e)
        return []
    if state.date != today:
        state = DayState(date=today)

    try:
        clock = broker.clock()
        account = dict(broker.account())
        positions = dict(broker.positions())
        orders = broker.account_orders(n - timedelta(days=_LOOKBACK_DAYS))
    except Exception as e:
        logger.warning("Auto-trader: broker unavailable, no entries this cycle: %s", e)
        return []

    if not clock.get("is_open"):
        logger.info("Auto-trader: market is closed, no entries")
        return []
    minutes_to_close = float(clock.get("minutes_to_close", 0.0))

    holdings = owned_holdings(orders, positions)
    if any(h.entry_date and h.entry_date < today and h.qty > 0 for h in holdings):
        # An earlier day's position is still open (the close was missed).
        # The flatten guard deals with it; take nothing new until it has.
        logger.warning("Auto-trader: earlier position still open, no new entries")
        return []

    todays = [e for e in _entries(orders) if e["date"] == today and _counts_as_trade(e)]
    counts = DayCounts(
        trades=len(todays),
        symbols={e["symbol"] for e in todays},
        open_positions=sum(1 for h in holdings if h.qty > 0),
    )
    rows = rows or {}
    records: list[dict] = []
    day_start = n.replace(hour=0, minute=0, second=0, microsecond=0)

    for signal in sorted(signals, key=lambda s: s.confidence, reverse=True):
        sym = signal.symbol
        if is_paused():
            records.append(_skip(state, signal, "paused", n))
            continue

        quote = None
        try:
            quote = broker.quote(sym)
        except Exception as e:
            logger.debug("Auto-trader: quote failed for %s: %s", sym, e)
        try:
            has_orders = bool(broker.open_order_ids(sym))
        except Exception as e:
            logger.warning("Auto-trader: open-order check failed for %s: %s", sym, e)
            records.append(_skip(state, signal, "could not check open orders", n))
            continue

        try:
            decision = evaluate(
                signal, rows.get(sym), cfg, state.halted, counts, account,
                positions, quote, now=n, has_open_orders=has_orders,
                minutes_to_close=minutes_to_close,
            )
        except Exception as e:
            logger.warning("Auto-trader: evaluation failed for %s: %s", sym, e)
            records.append(_skip(state, signal, "evaluation error", n))
            continue

        if decision.halt:
            state.halted = decision.reason
            if not save_state(state) and has_persistent_store():
                logger.error("Auto-trader: loss halt could not be saved durably")
        if not decision.trade:
            records.append(_skip(state, signal, decision.reason, n))
            continue

        side = "buy" if signal.action == SignalAction.BUY else "sell"
        coid = f"{BOT_PREFIX}{today}-{sym}-{signal.setup_type.value}"
        order_id, status = "", ""
        try:
            result = broker.submit_bracket(
                sym, side, decision.qty, signal.stop_loss, signal.target, coid
            )
            order_id, status = result.get("order_id", ""), result.get("status", "")
        except Exception as e:
            # A timeout can hide an accepted order. Ask the broker before
            # deciding this was a rejection.
            if not _order_exists(broker, coid, day_start):
                logger.warning("Auto-trader: order rejected for %s: %s", sym, e)
                records.append(_skip(state, signal, f"order rejected: {e}"[:200], n))
                save_state(state)
                continue
            logger.warning("Auto-trader: submit errored but order exists for %s", sym)
            status = "submitted (confirmed after error)"

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
            "order_id": order_id,
            "client_order_id": coid,
            "status": status,
        }
        state.trades.append(trade)
        # Record immediately: a crash later in the batch must not lose this.
        save_state(state)

        positions[sym] = float(decision.qty if side == "buy" else -decision.qty)
        counts.trades += 1
        counts.symbols.add(sym)
        counts.open_positions += 1
        account["buying_power"] = float(account["buying_power"]) - decision.qty * decision.ref_price
        records.append({"type": "trade", **trade})
        logger.info(
            "Auto-trade (paper): %s %d %s stop %.2f target %.2f",
            side.upper(), decision.qty, sym, signal.stop_loss, signal.target,
        )

    save_state(state)
    return records


_STALE_CHECK_SECONDS = 300.0
_last_stale_check = float("-inf")


def _wait_cleared(
    broker: Broker, symbol: str, ids: list[str], tries: int = 10, delay: float = 0.5
) -> bool:
    """Poll until none of the bot's own order ids is still open."""
    wanted = set(ids)
    for attempt in range(tries):
        if not wanted & set(broker.open_order_ids(symbol)):
            return True
        if attempt < tries - 1:
            time.sleep(delay)
    return False


def _recount(broker: Broker, entry_coid: str, since: datetime, tries: int = 3):
    """Re-read the broker and return this entry's holding (None if gone).

    Called after the bot's legs were cancelled, when the shares have no stop:
    a single failed read must not leave them like that until the next cycle,
    so it is retried before giving up.
    """
    last: Exception | None = None
    for attempt in range(tries):
        try:
            current = owned_holdings(broker.account_orders(since), broker.positions())
            return {x.entry_coid: x for x in current}.get(entry_coid)
        except Exception as e:
            last = e
            if attempt < tries - 1:
                time.sleep(0.5)
    raise RuntimeError(f"could not recount after cancelling legs: {last}")


def maybe_flatten(
    broker: Broker | None = None,
    cfg: AutoTradeConfig | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Close what the bot owns, when it is time to.

    * Near the close (by the exchange clock, so half-days work): close every
      bot holding.
    * Earlier in an open session: close only holdings left over from a
      previous day (the close was missed, for example the server was down).
    * Market closed: do nothing. An order sent now would only queue for the
      next open and falsely look like a close.

    Runs regardless of the enabled and pause switches, so turning the bot
    off never strands a position. Cancels only the bot's own bracket legs
    and sells only the bot's own share count. Nothing is remembered between
    calls: each call recomputes from the broker, so a failed attempt is
    simply retried on the next one. Returns the symbols it sent a close for.
    """
    cfg = cfg or get_config()
    n = _now_et(now)
    if n.weekday() >= 5 or not (dtime(9, 30) <= n.time() < SESSION_CLOSE):
        return []

    broker = broker or AlpacaPaperBroker()
    if not broker.is_paper():
        return []

    global _last_stale_check
    since = n - timedelta(days=_LOOKBACK_DAYS)
    try:
        clock = broker.clock()
        if not clock.get("is_open"):
            return []
        due = float(clock.get("minutes_to_close", 1e9)) <= cfg.flatten_lead_min
        # Away from the close the only job is catching a leftover from an
        # earlier day; that does not need checking every 30 seconds.
        if not due and time.monotonic() - _last_stale_check < _STALE_CHECK_SECONDS:
            return []
        positions = broker.positions()
        orders = broker.account_orders(since)
        if not due:
            # Only a successful read uses up the throttle: after a failed one
            # the leftover check is retried on the next 30-second tick.
            _last_stale_check = time.monotonic()
    except Exception as e:
        logger.warning("Auto-trader flatten: broker unavailable: %s", e)
        return []

    today = n.date().isoformat()
    holdings = owned_holdings(orders, positions)

    # Shares remain but the bot no longer claims them, because the symbol was
    # also traded by hand. Its bracket legs must not go on selling shares it
    # does not claim, and the owner has to be told: nothing manages them now.
    for h in holdings:
        if h.qty <= 0 and h.position <= 0 and h.cancel_ids and due:
            # Live legs with no position behind them could open a short.
            for oid in h.cancel_ids:
                try:
                    broker.cancel_order(oid)
                except Exception as e:
                    logger.debug("Auto-trader: cancel %s: %s", oid, e)
        if h.qty <= 0 and h.position > 0 and h.cancel_ids:
            for oid in h.cancel_ids:
                try:
                    broker.cancel_order(oid)
                except Exception as e:
                    logger.debug("Auto-trader: cancel %s: %s", oid, e)
            logger.warning("Auto-trader: no longer managing %s (traded by hand)", h.symbol)
            add_notice(
                h.symbol,
                f"{h.symbol} was also traded by hand, so the bot stopped managing it and "
                f"cancelled its own stop and target. {h.position:g} shares are open with "
                "no stop from the bot. Check this position yourself.",
                today,
            )

    targets = [
        h for h in holdings
        if h.qty > 0 and (due or (h.entry_date and h.entry_date < today))
    ]

    closed: list[str] = []
    for h in targets:
        try:
            for oid in h.cancel_ids:
                try:
                    broker.cancel_order(oid)
                except Exception as e:
                    # Cancelling one bracket leg can cancel its sibling too;
                    # the second cancel then errors. The wait below decides.
                    logger.debug("Auto-trader: cancel %s: %s", oid, e)
            # Cancels are asynchronous: the shares stay reserved until the
            # legs are really gone.
            if h.cancel_ids and not _wait_cleared(broker, h.symbol, h.cancel_ids):
                logger.warning(
                    "Auto-trader flatten: %s legs still open, retrying next cycle", h.symbol
                )
                continue
            # The target or stop may have filled while the legs were being
            # cancelled. Recount from the broker now that no bot order can
            # fill any more, so the close can never oversell into a short.
            fresh = _recount(broker, h.entry_coid, since)
            if fresh is None or fresh.qty <= 0:
                continue
            suffix = h.entry_coid[len(BOT_PREFIX):]
            broker.submit_market(
                h.symbol,
                "sell" if h.side == "buy" else "buy",
                fresh.qty,
                f"{FLAT_PREFIX}{suffix}-{fresh.flat_attempts + 1}",
            )
            closed.append(h.symbol)
        except Exception as e:
            logger.warning("Auto-trader flatten failed for %s: %s", h.symbol, e)

    if closed:
        logger.info("Auto-trader sent closing orders: %s", ", ".join(closed))
    return closed


def status() -> dict:
    """Snapshot for the API: config, switches, and today's log. Makes no
    broker call, so it is safe to poll."""
    cfg = get_config()
    today = _now_et(None).date().isoformat()
    paper = AlpacaPaperBroker().is_paper()
    paused = is_paused()
    store_ok = True
    try:
        state = load_state()
    except StoreError:
        state, store_ok = DayState(), False
    if state.date != today:
        state = DayState(date=today)   # never present an earlier day as today

    if not cfg.enabled:
        mode = "off"
    elif not paper:
        mode = "refusing (not a paper endpoint)"
    elif cfg.require_persistent_store and not has_persistent_store():
        mode = "stopped (no persistent store configured)"
    elif not store_ok:
        mode = "stopped (state store unreachable)"
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
        "store_ok": store_ok,
        "resume_hint": resume_available()[1],
        "notices": load_notices((_now_et(None) - timedelta(days=7)).date().isoformat()),
        "config": cfg.to_dict(),
        "date": state.date,
        "halted": state.halted,
        "trades": state.trades,
        "skips": state.skips[-50:],
    }
