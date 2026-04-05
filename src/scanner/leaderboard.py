"""Signal Leaderboard - tracks real-time signal accuracy.

Records every generated signal with entry/target/stop, then checks
outcomes after a configurable window. Provides public stats on
signal accuracy by setup type, time period, and symbol.
"""

import logging
from datetime import datetime, timedelta, timezone

from src.data import client as alpaca_client
from src.data.redis_store import (
    get_leaderboard_signals,
    record_signal,
    update_leaderboard_signals,
)

logger = logging.getLogger("mse.leaderboard")


def track_signals(signals: list) -> int:
    """Record new signals for leaderboard tracking.

    Called from the background refresh loop after signal generation.
    Returns number of signals recorded.
    """
    count = 0
    now = datetime.now(timezone.utc).isoformat()

    for s in signals:
        data = {
            "symbol": s.symbol,
            "action": s.action.value,
            "setup_type": s.setup_type.value if hasattr(s.setup_type, 'value') else str(s.setup_type),
            "entry": s.entry,
            "target": s.target,
            "stop_loss": s.stop_loss,
            "confidence": s.confidence,
            "recorded_at": now,
            "outcome": None,  # pending
            "exit_price": None,
            "resolved_at": None,
        }
        if record_signal(data):
            count += 1

    return count


def check_outcomes(lookback_days: int = 10) -> int:
    """Check outcomes for pending signals.

    Fetches current prices and checks if target or stop was hit.
    Returns number of signals resolved.
    """
    signals = get_leaderboard_signals()
    if not signals:
        return 0

    pending = [s for s in signals if s.get("outcome") is None]
    if not pending:
        return 0

    resolved = 0
    now = datetime.now(timezone.utc)

    for s in pending:
        recorded = s.get("recorded_at", "")
        if not recorded:
            continue

        try:
            recorded_dt = datetime.fromisoformat(recorded.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        days_elapsed = (now - recorded_dt).days
        if days_elapsed < 1:
            continue  # too early to check

        symbol = s.get("symbol", "")
        if not symbol:
            continue

        try:
            df = alpaca_client.get_bars(symbol, days=days_elapsed + 5)
            if df is None or df.empty:
                continue

            entry = s["entry"]
            target = s["target"]
            stop = s["stop_loss"]
            is_buy = s["action"] == "BUY"

            # Check each bar after the signal date
            outcome = None
            exit_price = None

            for _, bar in df.iterrows():
                high = bar["high"]
                low = bar["low"]

                if is_buy:
                    if high >= target:
                        outcome = "win"
                        exit_price = target
                        break
                    if low <= stop:
                        outcome = "loss"
                        exit_price = stop
                        break
                else:
                    if low <= target:
                        outcome = "win"
                        exit_price = target
                        break
                    if high >= stop:
                        outcome = "loss"
                        exit_price = stop
                        break

            if outcome is None and days_elapsed >= lookback_days:
                # Expired
                last_close = df["close"].iloc[-1]
                if is_buy:
                    outcome = "win" if last_close > entry else "loss"
                else:
                    outcome = "win" if last_close < entry else "loss"
                exit_price = float(last_close)

            if outcome:
                s["outcome"] = outcome
                s["exit_price"] = exit_price
                s["resolved_at"] = now.isoformat()
                resolved += 1

        except Exception as e:
            logger.debug("Outcome check failed for %s: %s", symbol, e)
            continue

    if resolved > 0:
        update_leaderboard_signals(signals)
        logger.info("Leaderboard: resolved %d signal outcomes", resolved)

    return resolved


def compute_leaderboard() -> dict:
    """Compute leaderboard stats from tracked signals."""
    signals = get_leaderboard_signals()
    if not signals:
        return {"total_tracked": 0, "resolved": 0, "pending": 0, "stats": {}, "by_setup": {}, "recent": []}

    resolved = [s for s in signals if s.get("outcome") is not None]
    pending = [s for s in signals if s.get("outcome") is None]

    if not resolved:
        return {
            "total_tracked": len(signals),
            "resolved": 0,
            "pending": len(pending),
            "stats": {},
            "by_setup": {},
            "recent": signals[-20:],
        }

    wins = [s for s in resolved if s["outcome"] == "win"]
    losses = [s for s in resolved if s["outcome"] == "loss"]

    win_rate = len(wins) / len(resolved) * 100 if resolved else 0

    # By setup type
    by_setup = {}
    for s in resolved:
        st = s.get("setup_type", "unknown")
        if st not in by_setup:
            by_setup[st] = {"total": 0, "wins": 0}
        by_setup[st]["total"] += 1
        if s["outcome"] == "win":
            by_setup[st]["wins"] += 1

    for st in by_setup:
        d = by_setup[st]
        d["win_rate"] = round(d["wins"] / d["total"] * 100, 1) if d["total"] else 0

    # By time period (last 7d, 30d, all)
    now = datetime.now(timezone.utc)
    periods = {}
    for label, days in [("7d", 7), ("30d", 30), ("all", 9999)]:
        cutoff = (now - timedelta(days=days)).isoformat() if days < 9999 else ""
        period_signals = [
            s for s in resolved
            if not cutoff or s.get("recorded_at", "") >= cutoff
        ]
        p_wins = [s for s in period_signals if s["outcome"] == "win"]
        periods[label] = {
            "total": len(period_signals),
            "wins": len(p_wins),
            "win_rate": round(len(p_wins) / len(period_signals) * 100, 1) if period_signals else 0,
        }

    # Weekly performance over time (for charting)
    weekly_performance = _compute_weekly_performance(resolved)

    return {
        "total_tracked": len(signals),
        "resolved": len(resolved),
        "pending": len(pending),
        "stats": {
            "win_rate": round(win_rate, 1),
            "total_wins": len(wins),
            "total_losses": len(losses),
            "periods": periods,
        },
        "by_setup": by_setup,
        "weekly_performance": weekly_performance,
        "recent": list(reversed(resolved[-20:])),
    }


def _compute_weekly_performance(resolved: list[dict]) -> list[dict]:
    """Compute win rate by week for time-series charting."""
    if not resolved:
        return []

    # Group by week
    weeks: dict[str, dict] = {}
    for s in resolved:
        recorded = s.get("recorded_at", "")
        if not recorded:
            continue
        try:
            dt = datetime.fromisoformat(recorded.replace("Z", "+00:00"))
            week_key = dt.strftime("%Y-W%W")
            week_start = (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue

        if week_key not in weeks:
            weeks[week_key] = {"week": week_start, "total": 0, "wins": 0}
        weeks[week_key]["total"] += 1
        if s["outcome"] == "win":
            weeks[week_key]["wins"] += 1

    result = []
    for week_key in sorted(weeks.keys()):
        w = weeks[week_key]
        w["win_rate"] = round(w["wins"] / w["total"] * 100, 1) if w["total"] else 0
        result.append(w)

    return result
