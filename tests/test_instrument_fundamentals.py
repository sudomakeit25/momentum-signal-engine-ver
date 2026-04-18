"""Unit tests for instrument_fundamentals (Altman Z, empty fallback)."""

import pytest

from src.scanner import instrument_fundamentals as ifund


class TestAltmanZScore:
    def test_healthy_company_scores_safe(self):
        income = {"revenue": 100, "operatingIncome": 20, "netIncome": 15}
        balance = {
            "totalAssets": 200,
            "totalLiabilities": 50,
            "totalCurrentAssets": 80,
            "totalCurrentLiabilities": 30,
            "retainedEarnings": 60,
        }
        z = ifund._altman_z_score(income, balance, market_cap=500)
        assert z is not None
        assert z > 2.99  # safe zone

    def test_distressed_company_scores_low(self):
        income = {"revenue": 50, "operatingIncome": -30, "netIncome": -40}
        balance = {
            "totalAssets": 100,
            "totalLiabilities": 90,
            "totalCurrentAssets": 20,
            "totalCurrentLiabilities": 40,
            "retainedEarnings": -60,
        }
        z = ifund._altman_z_score(income, balance, market_cap=10)
        assert z is not None
        assert z < 1.81  # distress zone

    def test_zero_total_assets_returns_none(self):
        assert ifund._altman_z_score(
            {"revenue": 0}, {"totalAssets": 0, "totalLiabilities": 10}, 100,
        ) is None

    def test_zero_liabilities_returns_none(self):
        assert ifund._altman_z_score(
            {"revenue": 0}, {"totalAssets": 100, "totalLiabilities": 0}, 100,
        ) is None


class TestZVerdict:
    def test_safe(self):
        assert ifund._z_verdict(3.5) == "safe"
    def test_grey(self):
        assert ifund._z_verdict(2.0) == "grey"
    def test_distress(self):
        assert ifund._z_verdict(1.0) == "distress"
    def test_none(self):
        assert ifund._z_verdict(None) == "n/a"


class TestEmptyFallback:
    def test_no_fmp_returns_structured_empty(self, monkeypatch):
        """When FMP is unavailable, get_fundamentals returns a full shape with empty values."""
        monkeypatch.setattr(ifund.fmp_client, "get_company_profile", lambda s: {})
        monkeypatch.setattr(ifund.fmp_client, "get_quote", lambda s: {})
        monkeypatch.setattr(ifund.fmp_client, "get_key_metrics_ttm", lambda s: {})
        monkeypatch.setattr(ifund.fmp_client, "get_income_statement", lambda s, **k: [])
        monkeypatch.setattr(ifund.fmp_client, "get_balance_sheet", lambda s, **k: [])
        monkeypatch.setattr(ifund.fmp_client, "get_enterprise_values", lambda s, **k: [])

        r = ifund.get_fundamentals("FAKE")
        assert r["header"]["symbol"] == "FAKE"
        assert r["income_series"] == []
        assert r["shares_series"] == []
        assert r["fair_value"]["fair_value"] is None
        assert r["altman_z"]["latest"] is None
        assert r["has_fundamentals"] is False

    def test_with_data_populates(self, monkeypatch):
        monkeypatch.setattr(ifund.fmp_client, "get_company_profile", lambda s: {
            "companyName": "Test Co", "sector": "Tech", "industry": "Software",
            "mktCap": 1_000_000_000, "exchangeShortName": "NASDAQ",
        })
        monkeypatch.setattr(ifund.fmp_client, "get_quote", lambda s: {
            "price": 50, "previousClose": 49, "eps": 2, "pe": 25,
        })
        monkeypatch.setattr(ifund.fmp_client, "get_key_metrics_ttm", lambda s: {
            "dividendYieldTTM": 0.02, "shareholdersYieldTTM": 0.05,
        })
        monkeypatch.setattr(ifund.fmp_client, "get_income_statement", lambda s, **k: [
            {"date": "2023-12-31", "revenue": 100, "netIncome": 10, "grossProfit": 40, "operatingIncome": 15},
            {"date": "2024-12-31", "revenue": 150, "netIncome": 20, "grossProfit": 60, "operatingIncome": 25},
        ])
        monkeypatch.setattr(ifund.fmp_client, "get_balance_sheet", lambda s, **k: [
            {"date": "2023-12-31", "totalAssets": 500, "totalLiabilities": 200,
             "totalCurrentAssets": 200, "totalCurrentLiabilities": 80, "retainedEarnings": 100},
            {"date": "2024-12-31", "totalAssets": 600, "totalLiabilities": 220,
             "totalCurrentAssets": 250, "totalCurrentLiabilities": 90, "retainedEarnings": 120},
        ])
        monkeypatch.setattr(ifund.fmp_client, "get_enterprise_values", lambda s, **k: [
            {"date": "2024-12-31", "numberOfShares": 10_000_000,
             "marketCapitalization": 500_000_000, "enterpriseValue": 600_000_000},
            {"date": "2023-12-31", "numberOfShares": 9_000_000,
             "marketCapitalization": 400_000_000, "enterpriseValue": 500_000_000},
        ])

        r = ifund.get_fundamentals("TEST")
        assert r["has_fundamentals"] is True
        assert r["header"]["name"] == "Test Co"
        assert r["header"]["sector"] == "Tech"
        assert len(r["income_series"]) == 2
        assert r["income_series"][0]["year"] == "2023"
        assert r["income_series"][1]["year"] == "2024"
        assert r["fair_value"]["fair_value"] is not None
        assert len(r["altman_z"]["series"]) == 2
        assert r["altman_z"]["latest"] is not None
