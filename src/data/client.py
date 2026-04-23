from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.enums import Adjustment
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest, CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetStatus

from config.settings import settings
from src.data.cache import Cache

_cache = Cache()

# Short-lived in-memory cache for intraday bars. Keyed by the same string
# as the on-disk cache but never persisted — minute/5-min data turns stale
# fast and reusing it across restarts would defeat the point.
_intraday_cache: dict[str, tuple[float, dict]] = {}
_INTRADAY_TTL_SECONDS = 60

_STOCK_CHUNK_SIZE = 200  # Alpaca URL length safe limit for batched bars


def _get_data_client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(
        settings.alpaca_api_key,
        settings.alpaca_secret_key,
    )


def _get_crypto_client() -> CryptoHistoricalDataClient:
    return CryptoHistoricalDataClient()


def _is_crypto(symbol: str) -> bool:
    return "/" in symbol


# Known international exchange suffixes FMP covers. Anything in this set
# routes to FMP historical-prices instead of Alpaca.
_INTL_SUFFIXES: set[str] = {
    "PA", "DE", "L", "TO", "V", "SW", "TA", "HK", "AS", "BR", "MI",
    "SS", "SZ", "KS", "T", "TW", "AX", "MC", "VI", "WA", "SA", "OL",
    "HE", "CO", "ST", "MX", "BO", "NS", "TWO", "JK",
}


def _is_international(symbol: str) -> bool:
    parts = symbol.split(".")
    return len(parts) == 2 and parts[1].upper() in _INTL_SUFFIXES


# Forex majors / minors / some crosses (FMP format — no separator).
_FOREX_PAIRS: set[str] = {
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    "EURJPY", "GBPJPY", "EURGBP", "EURCHF", "EURAUD", "EURCAD", "GBPCHF",
    "CHFJPY", "AUDJPY", "CADJPY", "NZDJPY", "AUDNZD", "GBPAUD", "GBPCAD",
}

# Common commodity codes used by FMP (typically ending in USD).
_COMMODITY_CODES: set[str] = {
    "GCUSD", "SIUSD", "PLUSD", "PAUSD",     # gold, silver, platinum, palladium
    "CLUSD", "BZUSD", "NGUSD", "HOUSD",     # WTI, brent, nat gas, heating oil
    "HGUSD", "ALIUSD",                       # copper, aluminum
    "ZCUSD", "ZSUSD", "ZWUSD", "ZLUSD",     # corn, soybeans, wheat, soybean oil
    "KCUSD", "CCUSD", "SBUSD", "CTUSD",     # coffee, cocoa, sugar, cotton
    "LEUSD", "HEUSD",                        # live cattle, lean hogs
}


def _is_forex(symbol: str) -> bool:
    return symbol.upper() in _FOREX_PAIRS


def _is_commodity(symbol: str) -> bool:
    return symbol.upper() in _COMMODITY_CODES


def _is_index(symbol: str) -> bool:
    return symbol.startswith("^")


def _use_fmp_historical(symbol: str) -> bool:
    """Symbols Alpaca doesn't cover — route through FMP historical prices."""
    return (
        _is_international(symbol)
        or _is_forex(symbol)
        or _is_commodity(symbol)
        or _is_index(symbol)
    )


def _get_trading_client() -> TradingClient:
    return TradingClient(
        settings.alpaca_api_key,
        settings.alpaca_secret_key,
        paper=("paper" in settings.alpaca_base_url),
    )


def get_bars(
    symbol: str,
    timeframe: TimeFrame = TimeFrame.Day,
    days: int = 200,
) -> pd.DataFrame:
    """Fetch historical bars for a symbol, returns a DataFrame."""
    cache_key = f"bars_{symbol}_{timeframe}_{days}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    # International, forex, commodity, and index tickers route through FMP
    # historical prices — Alpaca doesn't cover these.
    if _use_fmp_historical(symbol) and str(timeframe) == "1Day":
        from src.data import fmp_client
        bars = fmp_client.get_historical_prices(symbol, days)
        if not bars.empty:
            _cache.set(cache_key, bars)
        return bars

    start = datetime.now() - timedelta(days=days)
    if _is_crypto(symbol):
        client = _get_crypto_client()
        request = CryptoBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe,
            start=start,
        )
        barset = client.get_crypto_bars(request)
    else:
        client = _get_data_client()
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe,
            start=start,
            adjustment=Adjustment.ALL,
        )
        barset = client.get_stock_bars(request)
    bars = barset.df
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.droplevel("symbol")
    bars.index = pd.to_datetime(bars.index)
    bars = bars.sort_index()

    _cache.set(cache_key, bars)
    return bars


