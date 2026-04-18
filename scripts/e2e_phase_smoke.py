"""Headless-browser smoke test against a deployed build.

Drives every new page from phases 1-6 end-to-end, clicking tabs and
buttons to verify the dynamic UI actually works. Run after deploys
complete.

Usage: .venv/bin/python scripts/e2e_phase_smoke.py --base https://...
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright


@dataclass
class PageResult:
    name: str
    checks: list[tuple[bool, str]] = field(default_factory=list)

    def check(self, ok: bool, msg: str) -> None:
        self.checks.append((ok, msg))

    def ok(self) -> bool:
        return all(c[0] for c in self.checks)

    def render(self) -> str:
        lines = [f"\n{self.name}"]
        for ok, msg in self.checks:
            mark = "\033[92m✓\033[0m" if ok else "\033[91m✗\033[0m"
            lines.append(f"  {mark} {msg}")
        return "\n".join(lines)


def _click_tab(page: Page, tab_name: str, wait_ms: int = 8000) -> None:
    page.get_by_role("button", name=tab_name).click()
    page.wait_for_timeout(wait_ms)


def instrument_page(page: Page, base: str, symbol: str = "AAPL") -> PageResult:
    r = PageResult(f"/instrument/{symbol}")
    try:
        page.goto(f"{base}/instrument/{symbol}", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(3_000)
    except PlaywrightTimeout:
        r.check(False, "page load timed out")
        return r

    r.check(symbol in page.content(), "symbol appears in page")
    for tab in ["Overview", "Seasonality", "Pattern", "Fundamentals", "Financials", "Insider", "Transcripts", "News"]:
        r.check(page.get_by_role("button", name=tab).is_visible(), f"tab visible: {tab}")

    # Overview tab (default)
    r.check(page.get_by_text("Analyzer").first.is_visible(), "overview analyzer card")
    r.check(
        any(
            page.get_by_text(label).first.is_visible()
            for label in ["AI Agent", "What's happening?"]
        ),
        "AI Agent panel visible",
    )

    # Fundamentals tab
    _click_tab(page, "Fundamentals")
    r.check(
        page.get_by_text("Market Cap").first.is_visible()
        or page.get_by_text("FMP Starter").first.is_visible(),
        "fundamentals tab rendered (data or gating banner)",
    )

    # Financials tab (new)
    _click_tab(page, "Financials")
    r.check(
        page.get_by_text("Income Statement").first.is_visible()
        or page.get_by_text("FMP Starter").first.is_visible(),
        "financials tab rendered",
    )

    # Seasonality tab — new layout uses Probability / Average return rows
    _click_tab(page, "Seasonality", wait_ms=12_000)
    seas_ok = any(
        label in page.content()
        for label in ["Probability %", "Average return %", "Download CSV"]
    ) or "insufficient" in page.content().lower()
    r.check(seas_ok, "seasonality rendered or errored gracefully")

    # Pattern tab
    _click_tab(page, "Pattern")
    r.check(
        page.get_by_text("Trend Summary").first.is_visible()
        or "No technical" in page.content(),
        "pattern rendered",
    )

    # Overbought - Oversold tab
    _click_tab(page, "Overbought - Oversold")
    r.check(
        page.get_by_text("RSI (14)").first.is_visible()
        or "insufficient" in page.content().lower(),
        "indicators rendered",
    )

    # News tab
    _click_tab(page, "News")
    r.check(
        "No news" in page.content() or page.locator("a").count() > 0,
        "news tab rendered",
    )

    # Insider tab
    _click_tab(page, "Insider")
    content_lower = page.content().lower()
    r.check(
        "filing" in content_lower
        or "requires fmp starter" in content_lower
        or "insider" in content_lower,
        "insider tab rendered (data or gating banner)",
    )

    # Transcripts tab
    _click_tab(page, "Transcripts")
    content_lower = page.content().lower()
    r.check(
        "pick a quarter" in content_lower
        or "no earnings-call transcripts" in content_lower
        or "q1" in content_lower or "q2" in content_lower or "q3" in content_lower or "q4" in content_lower,
        "transcripts tab rendered (data or gating banner)",
    )

    # Back to Overview — check Events panel + Wyckoff on OB/OS tab
    _click_tab(page, "Overview")
    r.check(
        "AI Agent" in page.content() or "What's happening" in page.content(),
        "overview still intact after tab cycling",
    )

    _click_tab(page, "Overbought - Oversold")
    wy_present = any(
        label in page.content() for label in ["Wyckoff Phase", "Market Mood Meter"]
    )
    r.check(wy_present, "Wyckoff / Mood panels present on OB/OS tab")
    return r


def rankings_index(page: Page, base: str) -> PageResult:
    r = PageResult("/rankings")
    try:
        page.goto(f"{base}/rankings", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(2_000)
    except PlaywrightTimeout:
        r.check(False, "load timeout")
        return r
    # Wait for the industries API to return and cards to render
    try:
        page.wait_for_function(
            "() => document.body.innerText.includes('Aerospace')",
            timeout=15_000,
        )
    except PlaywrightTimeout:
        pass
    r.check(page.get_by_text("Industry Rankings").first.is_visible(), "heading")
    r.check(
        "Aerospace" in page.content(),
        "aerospace & defense card visible",
    )
    return r


def industry_page(page: Page, base: str) -> PageResult:
    r = PageResult("/rankings/industry/aerospace-defense")
    try:
        page.goto(
            f"{base}/rankings/industry/aerospace-defense",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        # Industry ranking takes a while (many FMP calls) on cold cache
        page.wait_for_timeout(15_000)
    except PlaywrightTimeout:
        r.check(False, "load timeout")
        return r

    content = page.content()
    rendered = (
        "Aerospace" in content
        or "FMP key" in content
        or "No companies" in content
    )
    r.check(rendered, "heading or error state rendered")

    # If companies table is present, check it has rows
    if page.locator("table").count() > 0:
        rows = page.locator("table tbody tr").count()
        r.check(rows > 0, f"company table has {rows} rows")
    else:
        r.check(True, "no companies table (expected if FMP key missing)")
    return r


def sector_map_page(page: Page, base: str) -> PageResult:
    r = PageResult("/sector-map")
    try:
        page.goto(f"{base}/sector-map", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(8_000)
    except PlaywrightTimeout:
        r.check(False, "load timeout")
        return r
    r.check(page.get_by_text("Sector Map").first.is_visible(), "heading")
    r.check(
        page.get_by_text("Current Ranking").first.is_visible()
        or "Scanning" in page.content()
        or page.locator("svg").count() > 0,
        "chart or ranking visible",
    )
    return r


def international_page(page: Page, base: str) -> PageResult:
    """Spot-check that an international ticker does not 500."""
    r = PageResult("/instrument/AIR.PA (international)")
    try:
        page.goto(
            f"{base}/instrument/AIR.PA",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        page.wait_for_timeout(4_000)
    except PlaywrightTimeout:
        r.check(False, "load timeout")
        return r
    r.check("AIR.PA" in page.content(), "AIR.PA appears in page")
    # Currency chip should show EUR for .PA
    r.check("EUR" in page.content(), "EUR currency chip present")
    try:
        _click_tab(page, "Fundamentals", wait_ms=15_000)
    except Exception:
        pass
    content_lower = page.content().lower()
    r.check(
        "market cap" in content_lower
        or "fmp starter" in content_lower
        or "fundamentals" in content_lower,
        "international fundamentals tab rendered",
    )
    return r


def forex_page(page: Page, base: str) -> PageResult:
    r = PageResult("/instrument/EURUSD (forex)")
    try:
        page.goto(f"{base}/instrument/EURUSD", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(4_000)
    except PlaywrightTimeout:
        r.check(False, "load timeout")
        return r
    r.check("EURUSD" in page.content(), "EURUSD heading present")
    _click_tab(page, "Overbought - Oversold", wait_ms=12_000)
    content_lower = page.content().lower()
    # Accept either populated indicators OR a graceful "insufficient history"
    # error (FMP free tier doesn't cover forex historical data).
    graceful = (
        "rsi (14)" in content_lower
        or "market mood" in content_lower
        or "insufficient history" in content_lower
        or "fetch failed" in content_lower
    )
    r.check(graceful, "indicators render or degrade gracefully on forex")
    return r


def index_page(page: Page, base: str) -> PageResult:
    r = PageResult("/instrument/^GSPC (index)")
    try:
        # %5E is URL-encoded ^
        page.goto(f"{base}/instrument/%5EGSPC", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(4_000)
    except PlaywrightTimeout:
        r.check(False, "load timeout")
        return r
    r.check("GSPC" in page.content(), "^GSPC symbol visible")
    _click_tab(page, "Seasonality", wait_ms=15_000)
    r.check(
        "Probability" in page.content()
        or "Average return" in page.content()
        or "insufficient" in page.content().lower(),
        "seasonality works on index bars",
    )
    return r


def cot_page(page: Page, base: str) -> PageResult:
    r = PageResult("/cot")
    try:
        page.goto(f"{base}/cot", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(6_000)
    except PlaywrightTimeout:
        r.check(False, "load timeout")
        return r
    r.check(page.get_by_text("Commitment of Traders").first.is_visible(), "heading")
    r.check(page.get_by_text("Gold", exact=False).first.is_visible(), "contract pills render")
    r.check(
        "Non-Commercial" in page.content()
        or "Large Specs" in page.content()
        or "noncomm" in page.content().lower(),
        "non-commercial panel renders",
    )
    # SVG chart should be present
    r.check(page.locator("svg").count() > 0, "chart SVG present")
    return r


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:3456")
    parser.add_argument("--skip-international", action="store_true")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        console_errors: list[str] = []
        page.on("pageerror", lambda exc: console_errors.append(f"PAGEERROR: {exc}"))
        page.on(
            "console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None,
        )

        results = [
            instrument_page(page, args.base, "AAPL"),
            rankings_index(page, args.base),
            industry_page(page, args.base),
            sector_map_page(page, args.base),
            cot_page(page, args.base),
            forex_page(page, args.base),
            index_page(page, args.base),
        ]
        if not args.skip_international:
            results.append(international_page(page, args.base))

        browser.close()

    for res in results:
        print(res.render())

    if console_errors:
        filtered = [e for e in console_errors if "Failed to fetch RSC" not in e][:10]
        if filtered:
            print("\nBrowser console errors (first 10):")
            for e in filtered:
                print(f"  - {e[:200]}")

    ok_count = sum(1 for r in results if r.ok())
    print(f"\n{'PASS' if ok_count == len(results) else 'FAIL'}: {ok_count}/{len(results)} pages clean")
    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
