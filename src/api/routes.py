"""FastAPI routes for the Momentum Signal Engine."""

import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Query

from src.backtest.engine import run_backtest
from src.data import client
import pandas as pd

# In-memory cache for scan results (avoids full recomputation)
_scan_cache: dict[str, tuple[float, list]] = {}
_SCAN_CACHE_TTL = 120  # seconds
_CACHE_TTL_MED = 300   # 5 min
_CACHE_TTL_LONG = 600  # 10 min

from src.data.models import (
    BacktestResult, ChartBar, ChartData, ChartPattern, PositionSize,
    PriceProjection, ScanResult, Signal, SupportResistanceLevel,
    TechnicalAnalysis, TrendLine,
)
from src.risk.position_sizer import calculate_position_size
from src.scanner.screener import get_default_universe, scan_universe
from src.signals.generator import generate_signals
from src.signals.indicators import add_all_indicators, relative_strength_vs_spy, vwap
from src.signals.patterns import detect_patterns

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "momentum-signal-engine"}


@router.get("/scan", response_model=list[ScanResult])
def scan(
    top: int = Query(default=20, ge=1, le=100, description="Number of top results"),
    min_price: float = Query(default=5.0, ge=0),
    max_price: float = Query(default=500.0, ge=0),
    min_volume: int = Query(default=500_000, ge=0),
):
    """Run momentum scanner on the default universe."""
    cache_key = f"scan_{top}_{min_price}_{max_price}_{min_volume}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _SCAN_CACHE_TTL:
        return cached[1]

    symbols = get_default_universe()
    results, bars_map = scan_universe(
        symbols, top_n=top, min_price=min_price, max_price=max_price,
        min_volume=min_volume, return_bars=True,
    )

    # Enrich with signals — reuse bars from scan, run in parallel
    def _enrich(result: ScanResult) -> None:
        try:
            df = bars_map.get(result.symbol)
            if df is None or len(df) < 50:
                return
            result.signals = generate_signals(df, result.symbol)
            result.setup_types.extend(detect_patterns(df))
            result.setup_types = list(set(result.setup_types))
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=8) as executor:
        executor.map(_enrich, results)

    _scan_cache[cache_key] = (time.time(), results)
    return results


@router.get("/scan/{symbol}", response_model=ScanResult | None)
def scan_symbol(symbol: str):
    """Detailed momentum analysis for a single stock."""
    results = scan_universe([symbol.upper()], top_n=1)
    if not results:
        return None
    result = results[0]
    try:
        df = client.get_bars(result.symbol, days=200)
        result.signals = generate_signals(df, result.symbol)
        result.setup_types.extend(detect_patterns(df))
        result.setup_types = list(set(result.setup_types))
    except Exception:
        pass
    return result


@router.get("/signals", response_model=list[Signal])
def get_signals(
    top: int = Query(default=20, ge=1, le=100),
):
    """Get current buy/sell signals across the default universe."""
    symbols = get_default_universe()
    all_signals: list[Signal] = []

    bars_map = client.get_multi_bars(symbols, days=200)
    for symbol, df in bars_map.items():
        if len(df) < 50:
            continue
        try:
            signals = generate_signals(df, symbol)
            all_signals.extend(signals)
        except Exception:
            continue

    # Sort by confidence descending
    all_signals.sort(key=lambda s: s.confidence, reverse=True)
    return all_signals[:top]


@router.get("/signals/{symbol}", response_model=list[Signal])
def get_symbol_signals(symbol: str):
    """Get signals for a specific stock."""
    df = client.get_bars(symbol.upper(), days=200)
    if df is None or len(df) < 50:
        return []
    try:
        return generate_signals(df, symbol.upper())
    except Exception:
        return []


@router.get("/chart/{symbol}", response_model=ChartData)
def chart_data(
    symbol: str,
    days: int = Query(default=200, ge=30, le=1000),
):
    """Get OHLCV + indicators for charting."""
    symbol = symbol.upper()
    df = client.get_bars(symbol, days=days)
    if df is None or len(df) < 10:
        return ChartData(symbol=symbol, bars=[], signals=[], technical_analysis=None)
    df = add_all_indicators(df)
    vwap_series = vwap(df)
    df["vwap_val"] = vwap_series

    # Compute relative strength vs SPY
    try:
        spy_df = client.get_bars("SPY", days=days)
        if len(df) >= 20 and len(spy_df) >= 20:
            rs = relative_strength_vs_spy(df["close"], spy_df["close"], 20)
            df["rs_vs_spy"] = rs
    except Exception:
        pass

    bars = []
    for idx, row in df.iterrows():
        ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
        bars.append(ChartBar(
            timestamp=ts,
            open=round(row["open"], 2),
            high=round(row["high"], 2),
            low=round(row["low"], 2),
            close=round(row["close"], 2),
            volume=int(row["volume"]),
            ema9=_safe_round(row.get("ema9")),
            ema21=_safe_round(row.get("ema21")),
            ema50=_safe_round(row.get("ema50")),
            ema200=_safe_round(row.get("ema200")),
            rsi=_safe_round(row.get("rsi")),
            macd_line=_safe_round(row.get("macd_line")),
            macd_signal=_safe_round(row.get("macd_signal")),
            macd_hist=_safe_round(row.get("macd_hist")),
            atr=_safe_round(row.get("atr")),
            volume_sma20=_safe_round(row.get("volume_sma20")),
            vwap=_safe_round(row.get("vwap_val")),
            rs_vs_spy=_safe_round(row.get("rs_vs_spy"), 3),
        ))

    signals = generate_signals(df, symbol)

    # Technical analysis
    technical_analysis = None
    if len(df) >= 60:
        technical_analysis = _compute_technical_analysis(df)

    return ChartData(symbol=symbol, bars=bars, signals=signals, technical_analysis=technical_analysis)


def _safe_round(val, decimals=2):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return round(float(val), decimals)


def _compute_technical_analysis(df: pd.DataFrame) -> TechnicalAnalysis:
    """Run all technical analysis: S/R, trendlines, patterns, projections."""
    from src.signals.support_resistance import detect_support_resistance
    from src.signals.trendlines import analyze_trendlines
    from src.signals.chart_patterns import detect_all_patterns
    from src.signals.price_projection import project_price_zones

    # Support/Resistance
    sr = detect_support_resistance(df)
    support_levels = [SupportResistanceLevel(**s) for s in sr.get("support", [])]
    resistance_levels = [SupportResistanceLevel(**r) for r in sr.get("resistance", [])]

    # Trendlines
    tl_analysis = analyze_trendlines(df)
    trendlines = []
    for t in tl_analysis.get("uptrends", []) + tl_analysis.get("downtrends", []):
        ts_start = t["start_time"]
        ts_end = t["end_time"]
        if hasattr(ts_start, "to_pydatetime"):
            ts_start = ts_start.to_pydatetime()
        if hasattr(ts_end, "to_pydatetime"):
            ts_end = ts_end.to_pydatetime()
        trendlines.append(TrendLine(
            start_time=ts_start,
            start_price=round(t["start_price"], 2),
            end_time=ts_end,
            end_price=round(t["end_price"], 2),
            touches=t["touches"],
            trend_type=t["trend_type"],
            projection=t.get("projection", []),
        ))

    # Chart patterns
    raw_patterns = detect_all_patterns(df)
    patterns = [ChartPattern(**p) for p in raw_patterns]

    # Price projections
    raw_projections = project_price_zones(df, raw_patterns, tl_analysis)
    projections = [PriceProjection(**p) for p in raw_projections]

    # Trend summary
    dominant = tl_analysis.get("dominant_trend", "neutral")
    pattern_names = [p.pattern_type.replace("_", " ").title() for p in patterns]
    if pattern_names:
        summary = f"Trend: {dominant.title()}. Patterns detected: {', '.join(pattern_names)}."
    elif dominant != "neutral":
        summary = f"Trend: {dominant.title()}. No major chart patterns detected."
    else:
        summary = "Trend: Neutral/consolidating. No clear directional bias."

    if support_levels:
        summary += f" Key support at ${support_levels[0].price:.2f}."
    if resistance_levels:
        summary += f" Key resistance at ${resistance_levels[0].price:.2f}."

    return TechnicalAnalysis(
        support_levels=support_levels,
        resistance_levels=resistance_levels,
        trendlines=trendlines,
        patterns=patterns,
        projections=projections,
        trend_summary=summary,
    )


SECTOR_MAP = {
    "Tech": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "AMD", "AVGO", "QCOM", "INTC", "MU", "ORCL", "CRM", "ADBE", "NFLX"],
    "Semis": ["LRCX", "KLAC", "AMAT", "MRVL", "ON", "SWKS", "TXN"],
    "Software": ["NOW", "INTU", "WDAY", "TEAM", "ZM", "OKTA", "MDB", "HUBS"],
    "Fintech": ["SQ", "PYPL", "COIN", "SOFI", "SHOP", "PLTR"],
    "Cloud/Cyber": ["SNOW", "DDOG", "NET", "CRWD", "ZS", "PANW"],
    "Consumer Disc.": ["TSLA", "ABNB", "UBER", "DASH", "RBLX", "U", "TTD", "NKE", "SBUX", "MCD", "HD", "LOW", "TGT"],
    "Consumer Staples": ["WMT", "COST", "PG", "KO", "PEP", "CL", "EL", "MNST"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "OXY", "DVN", "MPC", "PSX", "EOG", "HES", "VLO", "HAL"],
    "Clean Energy": ["ENPH", "SEDG", "FSLR", "CEG"],
    "Healthcare": ["LLY", "UNH", "JNJ", "PFE", "ABBV", "MRK", "BMY", "AMGN", "TMO", "ABT", "DHR", "ISRG", "MDT", "GILD", "VRTX", "REGN"],
    "Financials": ["JPM", "BAC", "GS", "MS", "WFC", "C", "SCHW", "BLK", "AXP", "COF", "ICE", "CME", "SPGI", "MMC"],
    "Industrials": ["CAT", "DE", "HON", "GE", "RTX", "LMT", "BA", "NOC", "UNP", "UPS", "FDX", "WM", "EMR", "ITW"],
    "Telecom/Media": ["DIS", "CMCSA", "T", "VZ", "CHTR", "TMUS"],
    "RE/Utilities": ["AMT", "PLD", "CCI", "EQIX", "NEE", "DUK", "SO", "AEP"],
    "Materials": ["LIN", "APD", "SHW", "ECL", "NEM", "FCX"],
    "Crypto": ["MARA", "RIOT"],
    "ETFs": ["SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK", "XLV"],
}


