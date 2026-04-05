"""Extra data features: SPAC tracker, currency strength, commodities,
REITs, bonds, anomaly detection, sector rotation bot, social sentiment proxy.

Features 9, 56, 60, 65-68, 75.
"""

import logging
import numpy as np

from src.data import client as alpaca_client
from src.data.cache import Cache

logger = logging.getLogger("mse.extra")
_cache = Cache()


# --- 9. SPAC Tracker (using known SPAC ETFs as proxy) ---

def get_spac_overview() -> dict:
    """Get SPAC market overview via ETFs."""
    cache_key = "spac_overview"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    spacs = {"SPAK": "SPAC ETF", "SPCX": "SPAC & New Issue ETF"}
    results = []
    for sym, label in spacs.items():
        try:
            df = alpaca_client.get_bars(sym, days=30)
            if df is None or len(df) < 2:
                continue
            current = float(df["close"].iloc[-1])
            prev = float(df["close"].iloc[-2])
            change_5d = (current - float(df["close"].iloc[-5])) / float(df["close"].iloc[-5]) * 100 if len(df) >= 5 else 0
            results.append({"symbol": sym, "label": label, "price": round(current, 2), "change_1d": round((current - prev) / prev * 100, 2), "change_5d": round(change_5d, 2)})
        except Exception:
            continue

    result = {"etfs": results, "note": "SPAC market proxy via ETFs. Detailed SPAC data requires premium API."}
    if results:
        _cache.set(cache_key, result)
    return result


# --- 56. Sector Rotation Strategy ---

def get_sector_rotation_signal() -> dict:
    """Simple sector rotation: buy strongest sector ETF, avoid weakest."""
    cache_key = "sector_rotation"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    etfs = {"XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Healthcare", "XLI": "Industrials", "XLP": "Staples", "XLY": "Discretionary", "XLU": "Utilities", "XLB": "Materials", "XLRE": "Real Estate"}
    results = []

    for sym, sector in etfs.items():
        try:
            df = alpaca_client.get_bars(sym, days=60)
            if df is None or len(df) < 20:
                continue
            close = df["close"]
            current = float(close.iloc[-1])
            mom_20d = (current - float(close.iloc[-20])) / float(close.iloc[-20]) * 100
            mom_5d = (current - float(close.iloc[-5])) / float(close.iloc[-5]) * 100 if len(close) >= 5 else 0

            ema9 = float(close.ewm(span=9).mean().iloc[-1])
            ema21 = float(close.ewm(span=21).mean().iloc[-1])

            results.append({"symbol": sym, "sector": sector, "price": round(current, 2), "momentum_20d": round(mom_20d, 2), "momentum_5d": round(mom_5d, 2), "ema_bullish": ema9 > ema21})
        except Exception:
            continue

    results.sort(key=lambda r: r["momentum_20d"], reverse=True)

    buy = results[0] if results else None
    avoid = results[-1] if results else None

    result = {
        "rankings": results,
        "recommendation": {
            "buy": {"symbol": buy["symbol"], "sector": buy["sector"], "momentum": buy["momentum_20d"]} if buy else None,
            "avoid": {"symbol": avoid["symbol"], "sector": avoid["sector"], "momentum": avoid["momentum_20d"]} if avoid else None,
        },
    }
    _cache.set(cache_key, result)
    return result


# --- 65. Currency Strength ---

def get_currency_strength() -> list[dict]:
    """Get currency strength via forex ETFs."""
    cache_key = "currency_strength"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    pairs = {"UUP": "USD", "FXE": "EUR", "FXY": "JPY", "FXB": "GBP", "FXA": "AUD", "FXC": "CAD"}
    results = []
    for sym, currency in pairs.items():
        try:
            df = alpaca_client.get_bars(sym, days=30)
            if df is None or len(df) < 5:
                continue
            current = float(df["close"].iloc[-1])
            change_5d = (current - float(df["close"].iloc[-5])) / float(df["close"].iloc[-5]) * 100
            change_20d = (current - float(df["close"].iloc[-20])) / float(df["close"].iloc[-20]) * 100 if len(df) >= 20 else 0
            results.append({"symbol": sym, "currency": currency, "price": round(current, 2), "change_5d": round(change_5d, 2), "change_20d": round(change_20d, 2), "strength": "strong" if change_5d > 0.5 else "weak" if change_5d < -0.5 else "neutral"})
        except Exception:
            continue

    results.sort(key=lambda r: r["change_5d"], reverse=True)
    if results:
        _cache.set(cache_key, results)
    return results


