"""Advanced signal scanners: VIX, premarket gaps, unusual volume,
short squeeze, golden/death cross, MACD divergence, Bollinger squeeze,
gap fill, ATR ranking, relative volume.
"""

import logging
import numpy as np
import pandas as pd

from src.data import client as alpaca_client
from src.data.cache import Cache
from src.scanner.screener import get_default_universe

logger = logging.getLogger("mse.advanced")
_cache = Cache()


# --- 1. VIX Integration ---

def get_vix_adjustment() -> dict:
    """Get VIX level and signal confidence adjustment."""
    try:
        # Use VIXY ETF as VIX proxy (Alpaca doesn't have VIX directly)
        df = alpaca_client.get_bars("VIXY", days=30)
        if df is None or df.empty:
            return {"vix_proxy": 0, "level": "unknown", "adjustment": 1.0}

        current = float(df["close"].iloc[-1])
        avg = float(df["close"].mean())
        ratio = current / avg if avg > 0 else 1

        if ratio > 1.3:
            level, adj = "high", 0.7
        elif ratio > 1.1:
            level, adj = "elevated", 0.85
        elif ratio < 0.8:
            level, adj = "low", 1.15
        else:
            level, adj = "normal", 1.0

        return {
            "vix_proxy": round(current, 2),
            "vix_avg_30d": round(avg, 2),
            "level": level,
            "confidence_adjustment": adj,
            "description": f"Volatility {level} (VIXY: {current:.2f} vs 30d avg {avg:.2f})",
        }
    except Exception as e:
        logger.debug("VIX check failed: %s", e)
        return {"vix_proxy": 0, "level": "unknown", "adjustment": 1.0}


# --- 2. Premarket/Afterhours Gap Scanner ---

def scan_gaps(min_gap_pct: float = 2.0) -> list[dict]:
    """Detect stocks gapping up or down vs previous close."""
    cache_key = f"gap_scan_{min_gap_pct}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    symbols = get_default_universe()
    results = []

    for sym in symbols:
        if "/" in sym:
            continue
        try:
            df = alpaca_client.get_bars(sym, days=5)
            if df is None or len(df) < 2:
                continue

            prev_close = float(df["close"].iloc[-2])
            current_open = float(df["open"].iloc[-1])
            current_close = float(df["close"].iloc[-1])
            gap_pct = (current_open - prev_close) / prev_close * 100

            if abs(gap_pct) >= min_gap_pct:
                filled = (gap_pct > 0 and current_close <= prev_close) or \
                         (gap_pct < 0 and current_close >= prev_close)
                results.append({
                    "symbol": sym,
                    "prev_close": round(prev_close, 2),
                    "open": round(current_open, 2),
                    "current": round(current_close, 2),
                    "gap_pct": round(gap_pct, 2),
                    "direction": "up" if gap_pct > 0 else "down",
                    "filled": filled,
                })
        except Exception:
            continue

    results.sort(key=lambda r: abs(r["gap_pct"]), reverse=True)
    if results:
        _cache.set(cache_key, results)
    return results


# --- 2b. Extended Hours Movers (premarket / after-hours) ---