@router.get("/sectors")
def sector_performance():
    """Sector rotation: average change % and RS by sector."""
    results = scan_universe(get_default_universe(), top_n=100, min_price=0, max_price=9999, min_volume=0)
    result_map = {r.symbol: r for r in results}

    sectors = []
    for sector, symbols in SECTOR_MAP.items():
        members = [result_map[s] for s in symbols if s in result_map]
        if not members:
            continue
        avg_change = sum(m.change_pct for m in members) / len(members)
        avg_rs = sum(m.relative_strength for m in members) / len(members)
        avg_score = sum(m.score for m in members) / len(members)
        sectors.append({
            "sector": sector,
            "avg_change_pct": round(avg_change, 2),
            "avg_rs": round(avg_rs, 3),
            "avg_score": round(avg_score, 1),
            "count": len(members),
            "top_stock": max(members, key=lambda m: m.change_pct).symbol,
        })

    sectors.sort(key=lambda s: s["avg_change_pct"], reverse=True)
    return sectors


@router.get("/breadth")
def market_breadth():
    """Market breadth: bullish vs bearish stock count."""
    symbols = get_default_universe()
    bars_map = client.get_multi_bars(symbols, days=200)

    bullish = 0
    bearish = 0
    neutral = 0
    above_ema21 = 0
    total = 0

    for symbol, df in bars_map.items():
        if len(df) < 50:
            continue
        total += 1
        try:
            df = add_all_indicators(df)
            last = df.iloc[-1]
            ema9 = last.get("ema9", 0)
            ema21 = last.get("ema21", 0)
            close = last["close"]

            if close > ema21:
                above_ema21 += 1

            if ema9 > ema21:
                bullish += 1
            elif ema9 < ema21:
                bearish += 1
            else:
                neutral += 1
        except Exception:
            continue

    return {
        "total": total,
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "above_ema21": above_ema21,
        "bullish_pct": round(bullish / total * 100, 1) if total > 0 else 0,
        "above_ema21_pct": round(above_ema21 / total * 100, 1) if total > 0 else 0,
    }


@router.get("/backtest", response_model=BacktestResult)
def backtest(
    symbol: str = Query(default="SPY"),
    days: int = Query(default=365, ge=30, le=1000),
    capital: float = Query(default=100_000, ge=1000),
    risk_pct: float = Query(default=2.0, ge=0.1, le=10),
):
    """Run backtest on a symbol with momentum strategy."""
    df = client.get_bars(symbol.upper(), days=days)
    return run_backtest(df, symbol.upper(), capital, risk_pct)


@router.get("/risk/position-size", response_model=PositionSize)
def position_size(
    account: float = Query(..., ge=0, description="Account size in dollars"),
    risk: float = Query(default=2.0, ge=0.1, le=10, description="Risk % per trade"),
    entry: float = Query(..., ge=0, description="Entry price"),
    stop: float = Query(..., ge=0, description="Stop-loss price"),
    target: float | None = Query(default=None, ge=0, description="Target price"),
):
    """Calculate position size."""
    return calculate_position_size(account, risk, entry, stop, target)



