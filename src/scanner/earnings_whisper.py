"""Earnings Whisper Engine - conviction scoring before earnings events.

Aggregates EPS surprise history, insider trades, analyst revisions,
and price action into a single conviction score (0-100).
"""

import logging
from datetime import datetime, timedelta

import numpy as np

from src.data import client as alpaca_client
from src.data.fmp_client import (
    get_analyst_estimate_revisions,
    get_earnings_calendar,
    get_earnings_surprises,
    get_insider_trades,
)
from src.data.models import EarningsConviction, EarningsEvent, InsiderTrade

logger = logging.getLogger("mse.earnings")


def get_upcoming_earnings(symbols: list[str], days_ahead: int = 14) -> list[EarningsEvent]:
    """Get upcoming earnings events for symbols in our universe."""
    calendar = get_earnings_calendar(days_ahead=days_ahead)
    if not calendar:
        return []

    symbol_set = {s.upper() for s in symbols}
    events = []
    for item in calendar:
        sym = item.get("symbol", "").upper()
        if sym not in symbol_set:
            continue

        date_str = item.get("date", "")
        if not date_str:
            continue

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue

        events.append(EarningsEvent(
            symbol=sym,
            date=date,
            eps_estimate=item.get("epsEstimated"),
            eps_actual=item.get("eps"),
            revenue_estimate=item.get("revenueEstimated"),
            revenue_actual=item.get("revenue"),
            time=_parse_time(item.get("time", "")),
        ))

    events.sort(key=lambda e: e.date)
    return events


def _parse_time(time_str: str) -> str:
    """Parse FMP time string to bmo/amc/unknown."""
    t = time_str.lower().strip()
    if "bmo" in t or "before" in t:
        return "bmo"
    elif "amc" in t or "after" in t:
        return "amc"
    return "unknown"


def compute_conviction(symbol: str, earnings_date: datetime) -> EarningsConviction | None:
    """Compute earnings conviction score for a symbol.

    Score components (total = 100):
    1. EPS Surprise History (0-25): consistency of beats
    2. Insider Activity (0-25): net insider buying
    3. Analyst Revisions (0-25): estimate direction
    4. Price Action (0-25): trend strength going in
    """
    components = {}
    alert_reasons = []

    # 1. EPS Surprise History (0-25)
    surprises = get_earnings_surprises(symbol)
    surprise_pcts = _extract_surprise_pcts(surprises)
    surprise_score, surprise_detail = _score_surprises(surprise_pcts)
    components["eps_surprises"] = surprise_score
    if surprise_detail:
        alert_reasons.append(surprise_detail)

    # 2. Insider Activity (0-25)
    insiders = get_insider_trades(symbol, limit=20)
    insider_sentiment, insider_score, insider_detail = _score_insiders(insiders)
    components["insider_activity"] = insider_score
    if insider_detail:
        alert_reasons.append(insider_detail)

    # 3. Analyst Revisions (0-25)
    revisions = get_analyst_estimate_revisions(symbol)
    revision_direction, revision_score, revision_detail = _score_revisions(revisions)
    components["analyst_revisions"] = revision_score
    if revision_detail:
        alert_reasons.append(revision_detail)

    # 4. Price Action (0-25)
    price_score, price_detail = _score_price_action(symbol)
    components["price_action"] = price_score
    if price_detail:
        alert_reasons.append(price_detail)

    total = sum(components.values())

    return EarningsConviction(
        symbol=symbol,
        earnings_date=earnings_date,
        conviction_score=round(total, 1),
        eps_surprise_history=surprise_pcts[:8],
        insider_sentiment=insider_sentiment,
        analyst_revisions=revision_direction,
        components=components,
        alert_reasons=alert_reasons,
    )


def _extract_surprise_pcts(surprises: list[dict]) -> list[float]:
    """Extract surprise percentages from FMP earnings surprise data."""
    pcts = []
    for s in surprises[:8]:
        actual = s.get("actualEarningResult")
        estimated = s.get("estimatedEarning")
        if actual is not None and estimated is not None and estimated != 0:
            pct = ((actual - estimated) / abs(estimated)) * 100
            pcts.append(round(pct, 2))
    return pcts


def _score_surprises(pcts: list[float]) -> tuple[float, str]:
    """Score EPS surprise history (0-25)."""
    if not pcts:
        return 0, ""

    beats = sum(1 for p in pcts if p > 0)
    total = len(pcts)
    beat_rate = beats / total

    # Consecutive beats bonus
    consecutive = 0
    for p in pcts:
        if p > 0:
            consecutive += 1
        else:
            break

    score = beat_rate * 15  # up to 15 for beat rate
    score += min(consecutive, 4) * 2.5  # up to 10 for consecutive beats
    score = min(score, 25)

    detail = ""
    if consecutive >= 4:
        detail = f"{symbol_placeholder}: {consecutive} consecutive EPS beats"
    elif beat_rate >= 0.75:
        detail = f"Beat EPS {beats}/{total} quarters"

    return round(score, 1), detail


# Placeholder for symbol in alert messages
symbol_placeholder = ""


