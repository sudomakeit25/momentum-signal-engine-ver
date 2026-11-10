"""Headlines per symbol (src/data/news.py). No network."""

from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from src.data import news


def item(headline, symbols, minute=0, source="benzinga"):
    return NS(headline=headline, symbols=symbols, source=source, url="https://x/y",
              created_at=datetime(2026, 11, 10, 9, minute, tzinfo=timezone.utc))


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    news._cache.clear()
    calls = []
    def install(items=None, error=None):
        def fake(symbols, since):
            calls.append(list(symbols))
            if error:
                raise error
            return items or []
        monkeypatch.setattr(news, "_fetch", fake)
        return calls
    return install


def test_specific_headline_ranks_above_a_market_wrap(_clean):
    _clean([
        item("Stocks mixed as chips rally", ["AMD", "MU", "NVDA", "RIOT", "SPY"], minute=30),
        item("Jefferies Upgrades Riot Platforms to Buy", ["RIOT"], minute=19),
    ])
    out = news.latest_headlines(["RIOT"])
    assert [h["headline"] for h in out["RIOT"]] == \
        ["Jefferies Upgrades Riot Platforms to Buy", "Stocks mixed as chips rally"]
    assert out["RIOT"][0]["specific"] is True and out["RIOT"][1]["specific"] is False


def test_newest_first_within_the_same_specificity(_clean):
    _clean([item("old", ["NVDA"], minute=1), item("new", ["NVDA"], minute=40)])
    assert [h["headline"] for h in news.latest_headlines(["NVDA"])["NVDA"]] == ["new", "old"]


def test_symbols_without_news_are_absent_and_cached(_clean):
    calls = _clean([item("x", ["NVDA"])])
    assert set(news.latest_headlines(["NVDA", "AMD"])) == {"NVDA"}
    news.latest_headlines(["NVDA", "AMD"])
    assert len(calls) == 1                       # both answers cached, even the empty one


def test_failure_returns_what_it_has_and_never_raises(_clean):
    _clean(error=RuntimeError("503"))
    assert news.latest_headlines(["NVDA"]) == {}


def test_empty_input_crypto_and_duplicates(_clean):
    calls = _clean([])
    assert news.latest_headlines([]) == {}
    news.latest_headlines(["BTC/USD", "nvda", "NVDA"])
    assert calls == [["NVDA"]]


def test_request_is_capped(_clean):
    calls = _clean([])
    news.latest_headlines([f"S{i}" for i in range(200)])
    assert len(calls[0]) == news._MAX_SYMBOLS


def test_blank_headlines_are_dropped_and_per_symbol_limit_applies(_clean):
    _clean([item("", ["NVDA"]), item("a", ["NVDA"], 1), item("b", ["NVDA"], 2), item("c", ["NVDA"], 3)])
    assert [h["headline"] for h in news.latest_headlines(["NVDA"], per_symbol=2)["NVDA"]] == ["c", "b"]