@router.get("/correlation")
def correlation_matrix(
    symbols: str = Query(default="AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,AMD,JPM,XOM"),
    days: int = Query(default=90, ge=30, le=365),
):
    """Compute correlation matrix for a set of symbols."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    bars_map = client.get_multi_bars(sym_list, days=days)

    # Build a DataFrame of daily closes
    closes = {}
    for sym in sym_list:
        if sym in bars_map and len(bars_map[sym]) > 20:
            closes[sym] = bars_map[sym]["close"]
    if len(closes) < 2:
        return {"symbols": [], "matrix": []}

    df = pd.DataFrame(closes).dropna()
    returns = df.pct_change().dropna()
    corr = returns.corr()

    syms = list(corr.columns)
    matrix = []
    for s1 in syms:
        row = []
        for s2 in syms:
            row.append(round(float(corr.loc[s1, s2]), 3))
        matrix.append(row)

    return {"symbols": syms, "matrix": matrix}


@router.get("/risk-report")
def daily_risk_report():
    """Daily risk report: portfolio exposure and signal summary."""
    try:
        from alpaca.trading.client import TradingClient
        from config.settings import settings
        tc = TradingClient(settings.alpaca_api_key, settings.alpaca_secret_key, paper=True)
        positions = tc.get_all_positions()
        account = tc.get_account()

        total_exposure = sum(abs(float(p.market_value)) for p in positions)
        equity = float(account.equity)
        cash = float(account.cash)

        long_exposure = sum(float(p.market_value) for p in positions if float(p.market_value) > 0)
        short_exposure = abs(sum(float(p.market_value) for p in positions if float(p.market_value) < 0))
        unrealized_pl = sum(float(p.unrealized_pl) for p in positions)

        position_list = []
        for p in positions:
            mv = float(p.market_value)
            pct = (mv / equity * 100) if equity > 0 else 0
            position_list.append({
                "symbol": p.symbol,
                "market_value": mv,
                "pct_of_portfolio": round(pct, 1),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc) * 100,
            })
        position_list.sort(key=lambda x: abs(x["pct_of_portfolio"]), reverse=True)

        return {
            "equity": equity,
            "cash": cash,
            "total_exposure": total_exposure,
            "long_exposure": long_exposure,
            "short_exposure": short_exposure,
            "exposure_pct": round(total_exposure / equity * 100, 1) if equity > 0 else 0,
            "cash_pct": round(cash / equity * 100, 1) if equity > 0 else 0,
            "unrealized_pl": round(unrealized_pl, 2),
            "position_count": len(positions),
            "positions": position_list,
        }
    except Exception as e:
        return {
            "error": str(e),
            "equity": 0, "cash": 0, "total_exposure": 0,
            "long_exposure": 0, "short_exposure": 0,
            "exposure_pct": 0, "cash_pct": 0,
            "unrealized_pl": 0, "position_count": 0,
            "positions": [],
        }


@router.get("/portfolio")
def portfolio():
    """Get open positions from Alpaca paper account."""
    try:
        from alpaca.trading.client import TradingClient
        from config.settings import settings
        tc = TradingClient(settings.alpaca_api_key, settings.alpaca_secret_key, paper=True)
        positions = tc.get_all_positions()
        account = tc.get_account()
        return {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "buying_power": float(account.buying_power),
            "positions": [
                {
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "avg_entry": float(p.avg_entry_price),
                    "current_price": float(p.current_price),
                    "market_value": float(p.market_value),
                    "unrealized_pl": float(p.unrealized_pl),
                    "unrealized_plpc": float(p.unrealized_plpc) * 100,
                    "side": p.side.value,
                }
                for p in positions
            ],
        }
    except Exception as e:
        return {"error": str(e), "equity": 0, "cash": 0, "buying_power": 0, "positions": []}


@router.post("/webhook/test")
def test_webhook(
    url: str = Query(...),
    platform: str = Query(default="discord"),
):
    """Test a webhook URL by sending a sample message."""
    import requests as http_requests
    try:
        if platform == "discord":
            payload = {
                "embeds": [{
                    "title": "MSE Signal Alert (Test)",
                    "description": "This is a test message from Momentum Signal Engine.",
                    "color": 3447003,
                    "fields": [
                        {"name": "Symbol", "value": "AAPL", "inline": True},
                        {"name": "Action", "value": "BUY", "inline": True},
                        {"name": "Confidence", "value": "75%", "inline": True},
                    ],
                }]
            }
            resp = http_requests.post(url, json=payload, timeout=10)
        elif platform == "telegram":
            # URL format: https://api.telegram.org/bot<TOKEN>/sendMessage
            # chat_id passed as a second query param
            payload = {
                "text": "*MSE Signal Alert (Test)*\nSymbol: AAPL\nAction: BUY\nConfidence: 75%",
                "parse_mode": "Markdown",
            }
            resp = http_requests.post(url, json=payload, timeout=10)
        else:
            # Generic webhook
            payload = {
                "text": "MSE Signal Alert (Test) - AAPL BUY @ 75% confidence",
            }
            resp = http_requests.post(url, json=payload, timeout=10)

        return {"status": "sent", "http_status": resp.status_code}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/webhook/notify")
def notify_signals(
    url: str = Query(...),
    platform: str = Query(default="discord"),
    top: int = Query(default=5, ge=1, le=20),
):
    """Send current top signals to a webhook."""
    import requests as http_requests
    symbols = get_default_universe()
    all_signals = []
    bars_map = client.get_multi_bars(symbols, days=200)
    for symbol, df in bars_map.items():
        if len(df) < 50:
            continue
        try:
            sigs = generate_signals(df, symbol)
            all_signals.extend(sigs)
        except Exception:
            continue
    all_signals.sort(key=lambda s: s.confidence, reverse=True)
    top_signals = all_signals[:top]

    if not top_signals:
        return {"status": "no_signals"}

    try:
        if platform == "discord":
            fields = []
            for s in top_signals:
                emoji = "\U0001f7e2" if s.action.value == "BUY" else "\U0001f534"
                fields.append({
                    "name": f"{emoji} {s.symbol} — {s.action.value}",
                    "value": f"Entry: ${s.entry:.2f} | Conf: {s.confidence*100:.0f}%\n{s.reason[:80]}",
                    "inline": False,
                })
            payload = {"embeds": [{"title": "MSE Signal Alerts", "color": 3447003, "fields": fields}]}
            resp = http_requests.post(url, json=payload, timeout=10)
        else:
            lines = ["*MSE Signal Alerts*\n"]
            for s in top_signals:
                emoji = "\U0001f7e2" if s.action.value == "BUY" else "\U0001f534"
                lines.append(f"{emoji} *{s.symbol}* {s.action.value} @ ${s.entry:.2f} ({s.confidence*100:.0f}%)")
            payload = {"text": "\n".join(lines), "parse_mode": "Markdown"} if platform == "telegram" else {"text": "\n".join(lines)}
            resp = http_requests.post(url, json=payload, timeout=10)

        return {"status": "sent", "signals_count": len(top_signals), "http_status": resp.status_code}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/trade")
def place_trade(
    symbol: str = Query(...),
    qty: int = Query(..., ge=1),
    side: str = Query(...),
):
    """Place a paper trade via Alpaca."""
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        from config.settings import settings
        tc = TradingClient(settings.alpaca_api_key, settings.alpaca_secret_key, paper=True)
        order = tc.submit_order(MarketOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        ))
        return {"status": "submitted", "order_id": str(order.id), "symbol": order.symbol}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- Notification Config Endpoints ---

from src.notifications.dispatcher import (
    load_config as load_notification_config,
    save_config as save_notification_config,
    NotificationConfig,
    send_sms,
    send_email_sms,
    CARRIER_GATEWAYS,
)


@router.get("/notifications/carriers")
def get_sms_carriers():
    """List supported carriers for email-to-SMS gateway."""
    return [{"key": k, "gateway": v} for k, v in CARRIER_GATEWAYS.items()]


@router.get("/notifications/config")
def get_notification_config():
    """Get current notification configuration."""
    config = load_notification_config()
    return config.to_dict()


@router.post("/notifications/config")
def set_notification_config(
    webhook_url: str = Query(default=""),
    webhook_platform: str = Query(default="discord"),
    sms_to: str = Query(default=""),
    sms_method: str = Query(default="email_gateway"),
    sms_carrier: str = Query(default=""),
    sms_consent: bool = Query(default=False),
    auto_alerts_enabled: bool = Query(default=False),
    min_confidence: float = Query(default=0.6, ge=0, le=1),
):
    """Save notification preferences."""
    from datetime import timezone

    # Record consent timestamp when user opts in
    existing = load_notification_config()
    consent_ts = existing.sms_consent_timestamp
    if sms_consent and not existing.sms_consent:
        # Fresh opt-in — record the timestamp
        consent_ts = datetime.now(timezone.utc).isoformat()
    elif not sms_consent:
        consent_ts = ""

    config = NotificationConfig(
        webhook_url=webhook_url,
        webhook_platform=webhook_platform,
        sms_to=sms_to,
        sms_method=sms_method,
        sms_carrier=sms_carrier,
        sms_consent=sms_consent,
        sms_consent_timestamp=consent_ts,
        auto_alerts_enabled=auto_alerts_enabled,
        min_confidence=min_confidence,
    )
    save_notification_config(config)
    return {"status": "saved", "config": config.to_dict()}


@router.post("/notifications/test-sms")
def test_sms(
    to: str = Query(..., description="Recipient phone number, e.g. +15559876543 or 5559876543"),
):
    """Send a test SMS via the configured method (Twilio or email gateway)."""
    # Verify consent before sending
    config = load_notification_config()
    if not config.sms_consent:
        return {"status": "error", "message": "SMS consent not given. Please opt in first."}

    from src.data.models import Signal, SignalAction, SetupType

    test_signal = Signal(
        symbol="AAPL",
        action=SignalAction.BUY,
        setup_type=SetupType.BREAKOUT,
        reason="Test signal from Momentum Signal Engine",
        entry=150.00,
        stop_loss=145.00,
        target=165.00,
        rr_ratio=3.0,
        confidence=0.85,
        timestamp=datetime.now(),
    )

    if config.sms_method == "email_gateway":
        if not config.sms_carrier:
            return {"status": "error", "message": "No carrier selected. Choose your carrier and save."}
        ok = send_email_sms(to, config.sms_carrier, [test_signal])
    else:
        ok = send_sms(to, [test_signal])

    return {"status": "sent" if ok else "error", "to": to}


# --- Dark Pool Endpoints ---

from src.data.models import DarkPoolResult
from src.scanner.dark_pool import analyze_symbol as dp_analyze, screen_universe as dp_screen


@router.get("/dark-pool/scan", response_model=list[DarkPoolResult])
def dark_pool_scan(
    top: int = Query(default=20, ge=1, le=50),
    days: int = Query(default=20, ge=5, le=60),
):
    """Scan the default universe for dark pool activity."""
    cache_key = f"dp_scan_{top}_{days}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 300:  # 5 min cache
        return cached[1]

    symbols = get_default_universe()
    results = dp_screen(symbols, days=days, top_n=top)
    _scan_cache[cache_key] = (time.time(), results)
    return results


@router.get("/dark-pool/{symbol}", response_model=DarkPoolResult)
def dark_pool_symbol(
    symbol: str,
    days: int = Query(default=20, ge=5, le=60),
):
    """Get dark pool activity for a single symbol."""
    result = dp_analyze(symbol.upper(), days=days)
    if result is None:
        return DarkPoolResult(
            symbol=symbol.upper(),
            entries=[],
            avg_short_pct=0,
            recent_short_pct=0,
            trend="neutral",
            trend_strength=0,
            price_change_pct=0,
            alert_reasons=[],
        )
    return result


# --- Earnings Whisper Endpoints ---

from src.data.models import EarningsConviction, EarningsEvent, InsiderTrade
from src.scanner.earnings_whisper import (
    get_upcoming_earnings,
    compute_conviction,
    screen_earnings,
)
from src.data.fmp_client import (
    get_earnings_calendar as fmp_earnings_cal,
    get_insider_trades as fmp_insider_trades,
)


@router.get("/earnings/upcoming", response_model=list[EarningsEvent])
def earnings_upcoming(
    days_ahead: int = Query(default=14, ge=1, le=30),
):
    """Get upcoming earnings events for stocks in our universe."""
    symbols = get_default_universe()
    return get_upcoming_earnings(symbols, days_ahead=days_ahead)


@router.get("/earnings/whisper", response_model=list[EarningsConviction])
def earnings_whisper(
    days_ahead: int = Query(default=14, ge=1, le=30),
    min_conviction: float = Query(default=0, ge=0, le=100),
):
    """Get earnings conviction scores for upcoming earnings."""
    cache_key = f"earnings_whisper_{days_ahead}_{min_conviction}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 600:  # 10 min cache
        return cached[1]

    symbols = get_default_universe()
    results = screen_earnings(symbols, days_ahead=days_ahead, min_conviction=min_conviction)
    _scan_cache[cache_key] = (time.time(), results)
    return results


@router.get("/earnings/conviction/{symbol}", response_model=EarningsConviction)
def earnings_conviction(symbol: str):
    """Get earnings conviction score for a single symbol."""
    events = get_upcoming_earnings([symbol.upper()], days_ahead=30)
    if not events:
        return EarningsConviction(
            symbol=symbol.upper(),
            earnings_date=datetime.now(),
            conviction_score=0,
            eps_surprise_history=[],
            insider_sentiment="neutral",
            analyst_revisions="stable",
            components={},
            alert_reasons=["No upcoming earnings found"],
        )
    result = compute_conviction(symbol.upper(), events[0].date)
    if result is None:
        return EarningsConviction(
            symbol=symbol.upper(),
            earnings_date=events[0].date,
            conviction_score=0,
            eps_surprise_history=[],
            insider_sentiment="neutral",
            analyst_revisions="stable",
            components={},
            alert_reasons=["Could not compute conviction (FMP API key missing?)"],
        )
    return result


@router.get("/insider/{symbol}", response_model=list[InsiderTrade])
def insider_trades(
    symbol: str,
    limit: int = Query(default=20, ge=1, le=100),
):
    """Get insider trading activity for a symbol."""
    trades = fmp_insider_trades(symbol.upper(), limit=limit)
    results = []
    for t in trades:
        try:
            tx_type = t.get("transactionType", "").lower()
            if "purchase" in tx_type or "buy" in tx_type or tx_type == "p-purchase":
                transaction = "purchase"
            else:
                transaction = "sale"

            shares = abs(t.get("securitiesTransacted", 0))
            price = t.get("price", 0) or 0

            results.append(InsiderTrade(
                symbol=symbol.upper(),
                insider_name=t.get("reportingName", "Unknown"),
                title=t.get("typeOfOwner", ""),
                transaction_type=transaction,
                shares=int(shares),
                price=price,
                total_value=round(shares * price, 2),
                filing_date=t.get("filingDate", "2000-01-01"),
            ))
        except Exception:
            continue
    return results


# --- Options Flow Endpoints ---

from src.data.models import OptionsFlowResult
from src.scanner.options_flow import (
    analyze_symbol as of_analyze,
    screen_universe as of_screen,
)


@router.get("/options-flow/scan", response_model=list[OptionsFlowResult])
def options_flow_scan(
    top: int = Query(default=20, ge=1, le=50),
):
    """Scan for unusual options activity across the universe.

    Note: Due to Polygon's 5 calls/min rate limit, this scans symbols
    sequentially and may take several minutes for large scans.
    """
    cache_key = f"of_scan_{top}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 300:  # 5 min cache
        return cached[1]

    symbols = get_default_universe()
    results = of_screen(symbols, top_n=top)
    _scan_cache[cache_key] = (time.time(), results)
    return results


@router.get("/options-flow/{symbol}", response_model=OptionsFlowResult)
def options_flow_symbol(symbol: str):
    """Get options flow analysis for a single symbol."""
    result = of_analyze(symbol.upper())
    if result is None:
        return OptionsFlowResult(
            symbol=symbol.upper(),
            unusual_contracts=[],
            put_call_ratio=0,
            total_call_volume=0,
            total_put_volume=0,
            flow_sentiment="neutral",
            alert_reasons=["No options data available (Polygon API key missing or no data)"],
        )
    return result


# --- Smart Money Convergence Endpoint ---

from src.scanner.smart_money import find_convergence


@router.get("/smart-money/convergence")
def smart_money_convergence():
    """Find symbols where multiple smart money signals converge.

    Combines dark pool, options flow, earnings, and momentum data.
    Returns symbols with 2+ aligned signals, sorted by convergence score.
    """
    cache_key = "smart_money_convergence"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 300:  # 5 min cache
        return cached[1]

    symbols = get_default_universe()

    # Gather data from each feature (use cached scan results where available)
    dp_results = []
    dp_cached = _scan_cache.get("dp_scan_20_20")
    if dp_cached and time.time() - dp_cached[0] < 600:
        dp_results = dp_cached[1]
    else:
        try:
            dp_results = dp_screen(symbols, days=20, top_n=50)
        except Exception:
            pass

    of_results = []
    of_cached = _scan_cache.get("of_scan_20")
    if of_cached and time.time() - of_cached[0] < 600:
        of_results = of_cached[1]

    earn_results = []
    earn_cached = _scan_cache.get("earnings_whisper_14_0")
    if earn_cached and time.time() - earn_cached[0] < 600:
        earn_results = earn_cached[1]
    else:
        try:
            earn_results = screen_earnings(symbols, days_ahead=14)
        except Exception:
            pass

    mom_results = []
    mom_cached = _scan_cache.get("scan_20_5.0_500.0_500000")
    if mom_cached and time.time() - mom_cached[0] < 300:
        mom_results = mom_cached[1]

    results = find_convergence(dp_results, of_results, earn_results, mom_results)
    _scan_cache[cache_key] = (time.time(), results)
    return results


# --- Trade Journal Endpoints ---

from src.data.redis_store import (
    get_trades, save_trade, delete_trade, update_trade,
    get_alert_history, get_watchlist, save_watchlist,
)
from src.journal.trade_journal import import_from_alpaca, compute_stats


@router.get("/journal/trades")
def journal_trades():
    """Get all trades from the journal."""
    return get_trades()


@router.post("/journal/trades")
def journal_add_trade(
    symbol: str = Query(...),
    side: str = Query(default="buy"),
    shares: float = Query(...),
    entry_price: float = Query(...),
    stop_loss: float = Query(default=0),
    target: float = Query(default=0),
    setup_type: str = Query(default=""),
    notes: str = Query(default=""),
):
    """Add a trade manually."""
    trade = {
        "symbol": symbol.upper(),
        "side": side,
        "shares": shares,
        "entry_price": entry_price,
        "exit_price": None,
        "stop_loss": stop_loss or None,
        "target": target or None,
        "status": "open",
        "setup_type": setup_type,
        "notes": notes,
        "entry_date": datetime.now().isoformat(),
        "exit_date": None,
        "pnl": None,
        "r_multiple": None,
    }
    ok = save_trade(trade)
    return {"status": "saved" if ok else "error"}


@router.post("/journal/trades/{trade_id}/close")
def journal_close_trade(
    trade_id: str,
    exit_price: float = Query(...),
):
    """Close an open trade with an exit price."""
    trades = get_trades()
    trade = next((t for t in trades if t.get("id") == trade_id), None)
    if not trade:
        return {"status": "error", "message": "Trade not found"}

    entry = trade.get("entry_price", 0)
    shares = trade.get("shares", 0)
    is_buy = trade.get("side", "buy").lower() in ("buy", "long")

    if is_buy:
        pnl = (exit_price - entry) * shares
    else:
        pnl = (entry - exit_price) * shares

    stop = trade.get("stop_loss")
    r_multiple = None
    if stop and stop != entry:
        risk = abs(entry - stop)
        if is_buy:
            r_multiple = round((exit_price - entry) / risk, 2) if risk > 0 else 0
        else:
            r_multiple = round((entry - exit_price) / risk, 2) if risk > 0 else 0

    ok = update_trade(trade_id, {
        "exit_price": exit_price,
        "exit_date": datetime.now().isoformat(),
        "status": "closed",
        "pnl": round(pnl, 2),
        "r_multiple": r_multiple,
    })
    return {"status": "closed" if ok else "error", "pnl": round(pnl, 2)}


@router.delete("/journal/trades/{trade_id}")
def journal_delete_trade(trade_id: str):
    """Delete a trade from the journal."""
    ok = delete_trade(trade_id)
    return {"status": "deleted" if ok else "error"}


@router.post("/journal/import-alpaca")
def journal_import(
    days: int = Query(default=30, ge=1, le=365),
):
    """Import closed orders from Alpaca."""
    imported = import_from_alpaca(days=days)
    return {"imported": len(imported), "trades": imported}


@router.get("/journal/stats")
def journal_stats():
    """Get trade journal performance statistics."""
    return compute_stats()


# --- Alert History Endpoints ---

@router.get("/alerts/history")
def alert_history(
    limit: int = Query(default=100, ge=1, le=500),
    enrich: bool = Query(default=False, description="Add current price and P&L"),
):
    """Get dispatched alert history, optionally enriched with current prices."""
    alerts = get_alert_history(limit=limit)
    if not enrich or not alerts:
        return alerts

    # Check cache first
    cache_key = f"alert_history_enriched_{limit}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 120:
        return cached[1]

    # Batch fetch current prices for all alerted symbols in one call
    symbols = list({a.get("symbol", "") for a in alerts if a.get("symbol")})
    prices = {}
    if symbols:
        try:
            bars_map = client.get_multi_bars(symbols, days=5)
            for sym, df in bars_map.items():
                if df is not None and not df.empty:
                    prices[sym] = float(df["close"].iloc[-1])
        except Exception:
            pass

    for a in alerts:
        sym = a.get("symbol", "")
        entry = a.get("entry", 0)
        current = prices.get(sym)
        if current and entry:
            a["current_price"] = round(current, 2)
            a["pnl_pct"] = round((current - entry) / entry * 100, 2)
            a["pnl_direction"] = "profit" if current > entry else "loss" if current < entry else "flat"
        else:
            a["current_price"] = None
            a["pnl_pct"] = None
            a["pnl_direction"] = None

    _scan_cache[cache_key] = (time.time(), alerts)
    return alerts


# --- Signal Backtester Endpoints ---

from src.backtest.signal_tester import backtest_signals


@router.get("/backtest/signals/{symbol}")
def backtest_symbol_signals(
    symbol: str,
    days: int = Query(default=200, ge=50, le=500),
    lookforward: int = Query(default=10, ge=3, le=30),
):
    """Backtest generated signals for a symbol against historical outcomes."""
    cache_key = f"signal_bt_{symbol}_{days}_{lookforward}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 600:
        return cached[1]

    result = backtest_signals(symbol.upper(), days=days, lookforward=lookforward)
    _scan_cache[cache_key] = (time.time(), result)
    return result


# --- Watchlist Alerts Endpoints ---

@router.get("/watchlist/server")
def watchlist_get():
    """Get server-side watchlist (synced to Redis)."""
    return get_watchlist()


@router.post("/watchlist/server")
def watchlist_save(symbols: str = Query(..., description="Comma-separated symbols")):
    """Save watchlist to Redis."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    ok = save_watchlist(sym_list)
    return {"status": "saved" if ok else "error", "symbols": sym_list}


