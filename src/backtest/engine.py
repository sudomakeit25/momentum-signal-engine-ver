"""Simple event-driven backtester."""

from datetime import datetime

import pandas as pd

from src.data.models import BacktestResult, Signal, SignalAction
from src.signals.generator import generate_signals
from src.signals.indicators import add_all_indicators


def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    initial_capital: float = 100_000,
    risk_pct: float = 2.0,
) -> BacktestResult:
    """Run a simple backtest over historical data.

    Walks forward through the data, generating signals and simulating trades.

    Args:
        df: DataFrame with OHLCV data.
        symbol: Ticker symbol.
        initial_capital: Starting capital.
        risk_pct: Risk per trade as percentage.

    Returns:
        BacktestResult with performance stats and trade log.
    """
    if len(df) < 100:
        return _empty_result(symbol, df)

    capital = initial_capital
    peak_capital = initial_capital
    max_drawdown = 0.0
    trades: list[dict] = []
    position: dict | None = None

    # Walk forward starting from bar 50 (need indicator warmup)
    for i in range(50, len(df)):
        window = df.iloc[: i + 1].copy()
        bar = df.iloc[i]
        bar_time = df.index[i]

        # Check exit conditions first
        if position is not None:
            exit_price = _check_exit(bar, position)
            if exit_price is not None:
                pnl = (exit_price - position["entry"]) * position["shares"]
                capital += pnl
                peak_capital = max(peak_capital, capital)
                drawdown = (peak_capital - capital) / peak_capital
                max_drawdown = max(max_drawdown, drawdown)

                trades.append(
                    {
                        "symbol": symbol,
                        "entry_date": str(position["entry_date"]),
                        "exit_date": str(bar_time),
                        "entry_price": position["entry"],
                        "exit_price": round(exit_price, 2),
                        "shares": position["shares"],
                        "pnl": round(pnl, 2),
                        "return_pct": round(
                            (exit_price / position["entry"] - 1) * 100, 2
                        ),
                    }
                )
                position = None

        # Check entry conditions
        if position is None:
            signals = generate_signals(window, symbol)
            buy_signals = [s for s in signals if s.action == SignalAction.BUY]
            if buy_signals:
                # Take the highest confidence buy signal
                best = max(buy_signals, key=lambda s: s.confidence)
                dollar_risk = capital * (risk_pct / 100)
                risk_per_share = abs(best.entry - best.stop_loss)
                if risk_per_share > 0:
                    shares = int(dollar_risk / risk_per_share)
                    if shares > 0:
                        position = {
                            "entry": best.entry,
                            "stop_loss": best.stop_loss,
                            "target": best.target,
                            "shares": shares,
                            "entry_date": bar_time,
                        }

    # Close any open position at the end
    if position is not None:
        last_price = df["close"].iloc[-1]
        pnl = (last_price - position["entry"]) * position["shares"]
        capital += pnl
        trades.append(
            {
                "symbol": symbol,
                "entry_date": str(position["entry_date"]),
                "exit_date": str(df.index[-1]),
                "entry_price": position["entry"],
                "exit_price": round(last_price, 2),
                "shares": position["shares"],
                "pnl": round(pnl, 2),
                "return_pct": round(
                    (last_price / position["entry"] - 1) * 100, 2
                ),
            }
        )

    # Compute stats
    winning = [t for t in trades if t["pnl"] > 0]
    losing = [t for t in trades if t["pnl"] <= 0]
    total = len(trades)
    win_rate = len(winning) / total if total > 0 else 0

    avg_win = sum(t["pnl"] for t in winning) / len(winning) if winning else 0
    avg_loss = abs(sum(t["pnl"] for t in losing) / len(losing)) if losing else 0
    avg_rr = avg_win / avg_loss if avg_loss > 0 else 0

    total_return = ((capital - initial_capital) / initial_capital) * 100

    return BacktestResult(
        strategy="momentum",
        start_date=df.index[50].to_pydatetime()
        if hasattr(df.index[50], "to_pydatetime")
        else df.index[50],
        end_date=df.index[-1].to_pydatetime()
        if hasattr(df.index[-1], "to_pydatetime")
        else df.index[-1],
        total_trades=total,
        winning_trades=len(winning),
        losing_trades=len(losing),
        win_rate=round(win_rate, 4),
        avg_rr=round(avg_rr, 2),
        total_return_pct=round(total_return, 2),
        max_drawdown_pct=round(max_drawdown * 100, 2),
        trades=trades,
    )


def _check_exit(bar: pd.Series, position: dict) -> float | None:
    """Check if exit conditions are met for the current bar.

    Returns exit price if triggered, None otherwise.
    """
    # Stop loss hit
    if bar["low"] <= position["stop_loss"]:
        return position["stop_loss"]

    # Target hit
    if bar["high"] >= position["target"]:
        return position["target"]

    return None


def _empty_result(symbol: str, df: pd.DataFrame) -> BacktestResult:
    """Return an empty backtest result when insufficient data."""
    now = datetime.now()
    return BacktestResult(
        strategy="momentum",
        start_date=now,
        end_date=now,
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        win_rate=0,
        avg_rr=0,
        total_return_pct=0,
        max_drawdown_pct=0,
        trades=[],
    )
