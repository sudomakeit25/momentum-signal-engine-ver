"""Multi-year trend analysis - long-horizon stats over weekly bars.

Computes returns (1y / 3y / 5y), CAGR, annualized volatility, max drawdown,
long-term relative strength vs SPY, and a secular regime label. Uses weekly
bars from Alpaca to keep the data volume reasonable for ~5y of history.
"""

import logging
import math

import pandas as pd
from alpaca.data.timeframe import TimeFrame

from src.data import client

logger = logging.getLogger("mse.trends")

_WEEKS_PER_YEAR = 52
_DAYS_PER_YEAR = 365


def _pct_return(series: pd.Series, lookback: int) -> float | None:
    if len(series) <= lookback:
        return None
    start = float(series.iloc[-lookback - 1])
    end = float(series.iloc[-1])
    if start <= 0:
        return None
    return (end / start - 1) * 100


def _cagr(series: pd.Series, years: float) -> float | None:
    if len(series) < 2 or years <= 0:
        return None
    start = float(series.iloc[0])
    end = float(series.iloc[-1])
    if start <= 0:
        return None
    return (math.pow(end / start, 1 / years) - 1) * 100


def _max_drawdown(series: pd.Series) -> float:
    if len(series) < 2:
        return 0.0
    running_max = series.cummax()
    drawdown = (series - running_max) / running_max
    return float(drawdown.min()) * 100


def _annualized_vol(weekly_close: pd.Series) -> float:
    rets = weekly_close.pct_change().dropna()
    if len(rets) < 4:
        return 0.0
    return float(rets.std() * math.sqrt(_WEEKS_PER_YEAR)) * 100


def _regime(weekly_close: pd.Series) -> str:
    """Label the long-term regime based on the slope of the 40-week SMA."""
    if len(weekly_close) < 80:
        return "insufficient_history"
    sma40 = weekly_close.rolling(40).mean()
    recent = sma40.iloc[-1]
    prior = sma40.iloc[-20]
    if pd.isna(recent) or pd.isna(prior) or prior == 0:
        return "unknown"
    slope_pct = (recent - prior) / prior * 100
    last = float(weekly_close.iloc[-1])
    if last > recent and slope_pct > 2:
        return "secular_uptrend"
    if last < recent and slope_pct < -2:
        return "secular_downtrend"
    if abs(slope_pct) <= 2:
        return "range_bound"
    return "transitioning"


def analyze_long_term(symbol: str) -> dict:
    """Return multi-year trend analysis for a symbol."""
    symbol = symbol.upper()
    try:
        df = client.get_bars(symbol, timeframe=TimeFrame.Week, days=_DAYS_PER_YEAR * 6)
    except Exception as e:
        return {"symbol": symbol, "error": f"fetch failed: {e}"}

    if df is None or df.empty or len(df) < 30:
        return {"symbol": symbol, "error": "insufficient weekly history"}

    try:
        spy_df = client.get_bars("SPY", timeframe=TimeFrame.Week, days=_DAYS_PER_YEAR * 6)
    except Exception:
        spy_df = pd.DataFrame()

    close = df["close"].astype(float)
    price = float(close.iloc[-1])

    years_covered = (close.index[-1] - close.index[0]).days / _DAYS_PER_YEAR

    ret_1y = _pct_return(close, _WEEKS_PER_YEAR)
    ret_3y = _pct_return(close, _WEEKS_PER_YEAR * 3)
    ret_5y = _pct_return(close, _WEEKS_PER_YEAR * 5)

    cagr_all = _cagr(close, years_covered) if years_covered > 0 else None
    cagr_3y = _cagr(close.tail(_WEEKS_PER_YEAR * 3 + 1), 3) if len(close) > _WEEKS_PER_YEAR * 3 else None
    cagr_5y = _cagr(close.tail(_WEEKS_PER_YEAR * 5 + 1), 5) if len(close) > _WEEKS_PER_YEAR * 5 else None

    max_dd_all = _max_drawdown(close)
    max_dd_3y = _max_drawdown(close.tail(_WEEKS_PER_YEAR * 3)) if len(close) > _WEEKS_PER_YEAR * 3 else max_dd_all

    vol = _annualized_vol(close)

    all_time_high = float(close.max())
    ath_date = close.idxmax()
    pct_off_ath = (price - all_time_high) / all_time_high * 100 if all_time_high else 0.0

    regime = _regime(close)

    rs_vs_spy_3y = None
    if ret_3y is not None and not spy_df.empty:
        spy_close = spy_df["close"].astype(float)
        spy_3y = _pct_return(spy_close, _WEEKS_PER_YEAR * 3)
        if spy_3y is not None:
            rs_vs_spy_3y = round(ret_3y - spy_3y, 2)

    trend_summary_parts = []
    if cagr_all is not None:
        trend_summary_parts.append(f"{cagr_all:.1f}% CAGR over {years_covered:.1f}y")
    if ret_1y is not None:
        trend_summary_parts.append(f"1y {ret_1y:+.1f}%")
    if max_dd_all < -30:
        trend_summary_parts.append(f"max DD {max_dd_all:.0f}%")
    summary = "; ".join(trend_summary_parts) if trend_summary_parts else "no summary"

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "weeks_of_history": len(close),
        "years_covered": round(years_covered, 2),
        "returns": {
            "1y_pct": None if ret_1y is None else round(ret_1y, 2),
            "3y_pct": None if ret_3y is None else round(ret_3y, 2),
            "5y_pct": None if ret_5y is None else round(ret_5y, 2),
        },
        "cagr": {
            "3y_pct": None if cagr_3y is None else round(cagr_3y, 2),
            "5y_pct": None if cagr_5y is None else round(cagr_5y, 2),
            "all_pct": None if cagr_all is None else round(cagr_all, 2),
        },
        "drawdowns": {
            "max_pct_all": round(max_dd_all, 2),
            "max_pct_3y": round(max_dd_3y, 2),
        },
        "volatility": {
            "annualized_pct": round(vol, 2),
        },
        "all_time_high": {
            "price": round(all_time_high, 2),
            "date": ath_date.isoformat() if hasattr(ath_date, "isoformat") else str(ath_date),
            "pct_off": round(pct_off_ath, 2),
        },
        "rs_vs_spy_3y_pct_points": rs_vs_spy_3y,
        "regime": regime,
        "summary": summary,
    }
