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
):
    """Get dispatched alert history."""
    return get_alert_history(limit=limit)


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

from src.auth.users import register as auth_register, login as auth_login
from src.auth.deps import get_current_user, optional_user
from src.data.redis_store import get_user_data, set_user_data
from fastapi import Depends


@router.post("/auth/register")
def register(
    email: str = Query(...),
    password: str = Query(...),
    name: str = Query(default=""),
):
    """Register a new user."""
    result = auth_register(email, password, name)
    if "error" in result:
        return {"status": "error", "message": result["error"]}
    return {"status": "ok", **result}


@router.post("/auth/login")
def login(
    email: str = Query(...),
    password: str = Query(...),
):
    """Login and get a JWT token."""
    result = auth_login(email, password)
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
    current_password: str = Query(...),
    new_password: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Change password for the authenticated user."""
    import bcrypt
    from src.auth.users import _load_users, _save_users

    if len(new_password) < 6:
        return {"status": "error", "message": "New password must be at least 6 characters"}

    users = _load_users()
    full_user = users.get(user["email"])
    if not full_user:
        return {"status": "error", "message": "User not found"}

    if not bcrypt.checkpw(current_password.encode(), full_user["password_hash"].encode()):
        return {"status": "error", "message": "Current password is incorrect"}

    new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    full_user["password_hash"] = new_hash
    users[user["email"]] = full_user
    _save_users(users)

    return {"status": "ok", "message": "Password updated"}


@router.post("/auth/update-name")
def update_name(
    name: str = Query(...),
    user: dict = Depends(get_current_user),
):
    """Update display name for the authenticated user."""
    from src.auth.users import _load_users, _save_users

    users = _load_users()
    full_user = users.get(user["email"])
    if not full_user:
        return {"status": "error", "message": "User not found"}

    full_user["name"] = name.strip()
    users[user["email"]] = full_user
    _save_users(users)

    return {"status": "ok", "name": name.strip()}


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