@router.post("/watchlist/sync")
def watchlist_sync(symbols: str = Query(..., description="Comma-separated symbols")):
    """Sync frontend watchlist to server for alert monitoring."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    ok = save_watchlist(sym_list)
    return {"status": "synced" if ok else "error", "count": len(sym_list)}


# --- Auth Endpoints ---

from pydantic import BaseModel as PydanticBaseModel
from src.auth.users import register as auth_register, login as auth_login
from src.auth.deps import get_current_user, optional_user
from src.data.redis_store import get_user_data, set_user_data
from fastapi import Depends


class AuthRequest(PydanticBaseModel):
    email: str
    password: str
    name: str = ""


class PasswordChangeRequest(PydanticBaseModel):
    current_password: str
    new_password: str


@router.post("/auth/register")
def register(req: AuthRequest):
    """Register a new user."""
    result = auth_register(req.email, req.password, req.name)
    if "error" in result:
        return {"status": "error", "message": result["error"]}
    return {"status": "ok", **result}


@router.post("/auth/login")
def login(req: AuthRequest):
    """Login and get a JWT token."""
    result = auth_login(req.email, req.password)
    if "error" in result:
        return {"status": "error", "message": result["error"]}
    return {"status": "ok", **result}


@router.get("/auth/me")
def auth_me(user: dict = Depends(get_current_user)):
    """Get current user info."""
    from src.auth.users import _load_users
    users = _load_users()
    full_user = users.get(user["email"], {})
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": full_user.get("name", ""),
        "created_at": full_user.get("created_at", ""),
    }


@router.post("/auth/change-password")
def change_password(
    req: PasswordChangeRequest,
    user: dict = Depends(get_current_user),
):
    """Change password for the authenticated user."""
    import bcrypt
    from src.auth.users import _load_users, _save_users

    if len(req.new_password) < 6:
        return {"status": "error", "message": "New password must be at least 6 characters"}

    users = _load_users()
    full_user = users.get(user["email"])
    if not full_user:
        return {"status": "error", "message": "User not found"}

    if not bcrypt.checkpw(req.current_password.encode(), full_user["password_hash"].encode()):
        return {"status": "error", "message": "Current password is incorrect"}

    new_hash = bcrypt.hashpw(req.new_password.encode(), bcrypt.gensalt()).decode()
    full_user["password_hash"] = new_hash
    users[user["email"]] = full_user
    _save_users(users)

    return {"status": "ok", "message": "Password updated"}


class NameUpdateRequest(PydanticBaseModel):
    name: str


@router.post("/auth/update-name")
def update_name(
    req: NameUpdateRequest,
    user: dict = Depends(get_current_user),
):
    """Update display name for the authenticated user."""
    from src.auth.users import _load_users, _save_users

    users = _load_users()
    full_user = users.get(user["email"])
    if not full_user:
        return {"status": "error", "message": "User not found"}

    full_user["name"] = req.name.strip()
    users[user["email"]] = full_user
    _save_users(users)

    return {"status": "ok", "name": req.name.strip()}


# --- Per-user Data Endpoints ---

@router.get("/user/trades")
def user_trades(user: dict = Depends(get_current_user)):
    """Get trades for the authenticated user."""
    data = get_user_data(user["user_id"], "trades")
    return data or []


@router.post("/user/trades")
def user_add_trade(
    symbol: str = Query(...),
    side: str = Query(default="buy"),
    shares: float = Query(...),
    entry_price: float = Query(...),
    stop_loss: float = Query(default=0),
    target: float = Query(default=0),
    setup_type: str = Query(default=""),
    notes: str = Query(default=""),
    user: dict = Depends(get_current_user),
):
    """Add a trade for the authenticated user."""
    trades = get_user_data(user["user_id"], "trades") or []
    trade = {
        "id": f"t_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "symbol": symbol.upper(),
        "side": side,
        "shares": shares,
        "entry_price": entry_price,
        "exit_price": None,
        "stop_loss": stop_loss or None,
        "target": target or None,
        "status": "open",
        "setup_type": setup_type,
        "notes": notes,
        "entry_date": datetime.now().isoformat(),
        "exit_date": None,
        "pnl": None,
        "r_multiple": None,
        "created_at": datetime.now().isoformat(),
    }
    trades.append(trade)
    ok = set_user_data(user["user_id"], "trades", trades)
    return {"status": "saved" if ok else "error"}


@router.get("/user/watchlist")
def user_watchlist(user: dict = Depends(get_current_user)):
    """Get watchlist for the authenticated user."""
    data = get_user_data(user["user_id"], "watchlist")
    return data or []


@router.post("/user/watchlist")
def user_save_watchlist(
    symbols: str = Query(..., description="Comma-separated symbols"),
    user: dict = Depends(get_current_user),
):
    """Save watchlist for the authenticated user."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    ok = set_user_data(user["user_id"], "watchlist", sym_list)
    return {"status": "saved" if ok else "error", "symbols": sym_list}