def scan_extended_hours_movers(
    session: str = "auto",
    min_move_pct: float = 1.0,
) -> list[dict]:
    """Scan for stocks moving in premarket (4:00-9:30 ET) or after-hours (16:00-20:00 ET).

    session: "premarket", "afterhours", or "auto" (picks based on current ET time).
    Returns symbols with last extended-hours price vs prior regular session close.
    """
    from datetime import datetime, time as dtime
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore

    et = ZoneInfo("America/New_York")
    now_et = datetime.now(et)

    if session == "auto":
        t = now_et.time()
        if dtime(4, 0) <= t < dtime(9, 30):
            session = "premarket"
        elif dtime(16, 0) <= t < dtime(20, 0):
            session = "afterhours"
        else:
            session = "afterhours"  # default to most recent

    cache_key = f"ext_hours_{session}_{min_move_pct}_{now_et.strftime('%Y%m%d_%H%M')[:-1]}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    symbols = get_default_universe()
    results = []

    for sym in symbols:
        if "/" in sym:
            continue
        try:
            minute_df = alpaca_client.get_extended_hours_bars(sym, days=2)
            if minute_df is None or minute_df.empty:
                continue

            # Convert UTC index to ET
            minute_df = minute_df.copy()
            minute_df.index = minute_df.index.tz_convert(et)

            # Get prior regular session close (last bar between 9:30 and 16:00 ET on the most recent regular session)
            regular_mask = (
                (minute_df.index.time >= dtime(9, 30))
                & (minute_df.index.time < dtime(16, 0))
            )
            regular = minute_df[regular_mask]
            if regular.empty:
                continue
            prior_close = float(regular["close"].iloc[-1])
            prior_close_date = regular.index[-1].date()

            # Filter to the requested extended session
            if session == "premarket":
                # Premarket bars after the prior regular close date
                ext_mask = (
                    (minute_df.index.date > prior_close_date)
                    & (minute_df.index.time >= dtime(4, 0))
                    & (minute_df.index.time < dtime(9, 30))
                )
            else:  # afterhours
                ext_mask = (
                    (minute_df.index.date == prior_close_date)
                    & (minute_df.index.time >= dtime(16, 0))
                    & (minute_df.index.time < dtime(20, 0))
                )

            ext = minute_df[ext_mask]
            if ext.empty:
                continue

            last_price = float(ext["close"].iloc[-1])
            ext_volume = int(ext["volume"].sum())
            move_pct = (last_price - prior_close) / prior_close * 100

            if abs(move_pct) >= min_move_pct:
                results.append({
                    "symbol": sym,
                    "session": session,
                    "prior_close": round(prior_close, 2),
                    "last_price": round(last_price, 2),
                    "move_pct": round(move_pct, 2),
                    "direction": "up" if move_pct > 0 else "down",
                    "ext_volume": ext_volume,
                    "last_bar_et": ext.index[-1].strftime("%Y-%m-%d %H:%M %Z"),
                })
        except Exception as e:
            logger.debug(f"ext-hours scan failed for {sym}: {e}")
            continue

    results.sort(key=lambda r: abs(r["move_pct"]), reverse=True)
    if results:
        _cache.set(cache_key, results)
    return results


# --- 3. Unusual Volume Detector ---

def scan_unusual_volume(min_ratio: float = 3.0) -> list[dict]:
    """Flag stocks with volume N times above average."""
    cache_key = f"unusual_vol_{min_ratio}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    symbols = get_default_universe()
    results = []

    for sym in symbols:
        if "/" in sym:
            continue
        try:
            df = alpaca_client.get_bars(sym, days=30)
            if df is None or len(df) < 20:
                continue

            avg_vol = float(df["volume"].iloc[-20:].mean())
            today_vol = float(df["volume"].iloc[-1])
            if avg_vol <= 0:
                continue

            ratio = today_vol / avg_vol
            if ratio >= min_ratio:
                results.append({
                    "symbol": sym,
                    "volume": int(today_vol),
                    "avg_volume": int(avg_vol),
                    "ratio": round(ratio, 1),
                    "price": round(float(df["close"].iloc[-1]), 2),
                    "change_pct": round((float(df["close"].iloc[-1]) - float(df["close"].iloc[-2])) / float(df["close"].iloc[-2]) * 100, 2) if len(df) >= 2 else 0,
                })
        except Exception:
            continue

    results.sort(key=lambda r: r["ratio"], reverse=True)
    if results:
        _cache.set(cache_key, results)
    return results


# --- 4. Short Squeeze Scanner ---

def compute_squeeze_score(
    days_to_cover: float,
    price_change_5d: float,
    si_change_pct: float,
    recent_short_vol_pct: float,
) -> float:
    """Composite 0-100 short-squeeze score from the four real ingredients.

    The squeeze setup is: shorts are trapped (high days-to-cover) AND the
    price is rising (forcing them to cover). Short-interest building into
    the rise and elevated daily short volume add confirmation.

      - 40 pts: days-to-cover, the primary fuel. Saturates at 10 days.
      - 35 pts: rising price, the trigger that forces covering. Saturates
                at a +15% 5-day move.
      - 15 pts: daily short volume above the ~40% liquid-stock baseline,
                saturating 20 points higher. Confirms shorting is active.
      - 10 pts: short interest rose vs the prior settlement period — shorts
                doubling down right before the squeeze = more trapped fuel.
    """
    dtc = 40.0 * min(max(days_to_cover, 0.0) / 10.0, 1.0)
    price = 35.0 * min(max(price_change_5d, 0.0) / 15.0, 1.0)
    vol = 15.0 * min(max(recent_short_vol_pct - 40.0, 0.0) / 20.0, 1.0)
    building = 10.0 if si_change_pct > 0 else 0.0
    return round(dtc + price + vol + building, 1)


