"""Sector map: 1-year returns for the 11 SPDR sector ETFs plus SPY baseline."""

from __future__ import annotations

import logging

import pandas as pd

from src.data import client

logger = logging.getLogger("mse.sector_map")

# SPDR sector ETFs + SPY baseline
SECTOR_ETFS: dict[str, str] = {
    "SPY": "S&P 500",
    "XLF": "Financial Services",
    "XLE": "Energy",
    "XLU": "Utilities",
    "XLB": "Basic Materials",
    "XLRE": "Real Estate",
    "XLV": "Healthcare",
    "XLY": "Consumer Cyclical",
    "XLI": "Industrials",
    "XLC": "Communication Services",
    "XLK": "Technology",
    "XLP": "Consumer Defensive",
}


def get_sector_map(days: int = 365) -> dict:
    """Return normalized cumulative-return series for each sector ETF."""
    symbols = list(SECTOR_ETFS.keys())
    try:
        bars = client.get_multi_bars(symbols, days=days + 30)
    except Exception as e:
        return {"error": f"fetch failed: {e}"}

    series_map: dict[str, pd.Series] = {}
    for sym in symbols:
        df = bars.get(sym)
        if df is None or df.empty:
            continue
        close = df["close"].astype(float).tail(days)
        if len(close) < 30:
            continue
        start = float(close.iloc[0])
        if start <= 0:
            continue
        series_map[sym] = (close / start - 1) * 100

    if not series_map:
        return {"error": "no sector data"}

    aligned = pd.concat(series_map, axis=1).ffill().dropna()

    rows = []
    for idx, row in aligned.iterrows():
        rec: dict = {"date": idx.strftime("%Y-%m-%d")}
        for sym in aligned.columns:
            rec[sym] = round(float(row[sym]), 2)
        rows.append(rec)

    # Latest ranking
    ranking = []
    for sym in symbols:
        if sym in aligned.columns:
            ranking.append({
                "symbol": sym,
                "label": SECTOR_ETFS[sym],
                "return_pct": round(float(aligned[sym].iloc[-1]), 2),
            })
    ranking.sort(key=lambda r: -r["return_pct"])

    return {
        "series": rows,
        "ranking": ranking,
        "sectors": [{"symbol": s, "label": SECTOR_ETFS[s]} for s in symbols],
    }