@router.get("/user/config")
def user_config(user: dict = Depends(get_current_user)):
    """Get notification config for the authenticated user."""
    data = get_user_data(user["user_id"], "notification_config")
    return data or {}


@router.post("/user/config")
def user_save_config(
    sms_to: str = Query(default=""),
    sms_method: str = Query(default="email_gateway"),
    sms_carrier: str = Query(default=""),
    sms_consent: bool = Query(default=False),
    auto_alerts_enabled: bool = Query(default=False),
    min_confidence: float = Query(default=0.6),
    user: dict = Depends(get_current_user),
):
    """Save notification config for the authenticated user."""
    config = {
        "sms_to": sms_to,
        "sms_method": sms_method,
        "sms_carrier": sms_carrier,
        "sms_consent": sms_consent,
        "auto_alerts_enabled": auto_alerts_enabled,
        "min_confidence": min_confidence,
    }
    ok = set_user_data(user["user_id"], "notification_config", config)
    return {"status": "saved" if ok else "error"}


# --- Signal Leaderboard Endpoints (public) ---

from src.scanner.leaderboard import compute_leaderboard


@router.get("/leaderboard")
def leaderboard():
    """Get signal accuracy leaderboard (public, no auth required)."""
    cache_key = "leaderboard_stats"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 120:
        return cached[1]

    result = compute_leaderboard()
    _scan_cache[cache_key] = (time.time(), result)
    return result


# --- News Sentiment Endpoints ---

from src.scanner.news_sentiment import fetch_news, get_symbol_sentiment, get_market_sentiment


@router.get("/news/feed")
def news_feed():
    """Get latest news with sentiment scoring."""
    cache_key = "news_feed"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 300:
        return cached[1]

    symbols = get_default_universe()
    articles = fetch_news(symbols)
    market = get_market_sentiment(articles)
    result = {"market_sentiment": market, "articles": articles[:50]}
    _scan_cache[cache_key] = (time.time(), result)
    return result


@router.get("/news/{symbol}")
def news_symbol(symbol: str):
    """Get news sentiment for a specific symbol."""
    symbols = get_default_universe()
    articles = fetch_news(symbols)
    return get_symbol_sentiment(symbol.upper(), articles)


# --- Sector Flow Endpoints ---

from src.scanner.sector_flow import compute_sector_flow


@router.get("/sectors/flow")
def sector_flow():
    """Get sector rotation dashboard with aggregated flow data."""
    cache_key = "sector_flow"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 300:
        return cached[1]

    symbols = get_default_universe()

    dp_results = []
    dp_cached = _scan_cache.get("dp_scan_20_20")
    if dp_cached and time.time() - dp_cached[0] < 600:
        dp_results = dp_cached[1]

    of_results = []
    of_cached = _scan_cache.get("of_scan_20")
    if of_cached and time.time() - of_cached[0] < 600:
        of_results = of_cached[1]

    mom_results = []
    mom_cached = _scan_cache.get("scan_20_5.0_500.0_500000")
    if mom_cached and time.time() - mom_cached[0] < 300:
        mom_results = mom_cached[1]

    result = compute_sector_flow(dp_results, of_results, mom_results)
    _scan_cache[cache_key] = (time.time(), result)
    return result


# --- Correlation Alerts Endpoints ---

from src.scanner.correlation_alerts import scan_pairs, analyze_pair


@router.get("/correlation/scan")
def correlation_scan(
    days: int = Query(default=60, ge=20, le=200),
):
    """Scan predefined pairs for correlation divergences."""
    cache_key = f"corr_scan_{days}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 300:
        return cached[1]

    result = scan_pairs(days=days)
    _scan_cache[cache_key] = (time.time(), result)
    return result


@router.get("/correlation/{sym_a}/{sym_b}")
def correlation_pair(
    sym_a: str,
    sym_b: str,
    days: int = Query(default=60, ge=20, le=200),
):
    """Analyze correlation between two specific symbols."""
    result = analyze_pair(sym_a.upper(), sym_b.upper(), days=days)
    if result is None:
        return {"pair": [sym_a.upper(), sym_b.upper()], "error": "Insufficient data"}
    return result


# --- Market Regime Endpoints ---

from src.scanner.market_regime import detect_regime


@router.get("/market/regime")
def market_regime():
    """Detect current market regime (trending, choppy, volatile, etc.)."""
    cache_key = "market_regime"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 300:
        return cached[1]

    result = detect_regime()
    _scan_cache[cache_key] = (time.time(), result)
    return result


# --- Paper Trading Endpoints ---

from src.trading.paper import (
    get_positions, get_account_info, place_order, close_position,
    get_orders, cancel_order,
)


@router.get("/trading/account")
def trading_account():
    """Get paper trading account info."""
    return get_account_info()


@router.get("/trading/positions")
def trading_positions():
    """Get all open positions."""
    return get_positions()


@router.get("/trading/orders")
def trading_orders(status: str = Query(default="open")):
    """Get recent orders."""
    return get_orders(status=status)


class OrderRequest(PydanticBaseModel):
    symbol: str
    qty: float
    side: str
    order_type: str = "market"
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: str = "day"


@router.post("/trading/order")
def trading_place_order(req: OrderRequest):
    """Place a paper trade order."""
    return place_order(
        symbol=req.symbol,
        qty=req.qty,
        side=req.side,
        order_type=req.order_type,
        limit_price=req.limit_price,
        stop_price=req.stop_price,
        time_in_force=req.time_in_force,
    )


@router.post("/trading/close/{symbol}")
def trading_close_position(symbol: str):
    """Close an open position."""
    return close_position(symbol)


@router.post("/trading/cancel/{order_id}")
def trading_cancel_order(order_id: str):
    """Cancel an open order."""
    return cancel_order(order_id)


# --- Custom Screener Endpoints ---

from src.scanner.custom_screener import run_custom_scan, get_available_filters


@router.get("/screener/filters")
def screener_filters():
    """Get available filter options for custom screener."""
    return get_available_filters()


@router.get("/screener/scan")
def screener_scan(
    min_price: float = Query(default=5),
    max_price: float = Query(default=500),
    min_volume: int = Query(default=500_000),
    min_score: float = Query(default=0),
    min_rs: float = Query(default=0),
    setup_types: str = Query(default=""),
    require_ema: bool = Query(default=False),
    min_change: float = Query(default=-999),
    max_change: float = Query(default=999),
    top_n: int = Query(default=50, ge=1, le=200),
):
    """Run a custom scan with user-defined criteria."""
    types_list = [s.strip() for s in setup_types.split(",") if s.strip()] if setup_types else None

    cache_key = f"custom_scan_{min_price}_{max_price}_{min_volume}_{min_score}_{min_rs}_{setup_types}_{require_ema}_{min_change}_{max_change}_{top_n}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _SCAN_CACHE_TTL:
        return cached[1]

    result = run_custom_scan(
        min_price=min_price,
        max_price=max_price,
        min_volume=min_volume,
        min_score=min_score,
        min_rs=min_rs,
        setup_types=types_list,
        require_ema_aligned=require_ema,
        min_change_pct=min_change if min_change > -999 else None,
        max_change_pct=max_change if max_change < 999 else None,
        top_n=top_n,
    )
    _scan_cache[cache_key] = (time.time(), result)
    return result


# --- Multi-Timeframe Endpoints ---

from src.scanner.multi_timeframe import analyze_multi_timeframe


@router.get("/multi-tf/{symbol}")
def multi_timeframe(symbol: str):
    """Analyze a symbol across weekly, daily, and hourly timeframes."""
    cache_key = f"multi_tf_{symbol}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _SCAN_CACHE_TTL:
        return cached[1]

    result = analyze_multi_timeframe(symbol.upper())
    _scan_cache[cache_key] = (time.time(), result)
    return result


# --- Share Signals + Community Feed Endpoints ---

from src.social.community import (
    share_signal, get_shared_signal, get_recent_shares,
    create_post, get_feed, add_comment, like_post,
)


