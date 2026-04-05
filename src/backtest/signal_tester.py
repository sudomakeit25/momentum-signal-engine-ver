"""Signal backtester - measures historical accuracy of generated signals.

Unlike the strategy backtester, this generates signals at each historical
point and checks if the entry/target/stop were hit within a time window.
"""

import logging

import pandas as pd

from src.data import client
from src.signals.generator import generate_signals

logger = logging.getLogger("mse.signal_tester")


def backtest_signals(
    symbol: str,
    days: int = 200,
    lookforward: int = 10,
) -> dict:
    """Generate signals over historical data and measure outcomes.

    For each signal generated, checks the next `lookforward` bars to see if:
    - Target was hit (win)
    - Stop loss was hit (loss)
    - Neither was hit (open/expired)

    Returns performance summary with individual signal results.
    """
    df = client.get_bars(symbol, days=days)
    if df is None or len(df) < 100:
        return {"symbol": symbol, "error": "Insufficient data", "signals": [], "stats": {}}

    results = []
    # Walk forward from bar 60 (need warmup) to `lookforward` bars before end
    for i in range(60, len(df) - lookforward):
        window = df.iloc[:i + 1].copy()
        try:
            signals = generate_signals(window, symbol)
        except Exception:
            continue

        for sig in signals:
            future = df.iloc[i + 1: i + 1 + lookforward]
            outcome = _evaluate_signal(sig, future)
            results.append({
                "date": df.index[i].isoformat() if hasattr(df.index[i], 'isoformat') else str(df.index[i]),
                "action": sig.action.value,
                "setup_type": sig.setup_type.value,
                "entry": sig.entry,
                "target": sig.target,
                "stop_loss": sig.stop_loss,
                "confidence": sig.confidence,
                "outcome": outcome["outcome"],
                "exit_price": outcome["exit_price"],
                "bars_to_exit": outcome["bars_to_exit"],
                "pnl_pct": outcome["pnl_pct"],
                "r_multiple": outcome["r_multiple"],
            })

    stats = _compute_signal_stats(results)

    return {
        "symbol": symbol,
        "total_bars": len(df),
        "lookforward": lookforward,
        "signals": results[-50:],  # last 50 for display
        "stats": stats,
    }


def _evaluate_signal(signal, future_bars: pd.DataFrame) -> dict:
    """Check if a signal's target or stop was hit in future bars."""
    entry = signal.entry
    target = signal.target
    stop = signal.stop_loss
    is_buy = signal.action.value == "BUY"

    for i, (_, bar) in enumerate(future_bars.iterrows()):
        high = bar["high"]
        low = bar["low"]

        if is_buy:
            if high >= target:
                pnl_pct = ((target - entry) / entry) * 100
                risk = abs(entry - stop)
                r = (target - entry) / risk if risk > 0 else 0
                return {"outcome": "win", "exit_price": target, "bars_to_exit": i + 1, "pnl_pct": round(pnl_pct, 2), "r_multiple": round(r, 2)}
            if low <= stop:
                pnl_pct = ((stop - entry) / entry) * 100
                return {"outcome": "loss", "exit_price": stop, "bars_to_exit": i + 1, "pnl_pct": round(pnl_pct, 2), "r_multiple": -1.0}
        else:
            if low <= target:
                pnl_pct = ((entry - target) / entry) * 100
                risk = abs(stop - entry)
                r = (entry - target) / risk if risk > 0 else 0
                return {"outcome": "win", "exit_price": target, "bars_to_exit": i + 1, "pnl_pct": round(pnl_pct, 2), "r_multiple": round(r, 2)}
            if high >= stop:
                pnl_pct = ((entry - stop) / entry) * 100
                return {"outcome": "loss", "exit_price": stop, "bars_to_exit": i + 1, "pnl_pct": round(pnl_pct, 2), "r_multiple": -1.0}

    # Neither hit - expired
    last_close = future_bars["close"].iloc[-1] if len(future_bars) > 0 else entry
    if is_buy:
        pnl_pct = ((last_close - entry) / entry) * 100
    else:
        pnl_pct = ((entry - last_close) / entry) * 100

    return {"outcome": "expired", "exit_price": round(last_close, 2), "bars_to_exit": len(future_bars), "pnl_pct": round(pnl_pct, 2), "r_multiple": 0}


def _compute_signal_stats(results: list[dict]) -> dict:
    """Compute aggregate stats from signal backtest results."""
    if not results:
        return {}

    total = len(results)
    wins = [r for r in results if r["outcome"] == "win"]
    losses = [r for r in results if r["outcome"] == "loss"]
    expired = [r for r in results if r["outcome"] == "expired"]

    win_rate = len(wins) / total * 100 if total else 0
    avg_pnl = sum(r["pnl_pct"] for r in results) / total
    avg_r = sum(r["r_multiple"] for r in results) / total

    # By setup type
    by_setup = {}
    for r in results:
        st = r["setup_type"]
        if st not in by_setup:
            by_setup[st] = {"total": 0, "wins": 0, "pnl_sum": 0}
        by_setup[st]["total"] += 1
        if r["outcome"] == "win":
            by_setup[st]["wins"] += 1
        by_setup[st]["pnl_sum"] += r["pnl_pct"]

    for st in by_setup:
        s = by_setup[st]
        s["win_rate"] = round(s["wins"] / s["total"] * 100, 1) if s["total"] else 0
        s["avg_pnl"] = round(s["pnl_sum"] / s["total"], 2) if s["total"] else 0
        del s["pnl_sum"]

    return {
        "total_signals": total,
        "wins": len(wins),
        "losses": len(losses),
        "expired": len(expired),
        "win_rate": round(win_rate, 1),
        "avg_pnl_pct": round(avg_pnl, 2),
        "avg_r_multiple": round(avg_r, 2),
        "avg_bars_to_exit": round(sum(r["bars_to_exit"] for r in results) / total, 1),
        "by_setup": by_setup,
    }
