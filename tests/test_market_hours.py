"""Tests for the intraday-loop market-hours gate.

The gate must stay correct across DST transitions. The previous
implementation hardcoded a UTC-4 offset, which silently broke the gate
once US DST ended in early November.
"""

from datetime import datetime, timezone

from src.main import _is_market_hours_et


def _utc(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# --- EDT (March-November, UTC-4) ---

def test_edt_open_window_start():
    # 13:35 UTC on a weekday in April == 09:35 EDT — gate opens.
    assert _is_market_hours_et(_utc(2026, 4, 23, 13, 35)) is True


def test_edt_open_window_end():
    # 19:45 UTC == 15:45 EDT — last bar of the gated window.
    assert _is_market_hours_et(_utc(2026, 4, 23, 19, 45)) is True


def test_edt_pre_open_blocked():
    # 13:30 UTC == 09:30 EDT — before our 9:35 grace period.
    assert _is_market_hours_et(_utc(2026, 4, 23, 13, 30)) is False


def test_edt_post_close_blocked():
    # 19:46 UTC == 15:46 EDT — past the 15:45 cutoff.
    assert _is_market_hours_et(_utc(2026, 4, 23, 19, 46)) is False


# --- EST (November-March, UTC-5) ---
# These are the cases the old timedelta(hours=4) implementation got wrong.

def test_est_open_window_start():
    # 14:35 UTC on Mon Nov 2 2026 == 09:35 EST — gate must open.
    assert _is_market_hours_et(_utc(2026, 11, 2, 14, 35)) is True


def test_est_open_window_end():
    # 20:45 UTC == 15:45 EST — last bar of the gated window.
    assert _is_market_hours_et(_utc(2026, 11, 2, 20, 45)) is True


def test_est_pre_open_blocked():
    # 13:30 UTC == 08:30 EST — pre-open.
    assert _is_market_hours_et(_utc(2026, 11, 2, 13, 30)) is False


def test_est_overnight_blocked():
    # 02:00 UTC == 21:00 prev-day EST — overnight, gate closed.
    assert _is_market_hours_et(_utc(2026, 11, 3, 2, 0)) is False


# --- Weekends ---

def test_saturday_blocked_in_window():
    # 14:35 UTC on Sat Apr 25 2026 — the time-of-day matches the open
    # window, but it's a weekend; the gate must stay closed.
    assert _is_market_hours_et(_utc(2026, 4, 25, 14, 35)) is False


def test_sunday_blocked_in_window():
    assert _is_market_hours_et(_utc(2026, 4, 26, 14, 35)) is False