@router.post("/share/signal")
def share_signal_endpoint(
    symbol: str = Query(...),
    action: str = Query(...),
    entry: float = Query(...),
    target: float = Query(...),
    stop_loss: float = Query(...),
    setup_type: str = Query(default=""),
    confidence: float = Query(default=0.5),
    user: dict | None = Depends(optional_user),
):
    """Share a signal and get a shareable link."""
    signal_data = {
        "symbol": symbol.upper(),
        "action": action.upper(),
        "entry": entry,
        "target": target,
        "stop_loss": stop_loss,
        "setup_type": setup_type,
        "confidence": confidence,
    }
    user_id = user["user_id"] if user else ""
    user_name = user.get("email", "").split("@")[0] if user else ""
    return share_signal(signal_data, user_id, user_name)


@router.get("/share/{share_id}")
def get_share(share_id: str):
    """Get a shared signal by ID."""
    result = get_shared_signal(share_id)
    if not result:
        return {"error": "Signal not found"}
    return result


@router.get("/share/recent/list")
def recent_shares(limit: int = Query(default=20, ge=1, le=100)):
    """Get recently shared signals."""
    return get_recent_shares(limit=limit)


class PostRequest(PydanticBaseModel):
    content: str
    symbol: str = ""
    trade_data: dict | None = None


@router.post("/community/post")
def community_post(req: PostRequest, user: dict = Depends(get_current_user)):
    """Create a community feed post."""
    return create_post(
        user_id=user["user_id"],
        user_name=user.get("email", "").split("@")[0],
        content=req.content,
        symbol=req.symbol,
        trade_data=req.trade_data,
    )


@router.get("/community/feed")
def community_feed(
    limit: int = Query(default=50, ge=1, le=200),
    symbol: str = Query(default=""),
):
    """Get community feed posts."""
    return get_feed(limit=limit, symbol=symbol)


class CommentRequest(PydanticBaseModel):
    content: str


@router.post("/community/post/{post_id}/comment")
def community_comment(
    post_id: str,
    req: CommentRequest,
    user: dict = Depends(get_current_user),
):
    """Add a comment to a post."""
    return add_comment(
        post_id=post_id,
        user_id=user["user_id"],
        user_name=user.get("email", "").split("@")[0],
        content=req.content,
    )


@router.post("/community/post/{post_id}/like")
def community_like(post_id: str):
    """Like a post."""
    return like_post(post_id)


# --- Options Strategy Builder Endpoints ---

from src.trading.options_strategies import build_strategy, list_strategies


@router.get("/options/strategies")
def options_strategy_list():
    """List available options strategies."""
    return list_strategies()


@router.get("/options/strategy/{strategy_key}")
def options_strategy_build(
    strategy_key: str,
    stock_price: float = Query(..., description="Current stock price"),
):
    """Build an options strategy with P&L calculations."""
    return build_strategy(strategy_key, stock_price)


# --- Advanced Signal Scanners (1-4, 14-18, 20) ---

from src.scanner.advanced_signals import (
    get_vix_adjustment, scan_gaps, scan_unusual_volume, scan_short_squeeze,
    scan_bollinger_squeeze, scan_macd_divergence, scan_ema_crosses,
    analyze_gap_fill, calculate_pivots, scan_atr_ranking,
    scan_extended_hours_movers,
)


@router.get("/signals/vix")
def vix_status():
    """Get VIX level and confidence adjustment."""
    return get_vix_adjustment()


@router.get("/signals/gaps")
def gap_scanner(min_gap: float = Query(default=2.0)):
    """Scan for premarket/afterhours gaps."""
    return scan_gaps(min_gap_pct=min_gap)


@router.get("/signals/extended-hours")
def extended_hours_movers(
    session: str = Query(default="auto", pattern="^(auto|premarket|afterhours)$"),
    min_move: float = Query(default=1.0),
):
    """Live premarket / after-hours movers vs prior regular session close."""
    return scan_extended_hours_movers(session=session, min_move_pct=min_move)


@router.get("/signals/unusual-volume")
def unusual_volume(min_ratio: float = Query(default=3.0)):
    """Flag stocks with unusually high volume."""
    return scan_unusual_volume(min_ratio=min_ratio)


@router.get("/signals/short-squeeze")
def short_squeeze():
    """Scan for short squeeze candidates."""
    return scan_short_squeeze()


@router.get("/signals/bollinger-squeeze")
def bollinger_squeeze():
    """Detect Bollinger Band squeezes."""
    return scan_bollinger_squeeze()


@router.get("/signals/macd-divergence")
def macd_divergence():
    """Scan for MACD divergences."""
    return scan_macd_divergence()


@router.get("/signals/ema-crosses")
def ema_crosses():
    """Detect golden/death crosses (50/200 EMA)."""
    return scan_ema_crosses()


@router.get("/signals/gap-fill/{symbol}")
def gap_fill(symbol: str):
    """Calculate gap fill probability for a symbol."""
    return analyze_gap_fill(symbol.upper())


@router.get("/signals/pivots/{symbol}")
def pivot_points(symbol: str):
    """Calculate pivot points for a symbol."""
    return calculate_pivots(symbol.upper())


@router.get("/signals/atr-ranking")
def atr_ranking():
    """Rank stocks by ATR volatility."""
    return scan_atr_ranking()


# --- Market Data Features (5-8, 11-13) ---

from src.scanner.market_data import (
    get_insider_aggregation, get_ipo_calendar, get_dividend_calendar,
    get_stock_splits, calculate_fibonacci, calculate_volume_profile,
    calculate_ichimoku,
)


@router.get("/market/insiders")
def insider_aggregation():
    """Get aggregated insider buying across sectors."""
    return get_insider_aggregation()


@router.get("/market/ipos")
def ipo_calendar():
    """Get upcoming and recent IPOs."""
    return get_ipo_calendar()


@router.get("/market/dividends")
def dividend_calendar():
    """Get upcoming dividend dates."""
    return get_dividend_calendar()


@router.get("/market/splits")
def stock_splits():
    """Get upcoming and recent stock splits."""
    return get_stock_splits()


@router.get("/analysis/fibonacci/{symbol}")
def fibonacci(symbol: str, days: int = Query(default=60)):
    """Calculate Fibonacci retracement levels."""
    return calculate_fibonacci(symbol.upper(), days=days)


@router.get("/analysis/volume-profile/{symbol}")
def volume_profile(symbol: str):
    """Calculate price-by-volume profile."""
    return calculate_volume_profile(symbol.upper())


@router.get("/analysis/ichimoku/{symbol}")
def ichimoku(symbol: str):
    """Calculate Ichimoku cloud components."""
    return calculate_ichimoku(symbol.upper())


# --- Portfolio Analytics (21-30) ---

from src.trading.portfolio_analytics import get_portfolio_analytics


@router.get("/portfolio/analytics")
def portfolio_analytics():
    """Get comprehensive portfolio analytics (heat map, drawdown, Sharpe, beta, etc.)."""
    cache_key = "portfolio_analytics"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 60:
        return cached[1]

    result = get_portfolio_analytics()
    _scan_cache[cache_key] = (time.time(), result)
    return result


# --- Market Breadth, Economic Calendar, Crypto F&G (19, 61, 62, 70) ---

from src.scanner.market_breadth import (
    compute_market_breadth, get_relative_volume_profile,
    get_economic_calendar, get_crypto_fear_greed,
)


@router.get("/market/breadth")
def market_breadth():
    """Get market breadth indicators (advance/decline, % above SMAs)."""
    cache_key = "market_breadth"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL_MED:
        return cached[1]
    result = compute_market_breadth()
    _scan_cache[cache_key] = (time.time(), result)
    return result


@router.get("/market/economic-calendar")
def economic_calendar():
    """Get upcoming economic events."""
    return get_economic_calendar()


@router.get("/market/crypto-fear-greed")
def crypto_fear_greed():
    """Get crypto fear and greed index."""
    return get_crypto_fear_greed()


@router.get("/analysis/relative-volume/{symbol}")
def relative_volume(symbol: str):
    """Get hourly volume profile for a symbol."""
    return get_relative_volume_profile(symbol.upper())


# --- Notification Channels (41-50) ---

from src.notifications.channels import (
    send_telegram, send_discord, generate_morning_briefing,
    generate_eod_report, evaluate_custom_rules, check_cooldown,
)


@router.get("/notifications/briefing")
def morning_briefing():
    """Generate morning market briefing."""
    from src.scanner.market_regime import detect_regime
    from src.scanner.news_sentiment import fetch_news

    symbols = get_default_universe()
    mom_cached = _scan_cache.get("scan_20_5.0_500.0_500000")
    scan_results = mom_cached[1] if mom_cached else []
    regime = detect_regime()
    news = fetch_news(symbols)

    return {"briefing": generate_morning_briefing(scan_results, regime, news)}


@router.get("/notifications/eod-report")
def eod_report():
    """Generate end-of-day report."""
    from src.trading.paper import get_positions
    mom_cached = _scan_cache.get("scan_20_5.0_500.0_500000")
    scan_results = mom_cached[1] if mom_cached else []
    alerts = get_alert_history(limit=50)
    positions = get_positions()

    return {"report": generate_eod_report(scan_results, alerts, positions)}


@router.post("/notifications/test-telegram")
def test_telegram(
    bot_token: str = Query(...),
    chat_id: str = Query(...),
    message: str = Query(default="Test from MSE"),
):
    """Test Telegram bot connection."""
    ok = send_telegram(bot_token, chat_id, message)
    return {"status": "sent" if ok else "error"}


@router.post("/notifications/test-discord")
def test_discord(
    webhook_url: str = Query(...),
    message: str = Query(default="Test from MSE"),
):
    """Test Discord webhook."""
    ok = send_discord(webhook_url, message)
    return {"status": "sent" if ok else "error"}


@router.get("/notifications/cooldown/{symbol}")
def alert_cooldown(symbol: str, minutes: int = Query(default=60)):
    """Check if a symbol is in alert cooldown."""
    ok = check_cooldown(symbol.upper(), minutes)
    return {"symbol": symbol.upper(), "can_alert": ok}


# --- RSS Feed of Signals (#98) ---