def _score_insiders(trades: list[dict]) -> tuple[str, float, str]:
    """Score insider trading activity (0-25)."""
    if not trades:
        return "neutral", 0, ""

    buy_value = 0.0
    sell_value = 0.0
    recent_cutoff = (datetime.now() - timedelta(days=90)).isoformat()

    for t in trades:
        filing_date = t.get("filingDate", "")
        if filing_date < recent_cutoff:
            continue

        tx_type = t.get("transactionType", "").lower()
        shares = abs(t.get("securitiesTransacted", 0))
        price = t.get("price", 0) or 0

        if "purchase" in tx_type or "buy" in tx_type or tx_type == "p-purchase":
            buy_value += shares * price
        elif "sale" in tx_type or "sell" in tx_type or tx_type == "s-sale":
            sell_value += shares * price

    net = buy_value - sell_value
    total = buy_value + sell_value

    if total == 0:
        return "neutral", 5, ""

    ratio = net / total  # -1 (all selling) to +1 (all buying)

    if ratio > 0.3:
        sentiment = "buying"
        score = min(15 + ratio * 10, 25)
        detail = f"Net insider buying: ${buy_value:,.0f} bought vs ${sell_value:,.0f} sold"
    elif ratio < -0.3:
        sentiment = "selling"
        score = max(5 - abs(ratio) * 5, 0)
        detail = f"Net insider selling: ${sell_value:,.0f} sold vs ${buy_value:,.0f} bought"
    else:
        sentiment = "neutral"
        score = 10
        detail = ""

    return sentiment, round(score, 1), detail


def _score_revisions(estimates: list[dict]) -> tuple[str, float, str]:
    """Score analyst estimate revisions (0-25)."""
    if not estimates or len(estimates) < 2:
        return "stable", 5, ""

    # Compare most recent estimate to previous
    recent = estimates[0]
    previous = estimates[1] if len(estimates) > 1 else None

    recent_eps = recent.get("estimatedEpsAvg", 0)
    prev_eps = previous.get("estimatedEpsAvg", 0) if previous else 0

    recent_rev = recent.get("estimatedRevenueAvg", 0)
    prev_rev = previous.get("estimatedRevenueAvg", 0) if previous else 0

    eps_change = 0
    if prev_eps and prev_eps != 0:
        eps_change = ((recent_eps - prev_eps) / abs(prev_eps)) * 100

    rev_change = 0
    if prev_rev and prev_rev != 0:
        rev_change = ((recent_rev - prev_rev) / abs(prev_rev)) * 100

    # Combined revision score
    combined = eps_change * 0.6 + rev_change * 0.4

    if combined > 3:
        direction = "up"
        score = min(15 + combined, 25)
        detail = f"Estimates revised up: EPS {eps_change:+.1f}%, Rev {rev_change:+.1f}%"
    elif combined < -3:
        direction = "down"
        score = max(5 - abs(combined) * 0.5, 0)
        detail = f"Estimates revised down: EPS {eps_change:+.1f}%, Rev {rev_change:+.1f}%"
    else:
        direction = "stable"
        score = 12
        detail = ""

    return direction, round(score, 1), detail


def _score_price_action(symbol: str) -> tuple[float, str]:
    """Score price action trend going into earnings (0-25)."""
    try:
        df = alpaca_client.get_bars(symbol, days=60)
        if df is None or len(df) < 20:
            return 5, ""
    except Exception:
        return 5, ""

    close = df["close"]
    current = close.iloc[-1]

    # 20-day momentum
    if len(close) >= 20:
        pct_20d = ((current - close.iloc[-20]) / close.iloc[-20]) * 100
    else:
        pct_20d = 0

    # EMA alignment (9 > 21 = bullish)
    ema9 = close.ewm(span=9).mean().iloc[-1]
    ema21 = close.ewm(span=21).mean().iloc[-1]
    ema_bullish = ema9 > ema21

    score = 12.5  # neutral baseline
    if pct_20d > 5 and ema_bullish:
        score = min(20 + pct_20d * 0.5, 25)
        detail = f"Strong uptrend: +{pct_20d:.1f}% over 20d, EMAs bullish"
    elif pct_20d > 0 and ema_bullish:
        score = 17
        detail = f"Uptrend: +{pct_20d:.1f}% over 20d"
    elif pct_20d < -5:
        score = max(5 - abs(pct_20d) * 0.3, 0)
        detail = f"Downtrend: {pct_20d:.1f}% over 20d"
    else:
        detail = ""

    return round(score, 1), detail


def screen_earnings(symbols: list[str], days_ahead: int = 14, min_conviction: float = 0) -> list[EarningsConviction]:
    """Screen for upcoming earnings with conviction scores.

    Returns results sorted by conviction score (highest first).
    """
    events = get_upcoming_earnings(symbols, days_ahead=days_ahead)
    if not events:
        return []

    results = []
    for event in events:
        try:
            global symbol_placeholder
            symbol_placeholder = event.symbol
            conviction = compute_conviction(event.symbol, event.date)
            if conviction and conviction.conviction_score >= min_conviction:
                results.append(conviction)
        except Exception as e:
            logger.debug("Conviction scoring failed for %s: %s", event.symbol, e)
            continue

    results.sort(key=lambda c: c.conviction_score, reverse=True)
    return results
