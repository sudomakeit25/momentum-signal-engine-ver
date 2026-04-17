"""Parse pasted portfolio text into a list of holdings.

Accepts Robinhood-style text (ticker line + "N shares" line), CSV
("TICKER,SHARES"), or a plain list of tickers. Extracts tickers 1-5
chars A-Z and an optional share count.
"""

from __future__ import annotations

import re

_TICKER_RE = re.compile(r"\b([A-Z]{1,5}(?:\.[A-Z])?)\b")
_SHARES_RE = re.compile(
    r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*(?:shares?|sh\b)",
    re.IGNORECASE,
)

# Common noise that also matches the ticker regex
_BLACKLIST = {
    "USD", "ETF", "IRA", "NYSE", "NASDAQ", "AMEX", "LLC", "INC", "CORP",
    "CO", "LTD", "THE", "AND", "OR", "OF", "TO", "FOR", "AT", "IN", "ON",
    "BUY", "SELL", "HOLD", "GAIN", "LOSS", "YTD", "YTY", "MTD", "TOTAL",
    "CASH", "STOCK", "STOCKS", "SHARE", "SHARES", "DAY", "ALL", "AM", "PM",
    "TODAY", "ROI", "PNL", "PL", "DIV", "REIT", "EPS", "FTSE",
}


def _extract_shares(line: str) -> float | None:
    m = _SHARES_RE.search(line)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_portfolio_text(text: str) -> list[dict]:
    """Parse a pasted portfolio / watchlist blob.

    Handles same-line ("MU 900 shares") and multi-line layouts where the
    share count is on the line immediately after the ticker. Returns a
    list of {"symbol", "shares"?} dicts, preserving first-seen order.
    """
    lines = [ln.strip() for ln in text.splitlines()]
    holdings: list[dict] = []
    seen: set[str] = set()

    for i, line in enumerate(lines):
        if not line:
            continue

        tickers = [t for t in _TICKER_RE.findall(line) if t not in _BLACKLIST]
        if not tickers:
            continue

        shares = _extract_shares(line)
        if shares is None:
            for j in range(i + 1, min(i + 3, len(lines))):
                nxt = lines[j]
                if not nxt:
                    continue
                shares = _extract_shares(nxt)
                break

        # Comma/space-separated ticker lists (no share count) → emit each;
        # otherwise treat as a single holding line and use the first ticker.
        emit = tickers if (shares is None and len(tickers) > 1) else [tickers[0]]
        for sym in emit:
            if sym in seen:
                continue
            entry: dict = {"symbol": sym}
            if shares is not None and len(emit) == 1:
                entry["shares"] = shares
            holdings.append(entry)
            seen.add(sym)

    return holdings