@router.get("/feed/signals.rss")
def signals_rss():
    """RSS feed of recent signals."""
    from fastapi.responses import Response

    mom_cached = _scan_cache.get("scan_20_5.0_500.0_500000")
    results = mom_cached[1][:10] if mom_cached else []

    items = ""
    for r in results:
        sym = r.symbol if hasattr(r, 'symbol') else r.get('symbol', '')
        score = r.score if hasattr(r, 'score') else r.get('score', 0)
        price = r.price if hasattr(r, 'price') else r.get('price', 0)
        items += f"""<item>
      <title>{sym} - Score {score:.0f}</title>
      <description>{sym} at ${price:.2f}, momentum score {score:.0f}</description>
      <link>https://momentum-signal-engine.vercel.app/chart/{sym}</link>
    </item>\n"""

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>MSE Signal Feed</title>
    <description>Momentum Signal Engine - Latest Signals</description>
    <link>https://momentum-signal-engine.vercel.app</link>
    {items}
  </channel>
</rss>"""

    return Response(content=rss, media_type="application/rss+xml")


# --- iCal Feed of Earnings (#99) ---

@router.get("/feed/earnings.ics")
def earnings_ical():
    """iCal feed of upcoming earnings dates."""
    from fastapi.responses import Response

    earn_cached = _scan_cache.get("earnings_whisper_14_0")
    events = earn_cached[1][:20] if earn_cached else []

    cal_events = ""
    for e in events:
        sym = e.symbol if hasattr(e, 'symbol') else e.get('symbol', '')
        date = e.earnings_date if hasattr(e, 'earnings_date') else e.get('earnings_date', '')
        date_str = date.strftime("%Y%m%d") if hasattr(date, 'strftime') else str(date)[:10].replace("-", "")
        cal_events += f"""BEGIN:VEVENT
DTSTART;VALUE=DATE:{date_str}
SUMMARY:{sym} Earnings
DESCRIPTION:Earnings report for {sym}
END:VEVENT
"""

    ical = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//MSE//Earnings Calendar//EN
{cal_events}END:VCALENDAR"""

    return Response(content=ical, media_type="text/calendar")


# --- Order Tools (57-59) ---

from src.trading.order_tools import (
    get_dca_schedules, add_dca_schedule, remove_dca_schedule,
    get_trailing_stops, add_trailing_stop, check_trailing_stops,
    build_bracket_order,
)


@router.get("/trading/dca")
def dca_list():
    """Get DCA schedules."""
    return get_dca_schedules()


@router.post("/trading/dca")
def dca_add(
    symbol: str = Query(...),
    amount: float = Query(...),
    frequency: str = Query(default="weekly"),
):
    """Add a DCA schedule."""
    return add_dca_schedule(symbol, amount, frequency)


@router.delete("/trading/dca/{schedule_id}")
def dca_remove(schedule_id: str):
    """Remove a DCA schedule."""
    ok = remove_dca_schedule(schedule_id)
    return {"status": "removed" if ok else "error"}


@router.get("/trading/trailing-stops")
def trailing_stops_list():
    """Get all trailing stops."""
    return get_trailing_stops()


@router.post("/trading/trailing-stop")
def trailing_stop_add(
    symbol: str = Query(...),
    trail_pct: float = Query(...),
    entry_price: float = Query(...),
):
    """Add a trailing stop."""
    return add_trailing_stop(symbol, trail_pct, entry_price)


@router.post("/trading/trailing-stops/check")
def trailing_stops_check():
    """Check all trailing stops against current prices."""
    return check_trailing_stops()


@router.post("/trading/bracket-order")
def bracket_order(
    symbol: str = Query(...),
    qty: float = Query(...),
    entry: float = Query(...),
    stop_loss: float = Query(...),
    take_profit: float = Query(...),
):
    """Submit a bracket order (entry + stop + target)."""
    return build_bracket_order(symbol, qty, entry, stop_loss, take_profit)


# --- Comparison & Global Markets (55, 63-64, 69) ---

from src.scanner.comparison import (
    compare_stocks, get_yield_curve, get_global_markets,
    get_usage_stats, track_usage,
)


@router.get("/compare")
def stock_compare(symbols: str = Query(..., description="Comma-separated symbols")):
    """Compare stocks side by side."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    return compare_stocks(sym_list)


@router.get("/market/yield-curve")
def yield_curve():
    """Get treasury yield curve data."""
    return get_yield_curve()


@router.get("/market/global")
def global_markets():
    """Get global market dashboard."""
    cache_key = "global_markets"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL_MED:
        return cached[1]
    result = get_global_markets()
    _scan_cache[cache_key] = (time.time(), result)
    return result


@router.get("/analytics/usage")
def usage_analytics():
    """Get usage analytics."""
    return get_usage_stats()


# --- TradingView Webhook Receiver (#95) ---

class WebhookPayload(PydanticBaseModel):
    symbol: str = ""
    action: str = ""
    price: float = 0
    message: str = ""


@router.post("/webhook/tradingview")
def tradingview_webhook(payload: WebhookPayload):
    """Receive alerts from TradingView webhooks."""
    from src.data.redis_store import log_alert

    log_alert({
        "symbol": payload.symbol.upper(),
        "action": payload.action.upper(),
        "entry": payload.price,
        "confidence": 0,
        "reason": f"TradingView: {payload.message}",
        "sms_sent": False,
        "webhook_sent": False,
        "source": "tradingview",
    })

    # Optionally dispatch through our alert system
    logger_name = logging.getLogger("mse.webhook")
    logger_name.info("TradingView webhook: %s %s @ %s", payload.action, payload.symbol, payload.price)

    return {"status": "received", "symbol": payload.symbol, "action": payload.action}


# --- Extra Data (9, 56, 60, 65-68, 75, 77) ---

from src.scanner.extra_data import (
    get_spac_overview, get_sector_rotation_signal, get_currency_strength,
    get_commodities, get_reit_analysis, get_bond_market,
    detect_anomalies, optimize_portfolio,
)


@router.get("/market/spacs")
def spac_tracker():
    """Get SPAC market overview."""
    return get_spac_overview()


@router.get("/market/sector-rotation")
def sector_rotation():
    """Get sector rotation signals."""
    cache_key = "sector_rotation"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL_MED:
        return cached[1]
    result = get_sector_rotation_signal()
    _scan_cache[cache_key] = (time.time(), result)
    return result


@router.get("/market/currencies")
def currency_strength():
    """Get currency strength via forex ETFs."""
    return get_currency_strength()


@router.get("/market/commodities")
def commodities():
    """Track major commodities via ETFs."""
    return get_commodities()


@router.get("/market/reits")
def reit_analysis():
    """Analyze REITs and REIT ETFs."""
    return get_reit_analysis()


@router.get("/market/bonds")
def bond_market():
    """Monitor bond market via ETFs."""
    return get_bond_market()


@router.get("/signals/anomalies")
def anomalies():
    """Detect price/volume anomalies across the universe."""
    return detect_anomalies()


@router.get("/portfolio/optimize")
def portfolio_optimize(symbols: str = Query(..., description="Comma-separated symbols")):
    """Optimize portfolio weights (mean-variance)."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    return optimize_portfolio(sym_list)


# --- Natural Language Screener (#72) ---

from src.scanner.nl_screener import parse_query


@router.get("/screener/nl")
def natural_language_screen(q: str = Query(..., description="Natural language query")):
    """Parse natural language into scan filters and run the scan."""
    parsed = parse_query(q)
    filters = parsed["parsed_filters"]

    # Run the scan with parsed filters
    from src.scanner.custom_screener import run_custom_scan
    results = run_custom_scan(
        min_price=filters.get("min_price", 5),
        max_price=filters.get("max_price", 500),
        min_volume=filters.get("min_volume", 500000),
        min_score=filters.get("min_score", 0),
        min_rs=filters.get("min_rs", 0),
        setup_types=[s.strip() for s in filters["setup_types"].split(",") if s.strip()] if filters.get("setup_types") else None,
        require_ema_aligned=filters.get("require_ema", False),
        top_n=filters.get("top_n", 20),
    )

    return {
        "query": parsed["query"],
        "parsed": parsed["parsed_filters"],
        "description": parsed["description"],
        "results": results,
    }


# --- Feedback Widget (#89) ---

from src.data.redis_store import _get_redis as get_redis_client
import json as json_module


class FeedbackRequest(PydanticBaseModel):
    type: str = "general"
    message: str = ""
    page: str = ""
    rating: int = 0


