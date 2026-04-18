"""Test that international tickers route to FMP instead of Alpaca."""

import pandas as pd
import pytest

from src.data import client


class TestFMPRouting:
    """Broader than just international — forex, commodities, indices all route to FMP too."""
    def test_forex(self): assert client._use_fmp_historical("EURUSD")
    def test_index(self): assert client._use_fmp_historical("^GSPC")
    def test_commodity(self): assert client._use_fmp_historical("GCUSD")
    def test_us_stock_does_not(self): assert not client._use_fmp_historical("AAPL")
    def test_crypto_does_not(self): assert not client._use_fmp_historical("BTC/USD")


class TestIsInternational:
    def test_us_ticker(self):
        assert client._is_international("AAPL") is False

    def test_french(self):
        assert client._is_international("AIR.PA") is True

    def test_german(self):
        assert client._is_international("RHM.DE") is True

    def test_london(self):
        assert client._is_international("BA.L") is True

    def test_canadian(self):
        assert client._is_international("MDA.TO") is True

    def test_swiss(self):
        assert client._is_international("ACLN.SW") is True

    def test_crypto_not_international(self):
        assert client._is_international("BTC/USD") is False

    def test_us_dotted_like_brk_b(self):
        # Not in intl suffix list — should be false
        assert client._is_international("BRK.B") is False


class TestGetBarsRoutesInternational:
    def test_intl_ticker_calls_fmp_not_alpaca(self, monkeypatch):
        called = {"fmp": False, "alpaca": False}

        def fake_fmp(sym, days):
            called["fmp"] = True
            return pd.DataFrame({
                "open": [1], "high": [2], "low": [1], "close": [1.5], "volume": [100],
            }, index=pd.to_datetime(["2024-01-01"]))

        def fake_alpaca():
            called["alpaca"] = True
            raise AssertionError("Alpaca should not be called for intl tickers")

        from src.data import fmp_client
        monkeypatch.setattr(fmp_client, "get_historical_prices", fake_fmp)
        monkeypatch.setattr(client, "_get_data_client", fake_alpaca)
        # Bypass cache for the assertion
        monkeypatch.setattr(client._cache, "get", lambda k: None)
        monkeypatch.setattr(client._cache, "set", lambda k, v: None)

        df = client.get_bars("AIR.PA", days=60)
        assert called["fmp"] is True
        assert called["alpaca"] is False
        assert not df.empty

    def test_us_ticker_still_uses_alpaca_path(self, monkeypatch):
        """Make sure we didn't break US ticker routing."""
        monkeypatch.setattr(client._cache, "get", lambda k: None)
        monkeypatch.setattr(client._cache, "set", lambda k, v: None)

        def fake_fmp(sym, days):
            raise AssertionError("FMP should not be called for US tickers")

        from src.data import fmp_client
        monkeypatch.setattr(fmp_client, "get_historical_prices", fake_fmp)

        # We expect it to attempt Alpaca; raise there to short-circuit the test
        class FakeClient:
            def get_stock_bars(self, req):
                raise RuntimeError("alpaca ok")
        monkeypatch.setattr(client, "_get_data_client", lambda: FakeClient())
        with pytest.raises(RuntimeError, match="alpaca ok"):
            client.get_bars("AAPL", days=60)
