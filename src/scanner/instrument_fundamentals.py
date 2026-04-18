"""Fundamental analysis data for a single instrument.

Consolidates FMP profile + income / balance / cash flow / enterprise value
into one view model for the Fundamentals tab. All FMP endpoints require
Starter+; when any are unavailable the corresponding fields come back
empty and the frontend shows placeholder UI.
"""

from __future__ import annotations

import logging

from src.data import fmp_client

logger = logging.getLogger("mse.instrument_fundamentals")


def _safe_float(v) -> float:
    try:
        if v is None:
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _altman_z_score(income: dict, balance: dict, market_cap: float) -> float | None:
    """Compute Altman Z-Score for one period.

    Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E where:
      A = working_capital / total_assets
      B = retained_earnings / total_assets
      C = EBIT / total_assets
      D = market_cap / total_liabilities
      E = sales / total_assets
    """
    total_assets = _safe_float(balance.get("totalAssets"))
    total_liabilities = _safe_float(balance.get("totalLiabilities"))
    if total_assets <= 0 or total_liabilities <= 0:
        return None

    working_capital = _safe_float(balance.get("totalCurrentAssets")) - _safe_float(
        balance.get("totalCurrentLiabilities")
    )
    retained_earnings = _safe_float(balance.get("retainedEarnings"))
    ebit = _safe_float(income.get("operatingIncome")) or (
        _safe_float(income.get("netIncome"))
        + _safe_float(income.get("interestExpense"))
        + _safe_float(income.get("incomeTaxExpense"))
    )
    sales = _safe_float(income.get("revenue"))

    a = working_capital / total_assets
    b = retained_earnings / total_assets
    c = ebit / total_assets
    d = market_cap / total_liabilities if market_cap else 0.0
    e = sales / total_assets

    return round(1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e, 2)


def _z_verdict(z: float | None) -> str:
    if z is None:
        return "n/a"
    if z > 2.99:
        return "safe"
    if z >= 1.81:
        return "grey"
    return "distress"


def get_fundamentals(symbol: str) -> dict:
    """Return a fundamentals bundle for the given symbol.

    Each top-level key can be empty independently; UI should handle nulls.
    """
    symbol = symbol.upper()
    profile = fmp_client.get_company_profile(symbol)
    quote = fmp_client.get_quote(symbol)
    km_ttm = fmp_client.get_key_metrics_ttm(symbol)

    income_annual = fmp_client.get_income_statement(symbol, period="annual", limit=10)
    balance_annual = fmp_client.get_balance_sheet(symbol, period="annual", limit=10)
    ev_annual = fmp_client.get_enterprise_values(symbol, period="annual", limit=10)

    # Header row
    header = {
        "symbol": symbol,
        "name": profile.get("companyName") or quote.get("name") or symbol,
        "logo": profile.get("image") or "",
        "sector": profile.get("sector") or "",
        "industry": profile.get("industry") or "",
        "country": profile.get("country") or "",
        "exchange": profile.get("exchangeShortName") or profile.get("exchange") or "",
        "market_cap": _safe_float(profile.get("mktCap") or quote.get("marketCap")),
        "price": _safe_float(quote.get("price") or profile.get("price")),
        "last_close": _safe_float(quote.get("previousClose") or quote.get("price")),
        "eps_ttm": _safe_float(quote.get("eps") or km_ttm.get("netIncomePerShareTTM")),
        "pe_ttm": _safe_float(quote.get("pe") or km_ttm.get("peRatioTTM")),
        "dividend_yield_pct": _safe_float(km_ttm.get("dividendYieldTTM")) * 100,
        "shareholders_yield_pct": _safe_float(km_ttm.get("shareholdersYieldTTM")) * 100,
        "next_earnings": quote.get("earningsAnnouncement") or "",
    }

    # Income series for the Sales vs Net Income chart (oldest first)
    income_series = []
    for row in sorted(income_annual, key=lambda r: r.get("date", "")):
        income_series.append({
            "date": row.get("date", "")[:10],
            "year": row.get("date", "")[:4],
            "revenue": _safe_float(row.get("revenue")),
            "net_income": _safe_float(row.get("netIncome")),
            "gross_profit": _safe_float(row.get("grossProfit")),
            "operating_income": _safe_float(row.get("operatingIncome")),
        })

    # Shares outstanding series (from enterprise-values) oldest first
    shares_series = []
    for row in sorted(ev_annual, key=lambda r: r.get("date", "")):
        shares_series.append({
            "date": row.get("date", "")[:10],
            "year": row.get("date", "")[:4],
            "shares_outstanding": _safe_float(row.get("numberOfShares")),
            "market_cap": _safe_float(row.get("marketCapitalization")),
            "enterprise_value": _safe_float(row.get("enterpriseValue")),
        })

    # Fair value via EV/Sales multiple: fair_value ~ (avg_ev_sales * current_sales) / shares
    fair_value = None
    fair_value_basis = None
    current_price = header["price"] or header["last_close"]
    if income_series and ev_annual:
        latest_sales = income_series[-1]["revenue"]
        ev_latest = _safe_float(ev_annual[0].get("enterpriseValue"))
        shares_latest = _safe_float(ev_annual[0].get("numberOfShares"))
        # Average the historical EV/Sales excluding the most recent year
        ratios = []
        for inc, ev in zip(income_series, sorted(ev_annual, key=lambda r: r.get("date", ""))):
            s = inc["revenue"]
            evv = _safe_float(ev.get("enterpriseValue"))
            if s > 0 and evv > 0:
                ratios.append(evv / s)
        if ratios and shares_latest > 0 and latest_sales > 0:
            avg_ratio = sum(ratios[:-1]) / max(1, len(ratios) - 1) if len(ratios) > 1 else ratios[0]
            fair_ev = avg_ratio * latest_sales
            fair_value = round(fair_ev / shares_latest, 2)
            fair_value_basis = "EV/Sales"

    fair_value_block = {
        "method": fair_value_basis,
        "fair_value": fair_value,
        "current_price": round(current_price, 2) if current_price else None,
        "deviation_pct": (
            round((current_price - fair_value) / fair_value * 100, 2)
            if fair_value and current_price
            else None
        ),
    }

    # Altman Z-Score per year
    altman_series = []
    bs_by_year = {r.get("date", "")[:4]: r for r in balance_annual}
    mc_by_year = {r.get("date", "")[:4]: _safe_float(r.get("marketCapitalization")) for r in ev_annual}
    for inc in income_series:
        y = inc["year"]
        bs = bs_by_year.get(y)
        if not bs:
            continue
        mcap = mc_by_year.get(y, 0.0)
        z = _altman_z_score(
            {
                "revenue": inc["revenue"],
                "operatingIncome": inc["operating_income"],
                "netIncome": inc["net_income"],
            },
            bs,
            mcap,
        )
        altman_series.append({
            "year": y,
            "z_score": z,
            "verdict": _z_verdict(z),
        })

    latest_z = next(
        (x["z_score"] for x in reversed(altman_series) if x["z_score"] is not None),
        None,
    )

    return {
        "header": header,
        "income_series": income_series,
        "shares_series": shares_series,
        "fair_value": fair_value_block,
        "altman_z": {
            "series": altman_series,
            "latest": latest_z,
            "verdict": _z_verdict(latest_z),
        },
        "has_fundamentals": bool(income_annual and balance_annual),
    }
