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

# Stop our handler from propagating to root — otherwise basicConfig's root
# handler prints each mse.* record a second time and every line appears
# twice in Render logs.
logger.propagate = False
logging.getLogger("mse.notifications").propagate = False

# Yahoo Finance blocks cloud IPs with anti-bot challenges ("Invalid Crumb",
# "User is unable to access this feature"). The errors are harmless — the
# Stock Screener page degrades gracefully — but they flood the log. Silence
# them in production; locally these loggers stay at default.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("curl_cffi").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)

_REFRESH_INTERVAL = 600  # 10 min — dynamic universe is ~2k stocks, gives scan time to finish

# Intraday-pattern scan runs on its own faster cadence and only during
# regular US market hours. Universe is capped — see _intraday_universe().
_INTRADAY_INTERVAL = 300  # 5 min
_stop_event = threading.Event()


def _is_market_hours_et() -> bool:
    """True between 9:35 ET and 15:45 ET on weekdays.

    Skips the first 5 min after open (huge gaps look like Vs) and the
    last 15 min before close (close-out volatility distorts the window).
    Uses naive UTC math + offset rather than zoneinfo to avoid pulling
    in a hard dep — close enough for an intraday gate.
    """
    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    if now_utc.weekday() >= 5:
        return False
    # ET is UTC-4 in DST, UTC-5 outside. Approximate with -4 since we
    # only care about regular trading hours; the gate is by design soft.
    et = now_utc - timedelta(hours=4)
    minutes = et.hour * 60 + et.minute
    return 9 * 60 + 35 <= minutes <= 15 * 60 + 45


def _intraday_universe(top_n: int = 100) -> list[str]:
    """Universe for the intraday scan: watchlist + top movers from the
    most recent daily scan, deduped and capped."""
    from src.data.redis_store import get_watchlist
    universe: list[str] = []
    try:
        universe.extend(get_watchlist() or [])
    except Exception:
        pass
    cached = _scan_cache.get("scan_full")
    if cached:
        results = cached[1] or []
        # Sort by dollar volume, keep the top N.
        try:
            ranked = sorted(
                results,
                key=lambda r: (r.volume or 0) * (r.price or 0),
                reverse=True,
            )[:top_n]
            universe.extend(r.symbol for r in ranked)
        except Exception:
            pass
    # Dedupe preserving order so the watchlist appears first.
    seen = set()
    deduped = []
    for s in universe:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def signal_key(s) -> str:
    """Stable dedup key — symbol + action only.

    Price was dropped first because micro-drift re-fired the same alert.
    setup_type was dropped next: the generator emits the same symbol/action
    across multiple setup types (EMA_CROSSOVER, BREAKOUT, RSI_PULLBACK,
    VWAP_RECLAIM) on successive cycles as price drifts through trigger
    conditions, and the SMS body for each variant is identical to the
    user. A single BUY or SELL per symbol per day is the user-facing
    contract.
    """
    return f"{s.symbol}:{s.action.value}"


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

    from src.data.redis_store import load_seen_signals, save_seen_signals

    # Load persisted dedup state on boot so a Render restart doesn't mass-refire.
    _seen_signal_keys, _seen_date = load_seen_signals()
    logger.info(
        "Auto-dispatch boot: loaded %d seen keys (date=%s)",
        len(_seen_signal_keys), _seen_date or "none",
    )

    # `signal_key` is defined at module scope so it's importable by tests.

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

            current_keys = {signal_key(s) for s in all_signals}

            # Daily rollover: start a fresh seen-set BUT still seed with current
            # keys so the rollover itself doesn't re-fire every live signal.
            from datetime import datetime
            today_str = datetime.now().strftime("%Y-%m-%d")
            if today_str != _seen_date:
                logger.info(
                    "Daily rollover: clearing %d seen keys (was %s -> %s)",
                    len(_seen_signal_keys), _seen_date or "none", today_str,
                )
                _seen_signal_keys = set(current_keys)
                _seen_date = today_str
                save_seen_signals(_seen_signal_keys, _seen_date)
                new_signals = []  # do not re-fire on rollover
            elif not _seen_signal_keys:
                # Cold start with no persisted state: seed, don't re-fire.
                logger.info(
                    "Cold-start seed: recording %d current keys without dispatching",
                    len(current_keys),
                )
                _seen_signal_keys = set(current_keys)
                save_seen_signals(_seen_signal_keys, today_str)
                new_signals = []
            else:
                new_signals = [
                    s for s in all_signals if signal_key(s) not in _seen_signal_keys
                ]

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

            # Record every currently-live key as seen and persist, so the next
            # cycle's dedup sees them even after a restart mid-day.
            _seen_signal_keys.update(current_keys)
            save_seen_signals(_seen_signal_keys, today_str)

            # (The previous 'watchlist alerts' block here double-dispatched
            # the same signals that had just gone out in the main block above.
            # Removed — a watchlist symbol already fires through the main
            # dispatch when a new signal appears on it.)

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


