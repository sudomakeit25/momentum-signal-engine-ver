"""Cyclical / mean-reverting pattern detection.

Detects stocks whose price oscillates between a consistent range with
a predictable rhythm — the opposite profile from a trending stock.
Useful for mean-reversion trading: buy near the bottom of the range,
sell near the top.

Criteria (all four must hold):
  1. Regular peaks and troughs      — ≥ 3 full cycles in the window
  2. Meaningful amplitude            — mean peak-to-trough ≥ 8%
  3. Predictable rhythm              — CV of time-between-peaks ≤ 0.4
  4. Similar amplitude                — CV of swing sizes ≤ 0.4

Coefficient of variation (std/mean) is used so the regularity test is
scale-free: a 10%-amplitude stock and a 50%-amplitude stock both
qualify as "regular" if their swings are consistent relative to their
own mean.

Output includes a `range_position` (0 = at recent trough, 1 = at recent
peak) and a BUY/SELL/HOLD bias so the UI can rank stocks by how close
they are to an actionable entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, stdev
from typing import Iterable
import logging

import pandas as pd
from alpaca.data.timeframe import TimeFrame

from src.data import client

logger = logging.getLogger("mse.cyclical")


DEFAULT_ZIGZAG_THRESHOLD_PCT = 4.0
DEFAULT_MIN_CYCLES = 2
DEFAULT_MIN_MEAN_AMPLITUDE_PCT = 5.0
DEFAULT_AMPLITUDE_CV_MAX = 0.4
DEFAULT_PERIOD_CV_MAX = 0.4
DEFAULT_HOURLY_LOOKBACK_DAYS = 7


# Curated universe of names that are *prior candidates* for cyclical
# behavior. Sector ETFs explicitly rotate against each other; utilities
# / staples / REITs trade in narrow ranges driven by rate moves; bond
# proxies (TLT, HYG) oscillate with yields. The momentum-based top-N
# universe misses these because they rarely have headline volatility,
# so we always include this set in the scan regardless of momentum.
CYCLICAL_CANDIDATES_EXTRA: tuple[str, ...] = (
    # Broad-market and sector ETFs (the rotation baseline)
    "SPY", "QQQ", "IWM", "DIA",
    "XLE", "XLF", "XLK", "XLV", "XLP", "XLY",
    "XLI", "XLB", "XLRE", "XLC", "XLU",
    # Fixed-income and rate-sensitive ETFs
    "TLT", "HYG", "LQD", "TIP",
    # Commodity and FX proxies
    "GLD", "SLV", "USO", "UNG", "UUP",
    # Utilities — classic rate-driven oscillators
    "NEE", "DUK", "SO", "AEP", "D", "ED", "EXC",
    # Consumer staples — slow swing range traders
    "KO", "PG", "PEP", "KMB", "CL", "WMT", "COST",
    # Telecom — typically range-bound
    "T", "VZ", "TMUS",
    # REITs
    "O", "AMT", "PLD", "EQIX", "SPG",
    # Energy majors (oscillate with crude)
    "XOM", "CVX", "COP", "OXY",
    # Big banks (oscillate with rate expectations)
    "JPM", "BAC", "WFC", "C", "GS", "MS",
    # Defense — quiet oscillators
    "LMT", "RTX", "NOC", "GD",
    # Industrials with cyclical demand
    "CAT", "DE", "MMM",
)

# Notes on defaults — tuned 2026-04-23 against CLSK / MARA / RIOT hourly
# bars where the user-observed swings were clearly cyclical but much
# smaller than a sine wave. The weekly chart's apparent 10% amplitude
# spans multiple partial cycles; individual hourly cycles oscillate
# ~5–8%. Require at least 2 full cycles so shorter windows can still
# surface a pattern, and keep the CV gates strict so only *regular*
# oscillations qualify.


@dataclass
class ZigzagPoint:
    index: int
    timestamp: pd.Timestamp | None
    price: float
    kind: str  # "peak" | "trough"


@dataclass
class CyclicalStock:
    symbol: str
    cycles: int
    mean_amplitude_pct: float
    amplitude_cv: float
    mean_period_bars: float
    period_cv: float
    range_position: float      # 0 = at recent trough, 1 = at recent peak
    range_low: float
    range_high: float
    current_price: float
    cyclical_score: float      # 0..1, higher = more regular
    bias: str                  # "BUY" | "SELL" | "HOLD"

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "cycles": self.cycles,
            "mean_amplitude_pct": self.mean_amplitude_pct,
            "amplitude_cv": self.amplitude_cv,
            "mean_period_bars": self.mean_period_bars,
            "period_cv": self.period_cv,
            "range_position": self.range_position,
            "range_low": self.range_low,
            "range_high": self.range_high,
            "current_price": self.current_price,
            "cyclical_score": self.cyclical_score,
            "bias": self.bias,
        }


def find_zigzag_extremes(
    closes: pd.Series,
    threshold_pct: float = DEFAULT_ZIGZAG_THRESHOLD_PCT,
) -> list[ZigzagPoint]:
    """Walk the price series and emit a peak or trough only once the
    price has moved at least `threshold_pct` from the running extreme
    in the opposite direction. Filters out wiggles smaller than the
    threshold and keeps the extremes a human would annotate.

    We track the running high AND low since the last confirmed extreme,
    so slow directional moves (e.g. a 12% rise in 4% steps) still
    trigger once the cumulative move crosses the threshold.
    """
    n = len(closes)
    if n < 2:
        return []

    extremes: list[ZigzagPoint] = []

    def _ts(i: int) -> pd.Timestamp | None:
        try:
            return closes.index[i]
        except Exception:
            return None

    hi_idx, hi_price = 0, float(closes.iloc[0])
    lo_idx, lo_price = 0, float(closes.iloc[0])
    direction = 0  # 0 = unknown, +1 = in upswing, -1 = in downswing

    for i in range(1, n):
        c = float(closes.iloc[i])
        if c > hi_price:
            hi_idx, hi_price = i, c
        if c < lo_price:
            lo_idx, lo_price = i, c

        # Look for a confirmed trough first (an upswing of threshold_pct
        # from the running low). Applies to direction 0 (first move up)
        # or direction -1 (reversal from a prior peak).
        if direction <= 0 and lo_price > 0:
            if (c - lo_price) / lo_price * 100 >= threshold_pct:
                extremes.append(
                    ZigzagPoint(lo_idx, _ts(lo_idx), lo_price, "trough")
                )
                hi_idx, hi_price = i, c
                lo_idx, lo_price = i, c
                direction = 1
                continue

        # Otherwise check for a confirmed peak (downswing of threshold_pct
        # from the running high).
        if direction >= 0 and hi_price > 0:
            if (hi_price - c) / hi_price * 100 >= threshold_pct:
                extremes.append(
                    ZigzagPoint(hi_idx, _ts(hi_idx), hi_price, "peak")
                )
                hi_idx, hi_price = i, c
                lo_idx, lo_price = i, c
                direction = -1
                continue

    return extremes


def _cv(values: list[float]) -> float:
    """Coefficient of variation (std/mean). 0 when only one sample."""
    if len(values) < 2:
        return 0.0
    m = mean(values)
    if m == 0:
        return 0.0
    return stdev(values) / m


def detect_cyclical(
    bars: pd.DataFrame,
    symbol: str,
    *,
    zigzag_threshold_pct: float = DEFAULT_ZIGZAG_THRESHOLD_PCT,
    min_cycles: int = DEFAULT_MIN_CYCLES,
    min_mean_amplitude_pct: float = DEFAULT_MIN_MEAN_AMPLITUDE_PCT,
    amplitude_cv_max: float = DEFAULT_AMPLITUDE_CV_MAX,
    period_cv_max: float = DEFAULT_PERIOD_CV_MAX,
) -> CyclicalStock | None:
    """Return a CyclicalStock if the four regularity tests pass, else None."""
    if bars is None or len(bars) < 20:
        return None

    closes = bars["close"]
    extremes = find_zigzag_extremes(closes, threshold_pct=zigzag_threshold_pct)
    # Boundary artifact: the zigzag emits the starting bar as an
    # "extreme" when the window happens to open mid-cycle. That price
    # isn't a real turning point (there's no prior move in the opposite
    # direction), so drop it. Same logic doesn't apply to the last
    # extreme — that's a real swing that confirmed before we stopped
    # observing.
    if extremes and extremes[0].index == 0:
        extremes = extremes[1:]
    peaks = [e for e in extremes if e.kind == "peak"]
    troughs = [e for e in extremes if e.kind == "trough"]
    if len(peaks) < min_cycles or len(troughs) < min_cycles:
        return None

    # Amplitude of each cycle = peak - most recent preceding trough
    amplitudes: list[float] = []
    for peak in peaks:
        preceding = [t for t in troughs if t.index < peak.index]
        if not preceding:
            continue
        trough = preceding[-1]
        if trough.price <= 0:
            continue
        amp_pct = (peak.price - trough.price) / trough.price * 100
        if amp_pct > 0:
            amplitudes.append(amp_pct)
    if len(amplitudes) < min_cycles:
        return None

    mean_amp = mean(amplitudes)
    amp_cv = _cv(amplitudes)

    # Period = bar count between successive peaks
    peak_indices = [p.index for p in peaks]
    periods = [peak_indices[i + 1] - peak_indices[i] for i in range(len(peak_indices) - 1)]
    if not periods:
        return None
    mean_period = mean(periods)
    period_cv = _cv([float(p) for p in periods])

    # Regularity gate
    is_cyclical = (
        mean_amp >= min_mean_amplitude_pct
        and amp_cv <= amplitude_cv_max
        and period_cv <= period_cv_max
    )
    if not is_cyclical:
        return None

    # Range position using the most recent 3 peaks and 3 troughs
    recent_peaks = peaks[-3:]
    recent_troughs = troughs[-3:]
    range_high = max(p.price for p in recent_peaks)
    range_low = min(t.price for t in recent_troughs)
    current_price = float(closes.iloc[-1])
    if range_high > range_low:
        range_position = (current_price - range_low) / (range_high - range_low)
        range_position = max(0.0, min(1.0, range_position))
    else:
        range_position = 0.5

    if range_position <= 0.3:
        bias = "BUY"
    elif range_position >= 0.7:
        bias = "SELL"
    else:
        bias = "HOLD"

    # Score: how regular is the oscillation? Drops toward 0 as either CV
    # approaches its cap.
    cyclical_score = max(0.0, 1.0 - (amp_cv + period_cv) / 2.0)

    return CyclicalStock(
        symbol=symbol,
        cycles=min(len(peaks), len(troughs)),
        mean_amplitude_pct=round(mean_amp, 2),
        amplitude_cv=round(amp_cv, 3),
        mean_period_bars=round(float(mean_period), 1),
        period_cv=round(period_cv, 3),
        range_position=round(range_position, 3),
        range_low=round(range_low, 2),
        range_high=round(range_high, 2),
        current_price=round(current_price, 2),
        cyclical_score=round(cyclical_score, 3),
        bias=bias,
    )


def scan_cyclicals(
    symbols: Iterable[str],
    *,
    timeframe: TimeFrame = TimeFrame.Hour,
    lookback_days: int = DEFAULT_HOURLY_LOOKBACK_DAYS,
    min_mean_amplitude_pct: float = DEFAULT_MIN_MEAN_AMPLITUDE_PCT,
) -> list[CyclicalStock]:
    """Run detect_cyclical on every symbol. Results are sorted by
    cyclical_score descending so the UI can slice off the top N.

    Two modes are intended:
      - hourly bars over ~7 days for fast movers (default).
      - daily bars over ~60 days for slow oscillators (sector ETFs,
        utilities, REITs) — pass timeframe=TimeFrame.Day, lookback_days=60.
    """
    symbol_list = [s for s in symbols if s]
    if not symbol_list:
        return []

    try:
        bars_map = client.get_multi_bars(
            symbol_list,
            timeframe=timeframe,
            days=lookback_days,
        )
    except Exception as e:
        logger.warning("Cyclical scan: bar fetch failed: %s", e)
        return []

    results: list[CyclicalStock] = []
    for symbol in symbol_list:
        df = bars_map.get(symbol)
        if df is None or df.empty:
            continue
        try:
            r = detect_cyclical(
                df, symbol, min_mean_amplitude_pct=min_mean_amplitude_pct
            )
        except Exception as e:
            logger.debug("detect_cyclical failed for %s: %s", symbol, e)
            continue
        if r is not None:
            results.append(r)

    results.sort(key=lambda r: r.cyclical_score, reverse=True)
    return results