# --- 66. Commodity Tracker ---

def get_commodities() -> list[dict]:
    """Track major commodities via ETFs."""
    cache_key = "commodities"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    etfs = {"GLD": "Gold", "SLV": "Silver", "USO": "Oil", "UNG": "Natural Gas", "CORN": "Corn", "WEAT": "Wheat", "DBA": "Agriculture", "DBB": "Base Metals", "PDBC": "Broad Commodities"}
    results = []
    for sym, name in etfs.items():
        try:
            df = alpaca_client.get_bars(sym, days=30)
            if df is None or len(df) < 5:
                continue
            current = float(df["close"].iloc[-1])
            change_1d = (current - float(df["close"].iloc[-2])) / float(df["close"].iloc[-2]) * 100 if len(df) >= 2 else 0
            change_5d = (current - float(df["close"].iloc[-5])) / float(df["close"].iloc[-5]) * 100
            results.append({"symbol": sym, "commodity": name, "price": round(current, 2), "change_1d": round(change_1d, 2), "change_5d": round(change_5d, 2)})
        except Exception:
            continue

    if results:
        _cache.set(cache_key, results)
    return results


# --- 67. REIT Analyzer ---

def get_reit_analysis() -> list[dict]:
    """Analyze REIT ETFs and major REITs."""
    cache_key = "reit_analysis"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    reits = {"VNQ": "Vanguard REIT", "AMT": "American Tower", "PLD": "Prologis", "CCI": "Crown Castle", "EQIX": "Equinix", "O": "Realty Income", "SPG": "Simon Property", "WELL": "Welltower"}
    est_yields = {"VNQ": 3.8, "AMT": 2.8, "PLD": 2.5, "CCI": 5.5, "EQIX": 1.8, "O": 5.2, "SPG": 4.5, "WELL": 2.8}
    results = []

    for sym, name in reits.items():
        try:
            df = alpaca_client.get_bars(sym, days=60)
            if df is None or len(df) < 20:
                continue
            current = float(df["close"].iloc[-1])
            change_20d = (current - float(df["close"].iloc[-20])) / float(df["close"].iloc[-20]) * 100
            results.append({"symbol": sym, "name": name, "price": round(current, 2), "change_20d": round(change_20d, 2), "est_yield": est_yields.get(sym, 3.0)})
        except Exception:
            continue

    results.sort(key=lambda r: r["est_yield"], reverse=True)
    if results:
        _cache.set(cache_key, results)
    return results


# --- 68. Bond Market Monitor ---

def get_bond_market() -> dict:
    """Monitor bond market via ETFs."""
    cache_key = "bond_market"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    etfs = {"TLT": "20+ Year Treasury", "IEF": "7-10 Year Treasury", "SHY": "1-3 Year Treasury", "LQD": "Investment Grade Corp", "HYG": "High Yield Corp", "TIP": "TIPS (Inflation Protected)", "AGG": "Aggregate Bond"}
    results = []
    for sym, name in etfs.items():
        try:
            df = alpaca_client.get_bars(sym, days=30)
            if df is None or len(df) < 5:
                continue
            current = float(df["close"].iloc[-1])
            change_5d = (current - float(df["close"].iloc[-5])) / float(df["close"].iloc[-5]) * 100
            change_20d = (current - float(df["close"].iloc[-20])) / float(df["close"].iloc[-20]) * 100 if len(df) >= 20 else 0
            results.append({"symbol": sym, "name": name, "price": round(current, 2), "change_5d": round(change_5d, 2), "change_20d": round(change_20d, 2)})
        except Exception:
            continue

    risk_on = any(r["change_5d"] < -0.3 for r in results if r["symbol"] == "TLT")
    result = {"bonds": results, "signal": "risk_on" if risk_on else "risk_off", "note": "Bond prices falling = yields rising = risk-on"}
    if results:
        _cache.set(cache_key, result)
    return result


# --- 75. Anomaly Detection ---

