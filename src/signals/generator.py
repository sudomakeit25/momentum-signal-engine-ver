"""Buy/sell signal engine — generates trade signals with entry, stop, target."""

from datetime import datetime

import pandas as pd

from src.data.models import Signal, SignalAction, SetupType
from src.signals.indicators import (
    add_all_indicators,
    atr,
    atr_trailing_stop,
    ema,
    ema_crossover,
    ema_crossunder,
    is_ema_stacked,
    rsi,
    rsi_divergence,
    rsi_pullback_in_uptrend,
    volume_climax,
    volume_surge,
    vwap,
)


def _weekly_trend(df: pd.DataFrame) -> str:
    """Check weekly trend using resampled data. Returns 'bullish', 'bearish', or 'neutral'."""
    if len(df) < 50:
        return "neutral"
    try:
        weekly = df.resample("W").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        if len(weekly) < 10:
            return "neutral"
        ema9w = ema(weekly["close"], 9)
        ema21w = ema(weekly["close"], 21)
        if ema9w.iloc[-1] > ema21w.iloc[-1]:
            return "bullish"
        elif ema9w.iloc[-1] < ema21w.iloc[-1]:
            return "bearish"
    except Exception:
        pass
    return "neutral"


def generate_signals(df: pd.DataFrame, symbol: str) -> list[Signal]:
    """Generate buy and sell signals for a stock.

    Args:
        df: DataFrame with OHLCV data.
        symbol: Ticker symbol.

    Returns:
        List of Signal objects for the latest bar.
    """
    if len(df) < 50:
        return []

    # Skip indicator computation if already present
    if "ema9" not in df.columns:
        df = add_all_indicators(df)
    weekly = _weekly_trend(df)
    buys = _buy_signals(df, symbol)
    sells = _sell_signals(df, symbol)

    # Multi-timeframe boost: increase confidence when weekly trend aligns
    for sig in buys:
        if weekly == "bullish":
            sig.confidence = min(sig.confidence + 0.05, 0.95)
            sig.reason += " (weekly trend confirms)"
        elif weekly == "bearish":
            sig.confidence = max(sig.confidence - 0.10, 0.20)
            sig.reason += " (caution: weekly trend bearish)"

    for sig in sells:
        if weekly == "bearish":
            sig.confidence = min(sig.confidence + 0.05, 0.95)
            sig.reason += " (weekly trend confirms)"
        elif weekly == "bullish":
            sig.confidence = max(sig.confidence - 0.10, 0.20)
            sig.reason += " (caution: weekly trend bullish)"

    # Resolve conflicts: if both buy and sell fire, keep the higher-confidence side
    if buys and sells:
        best_buy = max(b.confidence for b in buys)
        best_sell = max(s.confidence for s in sells)
        if best_buy >= best_sell:
            return buys
        else:
            return sells

    return buys + sells