def get_multi_bars(
    symbols: list[str],
    timeframe: TimeFrame = TimeFrame.Day,
    days: int = 200,
) -> dict[str, pd.DataFrame]:
    """Fetch bars for multiple symbols at once."""
    cache_key = f"multi_bars_{'_'.join(sorted(symbols))}_{timeframe}_{days}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    start = datetime.now() - timedelta(days=days)
    result: dict[str, pd.DataFrame] = {}

    stock_symbols = [
        s for s in symbols
        if not _is_crypto(s) and not _use_fmp_historical(s)
    ]
    crypto_symbols = [s for s in symbols if _is_crypto(s)]
    fmp_symbols = [s for s in symbols if _use_fmp_historical(s)]

    if fmp_symbols and str(timeframe) == "1Day":
        from src.data import fmp_client
        def _fmp_fetch(sym: str) -> tuple[str, pd.DataFrame]:
            return sym, fmp_client.get_historical_prices(sym, days)
        with ThreadPoolExecutor(max_workers=min(8, len(fmp_symbols))) as pool:
            for sym, df in pool.map(_fmp_fetch, fmp_symbols):
                if not df.empty:
                    result[sym] = df

    def _parse_barset(df: pd.DataFrame, syms: list[str]) -> None:
        if isinstance(df.index, pd.MultiIndex) and "symbol" in df.index.names:
            for sym in df.index.get_level_values("symbol").unique():
                sym_df = df.xs(sym, level="symbol").sort_index()
                sym_df.index = pd.to_datetime(sym_df.index)
                result[sym] = sym_df
        elif len(syms) == 1:
            df.index = pd.to_datetime(df.index)
            result[syms[0]] = df.sort_index()

    if stock_symbols:
        client = _get_data_client()

        def _fetch_chunk(chunk: list[str]) -> tuple[list[str], pd.DataFrame]:
            request = StockBarsRequest(
                symbol_or_symbols=chunk,
                timeframe=timeframe,
                start=start,
                adjustment=Adjustment.ALL,
            )
            return chunk, client.get_stock_bars(request).df

        chunks = [
            stock_symbols[i : i + _STOCK_CHUNK_SIZE]
            for i in range(0, len(stock_symbols), _STOCK_CHUNK_SIZE)
        ]
        with ThreadPoolExecutor(max_workers=min(8, len(chunks))) as pool:
            for chunk, df in pool.map(_fetch_chunk, chunks):
                _parse_barset(df, chunk)

    if crypto_symbols:
        crypto_client = _get_crypto_client()
        request = CryptoBarsRequest(
            symbol_or_symbols=crypto_symbols,
            timeframe=timeframe,
            start=start,
        )
        _parse_barset(crypto_client.get_crypto_bars(request).df, crypto_symbols)

    _cache.set(cache_key, result)

    # Seed individual symbol caches so get_bars() hits cache
    for sym, sym_df in result.items():
        individual_key = f"bars_{sym}_{timeframe}_{days}"
        _cache.set(individual_key, sym_df)

    return result