def scan_short_squeeze(
    *,
    min_days_to_cover: float = 3.0,
    min_price_change_5d: float = 2.0,
) -> list[dict]:
    """Find short-squeeze candidates using real short interest, not the
    daily short-volume proxy.

    Gate: a stock must have at least `min_days_to_cover` days of short
    interest to buy back (real squeeze fuel, from FINRA's bi-monthly
    consolidated short interest) AND be rising at least
    `min_price_change_5d`% over 5 days (the trigger forcing covers).
    Candidates are ranked by a composite squeeze score.

    All numeric outputs are native Python int/float (no numpy types) so
    the FastAPI response serializes cleanly.
    """
    from src.data.finra_client import get_short_interest, get_short_volume_batch

    cache_key = "short_squeeze_scan"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    si_cycle = get_short_interest()
    if not si_cycle:
        logger.info("Short squeeze scan: no short interest cycle available")
        return []

    symbols = [s for s in get_default_universe() if "/" not in s]
    # Pre-filter to names that clear the days-to-cover bar before doing any
    # price fetches — keeps the Alpaca call count small.
    candidates = [
        s for s in symbols
        if si_cycle.get(s.upper(), {}).get("days_to_cover", 0.0) >= min_days_to_cover
    ]
    if not candidates:
        return []

    # Daily short volume for confirmation (batch, one set of FINRA fetches).
    vol_batch = get_short_volume_batch(candidates, days=10)

    results = []
    for sym in candidates:
        si = si_cycle.get(sym.upper())
        if not si:
            continue
        try:
            df = alpaca_client.get_bars(sym, days=20)
            if df is None or len(df) < 6:
                continue

            last_close = float(df["close"].iloc[-1])
            close_5d_ago = float(df["close"].iloc[-5])
            if close_5d_ago <= 0:
                continue
            price_change_5d = (last_close - close_5d_ago) / close_5d_ago * 100
            if price_change_5d < min_price_change_5d:
                continue

            entries = vol_batch.get(sym, [])
            recent_short_vol_pct = (
                float(np.mean([e["short_pct"] for e in entries[-3:]]))
                if entries else 0.0
            )

            days_to_cover = float(si["days_to_cover"])
            si_change_pct = float(si["change_pct"])

            score = compute_squeeze_score(
                days_to_cover=days_to_cover,
                price_change_5d=price_change_5d,
                si_change_pct=si_change_pct,
                recent_short_vol_pct=recent_short_vol_pct,
            )

            results.append({
                "symbol": sym,
                "price": round(last_close, 2),
                "days_to_cover": round(days_to_cover, 2),
                "shares_short": int(si["shares_short"]),
                "si_change_pct": round(si_change_pct, 1),
                "price_change_5d": round(price_change_5d, 2),
                "recent_short_vol_pct": round(recent_short_vol_pct, 1),
                "settlement_date": si["settlement_date"],
                "squeeze_score": score,
            })
        except Exception:
            continue

    results.sort(key=lambda r: r["squeeze_score"], reverse=True)
    if results:
        _cache.set(cache_key, results)
    return results


# --- 14. Bollinger Band Squeeze Detector ---

def scan_bollinger_squeeze(squeeze_threshold: float = 0.04) -> list[dict]:
    """Detect stocks in Bollinger Band squeeze (low volatility before breakout)."""
    cache_key = f"bb_squeeze_{squeeze_threshold}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    symbols = [s for s in get_default_universe() if "/" not in s]
    results = []

    for sym in symbols:
        try:
            df = alpaca_client.get_bars(sym, days=60)
            if df is None or len(df) < 30:
                continue

            close = df["close"]
            sma20 = close.rolling(20).mean()
            std20 = close.rolling(20).std()
            upper = sma20 + 2 * std20
            lower = sma20 - 2 * std20

            # Bandwidth = (upper - lower) / sma
            bandwidth = ((upper - lower) / sma20).dropna()
            if len(bandwidth) < 10:
                continue

            current_bw = float(bandwidth.iloc[-1])
            avg_bw = float(bandwidth.mean())

            if current_bw < squeeze_threshold or current_bw < avg_bw * 0.5:
                results.append({
                    "symbol": sym,
                    "bandwidth": round(current_bw, 4),
                    "avg_bandwidth": round(avg_bw, 4),
                    "squeeze_ratio": round(current_bw / avg_bw, 2) if avg_bw > 0 else 0,
                    "price": round(float(close.iloc[-1]), 2),
                    "upper_band": round(float(upper.iloc[-1]), 2),
                    "lower_band": round(float(lower.iloc[-1]), 2),
                })
        except Exception:
            continue

    results.sort(key=lambda r: r["squeeze_ratio"])
    if results:
        _cache.set(cache_key, results)
    return results


