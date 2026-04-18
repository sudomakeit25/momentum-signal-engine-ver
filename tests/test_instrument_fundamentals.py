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


class TestPiotroskiF:
    def test_strong_company_scores_high(self):
        cur_i = {"netIncome": 100, "revenue": 1000, "grossProfit": 400, "weightedAverageShsOut": 100}
        prev_i = {"netIncome": 50, "revenue": 800, "grossProfit": 280, "weightedAverageShsOut": 105}
        cur_b = {"totalAssets": 2000, "totalCurrentAssets": 800, "totalCurrentLiabilities": 300, "longTermDebt": 100}
        prev_b = {"totalAssets": 1800, "totalCurrentAssets": 700, "totalCurrentLiabilities": 400, "longTermDebt": 200}
        cur_cf = {"operatingCashFlow": 150}
        f = ifund._piotroski_f_score(cur_i, prev_i, cur_b, prev_b, cur_cf)
        assert f is not None and f >= 7

    def test_weak_company_scores_low(self):
        cur_i = {"netIncome": -100, "revenue": 800, "grossProfit": 200, "weightedAverageShsOut": 120}
        prev_i = {"netIncome": 50, "revenue": 1000, "grossProfit": 400, "weightedAverageShsOut": 100}
        cur_b = {"totalAssets": 1800, "totalCurrentAssets": 500, "totalCurrentLiabilities": 500, "longTermDebt": 300}
        prev_b = {"totalAssets": 2000, "totalCurrentAssets": 700, "totalCurrentLiabilities": 300, "longTermDebt": 200}
        cur_cf = {"operatingCashFlow": -50}
        f = ifund._piotroski_f_score(cur_i, prev_i, cur_b, prev_b, cur_cf)
        assert f is not None and f <= 3

    def test_zero_assets_returns_none(self):
        assert ifund._piotroski_f_score(
            {"netIncome": 100, "revenue": 100}, {"netIncome": 50, "revenue": 100},
            {"totalAssets": 0}, {"totalAssets": 100}, {"operatingCashFlow": 10},
        ) is None


class TestFVerdict:
    def test_strong(self): assert ifund._f_verdict(8) == "strong"
    def test_average(self): assert ifund._f_verdict(5) == "average"
    def test_weak(self): assert ifund._f_verdict(2) == "weak"
    def test_none(self): assert ifund._f_verdict(None) == "n/a"


class TestMVerdict:
    def test_clean(self): assert ifund._m_verdict(-2.0) == "clean"
    def test_flagged(self): assert ifund._m_verdict(-1.0) == "flagged"
    def test_none(self): assert ifund._m_verdict(None) == "n/a"


class TestPeterLynch:
    def test_growth_cap_at_30(self):
        fv = ifund._peter_lynch_fair_value(eps_ttm=2.0, growth_pct=50.0, dividend_yield_pct=2.0)
        # 50+2 > 30, cap at 30 → 2 * 30 = 60
        assert fv == 60.0
    def test_negative_growth_returns_none(self):
        assert ifund._peter_lynch_fair_value(2.0, -5.0, 0.0) is None
    def test_zero_eps_returns_none(self):
        assert ifund._peter_lynch_fair_value(0, 20.0, 1.0) is None


class TestDCF:
    def test_basic(self):
        # FCF $1B, 10% growth, 100M shares → plausibly > current for a healthy growth co
        fv = ifund._dcf_fair_value(
            fcf_latest=1_000_000_000,
            growth_pct=10.0,
            shares_outstanding=100_000_000,
        )
        assert fv is not None and fv > 0

    def test_zero_fcf_returns_none(self):
        assert ifund._dcf_fair_value(0, 10.0, 100) is None

    def test_zero_shares_returns_none(self):
        assert ifund._dcf_fair_value(1e9, 10.0, 0) is None


class TestShareholdersYield:
    def test_basic(self):
        # $500M in dividends + $1B buybacks / $10B cap = 15%
        r = ifund._shareholders_yield(
            dividend_paid=-500_000_000,
            stock_repurchased=-1_000_000_000,
            market_cap=10_000_000_000,
        )
        assert r == 15.0

    def test_zero_cap_returns_none(self):
        assert ifund._shareholders_yield(1, 1, 0) is None


class TestKeyMetrics:
    def test_basic(self):
        income = {
            "revenue": 100, "netIncome": 10, "grossProfit": 40,
            "operatingIncome": 20, "interestExpense": 2,
        }
        balance = {"totalAssets": 500, "totalStockholdersEquity": 200, "totalDebt": 150}
        m = ifund._key_metrics(income, balance)
        assert m["gross_margin_pct"] == 40.0
        assert m["operating_margin_pct"] == 20.0
        assert m["net_margin_pct"] == 10.0
        assert m["roe_pct"] == 5.0
        assert m["roa_pct"] == 2.0
        assert m["debt_to_equity"] == 0.75
        assert m["interest_coverage"] == 10.0


class TestEmptyFallback:
    def test_no_fmp_returns_structured_empty(self, monkeypatch):
        """When FMP is unavailable, get_fundamentals returns a full shape with empty values."""
        monkeypatch.setattr(ifund.fmp_client, "get_company_profile", lambda s: {})
        monkeypatch.setattr(ifund.fmp_client, "get_quote", lambda s: {})
        monkeypatch.setattr(ifund.fmp_client, "get_key_metrics_ttm", lambda s: {})
        monkeypatch.setattr(ifund.fmp_client, "get_income_statement", lambda s, **k: [])
        monkeypatch.setattr(ifund.fmp_client, "get_balance_sheet", lambda s, **k: [])
        monkeypatch.setattr(ifund.fmp_client, "get_cash_flow", lambda s, **k: [])
        monkeypatch.setattr(ifund.fmp_client, "get_enterprise_values", lambda s, **k: [])

        # Block the Alpaca fallback for this test by patching get_bars
        from src.data import client as _price_client
        monkeypatch.setattr(_price_client, "get_bars", lambda s, **k: None)

        r = ifund.get_fundamentals("FAKE")
        assert r["header"]["symbol"] == "FAKE"
        assert r["income_series"] == []
        assert r["shares_series"] == []
        assert r["fair_value"]["fair_value"] is None
        assert r["altman_z"]["latest"] is None
        assert r["has_fundamentals"] is False

    def test_price_falls_back_to_alpaca(self, monkeypatch):
        """When FMP is unavailable, header.price should fall back to Alpaca close."""
        import pandas as pd
        monkeypatch.setattr(ifund.fmp_client, "get_company_profile", lambda s: {})
        monkeypatch.setattr(ifund.fmp_client, "get_quote", lambda s: {})
        monkeypatch.setattr(ifund.fmp_client, "get_key_metrics_ttm", lambda s: {})
        monkeypatch.setattr(ifund.fmp_client, "get_income_statement", lambda s, **k: [])
        monkeypatch.setattr(ifund.fmp_client, "get_balance_sheet", lambda s, **k: [])
        monkeypatch.setattr(ifund.fmp_client, "get_cash_flow", lambda s, **k: [])
        monkeypatch.setattr(ifund.fmp_client, "get_enterprise_values", lambda s, **k: [])

        from src.data import client as _price_client
        fake_bars = pd.DataFrame(
            {"close": [95.0, 97.5, 100.25]},
            index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        )
        monkeypatch.setattr(_price_client, "get_bars", lambda s, **k: fake_bars)

        r = ifund.get_fundamentals("FAKE")
        assert r["header"]["price"] == 100.25
        assert r["header"]["last_close"] == 100.25

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