def _buy_signals(df: pd.DataFrame, symbol: str) -> list[Signal]:
    """Detect buy signals on the latest bar."""
    signals: list[Signal] = []
    last = df.iloc[-1]
    atr_val = last.get("atr", 0)
    if pd.isna(atr_val) or atr_val <= 0:
        return signals

    entry = last["close"]
    stop = entry - 2 * atr_val
    target = entry + 4 * atr_val  # 2:1 R:R
    risk = entry - stop
    rr = (target - entry) / risk if risk > 0 else 0
    ts = df.index[-1]
    if not isinstance(ts, datetime):
        ts = pd.Timestamp(ts).to_pydatetime()

    ema9 = ema(df["close"], 9)
    ema21 = ema(df["close"], 21)
    rsi_val = rsi(df["close"])

    # 1. EMA crossover (9 crosses above 21) — exact crossover bar
    crossovers = ema_crossover(df["close"], 9, 21)
    if crossovers.iloc[-1]:
        signals.append(
            Signal(
                symbol=symbol,
                action=SignalAction.BUY,
                setup_type=SetupType.EMA_CROSSOVER,
                reason="EMA 9 just crossed above EMA 21 — new short-term uptrend starting",
                entry=round(entry, 2),
                stop_loss=round(stop, 2),
                target=round(target, 2),
                rr_ratio=round(rr, 2),
                confidence=0.65,
                timestamp=ts,
            )
        )
    # 1b. EMA trend active: EMA9 > EMA21 and recent crossover (within 5 bars)
    elif ema9.iloc[-1] > ema21.iloc[-1] and crossovers.tail(5).any():
        signals.append(
            Signal(
                symbol=symbol,
                action=SignalAction.BUY,
                setup_type=SetupType.EMA_CROSSOVER,
                reason="EMA 9 crossed above EMA 21 within last 5 bars — uptrend still fresh",
                entry=round(entry, 2),
                stop_loss=round(stop, 2),
                target=round(target, 2),
                rr_ratio=round(rr, 2),
                confidence=0.55,
                timestamp=ts,
            )
        )

    # 2. Breakout above consolidation with volume
    if _is_breakout(df):
        breakout_stop = entry - 1.5 * atr_val
        breakout_target = entry + 3 * atr_val
        breakout_risk = entry - breakout_stop
        breakout_rr = (
            (breakout_target - entry) / breakout_risk if breakout_risk > 0 else 0
        )
        signals.append(
            Signal(
                symbol=symbol,
                action=SignalAction.BUY,
                setup_type=SetupType.BREAKOUT,
                reason="Price broke above 20-day resistance on above-average volume — breakout confirmed",
                entry=round(entry, 2),
                stop_loss=round(breakout_stop, 2),
                target=round(breakout_target, 2),
                rr_ratio=round(breakout_rr, 2),
                confidence=0.75,
                timestamp=ts,
            )
        )

    # 3. RSI pullback in uptrend (40-50) OR moderate pullback (50-60) with stacked EMAs
    pullbacks = rsi_pullback_in_uptrend(df)
    if pullbacks.iloc[-1]:
        signals.append(
            Signal(
                symbol=symbol,
                action=SignalAction.BUY,
                setup_type=SetupType.RSI_PULLBACK,
                reason=f"RSI pulled back to {rsi_val.iloc[-1]:.0f} in an uptrend — healthy dip, likely to bounce",
                entry=round(entry, 2),
                stop_loss=round(stop, 2),
                target=round(target, 2),
                rr_ratio=round(rr, 2),
                confidence=0.70,
                timestamp=ts,
            )
        )
    elif (
        not rsi_val.empty
        and is_ema_stacked(df).iloc[-1]
        and 50 <= rsi_val.iloc[-1] <= 60
    ):
        signals.append(
            Signal(
                symbol=symbol,
                action=SignalAction.BUY,
                setup_type=SetupType.RSI_PULLBACK,
                reason=f"RSI at {rsi_val.iloc[-1]:.0f} with bullish EMA stack — mild pullback in strong trend",
                entry=round(entry, 2),
                stop_loss=round(stop, 2),
                target=round(target, 2),
                rr_ratio=round(rr, 2),
                confidence=0.55,
                timestamp=ts,
            )
        )

    # 4. VWAP reclaim (price crosses above VWAP)
    if _is_vwap_reclaim(df):
        signals.append(
            Signal(
                symbol=symbol,
                action=SignalAction.BUY,
                setup_type=SetupType.VWAP_RECLAIM,
                reason="Price reclaimed VWAP from below — institutional buyers stepping in",
                entry=round(entry, 2),
                stop_loss=round(stop, 2),
                target=round(target, 2),
                rr_ratio=round(rr, 2),
                confidence=0.60,
                timestamp=ts,
            )
        )

    # 5. Uptrend momentum: EMAs stacked bullishly with strong RS (always-on signal)
    if (
        is_ema_stacked(df).iloc[-1]
        and not rsi_val.empty
        and 55 <= rsi_val.iloc[-1] <= 80
        and not signals  # Only add if no other buy signal already present
    ):
        signals.append(
            Signal(
                symbol=symbol,
                action=SignalAction.BUY,
                setup_type=SetupType.EMA_CROSSOVER,
                reason=f"EMAs stacked bullishly (9>21>50) with RSI {rsi_val.iloc[-1]:.0f} — sustained uptrend",
                entry=round(entry, 2),
                stop_loss=round(stop, 2),
                target=round(target, 2),
                rr_ratio=round(rr, 2),
                confidence=0.50,
                timestamp=ts,
            )
        )

    return signals