# --- 15. MACD Divergence Scanner ---

def scan_macd_divergence() -> list[dict]:
    """Detect bullish/bearish MACD divergences."""
    cache_key = "macd_divergence"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    symbols = [s for s in get_default_universe() if "/" not in s]
    results = []

    for sym in symbols:
        try:
            df = alpaca_client.get_bars(sym, days=60)
            if df is None or len(df) < 40:
                continue

            close = df["close"]
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            macd = ema12 - ema26

            # Check last 20 bars for divergence
            recent_close = close.iloc[-20:]
            recent_macd = macd.iloc[-20:]

            price_trend = float(recent_close.iloc[-1]) - float(recent_close.iloc[0])
            macd_trend = float(recent_macd.iloc[-1]) - float(recent_macd.iloc[0])

            # Bullish divergence: price falling, MACD rising
            if price_trend < 0 and macd_trend > 0:
                results.append({
                    "symbol": sym,
                    "type": "bullish",
                    "price": round(float(close.iloc[-1]), 2),
                    "price_change": round(price_trend / float(recent_close.iloc[0]) * 100, 2),
                    "macd": round(float(macd.iloc[-1]), 4),
                    "description": "Price making lower lows while MACD making higher lows",
                })
            # Bearish divergence: price rising, MACD falling
            elif price_trend > 0 and macd_trend < 0:
                results.append({
                    "symbol": sym,
                    "type": "bearish",
                    "price": round(float(close.iloc[-1]), 2),
                    "price_change": round(price_trend / float(recent_close.iloc[0]) * 100, 2),
                    "macd": round(float(macd.iloc[-1]), 4),
                    "description": "Price making higher highs while MACD making lower highs",
                })
        except Exception:
            continue

    results.sort(key=lambda r: abs(r["price_change"]), reverse=True)
    if results:
        _cache.set(cache_key, results)
    return results


# --- 16. Golden/Death Cross Alerts ---

def scan_ema_crosses() -> list[dict]:
    """Detect golden crosses (50 > 200 EMA) and death crosses."""
    cache_key = "ema_crosses"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    symbols = [s for s in get_default_universe() if "/" not in s]
    results = []

    for sym in symbols:
        try:
            df = alpaca_client.get_bars(sym, days=250)
            if df is None or len(df) < 210:
                continue

            close = df["close"]
            ema50 = close.ewm(span=50).mean()
            ema200 = close.ewm(span=200).mean()

            # Check if cross happened in last 5 bars
            for i in range(-5, 0):
                prev_above = float(ema50.iloc[i-1]) > float(ema200.iloc[i-1])
                curr_above = float(ema50.iloc[i]) > float(ema200.iloc[i])

                if not prev_above and curr_above:
                    results.append({
                        "symbol": sym,
                        "type": "golden_cross",
                        "price": round(float(close.iloc[-1]), 2),
                        "ema50": round(float(ema50.iloc[-1]), 2),
                        "ema200": round(float(ema200.iloc[-1]), 2),
                        "bars_ago": abs(i),
                        "description": "EMA 50 crossed above EMA 200 (bullish)",
                    })
                    break
                elif prev_above and not curr_above:
                    results.append({
                        "symbol": sym,
                        "type": "death_cross",
                        "price": round(float(close.iloc[-1]), 2),
                        "ema50": round(float(ema50.iloc[-1]), 2),
                        "ema200": round(float(ema200.iloc[-1]), 2),
                        "bars_ago": abs(i),
                        "description": "EMA 50 crossed below EMA 200 (bearish)",
                    })
                    break
        except Exception:
            continue

    if results:
        _cache.set(cache_key, results)
    return results


# --- 17. Gap Fill Probability ---

