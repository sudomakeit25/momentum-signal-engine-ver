import logging
import os
import threading
import time

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from src import heavy
from src.api.routes import router, _scan_cache, _SCAN_CACHE_TTL

# Before any background thread starts: make the allocator return freed memory
# (see src/heavy.py; the host has 512 MB and kept running out).
_ALLOCATOR = heavy.configure_allocator()

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


def _is_market_hours_et(now_utc: "datetime | None" = None) -> bool:
    """True between 9:35 ET and 15:45 ET on weekdays.

    Skips the first 5 min after open (huge gaps look like Vs) and the
    last 15 min before close (close-out volatility distorts the window).

    Uses zoneinfo so the gate stays correct across DST transitions. The
    `now_utc` argument is for tests; production calls leave it None.
    """
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    et = now_utc.astimezone(ZoneInfo("America/New_York"))
    if et.weekday() >= 5:
        return False
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

            # Refresh Alpaca bar data and run the scan, one heavy step at a
            # time (src/heavy.py) so peaks do not stack past the host's memory.
            # top_n covers all symbols so every qualifying signal can dispatch;
            # max_price lifted so high-priced names like AVGO aren't excluded.
            with heavy.heavy("daily scan"):
                client.get_bars("SPY", days=200)
                bars_map = client.get_multi_bars(symbols, days=200)
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
                        "Auto-dispatch result: telegram=%s, webhook=%s, sms=%s",
                        dispatch_results.get("telegram"),
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
                warmed = 0 if heavy.should_skip("profile warmup") else heavy.run(
                    "profile warmup", warm_cache)
                if warmed:
                    logger.info("Profile screener cache warmed: %d rows", warmed)
            except Exception as e:
                logger.debug("Profile screener warmup failed: %s", e)

            # Cyclical / mean-reversion scan, hourly. Two parallel scans
            # at different time horizons, merged into one cache:
            #   FAST: hourly bars / 7 days, on watchlist + top 300 by
            #         momentum score. Catches active oscillators like
            #         CLSK, RIVN.
            #   SLOW: daily bars / 60 days, on a curated list of sector
            #         ETFs, utilities, staples, REITs, bond proxies.
            #         These rarely show up in momentum scans but
            #         oscillate cleanly on the larger timeframe.
            # Same detector + thresholds — only the bar timeframe and
            # lookback differ.
            try:
                prev = _scan_cache.get("cyclicals")
                stale = (not prev) or (time.time() - prev[0] >= 60 * 60)
                if stale and not heavy.should_skip("cyclical scan"):
                    from src.scanner.cyclical import scan_cyclicals, CYCLICAL_CANDIDATES_EXTRA
                    from src.data.redis_store import get_watchlist
                    from alpaca.data.timeframe import TimeFrame as _TF

                    top_by_score = sorted(
                        results, key=lambda r: r.score or 0, reverse=True
                    )[:300]
                    fast_universe = list(
                        {s for s in (get_watchlist() or [])}
                        | {r.symbol for r in top_by_score}
                    )

                    cyc_fast = []
                    if fast_universe:
                        cyc_fast = heavy.run("cyclical scan", scan_cyclicals, fast_universe)
                        logger.info(
                            "Cyclical fast scan: %d cyclicals from %d symbols",
                            len(cyc_fast), len(fast_universe),
                        )

                    cyc_slow = heavy.run(
                        "cyclical scan (daily)", scan_cyclicals,
                        list(CYCLICAL_CANDIDATES_EXTRA),
                        timeframe=_TF.Day,
                        lookback_days=60,
                    )
                    logger.info(
                        "Cyclical slow scan: %d cyclicals from %d symbols",
                        len(cyc_slow), len(CYCLICAL_CANDIDATES_EXTRA),
                    )

                    # Dedup by symbol — fast wins on conflict (more
                    # actionable, shorter horizon).
                    seen = {c.symbol for c in cyc_fast}
                    merged = list(cyc_fast) + [c for c in cyc_slow if c.symbol not in seen]
                    merged.sort(key=lambda c: c.cyclical_score, reverse=True)
                    _scan_cache["cyclicals"] = (
                        time.time(),
                        [c.to_dict() for c in merged],
                    )
                    logger.info(
                        "Cyclical merged: %d total (%d fast + %d slow)",
                        len(merged), len(cyc_fast), len(cyc_slow),
                    )
            except Exception as e:
                logger.warning("Cyclical scan failed: %s", e)

            # Warm the short-squeeze scan so the web/mobile widgets get an
            # instant cache hit. scan_short_squeeze has its own internal
            # file cache, so this is cheap once warm (it recomputes only
            # after that cache's TTL expires).
            try:
                from src.scanner.advanced_signals import scan_short_squeeze
                if not heavy.should_skip("short squeeze"):
                    squeeze = heavy.run("short squeeze", scan_short_squeeze)
                    logger.info("Short squeeze scan: %d candidates", len(squeeze))
            except Exception as e:
                logger.warning("Short squeeze scan failed: %s", e)

            # Warm the catalyst watch too: uncached it takes about half a
            # minute, too long for a page load. It keeps its own 30-minute
            # cache, so most cycles this returns immediately.
            try:
                from src.scanner.catalyst_watch import scan_catalyst_watch
                if not heavy.should_skip("catalyst watch"):
                    watch = heavy.run("catalyst watch", scan_catalyst_watch)
                    logger.info(
                        "Catalyst watch: %d upcoming, %d reacting",
                        len(watch["upcoming"]), len(watch["reacting"]),
                    )
            except Exception as e:
                logger.warning("Catalyst watch scan failed: %s", e)

            # Pre-market gap list: keep it warm, and from 9:00 ET log the gaps
            # to the scorecard so we learn whether such gaps continue or fade.
            try:
                from datetime import datetime as _dt
                from src.scanner import premarket, scorecard as _sc
                et_now = _dt.now(tz=premarket.ET)
                if et_now.weekday() < 5 and premarket.PRE_OPEN <= et_now.time() < premarket.CLOSE:
                    gaps = heavy.run("pre-market gaps", premarket.scan_premarket_gaps)
                    if et_now.hour >= 9 and gaps.get("gaps"):
                        _score(_sc, premarket.scorecard_alerts(gaps))
            except Exception as e:
                logger.warning("Pre-market scan failed: %s", e)

            # Fill in what happened after each logged alert (throttled inside).
            try:
                from src.scanner import scorecard
                updated = 0 if heavy.should_skip("scorecard outcomes") else heavy.run(
                    "scorecard outcomes", scorecard.refresh_outcomes)
                if updated:
                    logger.info("Scorecard: %d outcomes updated", updated)
            except Exception as e:
                logger.warning("Scorecard refresh failed: %s", e)
        except Exception as e:
            logger.warning("Background refresh failed: %s", e)

        _stop_event.wait(_REFRESH_INTERVAL)