def _intraday_scan_loop():
    """Faster scan loop dedicated to intraday-pattern detection.

    Runs every 5 minutes, but only during regular US market hours so
    we never burn Alpaca rate limit pre-market or overnight. Each cycle:
      1. Build a small universe (watchlist + top 100 dollar-volume names
         from the most recent daily scan).
      2. Run all three pattern detectors over 5-min bars.
      3. Skip patterns already seen in this trading session.
      4. Dispatch new patterns through the intraday-specific dispatcher
         (separate dedup grain from the daily Signal flow).
      5. Cache the latest detection batch for the REST endpoint.
    """
    from src.data.redis_store import (
        load_intraday_seen,
        save_intraday_seen,
        save_intraday_latest,
    )
    from src.scanner.intraday_patterns import scan_intraday_patterns
    from src.notifications.dispatcher import dispatch_intraday_patterns
    from datetime import datetime

    seen_keys, seen_date = load_intraday_seen()
    logger.info(
        "Intraday loop boot: %d seen keys (date=%s)",
        len(seen_keys), seen_date or "none",
    )

    while not _stop_event.is_set():
        try:
            if not _is_market_hours_et():
                _stop_event.wait(_INTRADAY_INTERVAL)
                continue

            today_str = datetime.utcnow().strftime("%Y-%m-%d")
            if today_str != seen_date:
                logger.info(
                    "Intraday daily rollover: clearing %d seen keys (was %s -> %s)",
                    len(seen_keys), seen_date or "none", today_str,
                )
                seen_keys = set()
                seen_date = today_str
                save_intraday_seen(seen_keys, seen_date)

            symbols = _intraday_universe(top_n=100)
            if not symbols:
                logger.debug("Intraday loop: empty universe, skipping cycle")
                _stop_event.wait(_INTRADAY_INTERVAL)
                continue

            patterns = scan_intraday_patterns(symbols)
            logger.info(
                "Intraday scan: %d patterns from %d symbols",
                len(patterns), len(symbols),
            )

            # Cache the full batch for the REST endpoint so the mobile
            # Reversals card always has data, even if every pattern was
            # already seen and not re-dispatched.
            save_intraday_latest([p.to_dict() for p in patterns])

            new_patterns = [
                p for p in patterns
                if f"{p.symbol}:{p.pattern_type}" not in seen_keys
            ]
            if new_patterns:
                logger.info("Dispatching %d new intraday patterns", len(new_patterns))
                try:
                    result = dispatch_intraday_patterns(new_patterns)
                    logger.info(
                        "Intraday dispatch result: sms=%s push=%s",
                        result.get("sms"), result.get("push"),
                    )
                except Exception as e:
                    logger.warning("Intraday dispatch failed: %s", e)

            # Mark all current patterns as seen for this session, so a
            # restart mid-day doesn't re-fire them.
            seen_keys.update(f"{p.symbol}:{p.pattern_type}" for p in patterns)
            save_intraday_seen(seen_keys, seen_date)
        except Exception as e:
            logger.warning("Intraday loop iteration failed: %s", e)

        _stop_event.wait(_INTRADAY_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background refresh thread
    thread = threading.Thread(target=_refresh_loop, daemon=True)
    thread.start()
    # Intraday-pattern scan thread (5-min cadence, market hours only)
    threading.Thread(target=_intraday_scan_loop, daemon=True).start()
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