def analyze_gap_fill(symbol: str) -> dict:
    """Calculate gap fill probability based on historical gaps."""
    try:
        df = alpaca_client.get_bars(symbol, days=200)
        if df is None or len(df) < 50:
            return {"symbol": symbol, "error": "Insufficient data"}

        gaps = []
        for i in range(1, len(df)):
            prev_close = float(df["close"].iloc[i-1])
            curr_open = float(df["open"].iloc[i])
            gap_pct = (curr_open - prev_close) / prev_close * 100

            if abs(gap_pct) >= 1.0:
                # Check if gap filled within 5 bars
                filled = False
                for j in range(i, min(i + 5, len(df))):
                    if gap_pct > 0 and float(df["low"].iloc[j]) <= prev_close:
                        filled = True
                        break
                    elif gap_pct < 0 and float(df["high"].iloc[j]) >= prev_close:
                        filled = True
                        break
                gaps.append({"gap_pct": gap_pct, "filled": filled, "direction": "up" if gap_pct > 0 else "down"})

        if not gaps:
            return {"symbol": symbol, "total_gaps": 0, "fill_rate": 0}

        filled_count = sum(1 for g in gaps if g["filled"])
        up_gaps = [g for g in gaps if g["direction"] == "up"]
        down_gaps = [g for g in gaps if g["direction"] == "down"]

        return {
            "symbol": symbol,
            "total_gaps": len(gaps),
            "fill_rate": round(filled_count / len(gaps) * 100, 1),
            "up_gap_fill_rate": round(sum(1 for g in up_gaps if g["filled"]) / len(up_gaps) * 100, 1) if up_gaps else 0,
            "down_gap_fill_rate": round(sum(1 for g in down_gaps if g["filled"]) / len(down_gaps) * 100, 1) if down_gaps else 0,
            "avg_gap_size": round(np.mean([abs(g["gap_pct"]) for g in gaps]), 2),
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


# --- 18. Pivot Points ---

def calculate_pivots(symbol: str) -> dict:
    """Calculate daily, weekly pivot points."""
    try:
        df = alpaca_client.get_bars(symbol, days=10)
        if df is None or len(df) < 2:
            return {"symbol": symbol, "error": "Insufficient data"}

        # Daily pivots from yesterday
        h = float(df["high"].iloc[-2])
        l = float(df["low"].iloc[-2])
        c = float(df["close"].iloc[-2])
        current = float(df["close"].iloc[-1])

        pp = (h + l + c) / 3
        r1 = 2 * pp - l
        s1 = 2 * pp - h
        r2 = pp + (h - l)
        s2 = pp - (h - l)
        r3 = h + 2 * (pp - l)
        s3 = l - 2 * (h - pp)

        return {
            "symbol": symbol,
            "current_price": round(current, 2),
            "pivot": round(pp, 2),
            "r1": round(r1, 2), "r2": round(r2, 2), "r3": round(r3, 2),
            "s1": round(s1, 2), "s2": round(s2, 2), "s3": round(s3, 2),
            "position": "above_pivot" if current > pp else "below_pivot",
            "nearest_resistance": round(r1 if current < r1 else r2, 2),
            "nearest_support": round(s1 if current > s1 else s2, 2),
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


# --- 20. ATR Ranking ---

def scan_atr_ranking() -> list[dict]:
    """Rank stocks by ATR (most volatile to least)."""
    cache_key = "atr_ranking"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    symbols = [s for s in get_default_universe() if "/" not in s]
    results = []

    for sym in symbols:
        try:
            df = alpaca_client.get_bars(sym, days=30)
            if df is None or len(df) < 15:
                continue

            high = df["high"]
            low = df["low"]
            close = df["close"]

            tr = pd.DataFrame({
                "hl": high - low,
                "hc": abs(high - close.shift(1)),
                "lc": abs(low - close.shift(1)),
            }).max(axis=1)

            atr14 = float(tr.rolling(14).mean().iloc[-1])
            price = float(close.iloc[-1])
            atr_pct = atr14 / price * 100

            results.append({
                "symbol": sym,
                "price": round(price, 2),
                "atr": round(atr14, 2),
                "atr_pct": round(atr_pct, 2),
            })
        except Exception:
            continue

    results.sort(key=lambda r: r["atr_pct"], reverse=True)
    if results:
        _cache.set(cache_key, results)
    return results