def _sell_signals(df: pd.DataFrame, symbol: str) -> list[Signal]:
    """Detect sell signals on the latest bar."""
    signals: list[Signal] = []
    last = df.iloc[-1]
    atr_val = last.get("atr", 0)
    if pd.isna(atr_val) or atr_val <= 0:
        return signals

    entry = last["close"]
    ts = df.index[-1]
    if not isinstance(ts, datetime):
        ts = pd.Timestamp(ts).to_pydatetime()

    # 1. ATR trailing stop hit
    trailing_stop = atr_trailing_stop(df)
    if not trailing_stop.empty and entry < trailing_stop.iloc[-1]:
        signals.append(
            Signal(
                symbol=symbol,
                action=SignalAction.SELL,
                setup_type=SetupType.EMA_CROSSOVER,
                reason=f"Price ${entry:.2f} dropped below ATR trailing stop ${trailing_stop.iloc[-1]:.2f} — trend protection triggered",
                entry=round(entry, 2),
                stop_loss=0.0,
                target=0.0,
                rr_ratio=0.0,
                confidence=0.70,
                timestamp=ts,
            )
        )

    # 2. EMA crossunder (9 crosses below 21)
    crossunders = ema_crossunder(df["close"], 9, 21)
    if crossunders.iloc[-1]:
        signals.append(
            Signal(
                symbol=symbol,
                action=SignalAction.SELL,
                setup_type=SetupType.EMA_CROSSOVER,
                reason="EMA 9 crossed below EMA 21 — short-term trend turning bearish",
                entry=round(entry, 2),
                stop_loss=0.0,
                target=0.0,
                rr_ratio=0.0,
                confidence=0.65,
                timestamp=ts,
            )
        )

    # 3. RSI divergence
    divergences = rsi_divergence(df)
    if divergences.iloc[-1]:
        signals.append(
            Signal(
                symbol=symbol,
                action=SignalAction.SELL,
                setup_type=SetupType.RSI_PULLBACK,
                reason="Bearish RSI divergence — price making highs but momentum fading",
                entry=round(entry, 2),
                stop_loss=0.0,
                target=0.0,
                rr_ratio=0.0,
                confidence=0.55,
                timestamp=ts,
            )
        )

    # 4. Volume climax
    climax = volume_climax(df)
    if climax.iloc[-1]:
        signals.append(
            Signal(
                symbol=symbol,
                action=SignalAction.SELL,
                setup_type=SetupType.BREAKOUT,
                reason="Volume climax detected — extreme selling pressure, possible exhaustion top",
                entry=round(entry, 2),
                stop_loss=0.0,
                target=0.0,
                rr_ratio=0.0,
                confidence=0.60,
                timestamp=ts,
            )
        )

    return signals


def _is_breakout(df: pd.DataFrame, lookback: int = 20) -> bool:
    """Detect breakout above consolidation range with volume."""
    if len(df) < lookback + 1:
        return False
    resistance = df["high"].iloc[-(lookback + 1) : -1].max()
    last_close = df["close"].iloc[-1]
    surging = volume_surge(df, 1.5)
    return last_close > resistance and bool(surging.iloc[-1])


def _is_vwap_reclaim(df: pd.DataFrame) -> bool:
    """Detect VWAP reclaim: price crosses above VWAP."""
    if len(df) < 2:
        return False
    vwap_series = vwap(df)
    prev_below = df["close"].iloc[-2] < vwap_series.iloc[-2]
    curr_above = df["close"].iloc[-1] > vwap_series.iloc[-1]
    return prev_below and curr_above
