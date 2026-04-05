"""Correlation Alerts - detect divergences in historically correlated pairs.

Monitors rolling correlations between defined pairs and alerts when
correlation breaks down (potential pairs trading opportunity).
"""

import logging

import numpy as np
import pandas as pd

from src.data import client as alpaca_client
from src.data.cache import Cache

logger = logging.getLogger("mse.correlation")
_cache = Cache()

# Historically correlated pairs to monitor
PAIRS = [
    ("AAPL", "MSFT"),
    ("GOOGL", "META"),
    ("XOM", "CVX"),
    ("JPM", "BAC"),
    ("GS", "MS"),
    ("HD", "LOW"),
    ("KO", "PEP"),
    ("V", "MA"),
    ("UNH", "LLY"),
    ("CAT", "DE"),
    ("BA", "RTX"),
    ("NVDA", "AMD"),
    ("CRM", "NOW"),
    ("NEE", "DUK"),
    ("SPY", "QQQ"),
]


def analyze_pair(sym_a: str, sym_b: str, days: int = 60, window: int = 20) -> dict | None:
    """Analyze correlation between two symbols.

    Returns correlation stats and divergence detection.
    """
    cache_key = f"corr_{sym_a}_{sym_b}_{days}_{window}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        df_a = alpaca_client.get_bars(sym_a, days=days)
        df_b = alpaca_client.get_bars(sym_b, days=days)
    except Exception:
        return None

    if df_a is None or df_b is None or len(df_a) < window + 10 or len(df_b) < window + 10:
        return None

    # Align by date
    ret_a = df_a["close"].pct_change().dropna()
    ret_b = df_b["close"].pct_change().dropna()

    # Align indices
    common = ret_a.index.intersection(ret_b.index)
    if len(common) < window + 5:
        return None

    ret_a = ret_a.loc[common]
    ret_b = ret_b.loc[common]

    # Rolling correlation
    rolling_corr = ret_a.rolling(window).corr(ret_b).dropna()
    if len(rolling_corr) < 5:
        return None

    current_corr = float(rolling_corr.iloc[-1])
    avg_corr = float(rolling_corr.mean())
    std_corr = float(rolling_corr.std()) if rolling_corr.std() > 0 else 0.1

    # Z-score of current correlation vs historical
    z_score = (current_corr - avg_corr) / std_corr

    # Price divergence: compare recent returns
    recent_days = min(10, len(ret_a))
    ret_a_recent = float(ret_a.iloc[-recent_days:].sum()) * 100
    ret_b_recent = float(ret_b.iloc[-recent_days:].sum()) * 100
    return_spread = ret_a_recent - ret_b_recent

    # Detect divergence
    diverging = abs(z_score) > 1.5 or (abs(return_spread) > 5 and current_corr < avg_corr - std_corr)

    alert_reasons = []
    if diverging:
        if z_score < -1.5:
            alert_reasons.append(
                f"{sym_a}/{sym_b}: Correlation breakdown ({current_corr:.2f} vs avg {avg_corr:.2f}). "
                f"{sym_a} {ret_a_recent:+.1f}% vs {sym_b} {ret_b_recent:+.1f}%"
            )
        if abs(return_spread) > 5:
            leader = sym_a if ret_a_recent > ret_b_recent else sym_b
            lagger = sym_b if leader == sym_a else sym_a
            alert_reasons.append(
                f"{leader} outperforming {lagger} by {abs(return_spread):.1f}% over {recent_days}d"
            )

    result = {
        "pair": [sym_a, sym_b],
        "current_correlation": round(current_corr, 3),
        "avg_correlation": round(avg_corr, 3),
        "z_score": round(z_score, 2),
        "return_a": round(ret_a_recent, 2),
        "return_b": round(ret_b_recent, 2),
        "return_spread": round(return_spread, 2),
        "diverging": diverging,
        "alert_reasons": alert_reasons,
        "correlation_history": [round(float(v), 3) for v in rolling_corr.iloc[-20:].values],
    }

    _cache.set(cache_key, result)
    return result


def scan_pairs(days: int = 60) -> list[dict]:
    """Scan all defined pairs for divergences.

    Returns results sorted by divergence strength.
    """
    cache_key = f"corr_scan_{days}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    results = []
    for sym_a, sym_b in PAIRS:
        result = analyze_pair(sym_a, sym_b, days=days)
        if result:
            results.append(result)

    results.sort(key=lambda r: (r["diverging"], abs(r["z_score"])), reverse=True)

    if results:
        _cache.set(cache_key, results)
    return results
