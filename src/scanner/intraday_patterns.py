"""Intraday pattern detection on 5-minute bars.

Scans recent intraday data (default 90-minute window) for three pattern
families that map to actionable signals during the trading day:

  V-reversal       — sharp drop then sharp recovery from the low
                     (e.g. CLSK 2026-04-23: $13.20 -> $11.42 -> $12.16)
  Inverted-V       — sharp rally then sharp fade from the high
                     (e.g. AMD 2026-04-23: pop and immediate retrace)
  Sustained move   — sharp move with no recovery, lower lows continuing
                     after the drop (e.g. AST, RKLB on 2026-04-23)

All three share the same window math; what differs is which extreme
they look at and what they require to happen after the extreme.

The user-facing contract: one signal per (symbol, pattern_type) per
trading session. Re-firing the same pattern within the same session is
suppressed downstream by the dispatcher's dedup layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging

import pandas as pd

from src.data import client

logger = logging.getLogger("mse.intraday_patterns")


# Defaults tuned on the four examples that motivated this feature
# (CLSK, AMD, AST, RKLB on 2026-04-23). They reject most noise on liquid
# names while still catching real Vs and breakdowns.
DEFAULT_TIMEFRAME_MINUTES = 5
DEFAULT_WINDOW_MINUTES = 90        # 18 bars at 5-min
DEFAULT_MIN_MOVE_PCT = 3.0         # at least 3% drop or rally to count
DEFAULT_MIN_RECOVERY_FRAC = 0.3    # V/inverted-V: recovered >= 30% of move
                                   # (CLSK on 2026-04-23 only retraced 42% off
                                   # the low and was clearly a V; 50% rejected
                                   # the motivating example)
DEFAULT_MIN_BARS_AFTER_EXTREME = 2 # fire after the V is actually forming
DEFAULT_BREAKDOWN_FOLLOWTHROUGH = 0.0  # sustained: still within 1/3 of the extreme


@dataclass
class IntradayPattern:
    symbol: str
    pattern_type: str        # "v_reversal" | "inverted_v" | "breakdown" | "breakout"
    action: str              # "BUY" | "SELL"
    trigger_price: float     # current/last close
    extreme_price: float     # the high or low that anchors the pattern
    move_pct: float          # signed % from the pre-extreme reference to the extreme
    recovery_pct: float      # signed % from the extreme to current price
    volume_confirmed: bool   # recovery-side volume > drop-side volume
    detected_at: datetime    # UTC

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "pattern_type": self.pattern_type,
            "action": self.action,
            "trigger_price": round(self.trigger_price, 2),
            "extreme_price": round(self.extreme_price, 2),
            "move_pct": round(self.move_pct, 2),
            "recovery_pct": round(self.recovery_pct, 2),
            "volume_confirmed": self.volume_confirmed,
            "detected_at": self.detected_at.isoformat(),
        }


def _trim_window(df: pd.DataFrame, window_minutes: int, timeframe_minutes: int) -> pd.DataFrame:
    """Keep only the most recent N bars."""
    bars_in_window = max(window_minutes // timeframe_minutes, 4)
    return df.tail(bars_in_window)


def _volume_split(df: pd.DataFrame, pivot_idx: int) -> tuple[float, float]:
    """Sum of volume before vs after a pivot row."""
    before = df.iloc[:pivot_idx]["volume"].sum()
    after = df.iloc[pivot_idx + 1:]["volume"].sum()
    return float(before), float(after)


def detect_v_reversal(
    df: pd.DataFrame,
    symbol: str,
    *,
    min_drop_pct: float = DEFAULT_MIN_MOVE_PCT,
    min_recovery_frac: float = DEFAULT_MIN_RECOVERY_FRAC,
    min_bars_after_extreme: int = DEFAULT_MIN_BARS_AFTER_EXTREME,
) -> IntradayPattern | None:
    """Sharp drop then recovery from the low (CLSK shape).

    Window's lowest low must be in the middle (not at the edges), the
    drop into it must be >= min_drop_pct, and the current price must
    have recovered at least min_recovery_frac of that drop. Fires BUY.
    """
    if df is None or len(df) < 6:
        return None

    low_idx = int(df["low"].values.argmin())
    if low_idx == 0 or low_idx >= len(df) - min_bars_after_extreme:
        return None  # need bars on both sides of the low

    pre_high = float(df.iloc[:low_idx + 1]["high"].max())
    extreme_price = float(df.iloc[low_idx]["low"])
    last_close = float(df.iloc[-1]["close"])

    if pre_high <= 0:
        return None
    drop_pct = (extreme_price - pre_high) / pre_high * 100  # negative
    if abs(drop_pct) < min_drop_pct:
        return None

    drop_amount = pre_high - extreme_price
    if drop_amount <= 0:
        return None
    recovery_amount = last_close - extreme_price
    recovery_frac = recovery_amount / drop_amount
    if recovery_frac < min_recovery_frac:
        return None

    before_vol, after_vol = _volume_split(df, low_idx)
    volume_confirmed = after_vol >= before_vol

    return IntradayPattern(
        symbol=symbol,
        pattern_type="v_reversal",
        action="BUY",
        trigger_price=last_close,
        extreme_price=extreme_price,
        move_pct=drop_pct,
        recovery_pct=(last_close - extreme_price) / extreme_price * 100,
        volume_confirmed=volume_confirmed,
        detected_at=datetime.now(timezone.utc),
    )


def detect_inverted_v(
    df: pd.DataFrame,
    symbol: str,
    *,
    min_rally_pct: float = DEFAULT_MIN_MOVE_PCT,
    min_fade_frac: float = DEFAULT_MIN_RECOVERY_FRAC,
    min_bars_after_extreme: int = DEFAULT_MIN_BARS_AFTER_EXTREME,
) -> IntradayPattern | None:
    """Sharp rally then fade from the high (AMD shape). Fires SELL."""
    if df is None or len(df) < 6:
        return None

    high_idx = int(df["high"].values.argmax())
    if high_idx == 0 or high_idx >= len(df) - min_bars_after_extreme:
        return None

    pre_low = float(df.iloc[:high_idx + 1]["low"].min())
    extreme_price = float(df.iloc[high_idx]["high"])
    last_close = float(df.iloc[-1]["close"])

    if pre_low <= 0:
        return None
    rally_pct = (extreme_price - pre_low) / pre_low * 100  # positive
    if rally_pct < min_rally_pct:
        return None

    rally_amount = extreme_price - pre_low
    if rally_amount <= 0:
        return None
    fade_amount = extreme_price - last_close
    fade_frac = fade_amount / rally_amount
    if fade_frac < min_fade_frac:
        return None

    before_vol, after_vol = _volume_split(df, high_idx)
    volume_confirmed = after_vol >= before_vol

    return IntradayPattern(
        symbol=symbol,
        pattern_type="inverted_v",
        action="SELL",
        trigger_price=last_close,
        extreme_price=extreme_price,
        move_pct=rally_pct,
        recovery_pct=(last_close - extreme_price) / extreme_price * 100,  # negative
        volume_confirmed=volume_confirmed,
        detected_at=datetime.now(timezone.utc),
    )


def detect_sustained_move(
    df: pd.DataFrame,
    symbol: str,
    *,
    min_move_pct: float = DEFAULT_MIN_MOVE_PCT,
    max_recovery_frac: float = 0.3,
) -> IntradayPattern | None:
    """Sharp move from the window's start that is NOT being reversed.

    The window high (for breakdown) must be in the early third of the
    window, with the price now significantly below it and within
    max_recovery_frac of the lowest low. Mirror logic for breakout.
    Fires SELL on breakdown, BUY on breakout.
    """
    if df is None or len(df) < 6:
        return None

    last_close = float(df.iloc[-1]["close"])
    early_third = max(2, len(df) // 3)

    # Breakdown: window high is in the early third, price has fallen
    # since, and current close is near the window low.
    high_idx = int(df["high"].values.argmax())
    if high_idx < early_third:
        window_high = float(df.iloc[high_idx]["high"])
        window_low = float(df["low"].min())
        if window_high > 0:
            move_pct = (window_low - window_high) / window_high * 100  # negative
            if abs(move_pct) >= min_move_pct:
                drop_amount = window_high - window_low
                if drop_amount > 0:
                    recovery_amount = last_close - window_low
                    recovery_frac = recovery_amount / drop_amount
                    if recovery_frac <= max_recovery_frac:
                        before_vol, after_vol = _volume_split(df, high_idx)
                        volume_confirmed = after_vol >= before_vol
                        return IntradayPattern(
                            symbol=symbol,
                            pattern_type="breakdown",
                            action="SELL",
                            trigger_price=last_close,
                            extreme_price=window_high,
                            move_pct=move_pct,
                            recovery_pct=recovery_frac * 100,
                            volume_confirmed=volume_confirmed,
                            detected_at=datetime.now(timezone.utc),
                        )

    # Breakout: window low is in the early third, price has rallied,
    # and current close is near the window high.
    low_idx = int(df["low"].values.argmin())
    if low_idx < early_third:
        window_low = float(df.iloc[low_idx]["low"])
        window_high = float(df["high"].max())
        if window_low > 0:
            move_pct = (window_high - window_low) / window_low * 100
            if move_pct >= min_move_pct:
                rally_amount = window_high - window_low
                if rally_amount > 0:
                    pullback_amount = window_high - last_close
                    pullback_frac = pullback_amount / rally_amount
                    if pullback_frac <= max_recovery_frac:
                        before_vol, after_vol = _volume_split(df, low_idx)
                        volume_confirmed = after_vol >= before_vol
                        return IntradayPattern(
                            symbol=symbol,
                            pattern_type="breakout",
                            action="BUY",
                            trigger_price=last_close,
                            extreme_price=window_high,
                            move_pct=move_pct,
                            recovery_pct=-pullback_frac * 100,
                            volume_confirmed=volume_confirmed,
                            detected_at=datetime.now(timezone.utc),
                        )

    return None


_DETECTORS = (detect_v_reversal, detect_inverted_v, detect_sustained_move)


def scan_intraday_patterns(
    symbols: list[str],
    *,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    timeframe_minutes: int = DEFAULT_TIMEFRAME_MINUTES,
) -> list[IntradayPattern]:
    """Run all detectors over the given symbols. Returns at most one
    pattern per symbol — the first detector that fires wins, with the
    pattern types tried in priority order (V > inverted-V > sustained).
    Volume-confirmed patterns are kept; unconfirmed ones are dropped to
    cut noise.
    """
    if not symbols:
        return []

    bars_map = client.get_intraday_multi_bars(
        symbols,
        minutes_back=window_minutes + 30,
        timeframe_minutes=timeframe_minutes,
    )

    detected: list[IntradayPattern] = []
    for symbol in symbols:
        df = bars_map.get(symbol)
        if df is None or df.empty:
            continue
        df = _trim_window(df, window_minutes, timeframe_minutes)
        if len(df) < 6:
            continue
        for fn in _DETECTORS:
            try:
                pattern = fn(df, symbol)
            except Exception as e:
                logger.debug("Pattern detection failed for %s/%s: %s", symbol, fn.__name__, e)
                continue
            if pattern is not None and pattern.volume_confirmed:
                detected.append(pattern)
                break

    return detected
