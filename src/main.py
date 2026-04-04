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

_REFRESH_INTERVAL = 120  # seconds — match scan cache TTL
_stop_event = threading.Event()


def _refresh_loop():
    """Continuously refresh market data and scan results in the background."""
    from src.data import client
    from src.scanner.screener import get_default_universe, scan_universe
    from src.signals.generator import generate_signals
    from src.signals.patterns import detect_patterns
    from src.data.models import ScanResult
    from concurrent.futures import ThreadPoolExecutor
    from src.notifications.dispatcher import dispatch_alerts

    symbols = get_default_universe()
    _seen_signal_keys: set[str] = set()
    _first_cycle = True

    while not _stop_event.is_set():
        try:
            # Refresh Alpaca bar data
            client.get_bars("SPY", days=200)
            bars_map = client.get_multi_bars(symbols, days=200)

            # Run the default scan and cache the result
            results, bars_map = scan_universe(
                symbols, top_n=20, min_price=5.0, max_price=500.0,
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

            if _first_cycle:
                # On first cycle, send all signals as alerts (nothing to compare against)
                new_signals = all_signals
                _first_cycle = False
                logger.info("First cycle: treating all %d signals as new", len(new_signals))
            else:
                new_signals = [s for s in all_signals
                               if f"{s.symbol}:{s.action.value}:{s.entry:.2f}" not in _seen_signal_keys]

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

            _seen_signal_keys = current_keys

            cache_key = "scan_20_5.0_500.0_500000"
            _scan_cache[cache_key] = (time.time(), results)
            logger.info("Background refresh complete: %d results cached", len(results))
        except Exception as e:
            logger.warning("Background refresh failed: %s", e)

        _stop_event.wait(_REFRESH_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background refresh thread
    thread = threading.Thread(target=_refresh_loop, daemon=True)
    thread.start()
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
