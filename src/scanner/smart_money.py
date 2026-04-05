"""Smart Money Convergence - finds symbols where multiple signals align.

Combines dark pool accumulation, options flow sentiment, earnings conviction,
and momentum signals to find the highest-conviction setups.
"""

import logging
from dataclasses import dataclass

from src.data.models import DarkPoolResult, EarningsConviction, OptionsFlowResult, ScanResult

logger = logging.getLogger("mse.smart_money")


@dataclass
class SmartMoneySignal:
    """A single signal source contributing to convergence."""
    source: str  # "dark_pool" | "options_flow" | "earnings" | "momentum"
    sentiment: str  # "bullish" | "bearish" | "neutral"
    strength: float  # 0-1
    detail: str


class SmartMoneyResult:
    """Convergence result for a symbol."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.signals: list[SmartMoneySignal] = []
        self.convergence_score: float = 0
        self.direction: str = "neutral"  # "bullish" | "bearish" | "neutral"
        self.signal_count: int = 0
        self.alert_reasons: list[str] = []

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "convergence_score": round(self.convergence_score, 1),
            "direction": self.direction,
            "signal_count": self.signal_count,
            "signals": [
                {
                    "source": s.source,
                    "sentiment": s.sentiment,
                    "strength": s.strength,
                    "detail": s.detail,
                }
                for s in self.signals
            ],
            "alert_reasons": self.alert_reasons,
        }


def find_convergence(
    dark_pool_results: list[DarkPoolResult],
    options_flow_results: list[OptionsFlowResult],
    earnings_results: list[EarningsConviction],
    momentum_results: list[ScanResult],
) -> list[dict]:
    """Find symbols where multiple smart money indicators converge.

    Returns list of SmartMoneyResult dicts sorted by convergence score.
    """
    # Index all results by symbol
    dp_map = {r.symbol: r for r in dark_pool_results}
    of_map = {r.symbol: r for r in options_flow_results}
    earn_map = {r.symbol: r for r in earnings_results}
    mom_map = {r.symbol: r for r in momentum_results}

    # Collect all symbols that appear in any result
    all_symbols = set()
    all_symbols.update(dp_map.keys())
    all_symbols.update(of_map.keys())
    all_symbols.update(earn_map.keys())
    all_symbols.update(mom_map.keys())

    results = []
    for symbol in all_symbols:
        sm = SmartMoneyResult(symbol)

        # Dark Pool signal
        dp = dp_map.get(symbol)
        if dp and dp.trend != "neutral" and dp.trend_strength >= 0.3:
            sentiment = "bullish" if dp.trend == "accumulating" else "bearish"
            sm.signals.append(SmartMoneySignal(
                source="dark_pool",
                sentiment=sentiment,
                strength=dp.trend_strength,
                detail=f"Dark pool {dp.trend} (strength: {dp.trend_strength:.0%}, "
                       f"short vol: {dp.recent_short_pct:.1f}%)",
            ))

        # Options Flow signal
        of = of_map.get(symbol)
        if of and of.flow_sentiment != "neutral" and of.unusual_contracts:
            sm.signals.append(SmartMoneySignal(
                source="options_flow",
                sentiment=of.flow_sentiment,
                strength=min(len(of.unusual_contracts) / 10.0, 1.0),
                detail=f"Options {of.flow_sentiment} (P/C: {of.put_call_ratio:.2f}, "
                       f"{len(of.unusual_contracts)} unusual contracts)",
            ))

        # Earnings signal
        earn = earn_map.get(symbol)
        if earn and earn.conviction_score >= 50:
            sentiment = "bullish" if earn.conviction_score >= 60 else "neutral"
            if earn.insider_sentiment == "selling":
                sentiment = "bearish"
            sm.signals.append(SmartMoneySignal(
                source="earnings",
                sentiment=sentiment,
                strength=earn.conviction_score / 100.0,
                detail=f"Earnings conviction {earn.conviction_score:.0f}/100 "
                       f"(insiders: {earn.insider_sentiment}, revisions: {earn.analyst_revisions})",
            ))

        # Momentum signal
        mom = mom_map.get(symbol)
        if mom and mom.score >= 50:
            sm.signals.append(SmartMoneySignal(
                source="momentum",
                sentiment="bullish",
                strength=min(mom.score / 100.0, 1.0),
                detail=f"Momentum score {mom.score:.0f} "
                       f"(RS: {mom.relative_strength:.2f}, change: {mom.change_pct:+.1f}%)",
            ))

        # Need at least 2 signals for convergence
        if len(sm.signals) < 2:
            continue

        # Calculate convergence score
        sm.signal_count = len(sm.signals)
        sm.convergence_score = _compute_convergence_score(sm.signals)
        sm.direction = _determine_direction(sm.signals)
        sm.alert_reasons = _build_alerts(symbol, sm)

        results.append(sm)

    results.sort(key=lambda r: r.convergence_score, reverse=True)
    return [r.to_dict() for r in results]


def _compute_convergence_score(signals: list[SmartMoneySignal]) -> float:
    """Compute convergence score based on signal count, alignment, and strength.

    Max score = 100.
    """
    if not signals:
        return 0

    # Base: number of signals (up to 40 points)
    count_score = min(len(signals) * 10, 40)

    # Alignment bonus: all signals agree on direction (up to 30 points)
    sentiments = [s.sentiment for s in signals if s.sentiment != "neutral"]
    if sentiments:
        bullish = sum(1 for s in sentiments if s == "bullish")
        bearish = sum(1 for s in sentiments if s == "bearish")
        total = len(sentiments)
        alignment = max(bullish, bearish) / total
        alignment_score = alignment * 30
    else:
        alignment_score = 0

    # Strength: average signal strength (up to 30 points)
    avg_strength = sum(s.strength for s in signals) / len(signals)
    strength_score = avg_strength * 30

    return min(count_score + alignment_score + strength_score, 100)


def _determine_direction(signals: list[SmartMoneySignal]) -> str:
    """Determine overall direction based on weighted signal consensus."""
    bullish_weight = 0
    bearish_weight = 0

    for s in signals:
        if s.sentiment == "bullish":
            bullish_weight += s.strength
        elif s.sentiment == "bearish":
            bearish_weight += s.strength

    if bullish_weight > bearish_weight * 1.5:
        return "bullish"
    elif bearish_weight > bullish_weight * 1.5:
        return "bearish"
    return "neutral"


def _build_alerts(symbol: str, sm: SmartMoneyResult) -> list[str]:
    """Build alert reasons for convergence."""
    alerts = []
    sources = [s.source.replace("_", " ").title() for s in sm.signals]

    if sm.signal_count >= 3:
        alerts.append(
            f"{symbol}: Strong convergence ({sm.signal_count} signals: "
            f"{', '.join(sources)}) -- {sm.direction}"
        )
    elif sm.signal_count == 2:
        alerts.append(
            f"{symbol}: Convergence ({sources[0]} + {sources[1]}) -- {sm.direction}"
        )

    return alerts
