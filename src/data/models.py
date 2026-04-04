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
