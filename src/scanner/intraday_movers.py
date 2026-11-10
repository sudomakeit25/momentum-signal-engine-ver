"""Intraday movers screener — the 0.5-1% scalp framework on 5-min bars.

Finds liquidity + volatility + a trigger:
  1. ATR%% of price does the math (can this stock even give 1%% today?)
  2. Filters: already moving (|chg| >= 2%%), relative volume >= 1.5x,
     price >= $20, avg daily volume >= 2M, spread < 0.1%%
  3. Setup detection on today's 5-min session:
     - afternoon range-box breakout (target = box height projected)
     - VWAP reclaim / rejection
     - higher-low trend continuation (target = day high)
  4. Every setup carries entry / stop / target with R:R >= 1.5
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import logging

import pandas as pd

from config.settings import settings
from src.data import client
from src.data.models import (
    IntradayResult, IntradayWatch, SetupType, Signal, SignalAction,
)
from src.signals.indicators import atr, macd, vwap

logger = logging.getLogger("mse.intraday_movers")

ET = ZoneInfo("America/New_York")
SESSION_OPEN = dtime(9, 30)
SESSION_CLOSE = dtime(16, 0)
SESSION_MINUTES = 390
MIDDAY = dtime(12, 0)


def is_market_hours(now: datetime | None = None) -> bool:
    """True during regular US equity session (Mon-Fri 9:30-16:00 ET)."""
    now_et = (now or datetime.now(tz=ET)).astimezone(ET)
    if now_et.weekday() >= 5:
        return False
    return SESSION_OPEN <= now_et.time() <= SESSION_CLOSE


def session_bars(df: pd.DataFrame, now: datetime | None = None) -> pd.DataFrame:
    """Slice today's regular-hours bars (ET), sorted chronologically."""
    if df is None or df.empty:
        return pd.DataFrame()
    idx = pd.to_datetime(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    local = idx.tz_convert(ET)
    out = df.copy()
    out.index = local
    out = out.sort_index()
    today = (now or datetime.now(tz=ET)).astimezone(ET).date()
    mask = (out.index.date == today) & (out.index.time >= SESSION_OPEN) & (
        out.index.time < SESSION_CLOSE
    )
    return out[mask]


def relative_volume(
    today_cum_volume: float, avg_daily_volume: float, now: datetime | None = None
) -> float:
    """Time-of-day adjusted RVOL: today's cumulative volume vs the fraction of
    an average day that should have traded by now."""
    if avg_daily_volume <= 0:
        return 0.0
    now_et = (now or datetime.now(tz=ET)).astimezone(ET)
    minutes = (
        (now_et.hour - SESSION_OPEN.hour) * 60 + now_et.minute - SESSION_OPEN.minute
    )
    elapsed = min(max(minutes / SESSION_MINUTES, 0.05), 1.0)
    return today_cum_volume / (avg_daily_volume * elapsed)


def _make_signal(
    symbol: str,
    action: SignalAction,
    setup: SetupType,
    reason: str,
    entry: float,
    stop: float,
    target: float,
    confidence: float,
    timestamp: datetime,
    min_rr: float,
) -> Signal | None:
    """Build a Signal, enforcing the checklist's R:R floor. Returns None if the
    geometry does not pay (risking 0.5% to make 0.5% loses to win-rate math)."""
    risk = entry - stop if action == SignalAction.BUY else stop - entry
    reward = target - entry if action == SignalAction.BUY else entry - target
    if risk <= 0 or reward <= 0:
        return None
    rr = reward / risk
    if rr < min_rr:
        return None
    return Signal(
        symbol=symbol,
        action=action,
        setup_type=setup,
        reason=reason,
        entry=round(entry, 2),
        stop_loss=round(stop, 2),
        target=round(target, 2),
        rr_ratio=round(rr, 2),
        confidence=round(min(confidence, 0.95), 2),
        timestamp=timestamp,
    )


def detect_range_breakout(
    sdf: pd.DataFrame,
    symbol: str,
    atr_pct: float,
    box_bars: int | None = None,
    min_rr: float | None = None,
) -> Signal | None:
    """Tight 30-60 min box after the lull, breaking out with volume.

    Box = the `box_bars` bars before the current one. Tight means the box
    height is small relative to the stock's daily range (ATR%%). Breakout bar
    must close beyond the box on >= 1.5x the box's average volume.
    Target = box height projected; stop = far side of the box.
    """
    box_bars = box_bars or settings.intraday_box_bars
    min_rr = min_rr if min_rr is not None else settings.intraday_min_rr
    if sdf is None or len(sdf) < box_bars + 1:
        return None

    box = sdf.iloc[-(box_bars + 1):-1]
    last = sdf.iloc[-1]
    price = float(last["close"])
    if price <= 0:
        return None

    box_high = float(box["high"].max())
    box_low = float(box["low"].min())
    height = box_high - box_low
    height_pct = height / price * 100
    if height <= 0:
        return None
    if not _box_is_tight(height_pct, atr_pct):
        return None

    box_avg_vol = float(box["volume"].mean())
    vol_ok = box_avg_vol > 0 and float(last["volume"]) >= 1.5 * box_avg_vol
    if not vol_ok:
        return None

    ts = sdf.index[-1].to_pydatetime()
    confidence = min(0.6 + (float(last["volume"]) / box_avg_vol - 1.5) * 0.05, 0.85)
    box_mid = box_low + height / 2

    # Measured move: target = box height projected from the broken edge,
    # stop at the box midpoint. The R:R floor in _make_signal then rejects
    # chased entries automatically (entry too far past the edge -> rr < min).
    if price > box_high:
        return _make_signal(
            symbol, SignalAction.BUY, SetupType.RANGE_BREAKOUT,
            f"Broke above {box_bars * 5}min box {box_low:.2f}-{box_high:.2f} "
            f"on {float(last['volume']) / box_avg_vol:.1f}x box volume",
            entry=price, stop=box_mid, target=box_high + height,
            confidence=confidence, timestamp=ts, min_rr=min_rr,
        )
    if price < box_low:
        return _make_signal(
            symbol, SignalAction.SELL, SetupType.RANGE_BREAKOUT,
            f"Broke below {box_bars * 5}min box {box_low:.2f}-{box_high:.2f} "
            f"on {float(last['volume']) / box_avg_vol:.1f}x box volume",
            entry=price, stop=box_mid, target=box_low - height,
            confidence=confidence, timestamp=ts, min_rr=min_rr,
        )
    return None


def detect_vwap_setup(
    sdf: pd.DataFrame, symbol: str, min_rr: float | None = None
) -> Signal | None:
    """VWAP reclaim (long) or rejection (short) against session VWAP.

    Reclaim: spent the last stretch below VWAP, now closes above it on
    volume — shorts cover into the close. Rejection: retested VWAP from
    below and failed. Stops hug the recent extreme; targets are the day
    high/low.
    """
    min_rr = min_rr if min_rr is not None else settings.intraday_min_rr
    if sdf is None or len(sdf) < 10:
        return None

    vw = vwap(sdf)
    closes = sdf["close"]
    last_close = float(closes.iloc[-1])
    prev_close = float(closes.iloc[-2])
    vw_last = float(vw.iloc[-1])
    vw_prev = float(vw.iloc[-2])
    if vw_last <= 0:
        return None

    below_recent = (closes.iloc[-8:-1] < vw.iloc[-8:-1]).sum()
    session_avg_vol = float(sdf["volume"].iloc[:-1].mean())
    last_vol = float(sdf["volume"].iloc[-1])
    vol_ok = session_avg_vol > 0 and last_vol >= 1.2 * session_avg_vol
    ts = sdf.index[-1].to_pydatetime()
    day_high = float(sdf["high"].max())
    day_low = float(sdf["low"].min())

    def _target_long(entry: float, stop: float) -> float | None:
        """Day high if there is enough room; 2R if already clearing the day
        high (continuation); otherwise the trade does not pay."""
        risk = entry - stop
        if risk <= 0:
            return None
        room = day_high - entry
        if room >= min_rr * risk:
            return day_high
        if room <= 0.2 * risk:
            return entry + 2 * risk
        return None

    def _target_short(entry: float, stop: float) -> float | None:
        risk = stop - entry
        if risk <= 0:
            return None
        room = entry - day_low
        if room >= min_rr * risk:
            return day_low
        if room <= 0.2 * risk:
            return entry - 2 * risk
        return None

    # Reclaim: was below, crossed above, with participation. Invalidation is
    # losing VWAP again, so the stop sits just under it.
    if prev_close < vw_prev and last_close > vw_last and below_recent >= 4 and vol_ok:
        stop = vw_last * 0.998
        target = _target_long(last_close, stop)
        if target is None:
            return None
        return _make_signal(
            symbol, SignalAction.BUY, SetupType.VWAP_RECLAIM,
            f"Reclaimed session VWAP {vw_last:.2f} on {last_vol / session_avg_vol:.1f}x "
            "volume after basing below it",
            entry=last_close, stop=stop, target=target,
            confidence=0.65, timestamp=ts, min_rr=min_rr,
        )

    # Rejection: approached VWAP from below (within 0.15% or tagged it),
    # failed, and closed back away from it
    prev_high = float(sdf["high"].iloc[-2])
    approached = prev_high >= vw_prev * 0.9985
    if (
        approached
        and last_close < vw_last
        and prev_close < vw_prev
        and below_recent >= 5
    ):
        stop = vw_last * 1.002
        target = _target_short(last_close, stop)
        if target is None:
            return None
        return _make_signal(
            symbol, SignalAction.SELL, SetupType.VWAP_REJECTION,
            f"Failed retest of session VWAP {vw_last:.2f} from below",
            entry=last_close, stop=stop, target=target,
            confidence=0.6, timestamp=ts, min_rr=min_rr,
        )
    return None


def detect_higher_low(
    sdf: pd.DataFrame, symbol: str, min_rr: float | None = None
) -> Signal | None:
    """Day low -> bounce -> pullback that holds above the day low -> price
    confirming back up. Works at any time of session (not only afternoon).

    Entry on confirmation (close back above the pivot bar's high), stop under
    the higher low. Target is the day high, or the bounce peak on a day whose
    high came before its low (the day high is not this leg's structure then).
    A rising MACD histogram raises confidence.
    """
    min_rr = min_rr if min_rr is not None else settings.intraday_min_rr
    if sdf is None or len(sdf) < 12:
        return None

    lows = sdf["low"].to_numpy(dtype=float)
    highs = sdf["high"].to_numpy(dtype=float)
    body = len(sdf) - 1  # everything before the latest (confirmation) bar

    day_low_i = int(lows[:body].argmin())
    bounce = highs[day_low_i + 1:body]
    if len(bounce) < 3:
        return None  # day low too recent: still falling, nothing to hold yet
    # Last occurrence of the bounce high, so the pullback is searched after it
    peak_i = day_low_i + 1 + (len(bounce) - 1 - int(bounce[::-1].argmax()))
    after_peak = lows[peak_i + 1:body]
    if len(after_peak) < 1:
        return None
    pivot_i = peak_i + 1 + int(after_peak.argmin())

    day_low = float(lows[day_low_i])
    pullback_low = float(lows[pivot_i])
    peak_high = float(highs[peak_i])
    last_close = float(sdf["close"].iloc[-1])

    # Higher low by a real margin (0.15%), not a retest of the day low
    if pullback_low <= day_low * 1.0015:
        return None
    # A real bounce came first, then a pullback into the pivot
    if peak_high < pullback_low * 1.003:
        return None
    # The confirmation bar must not undercut the higher low it confirms
    if float(lows[-1]) < pullback_low:
        return None
    # Confirmation: latest close back above the pivot bar's high
    if last_close <= float(highs[pivot_i]):
        return None

    day_high = float(highs.max())
    day_high_i = int(highs.argmax())
    target = peak_high if day_high_i < day_low_i else day_high
    # Need room to the target
    if last_close >= target:
        return None

    confidence = 0.62
    macd_note = ""
    try:
        hist = macd(sdf["close"])[2]
        if pd.notna(hist.iloc[-1]) and pd.notna(hist.iloc[-3]) and (
            float(hist.iloc[-1]) > float(hist.iloc[-3])
        ):
            confidence = 0.7
            macd_note = ", MACD histogram rising"
    except Exception:
        pass

    ts = sdf.index[-1].to_pydatetime()
    return _make_signal(
        symbol, SignalAction.BUY, SetupType.HIGHER_LOW,
        f"Higher low {pullback_low:.2f} held above day low {day_low:.2f}; "
        f"targeting {target:.2f}{macd_note}",
        entry=last_close, stop=pullback_low, target=target,
        confidence=confidence, timestamp=ts, min_rr=min_rr,
    )


def _box_is_tight(height_pct: float, atr_pct: float) -> bool:
    """Box is at most ~1/3 of the daily range, floored at 0.3% so low-ATR
    names are not unreachable."""
    return height_pct <= max(0.3, 0.35 * atr_pct)


def detect_box_forming(
    sdf: pd.DataFrame, symbol: str, atr_pct: float, box_bars: int | None = None
) -> IntradayWatch | None:
    """Tight box still intact after a real move: a range-break candidate.

    Fires before the break, with the two levels to watch, so the entry can
    be taken in the first bars instead of after the move. The box includes
    the current bar (price is still inside it by construction).
    """
    box_bars = box_bars or settings.intraday_box_bars
    # An hour of session must precede the box, otherwise the "box" is just
    # the opening range and every mover alerts at once mid-morning.
    if sdf is None or len(sdf) < box_bars + settings.intraday_watch_min_prior_bars:
        return None

    box = sdf.iloc[-box_bars:]
    price = float(box["close"].iloc[-1])
    if price <= 0:
        return None
    box_high = float(box["high"].max())
    box_low = float(box["low"].min())
    height_pct = (box_high - box_low) / price * 100
    # Stricter than the confirmed-breakout rule: this alert has no volume
    # trigger behind it, so the box itself has to be genuinely tight.
    max_height = min(
        settings.intraday_watch_box_max_pct,
        max(0.3, settings.intraday_watch_box_atr_frac * atr_pct),
    )
    if height_pct <= 0 or height_pct > max_height:
        return None

    day_range_pct = (float(sdf["high"].max()) - float(sdf["low"].min())) / price * 100
    if day_range_pct < settings.intraday_box_min_day_range_mult * height_pct:
        return None  # no real move before the box: just a quiet stock

    return IntradayWatch(
        symbol=symbol,
        watch_type="box_forming",
        detail=(
            f"{box_bars * 5}min box {box_low:.2f}-{box_high:.2f} "
            f"({height_pct:.2f}% tall, day range {day_range_pct:.2f}%). "
            f"Watch break of {box_high:.2f} / {box_low:.2f}"
        ),
        upper=round(box_high, 2),
        lower=round(box_low, 2),
        timestamp=sdf.index[-1].to_pydatetime(),
    )


def detect_vwap_tag(sdf: pd.DataFrame, symbol: str) -> IntradayWatch | None:
    """Price back at session VWAP after trending away from it: the decision
    point before a hold (reclaim) or a reject."""
    if sdf is None or len(sdf) < 20:
        return None

    vw = vwap(sdf)
    closes = sdf["close"]
    price = float(closes.iloc[-1])
    vw_last = float(vw.iloc[-1])
    if price <= 0 or not vw_last > 0:
        return None

    dist_now = abs(price - vw_last) / price * 100
    dist_hist = (closes - vw).abs() / closes * 100
    max_away = float(dist_hist.iloc[:-5].max())
    if dist_now > settings.intraday_vwap_near_pct:
        return None
    if not max_away >= settings.intraday_vwap_far_pct:
        return None

    side = "above" if price >= vw_last else "below"
    return IntradayWatch(
        symbol=symbol,
        watch_type="vwap_tag",
        detail=(
            f"Tagging VWAP {vw_last:.2f} from {side} "
            f"(was {max_away:.2f}% away). Watch hold / reject"
        ),
        upper=round(vw_last, 2),
        lower=round(vw_last, 2),
        timestamp=sdf.index[-1].to_pydatetime(),
    )


# High-beta liquid names that routinely have 4-10% daily ranges. Added to
# the fallback universe (used when the caller passes no symbols), which
# otherwise leans large-cap.
HIGH_BETA_EXTRAS = [
    "SNDK", "WDC", "TSM", "SMCI", "ASTS", "RKLB", "MSTR", "CLSK", "HOOD", "ARM",
]


def _intraday_universe(symbols: list[str] | None) -> list[str]:
    if symbols:
        base = list(symbols)
    else:
        from src.scanner.screener import get_default_universe
        base = list(dict.fromkeys(get_default_universe() + HIGH_BETA_EXTRAS))
    # Crypto has no session / VWAP semantics here
    return [s for s in base if "/" not in s]


def scan_intraday(
    symbols: list[str] | None = None,
    top_n: int | None = None,
    min_price: float | None = None,
    min_avg_volume: int | None = None,
    min_change_pct: float | None = None,
    min_rvol: float | None = None,
    check_spread: bool = True,
    now: datetime | None = None,
) -> list[IntradayResult]:
    """Run the intraday movers screen. Returns ranked IntradayResult rows."""
    top_n = top_n or settings.intraday_top_n
    min_price = min_price if min_price is not None else settings.intraday_min_price
    min_avg_volume = min_avg_volume or settings.intraday_min_avg_volume
    min_change_pct = (
        min_change_pct if min_change_pct is not None else settings.intraday_min_change_pct
    )
    min_rvol = min_rvol if min_rvol is not None else settings.intraday_min_rvol

    universe = _intraday_universe(symbols)
    if not universe:
        return []

    daily_map = client.get_multi_bars(universe, days=60)
    # Full session of 5-min bars (shares the 60s intraday cache with the
    # pattern scanner, so overlapping cycles don't double-fetch).
    intraday_map = client.get_intraday_multi_bars(
        universe, minutes_back=400, timeframe_minutes=5
    )

    results: list[IntradayResult] = []

    def _score_symbol(symbol: str) -> IntradayResult | None:
        try:
            daily = daily_map.get(symbol)
            sdf = session_bars(intraday_map.get(symbol), now=now)
            if daily is None or len(daily) < 21 or sdf.empty or len(sdf) < 3:
                return None

            price = float(sdf["close"].iloc[-1])
            if price < min_price:
                return None

            avg_vol = float(daily["volume"].iloc[-21:-1].mean())
            if avg_vol < min_avg_volume:
                return None

            atr_pct = float(atr(daily, 14).iloc[-1]) / price * 100

            # Yesterday close: last daily bar strictly before today (ET)
            today = (now or datetime.now(tz=ET)).astimezone(ET).date()
            prior = daily[pd.to_datetime(daily.index).date < today]
            if prior.empty:
                return None
            prev_close = float(prior["close"].iloc[-1])
            change_pct = (price - prev_close) / prev_close * 100
            if abs(change_pct) < min_change_pct:
                return None

            cum_vol = float(sdf["volume"].sum())
            bar_now = now or sdf.index[-1].to_pydatetime()
            rvol = relative_volume(cum_vol, avg_vol, now=bar_now)
            if rvol < min_rvol:
                return None

            vw = vwap(sdf)
            vwap_dist_pct = (price - float(vw.iloc[-1])) / float(vw.iloc[-1]) * 100

            signals = [
                s for s in (
                    detect_range_breakout(sdf, symbol, atr_pct),
                    detect_vwap_setup(sdf, symbol),
                    detect_higher_low(sdf, symbol),
                )
                if s is not None
            ]

            # Forming setups: only when the matching trigger has not fired
            fired = {s.setup_type for s in signals}
            watches: list[IntradayWatch] = []
            if SetupType.RANGE_BREAKOUT not in fired:
                w = detect_box_forming(sdf, symbol, atr_pct)
                if w is not None:
                    watches.append(w)
            if not fired & {SetupType.VWAP_RECLAIM, SetupType.VWAP_REJECTION}:
                w = detect_vwap_tag(sdf, symbol)
                if w is not None:
                    watches.append(w)

            score = min(
                100.0,
                abs(change_pct) * 6 + min(rvol, 5) * 8 + min(atr_pct, 10) * 3
                + 20 * len(signals) + 8 * len(watches),
            )

            return IntradayResult(
                symbol=symbol,
                price=round(price, 2),
                change_pct=round(change_pct, 2),
                atr_pct=round(atr_pct, 2),
                rvol=round(rvol, 2),
                volume=int(cum_vol),
                avg_volume=int(avg_vol),
                day_high=round(float(sdf["high"].max()), 2),
                day_low=round(float(sdf["low"].min()), 2),
                vwap_dist_pct=round(vwap_dist_pct, 2),
                score=round(score, 1),
                signals=signals,
                setup_types=[s.setup_type for s in signals],
                watches=watches,
            )
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        for res in executor.map(_score_symbol, universe):
            if res is not None:
                results.append(res)

    results.sort(key=lambda r: r.score, reverse=True)
    results = results[:top_n]

    # Checklist item 1: spread + slippage < 0.1%. Quotes only for finalists.
    if check_spread and results:
        def _attach_spread(r: IntradayResult) -> None:
            try:
                q = client.get_latest_quote(r.symbol)
                bid, ask = q["bid"], q["ask"]
                if bid > 0 and ask > bid:
                    r.spread_pct = round((ask - bid) / ((ask + bid) / 2) * 100, 3)
            except Exception:
                r.spread_pct = None

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(_attach_spread, results))

        results = [
            r for r in results
            if r.spread_pct is None or r.spread_pct <= settings.intraday_max_spread_pct
        ]

    # Checklist item 5: earnings check. A 0.5% scalp that accidentally
    # becomes an earnings hold is how small trades become big losses.
    if results:
        try:
            from src.scanner.earnings_whisper import get_upcoming_earnings

            events = get_upcoming_earnings(
                [r.symbol for r in results], days_ahead=1
            )
            reporting = {e.symbol for e in events}
            for r in results:
                r.earnings_soon = r.symbol in reporting
        except Exception as e:
            logger.debug("Earnings flag skipped: %s", e)

    return results
