"""Preset screener - canned strategies layered on the base scanner.

Exposes named strategies (momentum, breakout, pullback, oversold_bounce,
mean_reversion, trend_follow) that apply opinionated criteria. Unlike
`custom_screener`, the caller picks a strategy name and gets a curated list
without hand-tuning parameters.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from src.scanner.screener import get_default_universe, scan_universe
from src.signals.indicators import atr, ema, rsi, volume_sma

logger = logging.getLogger("mse.preset_screener")


STRATEGIES: dict[str, dict] = {
    "momentum": {
        "label": "Momentum leaders",
        "description": "High score, strong RS, EMAs stacked, near 52w high.",
    },
    "breakout": {
        "label": "Breakout candidates",
        "description": "Consolidating near highs with surging volume.",
    },
    "pullback": {
        "label": "Pullback in uptrend",
        "description": "Uptrending names pulled back to EMA21 with RSI 40-55.",
    },
    "oversold_bounce": {
        "label": "Oversold bounce",
        "description": "RSI under 30 with price above 200-day MA (quality dip).",
    },
    "mean_reversion": {
        "label": "Mean reversion",
        "description": "Stretched 2+ ATR from EMA21, RSI extremes.",
    },
    "trend_follow": {
        "label": "Long-term trend",
        "description": "Above 50 and 200 EMA, 50 > 200, 1-year return > 15%.",
    },
}


def list_strategies() -> list[dict]:
    """Return all available preset strategies."""
    return [{"key": k, **v} for k, v in STRATEGIES.items()]


def _passes(
    strategy: str,
    df: pd.DataFrame,
    score: float,
    rs: float,
    change_pct: float,
) -> tuple[bool, str]:
    """Apply a strategy's criteria to a symbol's bars. Returns (passed, note)."""
    if df is None or len(df) < 60:
        return False, "insufficient bars"

    close = df["close"]
    price = float(close.iloc[-1])
    ema9 = float(ema(close, 9).iloc[-1])
    ema21 = float(ema(close, 21).iloc[-1])
    ema50 = float(ema(close, 50).iloc[-1]) if len(close) >= 50 else ema21
    ema200 = float(ema(close, 200).iloc[-1]) if len(close) >= 200 else ema50
    rsi_val = float(rsi(close).iloc[-1])
    high_52w = float(close.tail(252).max()) if len(close) >= 100 else float(close.max())
    pct_off_high = (price - high_52w) / high_52w * 100
    avg_vol = float(volume_sma(df["volume"], 20).iloc[-1])
    rel_vol = float(df["volume"].iloc[-1]) / avg_vol if avg_vol > 0 else 0.0

    if strategy == "momentum":
        ok = score >= 60 and rs >= 1.0 and ema9 > ema21 > ema50 and pct_off_high > -8
        return ok, f"score={score:.0f} rs={rs:.2f} off_high={pct_off_high:.1f}%"

    if strategy == "breakout":
        last20_high = float(close.tail(20).max())
        ok = price >= last20_high * 0.99 and rel_vol >= 1.5 and ema21 > ema50
        return ok, f"rel_vol={rel_vol:.2f} off_20d_high={(price - last20_high) / last20_high * 100:.1f}%"

    if strategy == "pullback":
        near_ema21 = abs(price - ema21) / ema21 < 0.03
        ok = ema9 > ema21 > ema50 and 40 <= rsi_val <= 55 and near_ema21
        return ok, f"rsi={rsi_val:.1f} dist_ema21={(price - ema21) / ema21 * 100:.1f}%"

    if strategy == "oversold_bounce":
        ok = rsi_val <= 30 and price > ema200 and change_pct > -8
        return ok, f"rsi={rsi_val:.1f} above_ema200={price > ema200}"

    if strategy == "mean_reversion":
        atr_val = float(atr(df).iloc[-1])
        stretch = (price - ema21) / atr_val if atr_val > 0 else 0.0
        ok = abs(stretch) >= 2 and (rsi_val >= 70 or rsi_val <= 30)
        return ok, f"stretch={stretch:.2f}atr rsi={rsi_val:.1f}"

    if strategy == "trend_follow":
        ret_1y = 0.0
        if len(close) >= 252:
            ret_1y = (price / float(close.iloc[-252]) - 1) * 100
        ok = price > ema50 > ema200 and ret_1y > 15
        return ok, f"ret_1y={ret_1y:.1f}% ema50>200={ema50 > ema200}"

    return False, f"unknown strategy {strategy}"


def run_preset(
    strategy: str,
    symbols: list[str] | None = None,
    top_n: int = 25,
) -> dict:
    """Run a preset strategy over the universe and return ranked matches."""
    if strategy not in STRATEGIES:
        return {"error": f"unknown strategy '{strategy}'", "available": list(STRATEGIES.keys())}

    source = symbols or get_default_universe()
    base_results, bars_map = scan_universe(
        source,
        top_n=len(source),
        min_price=3.0,
        max_price=10_000.0,
        min_volume=300_000,
        return_bars=True,
    )
    result_by_sym = {r.symbol: r for r in base_results}

    matches: list[dict] = []

    def _check(sym: str) -> dict | None:
        df = bars_map.get(sym)
        base = result_by_sym.get(sym)
        score = base.score if base else 0.0
        rs = base.relative_strength if base else 0.0
        change_pct = base.change_pct if base else 0.0
        try:
            ok, note = _passes(strategy, df, score, rs, change_pct)
        except Exception as e:
            logger.debug("preset check failed for %s: %s", sym, e)
            return None
        if not ok:
            return None
        last_close = float(df["close"].iloc[-1])
        return {
            "symbol": sym,
            "price": round(last_close, 2),
            "change_pct": round(change_pct, 2),
            "score": round(score, 1),
            "relative_strength": round(rs, 3),
            "note": note,
        }

    with ThreadPoolExecutor(max_workers=8) as pool:
        for match in pool.map(_check, bars_map.keys()):
            if match:
                matches.append(match)

    matches.sort(key=lambda m: m["score"], reverse=True)

    info = STRATEGIES[strategy]
    return {
        "strategy": strategy,
        "label": info["label"],
        "description": info["description"],
        "universe_size": len(bars_map),
        "match_count": len(matches),
        "matches": matches[:top_n],
    }