@router.post("/feedback")
def submit_feedback(req: FeedbackRequest, user: dict | None = Depends(optional_user)):
    """Submit in-app feedback."""
    redis = get_redis_client()
    if not redis:
        return {"status": "error", "message": "Storage unavailable"}

    try:
        existing = redis.get("mse:feedback")
        feedback_list = json_module.loads(existing) if existing else []
        feedback_list.append({
            "type": req.type,
            "message": req.message,
            "page": req.page,
            "rating": req.rating,
            "user_id": user["user_id"] if user else "anonymous",
            "timestamp": datetime.now().isoformat(),
        })
        if len(feedback_list) > 500:
            feedback_list = feedback_list[-500:]
        redis.set("mse:feedback", json_module.dumps(feedback_list))
        return {"status": "submitted"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/feedback")
def get_feedback():
    """Get all feedback (admin)."""
    redis = get_redis_client()
    if not redis:
        return []
    try:
        data = redis.get("mse:feedback")
        return json_module.loads(data) if data else []
    except Exception:
        return []


# --- Zapier/Make Integration (#100) ---

@router.post("/webhook/zapier")
def zapier_webhook(payload: WebhookPayload):
    """Generic webhook receiver for Zapier/Make integrations."""
    from src.data.redis_store import log_alert
    log_alert({
        "symbol": payload.symbol.upper(),
        "action": payload.action.upper(),
        "entry": payload.price,
        "confidence": 0,
        "reason": f"Zapier/Make: {payload.message}",
        "source": "zapier",
        "sms_sent": False,
        "webhook_sent": False,
    })
    return {"status": "received"}


# --- Tax Lot Optimizer (#27) ---

from src.trading.tax_lots import optimize_tax_lots


@router.get("/portfolio/tax-lots")
def tax_lots():
    """Analyze positions for tax-loss harvesting opportunities."""
    return optimize_tax_lots()


# --- Weekly Digest & Escalation (#44, #48) ---

from src.notifications.channels import (
    generate_weekly_digest, send_email_digest,
    check_escalation, get_social_sentiment_proxy,
)


@router.get("/notifications/weekly-digest")
def weekly_digest():
    """Generate weekly email digest."""
    mom_cached = _scan_cache.get("scan_20_5.0_500.0_500000")
    scan_results = mom_cached[1] if mom_cached else []

    lb_cached = _scan_cache.get("leaderboard_stats")
    leaderboard = lb_cached[1] if lb_cached else {}

    alerts = get_alert_history(limit=100)
    body = generate_weekly_digest(scan_results, leaderboard, len(alerts))
    return {"digest": body}


@router.post("/notifications/send-digest")
def send_digest(to_email: str = Query(...)):
    """Send weekly digest to an email address."""
    mom_cached = _scan_cache.get("scan_20_5.0_500.0_500000")
    scan_results = mom_cached[1] if mom_cached else []
    lb_cached = _scan_cache.get("leaderboard_stats")
    leaderboard = lb_cached[1] if lb_cached else {}
    alerts = get_alert_history(limit=100)

    body = generate_weekly_digest(scan_results, leaderboard, len(alerts))
    ok = send_email_digest(to_email, "MSE Weekly Digest", body)
    return {"status": "sent" if ok else "error"}


@router.get("/signals/escalation/{symbol}")
def signal_escalation(symbol: str, confidence: float = Query(...)):
    """Check if a signal has escalated (strengthened)."""
    return check_escalation(symbol.upper(), confidence)


# --- Social Sentiment (#60) ---

@router.get("/sentiment/{symbol}")
def social_sentiment(symbol: str):
    """Get social sentiment proxy for a symbol."""
    return get_social_sentiment_proxy(symbol.upper())


# --- Referral Program (#83) ---

from src.auth.referrals import get_referral_stats, record_referral


@router.get("/referral/stats")
def referral_stats(user: dict = Depends(get_current_user)):
    """Get referral stats for the authenticated user."""
    return get_referral_stats(user["user_id"])


@router.post("/referral/apply")
def apply_referral(code: str = Query(...)):
    """Apply a referral code during registration."""
    return {"applied": record_referral(code, ""), "code": code}


# --- Preset Screener + Analyzer + Multi-year Trends ---

from src.scanner.analyzer import analyze_symbol
from src.scanner.multi_year_trends import analyze_long_term
from src.scanner.preset_screener import list_strategies, run_preset


@router.get("/screener/presets")
def screener_presets():
    """List available preset screener strategies."""
    return list_strategies()


@router.get("/screener/preset/{strategy}")
def screener_preset_run(
    strategy: str,
    top_n: int = Query(default=25, ge=1, le=100),
):
    """Run a named preset screener over the default universe."""
    cache_key = f"preset_{strategy}_{top_n}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _SCAN_CACHE_TTL:
        return cached[1]
    result = run_preset(strategy, top_n=top_n)
    _scan_cache[cache_key] = (time.time(), result)
    return result


@router.get("/analyzer/{symbol}")
def analyzer(symbol: str):
    """Consolidated analyzer report for a single symbol."""
    cache_key = f"analyzer_{symbol.upper()}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _SCAN_CACHE_TTL:
        return cached[1]
    result = analyze_symbol(symbol)
    _scan_cache[cache_key] = (time.time(), result)
    return result


@router.get("/trends/{symbol}")
def multi_year_trends(symbol: str):
    """Multi-year trend analysis (returns, CAGR, drawdowns, regime)."""
    cache_key = f"trends_{symbol.upper()}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL_LONG:
        return cached[1]
    result = analyze_long_term(symbol)
    _scan_cache[cache_key] = (time.time(), result)
    return result


# --- Portfolio paste parser (shared by /watchlist import and /holdings page) ---

from src.scanner.portfolio_parser import parse_portfolio_text


class PortfolioParseRequest(PydanticBaseModel):
    text: str


@router.post("/portfolio/parse")
def portfolio_parse(req: PortfolioParseRequest):
    """Parse pasted portfolio/watchlist text into (symbol, shares?) pairs."""
    holdings = parse_portfolio_text(req.text)
    return {"count": len(holdings), "holdings": holdings}


from src.scanner.portfolio_metrics import analyze_portfolio


class PortfolioAnalyzeRequest(PydanticBaseModel):
    holdings: list[dict]


@router.post("/portfolio/analyze")
def portfolio_analyze(req: PortfolioAnalyzeRequest):
    """Run portfolio-level metrics (sector weights, correlation, beta, DD)."""
    return analyze_portfolio(req.holdings)


# --- Instrument overview page ---

from src.scanner.instrument_fundamentals import get_fundamentals


@router.get("/instrument/{symbol}/fundamentals")
def instrument_fundamentals(symbol: str):
    """Return FMP-backed fundamentals bundle for the instrument page."""
    cache_key = f"instr_fund_{symbol.upper()}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL_LONG:
        return cached[1]
    result = get_fundamentals(symbol)
    _scan_cache[cache_key] = (time.time(), result)
    return result


from src.scanner.seasonality import analyze_seasonality


@router.get("/instrument/{symbol}/seasonality")
def instrument_seasonality(
    symbol: str,
    years: int = Query(default=10, ge=3, le=20),
):
    """Monthly seasonality stats for the instrument page."""
    cache_key = f"instr_seas_{symbol.upper()}_{years}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL_LONG:
        return cached[1]
    result = analyze_seasonality(symbol, years=years)
    _scan_cache[cache_key] = (time.time(), result)
    return result


from src.scanner.instrument_indicators import get_indicator_series


@router.get("/instrument/{symbol}/indicators")
def instrument_indicators(symbol: str):
    """Indicator series (RSI, MACD, Bollinger) for Overbought-Oversold tab."""
    cache_key = f"instr_ind_{symbol.upper()}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _SCAN_CACHE_TTL:
        return cached[1]
    result = get_indicator_series(symbol)
    _scan_cache[cache_key] = (time.time(), result)
    return result


@router.get("/instrument/{symbol}/news")
def instrument_news(symbol: str, limit: int = Query(default=20, ge=1, le=50)):
    """Articles mentioning the symbol, sorted by sentiment strength."""
    sym = symbol.upper()
    cache_key = f"instr_news_{sym}_{limit}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL_MED:
        return cached[1]
    from src.scanner.news_sentiment import fetch_news
    articles = fetch_news([sym])
    filtered = [a for a in articles if sym in a.get("symbols", [])][:limit]
    result = {"symbol": sym, "count": len(filtered), "articles": filtered}
    _scan_cache[cache_key] = (time.time(), result)
    return result


# --- Industry Rankings + Sector Map ---

from src.scanner.industry_rankings import (
    get_industry_ranking,
    list_known_industries,
)
from src.scanner.sector_map import get_sector_map


@router.get("/rankings/industries")
def rankings_industries():
    """List the industry slugs recognized by the rankings feature."""
    return list_known_industries()


@router.get("/rankings/industry/{industry_slug}")
def rankings_industry(industry_slug: str, limit: int = Query(default=30, ge=5, le=100)):
    """Ranked companies in an industry with Z/F/M scores."""
    return get_industry_ranking(industry_slug, limit=limit)


@router.get("/sector-map")
def sector_map(days: int = Query(default=365, ge=90, le=1825)):
    """Sector ETF cumulative-return time series (for sector-rotation chart)."""
    cache_key = f"sector_map_{days}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL_LONG:
        return cached[1]
    result = get_sector_map(days=days)
    _scan_cache[cache_key] = (time.time(), result)
    return result


# --- AI Agent ---

from src.ai.agent import list_topics, run_agent


@router.get("/agent/topics")
def agent_topics():
    """List available AI agent topics."""
    return list_topics()


@router.get("/instrument/{symbol}/agent/{topic}")
def instrument_agent(symbol: str, topic: str):
    """Run the AI agent for one topic on a symbol. Cached 24h per (symbol, topic)."""
    sym = symbol.upper()
    cache_key = f"agent_{sym}_{topic}"
    cached = _scan_cache.get(cache_key)
    if cached and time.time() - cached[0] < 24 * 60 * 60:
        return cached[1]
    # Pass the FMP-known company name when we have it cached
    from src.scanner.instrument_fundamentals import get_fundamentals
    name = None
    fund_cache = _scan_cache.get(f"instr_fund_{sym}")
    if fund_cache:
        try:
            name = fund_cache[1].get("header", {}).get("name")
        except Exception:
            pass
    if not name:
        try:
            name = get_fundamentals(sym).get("header", {}).get("name") or sym
        except Exception:
            name = sym
    result = run_agent(sym, topic, company_name=name)
    # Only cache successful calls
    if "error" not in result:
        _scan_cache[cache_key] = (time.time(), result)
    return result


# --- Profile Screener (yfinance fundamentals) ---

from src.scanner.profile_screener import list_profiles, list_sectors, screen as profile_screen


@router.get("/profile-screener/profiles")
def profile_screener_profiles():
    """List available profile presets."""
    return {"profiles": list_profiles(), "sectors": list_sectors()}


@router.get("/profile-screener/run")
def profile_screener_run(
    sector: str = Query(default="semiconductors"),
    max_fwd_pe: float | None = Query(default=None),
    min_momentum: float | None = Query(default=None),
    min_rev_growth: float | None = Query(default=None),
    min_cap: float | None = Query(default=None, description="Raw market cap (e.g. 5e9)"),
    custom: str = Query(default=""),
):
    """Run the profile screener with fundamental + momentum filters."""
    results = profile_screen(
        sector=sector,
        max_fwd_pe=max_fwd_pe,
        min_momentum_6m=min_momentum,
        min_rev_growth=min_rev_growth,
        min_cap=min_cap,
        custom_tickers=custom,
    )
    return {"results": results, "count": len(results), "sector": sector}
