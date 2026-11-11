"""Every trade the paper auto-trader made, rebuilt from the broker's order
history, with how each one ended and what it made or lost.

The broker is the source of truth, as it is for the auto-trader itself: the
bot's orders carry a client order id starting with `mse-auto-`, its bracket
legs are nested under the entry, and its end-of-day closing orders start with
`mse-auto-flat-`. Orders placed by hand are ignored.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta

from src.trading import auto_trader as at

logger = logging.getLogger("mse.trade_history")

MIN_DAYS, MAX_DAYS = 1, 90
_TTL = 60
_cache: dict[int, tuple[float, dict]] = {}

EXIT_TARGET = "target"
EXIT_STOP = "stop"
EXIT_CLOSE = "end of day close"


def parse_coid(coid: str) -> tuple[str, str, str]:
    """(date, symbol, setup) from `mse-auto-YYYY-MM-DD-SYM-setup`. Unknown
    parts come back as "" so a malformed id never raises."""
    rest = (coid or "")[len(at.BOT_PREFIX):] if (coid or "").startswith(at.BOT_PREFIX) else ""
    date, _, tail = rest[:10], rest[10:11], rest[11:]
    if len(date) != 10 or date[4] != "-" or date[7] != "-":
        return "", "", ""
    sym, _, setup = tail.partition("-")
    return date, sym, setup


def _qty(o: dict) -> float:
    try:
        return max(float(o.get("filled_qty") or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _leg_kind(leg: dict, entry_side: str, entry_price: float | None) -> str:
    """Take-profit or stop-loss leg. The order type decides; when it is
    missing, a leg with a stop price is the stop."""
    t = (leg.get("order_type") or "").lower()
    if t in ("stop", "stop_limit", "trailing_stop"):
        return EXIT_STOP
    if t == "limit":
        return EXIT_TARGET
    if leg.get("stop_price"):
        return EXIT_STOP
    if leg.get("limit_price") and entry_price:
        better = leg["limit_price"] > entry_price if entry_side == "buy" else leg["limit_price"] < entry_price
        return EXIT_TARGET if better else EXIT_STOP
    return EXIT_TARGET


def build_trades(orders: list[dict], positions: dict[str, float] | None = None) -> tuple[list[dict], int]:
    """(trades, entries that never filled). Accepts orders in any order.
    `positions` tells an open trade from one closed outside the bot."""
    positions = positions or {}
    bot = [o for o in orders if str(o.get("client_order_id", "")).startswith(at.BOT_PREFIX)]
    flats = [o for o in bot if o["client_order_id"].startswith(at.FLAT_PREFIX)]
    entries = sorted((o for o in bot if not o["client_order_id"].startswith(at.FLAT_PREFIX)),
                     key=lambda o: (o.get("ts") or 0.0, o["client_order_id"]))

    flats_by_owner: dict[str, list[dict]] = defaultdict(list)
    for f in flats:
        flats_by_owner[at._flat_owner(f["client_order_id"])].append(f)

    trades, unfilled = [], 0
    for e in entries:
        qty_in = _qty(e)
        if qty_in <= 0:
            unfilled += 1
            continue
        coid = e["client_order_id"]
        date, sym, setup = parse_coid(coid)
        side = str(e.get("side") or "buy")
        sign = 1.0 if side == "buy" else -1.0
        entry_price = e.get("filled_avg_price")
        legs = e.get("legs") or []
        stop = next((l.get("stop_price") for l in legs if _leg_kind(l, side, entry_price) == EXIT_STOP
                     and l.get("stop_price")), None)
        target = next((l.get("limit_price") for l in legs if _leg_kind(l, side, entry_price) == EXIT_TARGET
                       and l.get("limit_price")), None)

        exits = []
        for leg in legs:
            q = _qty(leg)
            if q > 0:
                exits.append((_leg_kind(leg, side, entry_price), q, leg.get("filled_avg_price"),
                              at._fill_time(leg)))
        for f in flats_by_owner.get(coid, []):
            q = _qty(f)
            if q > 0:
                exits.append((EXIT_CLOSE, q, f.get("filled_avg_price"), at._fill_time(f)))
        exits.sort(key=lambda x: x[3])

        qty_out = min(sum(x[1] for x in exits), qty_in)
        priced = [(q, p) for _, q, p, _ in exits if p]
        exit_price = (sum(q * p for q, p in priced) / sum(q for q, _ in priced)) if priced else None
        priced_qty = min(sum(q for q, _ in priced), qty_in)

        pnl = None
        if entry_price and exit_price and priced_qty > 0:
            pnl = round((exit_price - entry_price) * priced_qty * sign, 2)
        risk = abs(entry_price - stop) * priced_qty if entry_price and stop and priced_qty else None
        r_mult = round(pnl / risk, 2) if pnl is not None and risk else None

        left = round(qty_in - qty_out, 6)
        sym_key = sym or e.get("symbol", "")
        held = positions.get(sym_key, 0.0) * sign
        if left <= 0:
            outcome = "closed"
        elif held > 0:
            outcome = "open"
        else:
            outcome = "closed outside the bot"   # sold by hand, or by another feature

        by_kind: dict[str, float] = defaultdict(float)
        for kind, q, _, _ in exits:
            by_kind[kind] += q
        reason = max(by_kind, key=by_kind.get) if by_kind else ""
        trades.append({
            "date": date or e.get("date", ""),
            "symbol": sym_key,
            "setup": setup,
            "side": side,
            "qty": qty_in,
            "entry_price": round(entry_price, 4) if entry_price else None,
            "entry_time": at._fill_time(e),
            "stop": stop,
            "target": target,
            "exit_price": round(exit_price, 4) if exit_price else None,
            "exit_qty": qty_out,
            "exit_reason": reason,
            "exit_reasons": {k: v for k, v in by_kind.items()},
            "exit_time": exits[-1][3] if exits else None,
            "outcome": outcome,
            "open_qty": max(left, 0.0),
            "pnl": pnl,
            "r_multiple": r_mult,
            "client_order_id": coid,
        })
    trades.sort(key=lambda t: (t["date"], t["entry_time"] or 0.0), reverse=True)
    return trades, unfilled


def _done(trades: list[dict]) -> list[dict]:
    """Trades the bot fully closed at a known price. Only these count towards
    win rate and totals; a part-closed or hand-closed trade has no full result."""
    return [t for t in trades if t["outcome"] == "closed" and t["pnl"] is not None]


def _group(trades: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        groups[t[key] or "unknown"].append(t)
    out = []
    for name, ts in groups.items():
        done = _done(ts)
        wins = sum(1 for t in done if t["pnl"] > 0)
        rs = [t["r_multiple"] for t in done if t["r_multiple"] is not None]
        out.append({
            key: name,
            "trades": len(ts),
            "closed": len(done),
            "open": sum(1 for t in ts if t["outcome"] == "open"),
            "wins": wins,
            "losses": sum(1 for t in done if t["pnl"] < 0),
            "win_rate": round(wins / len(done) * 100, 1) if done else None,
            "pnl": round(sum(t["pnl"] for t in done), 2),
            "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
        })
    return out


def summarize(trades: list[dict], unfilled: int = 0) -> dict:
    done = _done(trades)
    rs = [t["r_multiple"] for t in done if t["r_multiple"] is not None]
    wins = [t for t in done if t["pnl"] > 0]
    best = max(done, key=lambda t: t["pnl"], default=None)
    worst = min(done, key=lambda t: t["pnl"], default=None)
    by_day = sorted(_group(trades, "date"), key=lambda g: g["date"], reverse=True)
    by_setup = sorted(_group(trades, "setup"), key=lambda g: (-g["trades"], g["setup"]))
    pick = lambda t: {"symbol": t["symbol"], "date": t["date"], "pnl": t["pnl"]} if t else None  # noqa: E731
    return {
        "totals": {
            "trades": len(trades),
            "closed": len(done),
            "open": sum(1 for t in trades if t["outcome"] == "open"),
            "closed_outside": sum(1 for t in trades if t["outcome"] == "closed outside the bot"),
            "not_filled": unfilled,
            "wins": len(wins),
            "losses": sum(1 for t in done if t["pnl"] < 0),
            "win_rate": round(len(wins) / len(done) * 100, 1) if done else None,
            "pnl": round(sum(t["pnl"] for t in done), 2),
            "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
            "best": pick(best),
            "worst": pick(worst),
        },
        "by_day": by_day,
        "by_setup": by_setup,
    }


def history(days: int = 30, broker=None) -> dict:
    """The API answer. Never raises: a broker failure gives data_ok False."""
    days = max(MIN_DAYS, min(MAX_DAYS, int(days)))
    hit = _cache.get(days)
    if broker is None and hit and time.time() - hit[0] < _TTL:
        return hit[1]
    broker = broker or at.AlpacaPaperBroker()
    now = datetime.now(at.ET)
    since = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        orders = broker.account_orders(since)
        positions = broker.positions()
    except Exception as e:
        logger.warning("Trade history unavailable: %s", str(e)[:200])
        return {"data_ok": False, "days": days,
                "note": "The paper account's order history could not be read. Try again shortly."}
    trades, unfilled = build_trades(orders, positions)
    result = {
        "data_ok": True,
        "days": days,
        "since": since.date().isoformat(),
        "as_of": now.isoformat(timespec="seconds"),
        "note": None,
        **summarize(trades, unfilled),
        "trades": trades,
    }
    _cache[days] = (time.time(), result)
    return result
