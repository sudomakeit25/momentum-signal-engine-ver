"""Natural language screener - parse simple English queries into scan filters.

Feature #72. No LLM needed - uses keyword matching for common patterns.
"""

import re


PATTERNS = [
    (r"tech\s+stocks?\s+near\s+52\s*w(?:eek)?\s+high", {"setup_types": "flat_base", "min_score": 50}),
    (r"high\s+volume", {"min_volume": 2000000}),
    (r"large\s+cap", {"min_price": 50, "max_price": 1000}),
    (r"penny", {"min_price": 1, "max_price": 10}),
    (r"mid\s*cap", {"min_price": 10, "max_price": 100}),
    (r"breakout", {"setup_types": "breakout", "min_score": 40}),
    (r"ema\s+(?:cross|aligned|bullish)", {"require_ema": True}),
    (r"rsi\s+pullback", {"setup_types": "rsi_pullback"}),
    (r"high\s+(?:relative\s+)?strength", {"min_rs": 1.2}),
    (r"strong\s+momentum", {"min_score": 70}),
    (r"score\s+(?:above|over|>)\s*(\d+)", lambda m: {"min_score": int(m.group(1))}),
    (r"price\s+(?:above|over|>)\s*\$?(\d+)", lambda m: {"min_price": float(m.group(1))}),
    (r"price\s+(?:below|under|<)\s*\$?(\d+)", lambda m: {"max_price": float(m.group(1))}),
    (r"volume\s+(?:above|over|>)\s*(\d+[km]?)", lambda m: {"min_volume": _parse_number(m.group(1))}),
    (r"top\s+(\d+)", lambda m: {"top_n": int(m.group(1))}),
]


def _parse_number(s: str) -> int:
    s = s.lower()
    if s.endswith("k"):
        return int(float(s[:-1]) * 1000)
    if s.endswith("m"):
        return int(float(s[:-1]) * 1000000)
    return int(s)


def parse_query(query: str) -> dict:
    """Parse a natural language query into scan filter parameters."""
    query_lower = query.lower().strip()
    filters: dict = {}

    for pattern, result in PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            if callable(result):
                filters.update(result(match))
            else:
                filters.update(result)

    # Extract specific symbols mentioned
    symbol_matches = re.findall(r'\b([A-Z]{2,5})\b', query)
    common_words = {"THE", "AND", "FOR", "WITH", "NEAR", "HIGH", "LOW", "ABOVE", "BELOW", "TOP", "EMA", "RSI", "SHOW", "FIND", "GET"}
    symbols = [s for s in symbol_matches if s not in common_words]
    if symbols:
        filters["symbols"] = ",".join(symbols)

    # Defaults
    if "min_price" not in filters:
        filters["min_price"] = 5
    if "max_price" not in filters:
        filters["max_price"] = 500
    if "min_volume" not in filters:
        filters["min_volume"] = 500000
    if "top_n" not in filters:
        filters["top_n"] = 20

    return {
        "query": query,
        "parsed_filters": filters,
        "description": _describe(filters),
    }


def _describe(filters: dict) -> str:
    parts = []
    if filters.get("min_score"):
        parts.append(f"score >= {filters['min_score']}")
    if filters.get("min_rs"):
        parts.append(f"RS >= {filters['min_rs']}")
    if filters.get("setup_types"):
        parts.append(f"setup: {filters['setup_types']}")
    if filters.get("require_ema"):
        parts.append("EMA aligned")
    if filters.get("min_price", 5) != 5 or filters.get("max_price", 500) != 500:
        parts.append(f"${filters.get('min_price', 5)}-${filters.get('max_price', 500)}")
    if filters.get("min_volume", 500000) != 500000:
        parts.append(f"vol >= {filters['min_volume']:,}")
    return ", ".join(parts) if parts else "default scan"
