"""News Sentiment Scanner - scrape financial RSS feeds and score sentiment.

Uses free RSS feeds from Yahoo Finance, MarketWatch, and Google News.
Simple keyword-based NLP scoring (no external API needed).
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape

import requests

from src.data.cache import Cache

logger = logging.getLogger("mse.news")
_cache = Cache()

RSS_FEEDS = [
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
]

# Sentiment keyword weights
BULLISH_WORDS = {
    "surge": 2, "surges": 2, "soar": 2, "soars": 2, "rally": 2, "rallies": 2,
    "breakout": 2, "bullish": 2, "upgrade": 2, "upgraded": 2, "beat": 1.5,
    "beats": 1.5, "exceeds": 1.5, "record": 1.5, "high": 1, "growth": 1,
    "gains": 1, "gain": 1, "rises": 1, "rise": 1, "jumps": 1, "jump": 1,
    "positive": 1, "strong": 1, "outperform": 1.5, "buy": 1, "boom": 2,
    "recover": 1, "recovery": 1, "optimistic": 1, "upbeat": 1,
}

BEARISH_WORDS = {
    "crash": 2, "crashes": 2, "plunge": 2, "plunges": 2, "sell-off": 2,
    "selloff": 2, "bearish": 2, "downgrade": 2, "downgraded": 2, "miss": 1.5,
    "misses": 1.5, "warns": 1.5, "warning": 1.5, "decline": 1, "declines": 1,
    "drops": 1, "drop": 1, "falls": 1, "fall": 1, "low": 1, "losses": 1,
    "loss": 1, "negative": 1, "weak": 1, "underperform": 1.5, "sell": 1,
    "recession": 2, "layoff": 1.5, "layoffs": 1.5, "cut": 1, "cuts": 1,
    "fear": 1, "risk": 0.5, "concern": 0.5, "slump": 1.5,
}


def _fetch_rss(url: str) -> list[dict]:
    """Fetch and parse an RSS feed. Returns list of articles."""
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "MSE/1.0"})
        if resp.status_code != 200:
            return []

        root = ET.fromstring(resp.content)
        articles = []

        for item in root.iter("item"):
            title = item.findtext("title", "")
            desc = item.findtext("description", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")

            if title:
                articles.append({
                    "title": unescape(title).strip(),
                    "description": unescape(re.sub(r"<[^>]+>", "", desc)).strip()[:300],
                    "link": link,
                    "pub_date": pub_date,
                })

        return articles
    except Exception as e:
        logger.debug("RSS fetch failed for %s: %s", url, e)
        return []


def _score_text(text: str) -> tuple[float, str]:
    """Score sentiment of text. Returns (score, sentiment).

    Score: -1.0 (very bearish) to +1.0 (very bullish).
    """
    words = text.lower().split()
    bull_score = 0.0
    bear_score = 0.0

    for word in words:
        clean = re.sub(r"[^a-z-]", "", word)
        if clean in BULLISH_WORDS:
            bull_score += BULLISH_WORDS[clean]
        if clean in BEARISH_WORDS:
            bear_score += BEARISH_WORDS[clean]

    total = bull_score + bear_score
    if total == 0:
        return 0.0, "neutral"

    score = (bull_score - bear_score) / total
    if score > 0.2:
        sentiment = "bullish"
    elif score < -0.2:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    return round(score, 3), sentiment


def _find_symbols(text: str, symbols: set[str]) -> list[str]:
    """Find stock symbols mentioned in text."""
    words = set(re.findall(r"\b[A-Z]{2,5}\b", text))
    return [w for w in words if w in symbols]


def fetch_news(symbols: list[str] | None = None) -> list[dict]:
    """Fetch news from all RSS feeds with sentiment scoring.

    If symbols provided, tags articles with mentioned symbols.
    """
    cache_key = "news_sentiment_all"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    symbol_set = set(symbols) if symbols else set()
    all_articles = []

    for source_name, url in RSS_FEEDS:
        articles = _fetch_rss(url)
        for article in articles:
            combined = f"{article['title']} {article['description']}"
            score, sentiment = _score_text(combined)
            mentioned = _find_symbols(combined, symbol_set) if symbol_set else []

            all_articles.append({
                "source": source_name,
                "title": article["title"],
                "description": article["description"],
                "link": article["link"],
                "pub_date": article["pub_date"],
                "sentiment_score": score,
                "sentiment": sentiment,
                "symbols": mentioned,
            })

    # Sort by absolute sentiment score (most opinionated first)
    all_articles.sort(key=lambda a: abs(a["sentiment_score"]), reverse=True)

    if all_articles:
        _cache.set(cache_key, all_articles)

    return all_articles


def get_symbol_sentiment(symbol: str, articles: list[dict] | None = None) -> dict:
    """Get aggregated sentiment for a specific symbol."""
    if articles is None:
        from src.scanner.screener import get_default_universe
        articles = fetch_news(get_default_universe())

    symbol_articles = [a for a in articles if symbol in a.get("symbols", [])]

    if not symbol_articles:
        return {
            "symbol": symbol,
            "article_count": 0,
            "avg_score": 0,
            "sentiment": "neutral",
            "articles": [],
        }

    avg_score = sum(a["sentiment_score"] for a in symbol_articles) / len(symbol_articles)
    if avg_score > 0.15:
        sentiment = "bullish"
    elif avg_score < -0.15:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    return {
        "symbol": symbol,
        "article_count": len(symbol_articles),
        "avg_score": round(avg_score, 3),
        "sentiment": sentiment,
        "articles": symbol_articles[:10],
    }


def get_market_sentiment(articles: list[dict] | None = None) -> dict:
    """Get overall market sentiment summary."""
    if articles is None:
        from src.scanner.screener import get_default_universe
        articles = fetch_news(get_default_universe())

    if not articles:
        return {"total": 0, "bullish": 0, "bearish": 0, "neutral": 0, "avg_score": 0, "sentiment": "neutral"}

    bullish = len([a for a in articles if a["sentiment"] == "bullish"])
    bearish = len([a for a in articles if a["sentiment"] == "bearish"])
    neutral = len([a for a in articles if a["sentiment"] == "neutral"])
    avg = sum(a["sentiment_score"] for a in articles) / len(articles)

    return {
        "total": len(articles),
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "avg_score": round(avg, 3),
        "sentiment": "bullish" if avg > 0.1 else "bearish" if avg < -0.1 else "neutral",
    }