def detect_anomalies() -> list[dict]:
    """Find stocks with unusual price/volume combinations."""
    cache_key = "anomalies"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    from src.scanner.screener import get_default_universe
    symbols = [s for s in get_default_universe() if "/" not in s]
    results = []

    for sym in symbols:
        try:
            df = alpaca_client.get_bars(sym, days=30)
            if df is None or len(df) < 20:
                continue

            close = df["close"]
            vol = df["volume"]
            current = float(close.iloc[-1])
            avg_price = float(close.iloc[-20:].mean())
            std_price = float(close.iloc[-20:].std())
            avg_vol = float(vol.iloc[-20:].mean())
            today_vol = float(vol.iloc[-1])

            # Price z-score
            price_z = (current - avg_price) / std_price if std_price > 0 else 0
            vol_ratio = today_vol / avg_vol if avg_vol > 0 else 0

            # Anomaly: extreme price move + high volume
            if abs(price_z) > 2 and vol_ratio > 2:
                results.append({
                    "symbol": sym,
                    "price": round(current, 2),
                    "price_z_score": round(price_z, 2),
                    "volume_ratio": round(vol_ratio, 1),
                    "type": "breakout" if price_z > 0 else "breakdown",
                    "severity": "high" if abs(price_z) > 3 else "medium",
                })
            # Volume anomaly without price move (accumulation?)
            elif vol_ratio > 4 and abs(price_z) < 1:
                results.append({
                    "symbol": sym,
                    "price": round(current, 2),
                    "price_z_score": round(price_z, 2),
                    "volume_ratio": round(vol_ratio, 1),
                    "type": "stealth_accumulation",
                    "severity": "medium",
                })
        except Exception:
            continue

    results.sort(key=lambda r: abs(r["price_z_score"]) * r["volume_ratio"], reverse=True)
    if results:
        _cache.set(cache_key, results)
    return results


# --- 77. Portfolio Optimizer (Simple MPT) ---

def optimize_portfolio(symbols: list[str], target_return: float = 0.1) -> dict:
    """Simple mean-variance portfolio optimization."""
    import pandas as pd

    if len(symbols) < 2:
        return {"error": "Need at least 2 symbols"}

    returns_data = {}
    for sym in symbols[:10]:
        try:
            df = alpaca_client.get_bars(sym.upper(), days=200)
            if df is not None and len(df) >= 50:
                returns_data[sym.upper()] = df["close"].pct_change().dropna()
        except Exception:
            continue

    if len(returns_data) < 2:
        return {"error": "Insufficient data for optimization"}

    # Align dates
    ret_df = pd.DataFrame(returns_data).dropna()
    if len(ret_df) < 30:
        return {"error": "Insufficient overlapping data"}

    n = len(ret_df.columns)
    mean_returns = ret_df.mean() * 252  # annualize
    cov_matrix = ret_df.cov() * 252

    # Equal weight baseline
    eq_weights = np.array([1.0 / n] * n)
    eq_return = float(np.dot(eq_weights, mean_returns))
    eq_vol = float(np.sqrt(np.dot(eq_weights, np.dot(cov_matrix, eq_weights))))

    # Minimum variance (simple: inverse variance weighting)
    variances = np.diag(cov_matrix.values)
    inv_var = 1.0 / variances
    min_var_weights = inv_var / inv_var.sum()
    mv_return = float(np.dot(min_var_weights, mean_returns))
    mv_vol = float(np.sqrt(np.dot(min_var_weights, np.dot(cov_matrix, min_var_weights))))

    return {
        "symbols": list(ret_df.columns),
        "equal_weight": {
            "weights": {sym: round(1.0/n, 3) for sym in ret_df.columns},
            "expected_return": round(eq_return * 100, 2),
            "volatility": round(eq_vol * 100, 2),
            "sharpe": round((eq_return - 0.05) / eq_vol, 2) if eq_vol > 0 else 0,
        },
        "min_variance": {
            "weights": {sym: round(w, 3) for sym, w in zip(ret_df.columns, min_var_weights)},
            "expected_return": round(mv_return * 100, 2),
            "volatility": round(mv_vol * 100, 2),
            "sharpe": round((mv_return - 0.05) / mv_vol, 2) if mv_vol > 0 else 0,
        },
        "correlation_matrix": {sym: {s2: round(v, 3) for s2, v in row.items()} for sym, row in ret_df.corr().iterrows()},
    }
