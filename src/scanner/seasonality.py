"""Monthly seasonality analysis.

Computes average return by calendar month (Jan-Dec) over N years of daily
bars. Also returns a year-by-month heatmap matrix so the UI can render
both aggregate bars and per-year detail.
"""

from __future__ import annotations

import logging

import pandas as pd

from src.data import client

logger = logging.getLogger("mse.seasonality")

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def analyze_seasonality(symbol: str, years: int = 10) -> dict:
    """Return monthly average returns and per-year heatmap for a symbol."""
    symbol = symbol.upper()
    try:
        df = client.get_bars(symbol, days=years * 365 + 30)
    except Exception as e:
        return {"symbol": symbol, "error": f"fetch failed: {e}"}

    if df is None or df.empty or len(df) < 60:
        return {"symbol": symbol, "error": "insufficient history"}

    close = df["close"].astype(float)
    # Resample to monthly close
    monthly = close.resample("ME").last().dropna()
    monthly_returns = monthly.pct_change().dropna() * 100

    if monthly_returns.empty:
        return {"symbol": symbol, "error": "no monthly data"}

    by_month = monthly_returns.groupby(monthly_returns.index.month)
    stats = []
    for m in range(1, 13):
        if m in by_month.groups:
            values = by_month.get_group(m)
            stats.append({
                "month": m,
                "label": MONTH_NAMES[m - 1],
                "avg_pct": round(float(values.mean()), 2),
                "median_pct": round(float(values.median()), 2),
                "win_rate": round(float((values > 0).sum()) / len(values) * 100, 1),
                "sample_size": int(len(values)),
            })
        else:
            stats.append({
                "month": m,
                "label": MONTH_NAMES[m - 1],
                "avg_pct": None,
                "median_pct": None,
                "win_rate": None,
                "sample_size": 0,
            })

    # Heatmap: rows = years, columns = months, values = monthly % return
    heatmap_rows = []
    for year, g in monthly_returns.groupby(monthly_returns.index.year):
        row = {"year": int(year)}
        for idx, val in g.items():
            row[MONTH_NAMES[idx.month - 1]] = round(float(val), 2)
        heatmap_rows.append(row)

    # Best / worst months
    valid = [s for s in stats if s["avg_pct"] is not None]
    best_month = max(valid, key=lambda s: s["avg_pct"]) if valid else None
    worst_month = min(valid, key=lambda s: s["avg_pct"]) if valid else None

    return {
        "symbol": symbol,
        "years_covered": len(heatmap_rows),
        "months": stats,
        "heatmap": heatmap_rows,
        "best_month": best_month,
        "worst_month": worst_month,
    }