def get_intraday_multi_bars(
    symbols: list[str],
    minutes_back: int = 120,
    timeframe_minutes: int = 5,
) -> dict[str, pd.DataFrame]:
    """Batch-fetch recent intraday bars for many symbols.

    Used by the intraday-pattern scanner. Default 5-minute bars over the
    last ~2 hours is enough to detect V-reversals, blow-off tops, and
    sustained breakdowns without pulling a full day of data per symbol.

    Cache TTL is short (60s) — multiple pattern detectors share the same
    fetched bars within a single scan cycle.
    """
    if not symbols:
        return {}

    # Skip non-Alpaca symbols — Alpaca handles US equities; FMP intraday
    # is a separate paid endpoint we don't currently use.
    stock_symbols = [
        s for s in symbols
        if not _is_crypto(s) and not _use_fmp_historical(s)
    ]
    if not stock_symbols:
        return {}

    import time as _time
    cache_key = f"intraday_{'_'.join(sorted(stock_symbols))}_{minutes_back}_{timeframe_minutes}"
    cached = _intraday_cache.get(cache_key)
    if cached is not None:
        ts, data = cached
        if _time.time() - ts < _INTRADAY_TTL_SECONDS:
            return data

    if timeframe_minutes == 1:
        timeframe = TimeFrame.Minute
    elif timeframe_minutes == 5:
        from alpaca.data.timeframe import TimeFrameUnit
        timeframe = TimeFrame(5, TimeFrameUnit.Minute)
    elif timeframe_minutes == 15:
        from alpaca.data.timeframe import TimeFrameUnit
        timeframe = TimeFrame(15, TimeFrameUnit.Minute)
    else:
        from alpaca.data.timeframe import TimeFrameUnit
        timeframe = TimeFrame(timeframe_minutes, TimeFrameUnit.Minute)

    # Pad the lookback so we get enough bars even if the first few are
    # outside the requested window after data alignment.
    start = datetime.now() - timedelta(minutes=minutes_back + timeframe_minutes * 2)

    client = _get_data_client()
    result: dict[str, pd.DataFrame] = {}

    def _fetch_chunk(chunk: list[str]) -> tuple[list[str], pd.DataFrame]:
        request = StockBarsRequest(
            symbol_or_symbols=chunk,
            timeframe=timeframe,
            start=start,
            adjustment=Adjustment.ALL,
        )
        return chunk, client.get_stock_bars(request).df

    chunks = [
        stock_symbols[i : i + _STOCK_CHUNK_SIZE]
        for i in range(0, len(stock_symbols), _STOCK_CHUNK_SIZE)
    ]
    with ThreadPoolExecutor(max_workers=min(8, len(chunks))) as pool:
        for chunk, df in pool.map(_fetch_chunk, chunks):
            if df.empty:
                continue
            if isinstance(df.index, pd.MultiIndex) and "symbol" in df.index.names:
                for sym in df.index.get_level_values("symbol").unique():
                    sym_df = df.xs(sym, level="symbol").sort_index()
                    sym_df.index = pd.to_datetime(sym_df.index, utc=True)
                    result[sym] = sym_df
            elif len(chunk) == 1:
                df.index = pd.to_datetime(df.index, utc=True)
                result[chunk[0]] = df.sort_index()

    # Short TTL — pattern scanner runs every ~5 min, but multiple
    # detectors within a cycle should share the same fetch.
    _intraday_cache[cache_key] = (_time.time(), result)
    return result


def get_extended_hours_bars(symbol: str, days: int = 2) -> pd.DataFrame:
    """Fetch minute bars covering extended hours (4am-8pm ET).

    Returns a DataFrame indexed by UTC timestamp. Caller is responsible for
    filtering to the session of interest (premarket / regular / afterhours).
    Alpaca minute bars include extended hours data.
    """
    cache_key = f"ext_bars_{symbol}_{days}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    if _is_crypto(symbol):
        return pd.DataFrame()

    start = datetime.now() - timedelta(days=days)
    client = _get_data_client()
    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
    )
    bars = client.get_stock_bars(request).df
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.droplevel("symbol")
    bars.index = pd.to_datetime(bars.index, utc=True)
    bars = bars.sort_index()

    _cache.set(cache_key, bars)
    return bars


def get_latest_quote(symbol: str) -> dict:
    """Get the latest quote for a symbol."""
    client = _get_data_client()
    request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
    quotes = client.get_stock_latest_quote(request)
    quote = quotes[symbol]
    return {
        "symbol": symbol,
        "bid": float(quote.bid_price),
        "ask": float(quote.ask_price),
        "bid_size": int(quote.bid_size),
        "ask_size": int(quote.ask_size),
    }


def get_tradeable_assets() -> list[dict]:
    """Get list of active, tradeable US equities."""
    cache_key = "tradeable_assets"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    client = _get_trading_client()
    request = GetAssetsRequest(
        asset_class=AssetClass.US_EQUITY,
        status=AssetStatus.ACTIVE,
    )
    assets = client.get_all_assets(request)
    result = [
        {"symbol": a.symbol, "name": a.name, "exchange": a.exchange}
        for a in assets
        if a.tradable and a.fractionable is not None
    ]
    _cache.set(cache_key, result)
    return result


def get_account() -> dict:
    """Get account info."""
    client = _get_trading_client()
    account = client.get_account()
    return {
        "equity": float(account.equity),
        "buying_power": float(account.buying_power),
        "cash": float(account.cash),
    }
