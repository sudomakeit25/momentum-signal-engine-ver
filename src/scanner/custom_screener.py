"""Custom Screener - user-defined scan criteria.

Lets users build custom filters beyond the default scanner: min RS,
min score, specific setup types, EMA filters, volume thresholds, etc.
"""

import logging

import pandas as pd

from src.data import client as alpaca_client
from src.data.models import ScanResult, SetupType
from src.scanner.screener import get_default_universe, scan_universe
from src.signals.indicators import relative_strength_vs_spy

logger = logging.getLogger("mse.custom_screener")


def run_custom_scan(
    min_price: float = 5,
    max_price: float = 500,
    min_volume: int = 500_000,
    min_score: float = 0,
    min_rs: float = 0,
    setup_types: list[str] | None = None,
    require_ema_aligned: bool = False,
    min_change_pct: float | None = None,
    max_change_pct: float | None = None,
    symbols: list[str] | None = None,
    top_n: int = 50,
) -> list[dict]:
    """Run a custom scan with user-defined criteria.

    Returns filtered and ranked results.
    """
    source_symbols = symbols or get_default_universe()

    # Run base scan
    results = scan_universe(
        source_symbols,
        top_n=200,
        min_price=min_price,
        max_price=max_price,
        min_volume=min_volume,
    )

    if not isinstance(results, list):
        results = results[0] if isinstance(results, tuple) else []

    filtered = []
    for r in results:
        # Score filter
        if r.score < min_score:
            continue

        # RS filter
        if min_rs > 0 and r.relative_strength < min_rs:
            continue

        # Setup type filter
        if setup_types:
            r_types = {st.value if hasattr(st, 'value') else str(st) for st in r.setup_types}
            if not r_types.intersection(set(setup_types)):
                continue

        # Change % filter
        if min_change_pct is not None and r.change_pct < min_change_pct:
            continue
        if max_change_pct is not None and r.change_pct > max_change_pct:
            continue

        # EMA alignment filter
        if require_ema_aligned:
            has_ema = any(
                (st.value if hasattr(st, 'value') else str(st)) == "ema_crossover"
                for st in r.setup_types
            )
            if not has_ema:
                continue

        filtered.append({
            "symbol": r.symbol,
            "price": r.price,
            "change_pct": r.change_pct,
            "volume": r.volume,
            "avg_volume": r.avg_volume,
            "relative_strength": r.relative_strength,
            "score": r.score,
            "setup_types": [st.value if hasattr(st, 'value') else str(st) for st in r.setup_types],
            "signal_count": len(r.signals),
        })

    filtered.sort(key=lambda r: r["score"], reverse=True)
    return filtered[:top_n]


def get_available_filters() -> dict:
    """Return available filter options for the UI."""
    return {
        "setup_types": [st.value for st in SetupType],
        "defaults": {
            "min_price": 5,
            "max_price": 500,
            "min_volume": 500_000,
            "min_score": 0,
            "min_rs": 0,
            "top_n": 50,
        },
    }
