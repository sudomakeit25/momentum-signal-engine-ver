"""Route-handler tests using FastAPI TestClient.

These patch the heavy dependencies (Alpaca, FMP, Redis) so the test
runs entirely in-process without network calls and stays fast.
"""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api import routes
from src.data import client as alpaca_client
from src.data import redis_store


@pytest.fixture
def app():
    from fastapi import FastAPI
    a = FastAPI()
    a.include_router(routes.router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


# --- Shared fake Redis used by token endpoints and a few others ---

class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(redis_store, "_get_redis", lambda: fake)
    return fake


# --- Tests ---

class TestHealth:
    def test_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "service": "momentum-signal-engine"}


class TestMobileTokenEndpoints:
    def test_register_valid_token(self, client, fake_redis):
        r = client.post(
            "/mobile/register-token",
            params={"token": "ExponentPushToken[abc]", "platform": "ios"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "registered"

    def test_register_invalid_token_rejected(self, client, fake_redis):
        r = client.post(
            "/mobile/register-token",
            params={"token": "not-an-expo-token"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "error"

    def test_register_missing_token_is_422(self, client):
        r = client.post("/mobile/register-token")
        assert r.status_code == 422  # FastAPI validation error

    def test_token_count_starts_at_zero(self, client, fake_redis):
        r = client.get("/mobile/token-count")
        assert r.status_code == 200
        assert r.json() == {"count": 0}

    def test_register_then_count_reflects(self, client, fake_redis):
        client.post(
            "/mobile/register-token",
            params={"token": "ExponentPushToken[x]", "platform": "android"},
        )
        client.post(
            "/mobile/register-token",
            params={"token": "ExponentPushToken[y]", "platform": "ios"},
        )
        r = client.get("/mobile/token-count")
        assert r.json() == {"count": 2}

    def test_unregister_removes(self, client, fake_redis):
        client.post(
            "/mobile/register-token",
            params={"token": "ExponentPushToken[z]"},
        )
        r = client.post(
            "/mobile/unregister-token",
            params={"token": "ExponentPushToken[z]"},
        )
        assert r.json()["status"] == "removed"
        assert client.get("/mobile/token-count").json()["count"] == 0

    def test_unregister_unknown_token(self, client, fake_redis):
        r = client.post(
            "/mobile/unregister-token",
            params={"token": "ExponentPushToken[never-seen]"},
        )
        assert r.json()["status"] == "not_found"

    def test_test_push_without_tokens(self, client, fake_redis):
        r = client.post("/mobile/test-push")
        assert r.json()["status"] == "no_tokens"


class TestAnalyzer:
    def test_analyzer_returns_error_without_bars(self, client, monkeypatch):
        """When bars can't be fetched, analyzer surfaces a clean error."""
        monkeypatch.setattr(
            alpaca_client,
            "get_bars",
            lambda sym, **kw: (_ for _ in ()).throw(RuntimeError("alpaca down")),
        )
        r = client.get("/analyzer/AAPL")
        assert r.status_code == 200
        body = r.json()
        assert "error" in body

    def test_analyzer_happy_path(self, client, monkeypatch):
        import numpy as np
        rng = np.random.default_rng(7)
        close = 50.0
        rows = []
        for _ in range(260):
            close *= 1 + 0.002 + rng.normal(0, 0.01)
            rows.append({
                "open": close, "high": close * 1.01, "low": close * 0.99,
                "close": close, "volume": 1_000_000,
            })
        df = pd.DataFrame(rows)
        df.index = pd.date_range("2024-01-01", periods=260, freq="B")

        def fake_bars(sym, days=260):
            return df
        monkeypatch.setattr(alpaca_client, "get_bars", fake_bars)

        r = client.get("/analyzer/TEST")
        assert r.status_code == 200
        body = r.json()
        assert body["symbol"] == "TEST"
        assert "composite_score" in body
        assert 0 <= body["composite_score"] <= 100
        assert body["verdict"] in {"strong_buy", "buy", "hold", "avoid"}


class TestInstrumentSeasonality:
    def test_seasonality_error_on_insufficient_history(self, client, monkeypatch):
        import numpy as np
        # Return only a handful of bars
        df = pd.DataFrame({
            "open": [1] * 10, "high": [1] * 10, "low": [1] * 10,
            "close": [1.0] * 10, "volume": [1000] * 10,
        })
        df.index = pd.date_range("2024-01-01", periods=10, freq="B")
        monkeypatch.setattr(alpaca_client, "get_bars", lambda sym, **kw: df)
        r = client.get("/instrument/TEST/seasonality")
        assert r.status_code == 200
        assert r.json().get("error")


class TestInstrumentIndicators:
    def test_indicators_graceful_error(self, client, monkeypatch):
        monkeypatch.setattr(
            alpaca_client, "get_bars",
            lambda sym, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        r = client.get("/instrument/EURUSD/indicators")
        assert r.status_code == 200
        assert "error" in r.json()


class TestInstrumentFundamentals:
    def test_empty_fallback_without_fmp(self, client, monkeypatch):
        from src.data import fmp_client
        # Block every FMP call
        monkeypatch.setattr(fmp_client, "get_company_profile", lambda s: {})
        monkeypatch.setattr(fmp_client, "get_quote", lambda s: {})
        monkeypatch.setattr(fmp_client, "get_key_metrics_ttm", lambda s: {})
        monkeypatch.setattr(fmp_client, "get_income_statement", lambda s, **kw: [])
        monkeypatch.setattr(fmp_client, "get_balance_sheet", lambda s, **kw: [])
        monkeypatch.setattr(fmp_client, "get_cash_flow", lambda s, **kw: [])
        monkeypatch.setattr(fmp_client, "get_enterprise_values", lambda s, **kw: [])
        monkeypatch.setattr(alpaca_client, "get_bars", lambda sym, **kw: None)
        # Also clear cache
        routes._scan_cache.pop("instr_fund_FAKE", None)

        r = client.get("/instrument/FAKE/fundamentals")
        assert r.status_code == 200
        body = r.json()
        assert body["has_fundamentals"] is False
        assert body["header"]["symbol"] == "FAKE"


class TestCotRoute:
    def test_unknown_contract_returns_error(self, client):
        r = client.get("/cot/not-a-contract")
        assert r.status_code == 200
        assert "error" in r.json()

    def test_contract_list_shape(self, client):
        r = client.get("/cot/contracts")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) > 0
        assert all("key" in c and "label" in c for c in data)


class TestScreenerPresets:
    def test_list_presets(self, client):
        r = client.get("/screener/presets")
        assert r.status_code == 200
        data = r.json()
        keys = {s["key"] for s in data}
        assert "momentum" in keys and "breakout" in keys