def _warm_profile_cache_on_startup() -> None:
    try:
        from src.scanner.profile_screener import warm_cache
        if heavy.should_skip("startup profile warmup"):
            return
        rows = heavy.run("startup profile warmup", warm_cache)
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
    from src.scanner.intraday_movers import scan_intraday as scan_intraday_movers
    from src.scanner import scorecard, spike_reversal
    from src.trading import auto_trader
    from src.notifications.dispatcher import (
        alert_label,
        dispatch_alerts,
        dispatch_intraday_patterns,
        dispatch_intraday_watches,
        retry_failed_telegram,
    )
    from datetime import datetime

    seen_keys, seen_date = load_intraday_seen()
    logger.info(
        "Intraday loop boot: %d seen keys (date=%s)",
        len(seen_keys), seen_date or "none",
    )

    while not _stop_event.is_set():
        try:
            # Resend Telegram alerts that failed earlier (the loops mark alerts
            # seen whether or not they were delivered). Runs outside market
            # hours too, because the refresh loop's alerts can fire any time.
            retry_failed_telegram()

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

            # Everything this loop sends is built from bars that may be behind
            # the market (15 minutes on the free data plan). Measure it once
            # per cycle and put it in the header of every alert.
            try:
                from src.data import freshness
                delay_suffix = freshness.label()
            except Exception:
                delay_suffix = ""

            symbols = _intraday_universe(top_n=100)
            if not symbols:
                logger.debug("Intraday loop: empty universe, skipping cycle")
                _stop_event.wait(_INTRADAY_INTERVAL)
                continue

            patterns = heavy.run("intraday patterns", scan_intraday_patterns, symbols)
            logger.info(
                "Intraday scan: %d patterns from %d symbols",
                len(patterns), len(symbols),
            )

            # Cache the full batch for the REST endpoint so the mobile
            # Reversals card always has data, even if every pattern was
            # already seen and not re-dispatched.
            save_intraday_latest([p.to_dict() for p in patterns])
            _score(scorecard, [
                {"symbol": p.symbol, "kind": p.pattern_type,
                 "direction": _pattern_direction(p.pattern_type), "price": p.trigger_price}
                for p in patterns
            ])

            new_patterns = [
                p for p in patterns
                if f"{p.symbol}:{p.pattern_type}" not in seen_keys
            ]
            if new_patterns:
                logger.info("Dispatching %d new intraday patterns", len(new_patterns))
                try:
                    with alert_label(delay_suffix):
                        result = dispatch_intraday_patterns(new_patterns)
                    logger.info(
                        "Intraday dispatch result: telegram=%s sms=%s push=%s",
                        result.get("telegram"), result.get("sms"), result.get("push"),
                    )
                except Exception as e:
                    logger.warning("Intraday dispatch failed: %s", e)

            # Mark all current patterns as seen for this session, so a
            # restart mid-day doesn't re-fire them.
            seen_keys.update(f"{p.symbol}:{p.pattern_type}" for p in patterns)
            save_intraday_seen(seen_keys, seen_date)

            # --- Intraday movers screen (0.5-1% scalp framework) ---
            # Risk-managed setups (range break / VWAP reclaim-reject /
            # higher low) with entry/stop/target. Shares this loop's
            # cadence and Redis seen-state; "M:"-prefixed keys keep its
            # dedup grain (symbol+setup+direction per day) separate from
            # the pattern keys above.
            try:
                movers = heavy.run("intraday movers", scan_intraday_movers, symbols=symbols)
                mover_signals = [s for r in movers for s in r.signals]
                new_setups = [
                    s for s in mover_signals
                    if f"M:{s.symbol}:{s.setup_type.value}:{s.action.value}"
                    not in seen_keys
                ]
                logger.info(
                    "Intraday movers: %d rows, %d setups (%d new)",
                    len(movers), len(mover_signals), len(new_setups),
                )
                _score(scorecard, [scorecard.from_signal(s) for s in mover_signals])
                if new_setups:
                    # Paper auto-trader first (the quote is freshest now).
                    # No-op unless AUTO_TRADE_ENABLED is set and not paused.
                    try:
                        records = auto_trader.handle_new_setups(
                            new_setups, {r.symbol: r for r in movers}
                        )
                        placed = [r for r in records if r.get("type") == "trade"]
                        if records:
                            logger.info(
                                "Auto-trader: %d orders placed, %d setups skipped",
                                len(placed), len(records) - len(placed),
                            )
                    except Exception as e:
                        logger.warning("Auto-trader failed: %s", e)
                    try:
                        with alert_label(delay_suffix):
                            result = dispatch_alerts(new_setups)
                        logger.info(
                            "Movers dispatch result: telegram=%s webhook=%s sms=%s",
                            result.get("telegram"), result.get("webhook"), result.get("sms"),
                        )
                    except Exception as e:
                        logger.warning("Movers dispatch failed: %s", e)
                seen_keys.update(
                    f"M:{s.symbol}:{s.setup_type.value}:{s.action.value}"
                    for s in mover_signals
                )

                # Forming setups (box intact, VWAP tag): alert once per
                # symbol+type per day, before the trigger, with levels.
                mover_watches = [w for r in movers for w in r.watches]
                new_watches = [
                    w for w in mover_watches
                    if f"W:{w.symbol}:{w.watch_type}" not in seen_keys
                ]
                if new_watches:
                    logger.info("Dispatching %d new setup watches", len(new_watches))
                    try:
                        with alert_label(delay_suffix):
                            result = dispatch_intraday_watches(new_watches)
                        logger.info(
                            "Watch dispatch result: telegram=%s sms=%s push=%s",
                            result.get("telegram"), result.get("sms"), result.get("push"),
                        )
                    except Exception as e:
                        logger.warning("Watch dispatch failed: %s", e)
                seen_keys.update(
                    f"W:{w.symbol}:{w.watch_type}" for w in mover_watches
                )
                save_intraday_seen(seen_keys, seen_date)
            except Exception as e:
                logger.warning("Intraday movers screen failed: %s", e)

            # --- Spikes and reversals: measured, not alerted ---
            # These detectors are new and unproven. They are shown on the
            # Spike Watch page and logged to the scorecard; no SMS until
            # the scorecard shows which of them are worth one.
            try:
                watch_universe = list(dict.fromkeys(
                    symbols + spike_reversal.default_universe()
                ))
                # Usual-volume profile: about 15 sessions of 5-minute bars,
                # built once a day a few symbols at a time and saved, so it is
                # limited to the active intraday universe. Spike Watch sends
                # no alerts, so it is the first thing dropped when memory is high.
                if not heavy.should_skip("spike watch"):
                    heavy.run("volume profile", spike_reversal.ensure_volume_profile, symbols)
                    spikes = heavy.run("spike watch", spike_reversal.scan_spikes_reversals,
                                       watch_universe)
                    _score(scorecard, spikes["events"])
                    logger.info("Spike watch: %d events", len(spikes["events"]))
            except Exception as e:
                logger.warning("Spike watch failed: %s", e)
        except Exception as e:
            logger.warning("Intraday loop iteration failed: %s", e)

        _stop_event.wait(_INTRADAY_INTERVAL)


