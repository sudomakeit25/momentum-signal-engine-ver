"""Playwright smoke test for the 4 new pages.

Drives a headless browser against a locally running frontend to catch
bugs that static page loads don't — pill clicks, form submission, table
rendering, error states. Run after starting backend + frontend manually.

Usage:
    .venv/bin/python scripts/e2e_smoke.py [--base http://127.0.0.1:3456]
"""

from __future__ import annotations

import argparse
import sys

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

DEFAULT_BASE = "http://127.0.0.1:3456"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"


class Result:
    def __init__(self, name: str):
        self.name = name
        self.checks: list[tuple[bool, str]] = []

    def check(self, ok: bool, msg: str) -> None:
        self.checks.append((ok, msg))

    def ok(self) -> bool:
        return all(c[0] for c in self.checks)

    def render(self) -> str:
        lines = [f"\n{self.name}"]
        for ok, msg in self.checks:
            lines.append(f"  {PASS if ok else FAIL} {msg}")
        return "\n".join(lines)


def screener_presets_page(page: Page, base: str) -> Result:
    r = Result("/screener-presets")
    page.goto(f"{base}/screener-presets", wait_until="networkidle")
    r.check(page.get_by_text("Preset Screeners").first.is_visible(), "heading renders")

    # Click the "Momentum leaders" card
    card = page.get_by_text("Momentum leaders").first
    r.check(card.is_visible(), "momentum card visible")
    card.click()

    # Wait for table OR "no matches" message — scan takes a few seconds
    try:
        page.wait_for_function(
            "() => document.querySelector('table') || "
            "document.body.innerText.includes('No symbols match')",
            timeout=60_000,
        )
        has_table = page.locator("table").count() > 0
        r.check(has_table, "results table rendered after card click")
        if has_table:
            rows = page.locator("table tbody tr").count()
            r.check(rows > 0, f"table has {rows} result rows")
    except PlaywrightTimeout:
        r.check(False, "timeout waiting for results")
    return r


def analyzer_page(page: Page, base: str) -> Result:
    r = Result("/analyzer")
    page.goto(f"{base}/analyzer", wait_until="networkidle")
    r.check(page.get_by_text("Stock Analyzer").first.is_visible(), "heading renders")

    page.get_by_placeholder("Symbol (e.g. AAPL)").fill("AAPL")
    page.get_by_role("button", name="Analyze").click()

    try:
        # Verdict pill appears when report renders
        page.wait_for_selector("text=/strong buy|buy|hold|avoid/", timeout=60_000)
        r.check(True, "verdict pill rendered")
        r.check(page.get_by_text("Component Scores").is_visible(), "component scores panel visible")
        r.check(page.get_by_text("Strengths").is_visible(), "strengths panel visible")
    except PlaywrightTimeout:
        r.check(False, "timeout waiting for analyzer output")
    return r


def trends_page(page: Page, base: str) -> Result:
    r = Result("/trends")
    page.goto(f"{base}/trends", wait_until="networkidle")
    r.check(page.get_by_text("Multi-Year Trends").first.is_visible(), "heading renders")

    page.get_by_placeholder("Symbol (e.g. AAPL)").fill("AAPL")
    page.get_by_role("button", name="Analyze").click()

    try:
        page.wait_for_selector("text=/secular uptrend|secular downtrend|range bound|transitioning/",
                              timeout=60_000)
        r.check(True, "regime label rendered")
        r.check(page.get_by_text("Returns", exact=True).is_visible(), "returns card visible")
        r.check(page.get_by_text("CAGR", exact=True).is_visible(), "CAGR card visible")
    except PlaywrightTimeout:
        r.check(False, "timeout waiting for trends output")
    return r


def stock_screener_page(page: Page, base: str) -> Result:
    r = Result("/stock-screener")
    page.goto(f"{base}/stock-screener", wait_until="networkidle")
    r.check(page.get_by_text("Stock Screener").first.is_visible(), "heading renders")

    # Wait for profile pills to load (they come from an API call)
    try:
        page.wait_for_selector("text=Like MU (cheap semis)", timeout=15_000)
    except PlaywrightTimeout:
        r.check(False, "profile pills never appeared")
        return r

    # Click a different profile and verify sector input changes.
    # The effect that seeds filters runs post-paint, so wait for it.
    page.get_by_role("button", name="Healthcare value").click()
    sector_select = page.locator("select").first
    try:
        sector_select.wait_for(state="attached", timeout=2_000)
        page.wait_for_function(
            "() => document.querySelector('select')?.value === 'healthcare'",
            timeout=5_000,
        )
        r.check(True, "sector changed to healthcare after pill click")
    except PlaywrightTimeout:
        r.check(False, f"sector did not change (still {sector_select.input_value()!r})")

    # Back to Like MU and run the screen
    page.get_by_role("button", name="Like MU (cheap semis)").click()
    page.get_by_role("button", name="Screen").click()

    try:
        page.wait_for_function(
            "() => document.querySelector('table') || "
            "document.body.innerText.includes('No stocks match')",
            timeout=60_000,
        )
        has_table = page.locator("table").count() > 0
        r.check(has_table, "results table rendered")
        if has_table:
            rows = page.locator("table tbody tr").count()
            r.check(rows > 0, f"table has {rows} rows")
            r.check(page.get_by_text("MU").first.is_visible(), "MU ticker visible in results")
    except PlaywrightTimeout:
        r.check(False, "timeout waiting for screener results")
    return r


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE)
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        # Bubble up browser console errors
        console_errors: list[str] = []
        page.on("pageerror", lambda exc: console_errors.append(f"PAGE ERROR: {exc}"))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        results = [
            screener_presets_page(page, args.base),
            analyzer_page(page, args.base),
            trends_page(page, args.base),
            stock_screener_page(page, args.base),
        ]
        browser.close()

    for res in results:
        print(res.render())

    if console_errors:
        print("\nBrowser console errors:")
        for err in console_errors[:20]:
            print(f"  - {err}")

    all_ok = all(r.ok() for r in results)
    print(f"\n{'PASS' if all_ok else 'FAIL'}: {sum(r.ok() for r in results)}/{len(results)} pages clean")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
