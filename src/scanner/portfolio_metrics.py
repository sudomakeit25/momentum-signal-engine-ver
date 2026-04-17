"""Portfolio-level metrics: sector weights, correlations, beta, drawdown.

Takes a list of {symbol, shares} holdings and produces everything the
/holdings page needs for aggregate analysis. One Alpaca batch fetch
feeds all calculations.
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from src.data import client, fmp_client

logger = logging.getLogger("mse.portfolio_metrics")


# Fallback sector guesses for tickers we can't reach via FMP.
_FALLBACK_SECTORS: dict[str, str] = {
    "SPY": "Index", "QQQ": "Index", "IWM": "Index", "DIA": "Index",
    "XLF": "Financial Services", "XLE": "Energy", "XLK": "Technology", "XLV": "Healthcare",
    "BTC/USD": "Crypto", "ETH/USD": "Crypto", "SOL/USD": "Crypto",
    "DOGE/USD": "Crypto", "AVAX/USD": "Crypto", "LINK/USD": "Crypto",
}


def _sector_of(symbol: str) -> str:
    if symbol in _FALLBACK_SECTORS:
        return _FALLBACK_SECTORS[symbol]
    try:
        profile = fmp_client.get_company_profile(symbol)
        sector = profile.get("sector") if profile else ""
        return sector or "Unknown"
    except Exception:
        return "Unknown"


def _max_drawdown(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    running_max = equity.cummax()
    dd = (equity - running_max) / running_max
    return float(dd.min()) * 100


def analyze_portfolio(holdings: list[dict]) -> dict:
    """Compute portfolio-level stats and per-holding details.

    `holdings` is a list of {"symbol": str, "shares": float?}.  Holdings
    with missing shares are included but count as zero weight in aggregate
    stats — they still show up in the correlation matrix.
    """
    symbols = [h["symbol"].upper() for h in holdings]
    if not symbols:
        return {"error": "no holdings provided"}

    shares_map = {h["symbol"].upper(): float(h.get("shares", 0) or 0) for h in holdings}

    # One Alpaca call for everything (plus SPY for beta)
    fetch_symbols = list({*symbols, "SPY"})
    try:
        bars_map = client.get_multi_bars(fetch_symbols, days=400)
    except Exception as e:
        return {"error": f"failed to fetch bars: {e}"}

    spy_df = bars_map.get("SPY")
    if spy_df is None or spy_df.empty:
        return {"error": "SPY bars unavailable"}

    # Per-symbol closing series
    closes: dict[str, pd.Series] = {}
    for sym in symbols:
        df = bars_map.get(sym)
        if df is not None and not df.empty:
            closes[sym] = df["close"].astype(float)

    # Sectors in parallel (cache-backed, so repeat hits are instant)
    sector_map: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for sym, sector in zip(symbols, pool.map(_sector_of, symbols)):
            sector_map[sym] = sector

    # Per-holding
    per_holding: list[dict] = []
    total_value = 0.0
    for sym in symbols:
        series = closes.get(sym)
        price = float(series.iloc[-1]) if series is not None and len(series) else 0.0
        shares = shares_map.get(sym, 0.0)
        value = price * shares
        total_value += value
        ret_1y = None
        if series is not None and len(series) > 252:
            start = float(series.iloc[-253])
            if start > 0:
                ret_1y = (price / start - 1) * 100
        per_holding.append({
            "symbol": sym,
            "sector": sector_map[sym],
            "price": round(price, 2),
            "shares": shares,
            "value": round(value, 2),
            "ret_1y_pct": round(ret_1y, 2) if ret_1y is not None else None,
        })

    # Fill weights now that we have total value
    for h in per_holding:
        h["weight"] = round(h["value"] / total_value, 4) if total_value > 0 else 0.0

    # Sector weights
    sector_weights: dict[str, float] = {}
    for h in per_holding:
        if total_value > 0:
            sector_weights[h["sector"]] = sector_weights.get(h["sector"], 0.0) + h["weight"]
    sector_weights = {k: round(v, 4) for k, v in sorted(
        sector_weights.items(), key=lambda kv: -kv[1],
    )}

    # Build an aligned returns DataFrame for correlation / beta / drawdown
    frames = {sym: s for sym, s in closes.items() if len(s) >= 30}
    if frames:
        returns = pd.DataFrame({sym: s.pct_change() for sym, s in frames.items()}).dropna()
    else:
        returns = pd.DataFrame()

    correlation_matrix: dict = {"symbols": [], "matrix": []}
    if not returns.empty and returns.shape[1] >= 2:
        corr = returns.corr().round(3)
        correlation_matrix = {
            "symbols": list(corr.columns),
            "matrix": corr.values.tolist(),
        }

    # Portfolio returns weighted by dollar value of each holding
    portfolio_beta = None
    portfolio_vol_pct = None
    portfolio_max_dd_pct = None
    portfolio_1y_return_pct = None

    if total_value > 0 and not returns.empty:
        weights = {
            h["symbol"]: h["weight"]
            for h in per_holding
            if h["symbol"] in returns.columns
        }
        if weights:
            w_sum = sum(weights.values())
            if w_sum > 0:
                weights = {k: v / w_sum for k, v in weights.items()}
                port_ret = sum(
                    returns[sym] * w for sym, w in weights.items()
                )

                spy_returns = spy_df["close"].pct_change().dropna()
                aligned = pd.concat(
                    [port_ret, spy_returns], axis=1, join="inner"
                ).dropna()
                if len(aligned) >= 30:
                    cov = float(aligned.iloc[:, 0].cov(aligned.iloc[:, 1]))
                    var_spy = float(aligned.iloc[:, 1].var())
                    if var_spy > 0:
                        portfolio_beta = round(cov / var_spy, 3)

                portfolio_vol_pct = round(
                    float(port_ret.std()) * math.sqrt(252) * 100, 2
                )

                equity = (1 + port_ret.fillna(0)).cumprod()
                portfolio_max_dd_pct = round(_max_drawdown(equity), 2)

                if len(port_ret) >= 252:
                    last_year = port_ret.iloc[-252:]
                    portfolio_1y_return_pct = round(
                        (float((1 + last_year).prod()) - 1) * 100, 2
                    )

    return {
        "total_value": round(total_value, 2),
        "holdings": per_holding,
        "sector_weights": sector_weights,
        "correlation": correlation_matrix,
        "portfolio": {
            "beta_vs_spy": portfolio_beta,
            "annualized_vol_pct": portfolio_vol_pct,
            "max_drawdown_pct": portfolio_max_dd_pct,
            "return_1y_pct": portfolio_1y_return_pct,
        },
    }