def _pattern_direction(pattern_type: str) -> str:
    """Which way an intraday pattern points, for the scorecard."""
    return "down" if pattern_type in ("inverted_v", "breakdown") else "up"


def _score(scorecard, alerts: list[dict]) -> None:
    """Log alerts to the scorecard. Measurement must never break a scan."""
    try:
        added = scorecard.log_alerts(alerts)
        if added:
            logger.info("Scorecard: %d new alerts logged", added)
    except Exception as e:
        logger.warning("Scorecard logging failed: %s", e)


def _auto_trade_guard_loop():
    """Closes the auto-trader's own positions before the bell.

    Separate from the 5-minute scan loop on purpose: the close has a short
    window, and a slow scan must not be able to miss it. Ticks every 30
    seconds whether or not the master switch is on, so a position opened
    before the bot was switched off is still closed, and a failed attempt is
    retried within seconds. `maybe_flatten` makes no broker call outside
    session hours and only a clock call away from the close.
    """
    from src.trading import auto_trader

    while not _stop_event.is_set():
        try:
            closed = auto_trader.maybe_flatten()
            if closed:
                logger.info("Auto-trader closing: %s", closed)
        except Exception as e:
            logger.warning("Auto-trader guard failed: %s", e)
        _stop_event.wait(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background refresh thread
    thread = threading.Thread(target=_refresh_loop, daemon=True)
    thread.start()
    # Intraday-pattern scan thread (5-min cadence, market hours only)
    threading.Thread(target=_intraday_scan_loop, daemon=True).start()
    # Auto-trader end-of-day close (30s cadence, no-op unless it owns positions)
    threading.Thread(target=_auto_trade_guard_loop, daemon=True).start()
    # Warm the yfinance cache in a separate thread so startup is not blocked
    threading.Thread(target=_warm_profile_cache_on_startup, daemon=True).start()
    # Keep a sleep-when-idle host awake through the trading day (no-op locally)
    from src import keepalive
    threading.Thread(target=keepalive.run, args=(_stop_event,), daemon=True).start()
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
