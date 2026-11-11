"""One memory-heavy background job at a time, and memory readings for the logs.

The free host gives the whole app 512 MB. Each scan fits on its own, but the
background loops ran them in parallel and their peaks stacked past the limit:
Render killed the process with "Ran out of memory (used over 512MB)" a dozen
times on 2026-11-11. The loops now run every heavy step through `run()`, which
lets only one run at a time and logs memory afterwards, and they ask
`should_skip()` before optional steps (Spike Watch, warm-ups), so that when
memory is already high the steps that send alerts and trade still run.
"""

from __future__ import annotations

import contextlib
import ctypes
import gc
import logging
import os
import resource
import sys
import threading
import time

logger = logging.getLogger("mse.memory")

LIMIT_MB = 512
SKIP_OPTIONAL_ABOVE_MB = 360   # leaves room for one step's peak under the limit
WAIT_LIMIT = 300               # seconds; a step never waits longer than this for another

_lock = threading.RLock()
_state_lock = threading.Lock()
_state: dict = {"steps": {}, "skipped": {}, "waited_out": 0, "allocator": {}}

# glibc mallopt parameters
_M_TRIM_THRESHOLD = -1
_M_MMAP_THRESHOLD = -3
_M_ARENA_MAX = -8
_ALLOCATOR = (("arena_max", _M_ARENA_MAX, 2),
              ("mmap_threshold", _M_MMAP_THRESHOLD, 128 * 1024),
              ("trim_threshold", _M_TRIM_THRESHOLD, 128 * 1024))


def configure_allocator() -> dict:
    """Make the Linux allocator hand freed memory back to the system.

    Measured on 2026-11-11: after a full cycle the program itself held only
    about 15 MB more than at start, yet the host reported 363 MB in use, up
    from 186 MB. The difference was freed memory the allocator kept. glibc
    gives each busy thread its own arena (the scans use thread pools), and it
    raises its mmap threshold after large frees, so big pandas arrays end up
    in arenas that are never returned. Two arenas and a fixed 128 KB mmap
    threshold keep large blocks returnable. Call before the background
    threads start; a no-op off Linux. Returns what was applied.
    """
    applied: dict = {}
    if sys.platform.startswith("linux"):
        try:
            libc = ctypes.CDLL("libc.so.6")
            for name, param, value in _ALLOCATOR:
                applied[name] = bool(libc.mallopt(param, value))
        except Exception as e:
            logger.warning("Memory: allocator settings not applied: %s", e)
    with _state_lock:
        _state["allocator"] = dict(applied)
    return applied


def rss_mb() -> float | None:
    """Memory the process holds right now, in MB. None where it cannot be read
    cheaply (it is read from /proc, which exists on the Linux host)."""
    try:
        with open("/proc/self/statm") as f:
            pages = int(f.read().split()[1])
        return round(pages * os.sysconf("SC_PAGE_SIZE") / 1024 / 1024, 1)
    except Exception:
        return None


def peak_mb() -> float:
    """Highest memory the process has held since it started, in MB."""
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / 1024 / 1024 if sys.platform == "darwin" else r / 1024, 1)


def release() -> None:
    """Free what can be freed and, on Linux, hand it back to the system so
    the next step starts from a lower base."""
    gc.collect()
    if sys.platform.startswith("linux"):
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass


@contextlib.contextmanager
def heavy(name: str):
    """Run a memory-heavy step while no other heavy step runs. A step that
    has waited WAIT_LIMIT seconds runs anyway (a hung request elsewhere must
    not stop alerts for the rest of the day), and says so in the log."""
    got = _lock.acquire(timeout=WAIT_LIMIT)
    if not got:
        with _state_lock:
            _state["waited_out"] += 1
        logger.warning("Memory: %s waited %ds for another step; running anyway", name, WAIT_LIMIT)
    before = rss_mb()
    started = time.time()
    try:
        yield
    finally:
        try:
            release()
            after = rss_mb()
            took = time.time() - started
            with _state_lock:
                _state["steps"][name] = {"seconds": round(took, 1), "mb_before": before,
                                         "mb_after": after, "at": round(time.time())}
            logger.info("Memory: %s took %.0fs, %s MB now, peak %.0f MB", name, took,
                        f"{after:.0f}" if after is not None else "?", peak_mb())
        finally:
            if got:
                _lock.release()


def run(name: str, fn, *args, **kwargs):
    """Call `fn` as a heavy step and return its result."""
    with heavy(name):
        return fn(*args, **kwargs)


def should_skip(name: str) -> bool:
    """True when an optional step should not run now: memory is above
    SKIP_OPTIONAL_ABOVE_MB even after freeing what can be freed. Always False
    where memory cannot be read."""
    now = rss_mb()
    if now is None or now <= SKIP_OPTIONAL_ABOVE_MB:
        return False
    release()
    now = rss_mb()
    if now is None or now <= SKIP_OPTIONAL_ABOVE_MB:
        return False
    with _state_lock:
        _state["skipped"][name] = _state["skipped"].get(name, 0) + 1
    logger.warning("Memory: skipped %s, %.0f MB already in use (limit %d MB)", name, now, LIMIT_MB)
    return True


def status() -> dict:
    with _state_lock:
        steps = {k: dict(v) for k, v in _state["steps"].items()}
        skipped = dict(_state["skipped"])
        waited_out = _state["waited_out"]
        allocator = dict(_state["allocator"])
    return {
        "allocator": allocator,
        "rss_mb": rss_mb(),
        "peak_mb": peak_mb(),
        "limit_mb": LIMIT_MB,
        "skip_optional_above_mb": SKIP_OPTIONAL_ABOVE_MB,
        "steps": steps,
        "skipped": skipped,
        "waited_out": waited_out,
    }
