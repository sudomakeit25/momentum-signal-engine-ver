import logging
import os
import threading
import time

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from src.api.routes import router, _scan_cache, _SCAN_CACHE_TTL

PORT = int(os.environ.get("PORT", 8000))

# Configure logging — uvicorn overrides basicConfig, so set levels explicitly
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("mse")
logger.setLevel(logging.INFO)
logging.getLogger("mse.notifications").setLevel(logging.INFO)

# Ensure our loggers have a handler if basicConfig was overridden
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logger.addHandler(_handler)
    logging.getLogger("mse.notifications").addHandler(_handler)

_REFRESH_INTERVAL = 600  # 10 min — dynamic universe is ~2k stocks, gives scan time to finish
_stop_event = threading.Event()


def _build_scan_universe() -> list[str]:
    """Build the scan universe from FMP screener + user watchlist, with fallback."""
    from src.data import fmp_client
    from src.data.redis_store import get_watchlist
    from src.scanner.screener import get_default_universe

    liquid = fmp_client.get_liquid_universe()
    if not liquid:
        liquid = get_default_universe()
        logger.info("Using hardcoded default universe fallback: %d symbols", len(liquid))
    try:
        watchlist = get_watchlist()
    except Exception:
        watchlist = []
    merged = sorted(set(liquid) | set(watchlist))
    logger.info(
        "Scan universe built: %d symbols (liquid=%d, watchlist=%d)",
        len(merged), len(liquid), len(watchlist),
    )
    return merged


def _refresh_loop():
    """Continuously refresh market data and scan results in the background."""
    from src.data import client
    from src.scanner.screener import scan_universe
    from src.signals.generator import generate_signals
    from src.signals.patterns import detect_patterns
    from src.data.models import ScanResult
    from concurrent.futures import ThreadPoolExecutor
    from src.notifications.dispatcher import dispatch_alerts

    _seen_signal_keys: set[str] = set()
    _seen_date: str = ""  # reset accumulator daily
    _first_cycle = True

    while not _stop_event.is_set():
        try:
            # Rebuild universe each cycle so watchlist changes take effect
            symbols = _build_scan_universe()

            # Refresh Alpaca bar data
            client.get_bars("SPY", days=200)
            bars_map = client.get_multi_bars(symbols, days=200)

            # Run the scan — pass top_n=None so all qualifying signals can dispatch;
            # max_price lifted so high-priced names like AVGO aren't excluded.
            results, bars_map = scan_universe(
                symbols, top_n=len(symbols), min_price=5.0, max_price=10_000.0,
                min_volume=500_000, return_bars=True,
            )

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

            # --- Auto-dispatch new signals ---
            all_signals = []
            for r in results:
                all_signals.extend(r.signals)

            logger.info("Signal check: %d total signals from %d results", len(all_signals), len(results))

            current_keys = set()
            for s in all_signals:
                key = f"{s.symbol}:{s.action.value}:{s.entry:.2f}"
                current_keys.add(key)

            # Reset accumulated keys at midnight so signals can re-fire the next day
            from datetime import datetime
            today_str = datetime.now().strftime("%Y-%m-%d")
            if today_str != _seen_date:
                _seen_signal_keys = set()
                _seen_date = today_str
                _first_cycle = True

            if _first_cycle:
                new_signals = all_signals
                _first_cycle = False
                logger.info("First cycle: treating all %d signals as new", len(new_signals))
            else:
                new_signals = [s for s in all_signals
                               if f"{s.symbol}:{s.action.value}:{s.entry:.2f}" not in _seen_signal_keys]

            # --- Track signals for leaderboard ---
            if new_signals:
                try:
                    from src.scanner.leaderboard import track_signals, check_outcomes
                    tracked = track_signals(new_signals)
                    if tracked:
                        logger.info("Leaderboard: tracked %d new signals", tracked)
                    # Check outcomes for older signals every cycle
                    check_outcomes(lookback_days=10)
                except Exception as e:
                    logger.debug("Leaderboard tracking failed: %s", e)

            if new_signals:
                logger.info("Dispatching %d new signals...", len(new_signals))
                try:
                    dispatch_results = dispatch_alerts(new_signals)
                    logger.info(
                        "Auto-dispatch result: webhook=%s, sms=%s",
                        dispatch_results["webhook"], dispatch_results["sms"],
                    )
                except Exception as e:
                    logger.warning("Auto-dispatch failed: %s", e)
            else:
                logger.info("No new signals to dispatch")

            _seen_signal_keys.update(current_keys)  # accumulate, don't replace

            # --- Watchlist alerts: check if any watched symbol has new signals ---
            try:
                from src.data.redis_store import get_watchlist
                watchlist = get_watchlist()
                if watchlist:
                    watchlist_signals = [s for s in all_signals if s.symbol in watchlist]
                    watchlist_new = [s for s in watchlist_signals
                                    if f"{s.symbol}:{s.action.value}:{s.entry:.2f}" not in _seen_signal_keys]
                    if watchlist_new:
                        logger.info("Watchlist alert: %d signals for watched stocks", len(watchlist_new))
                        dispatch_alerts(watchlist_new)
            except Exception as e:
                logger.debug("Watchlist alert check failed: %s", e)

            # Preserve the legacy cache slot the /scan endpoint reads with defaults
            legacy_top20 = [r for r in results if r.price <= 500.0][:20]
            _scan_cache["scan_20_5.0_500.0_500000"] = (time.time(), legacy_top20)
            _scan_cache["scan_full"] = (time.time(), results)
            logger.info(
                "Background refresh complete: %d total results, %d in legacy top-20 cache",
                len(results), len(legacy_top20),
            )

            # Warm the profile-screener (yfinance) cache for hot sectors so the
            # user never hits a cold load on the Stock Screener page.
            try:
                from src.scanner.profile_screener import warm_cache
                warmed = warm_cache()
                if warmed:
                    logger.info("Profile screener cache warmed: %d rows", warmed)
            except Exception as e:
                logger.debug("Profile screener warmup failed: %s", e)
        except Exception as e:
            logger.warning("Background refresh failed: %s", e)

        _stop_event.wait(_REFRESH_INTERVAL)


def _warm_profile_cache_on_startup() -> None:
    try:
        from src.scanner.profile_screener import warm_cache
        rows = warm_cache()
        logger.info("Startup profile cache warmup: %d rows", rows)
    except Exception as e:
        logger.warning("Startup profile cache warmup failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background refresh thread
    thread = threading.Thread(target=_refresh_loop, daemon=True)
    thread.start()
    # Warm the yfinance cache in a separate thread so startup is not blocked
    threading.Thread(target=_warm_profile_cache_on_startup, daemon=True).start()
    yield
    _stop_event.set()


app = FastAPI(
    title="Momentum Signal Engine",
    description="Stock trading analysis platform for high-probability momentum setups",
    version="0.1.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
