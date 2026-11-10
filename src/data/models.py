from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class SetupType(str, Enum):
    EMA_CROSSOVER = "ema_crossover"
    BREAKOUT = "breakout"
    RSI_PULLBACK = "rsi_pullback"
    VWAP_RECLAIM = "vwap_reclaim"
    FLAG = "flag"
    FLAT_BASE = "flat_base"
    TIGHT_CONSOLIDATION = "tight_consolidation"
    GAP_UP = "gap_up"
    RANGE_BREAKOUT = "range_breakout"
    VWAP_REJECTION = "vwap_rejection"
    HIGHER_LOW = "higher_low"


class StockBar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class StockQuote(BaseModel):
    symbol: str
    bid: float
    ask: float
    last: float
    volume: int


class Signal(BaseModel):
    symbol: str
    action: SignalAction
    setup_type: SetupType
    reason: str = ""
    entry: float
    stop_loss: float
    target: float
    rr_ratio: float
    confidence: float  # 0-1 score
    timestamp: datetime


class ScanResult(BaseModel):
    symbol: str
    price: float
    change_pct: float
    volume: int
    avg_volume: int
    relative_strength: float
    score: float
    signals: list[Signal]
    setup_types: list[SetupType]


class IntradayWatch(BaseModel):
    """A setup that is forming but has not triggered: levels to watch, no
    entry yet. Lets you catch the first bars of a move instead of the
    confirmation after it."""
    symbol: str
    watch_type: str            # "box_forming" | "vwap_tag"
    detail: str
    upper: float | None = None  # box high, or VWAP for a tag
    lower: float | None = None  # box low, or VWAP for a tag
    timestamp: datetime


class IntradayResult(BaseModel):
    """One row of the intraday movers screener (5-min bar based)."""
    symbol: str
    price: float
    change_pct: float          # today vs yesterday close
    atr_pct: float             # daily ATR14 as % of price
    rvol: float                # time-of-day adjusted relative volume
    spread_pct: float | None = None  # (ask-bid)/mid * 100, None if quote unavailable
    volume: int                # today's cumulative volume
    avg_volume: int            # 20-day average daily volume
    day_high: float
    day_low: float
    vwap_dist_pct: float       # % distance of last price from session VWAP
    score: float
    earnings_soon: bool = False  # reports today or tomorrow
    earnings_known: bool = True  # False when this symbol could not be checked
    signals: list[Signal] = []
    setup_types: list[SetupType] = []
    watches: list[IntradayWatch] = []
    headline: str = ""       # most specific recent news headline, if any


class PositionSize(BaseModel):
    symbol: str
    shares: int
    entry_price: float
    stop_loss: float
    target: float
    dollar_risk: float
    position_value: float
    rr_ratio: float


class ChartBar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    ema9: float | None = None
    ema21: float | None = None
    ema50: float | None = None
    ema200: float | None = None
    rsi: float | None = None
    macd_line: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    atr: float | None = None
    volume_sma20: float | None = None
    vwap: float | None = None
    rs_vs_spy: float | None = None


class SupportResistanceLevel(BaseModel):
    price: float
    strength: float
    touches: int
    zone_top: float
    zone_bottom: float
    level_type: str


class TrendLine(BaseModel):
    start_time: datetime
    start_price: float
    end_time: datetime
    end_price: float
    touches: int
    trend_type: str
    projection: list[dict] = []


class ChartPattern(BaseModel):
    pattern_type: str
    confidence: float
    target_price: float | None = None
    boundary_points: list[dict] = []
    description: str = ""
    bias: str = "neutral"  # "bullish" | "bearish" | "neutral"


class PriceProjection(BaseModel):
    price: float
    confidence: float
    reason: str
    projection_type: str
    estimated_days: int | None = None  # estimated trading days to reach target


class TechnicalAnalysis(BaseModel):
    support_levels: list[SupportResistanceLevel] = []
    resistance_levels: list[SupportResistanceLevel] = []
    trendlines: list[TrendLine] = []
    patterns: list[ChartPattern] = []
    projections: list[PriceProjection] = []
    trend_summary: str = ""


class ChartData(BaseModel):
    symbol: str
    bars: list[ChartBar]
    signals: list[Signal]
    technical_analysis: TechnicalAnalysis | None = None


class BacktestResult(BaseModel):
    strategy: str
    start_date: datetime
    end_date: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_rr: float
    total_return_pct: float
    max_drawdown_pct: float
    trades: list[dict]


# --- Dark Pool Models ---

class DarkPoolEntry(BaseModel):
    symbol: str
    date: datetime
    short_volume: int
    short_exempt_volume: int
    total_volume: int
    short_pct: float

class DarkPoolResult(BaseModel):
    symbol: str
    entries: list[DarkPoolEntry]
    avg_short_pct: float
    recent_short_pct: float
    trend: str  # "accumulating" | "distributing" | "neutral"
    trend_strength: float  # 0-1
    price_change_pct: float
    alert_reasons: list[str]


# --- Earnings Whisper Models ---

class EarningsEvent(BaseModel):
    symbol: str
    date: datetime
    eps_estimate: float | None = None
    eps_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_actual: float | None = None
    time: str = "unknown"  # "bmo" | "amc" | "unknown"

class InsiderTrade(BaseModel):
    symbol: str
    insider_name: str
    title: str
    transaction_type: str  # "purchase" | "sale"
    shares: int
    price: float
    total_value: float
    filing_date: datetime

class EarningsConviction(BaseModel):
    symbol: str
    earnings_date: datetime
    conviction_score: float  # 0-100
    eps_surprise_history: list[float]
    insider_sentiment: str  # "buying" | "selling" | "neutral"
    analyst_revisions: str  # "up" | "down" | "stable"
    components: dict
    alert_reasons: list[str]


# --- Options Flow Models ---

class OptionsContract(BaseModel):
    symbol: str
    expiration: datetime
    strike: float
    contract_type: str  # "call" | "put"
    volume: int
    open_interest: int
    vol_oi_ratio: float
    implied_volatility: float | None = None
    last_price: float | None = None

class OptionsFlowResult(BaseModel):
    symbol: str
    unusual_contracts: list[OptionsContract]
    put_call_ratio: float
    total_call_volume: int
    total_put_volume: int
    flow_sentiment: str  # "bullish" | "bearish" | "neutral"
    alert_reasons: list[str]
