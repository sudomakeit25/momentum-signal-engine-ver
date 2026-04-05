"""Thread-safe token-bucket rate limiter for external API calls."""

import threading
import time


class RateLimiter:
    """Token-bucket rate limiter.

    Example: RateLimiter(5, 60) allows 5 calls per 60 seconds.
    """

    def __init__(self, max_calls: int, period_seconds: float) -> None:
        self._max_calls = max_calls
        self._period = period_seconds
        self._calls: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until a call is allowed."""
        while True:
            with self._lock:
                now = time.time()
                self._calls = [t for t in self._calls if now - t < self._period]
                if len(self._calls) < self._max_calls:
                    self._calls.append(now)
                    return
            time.sleep(0.5)

    def try_acquire(self) -> bool:
        """Non-blocking: return True if allowed, False otherwise."""
        with self._lock:
            now = time.time()
            self._calls = [t for t in self._calls if now - t < self._period]
            if len(self._calls) < self._max_calls:
                self._calls.append(now)
                return True
            return False
