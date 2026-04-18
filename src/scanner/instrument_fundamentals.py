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


def _piotroski_f_score(
    cur_income: dict,
    prev_income: dict,
    cur_balance: dict,
    prev_balance: dict,
    cur_cash_flow: dict,
) -> int | None:
    """Piotroski F-Score (0-9). Nine binary tests across profitability,
    leverage, and operating efficiency. Returns None on insufficient data.
    """
    try:
        ni = _safe_float(cur_income.get("netIncome"))
        prev_ni = _safe_float(prev_income.get("netIncome"))
        assets = _safe_float(cur_balance.get("totalAssets"))
        prev_assets = _safe_float(prev_balance.get("totalAssets"))
        if assets <= 0 or prev_assets <= 0:
            return None
        avg_assets = (assets + prev_assets) / 2
        cfo = _safe_float(cur_cash_flow.get("operatingCashFlow"))
        revenue = _safe_float(cur_income.get("revenue"))
        prev_revenue = _safe_float(prev_income.get("revenue"))
        gross = _safe_float(cur_income.get("grossProfit"))
        prev_gross = _safe_float(prev_income.get("grossProfit"))
        lt_debt = _safe_float(cur_balance.get("longTermDebt"))
        prev_lt_debt = _safe_float(prev_balance.get("longTermDebt"))
        cur_assets = _safe_float(cur_balance.get("totalCurrentAssets"))
        cur_liab = _safe_float(cur_balance.get("totalCurrentLiabilities"))
        prev_cur_assets = _safe_float(prev_balance.get("totalCurrentAssets"))
        prev_cur_liab = _safe_float(prev_balance.get("totalCurrentLiabilities"))
        shares = _safe_float(cur_income.get("weightedAverageShsOut"))
        prev_shares = _safe_float(prev_income.get("weightedAverageShsOut"))

        score = 0
        # Profitability (4 points)
        if ni > 0: score += 1
        if cfo > 0: score += 1
        if avg_assets > 0 and ni / avg_assets > prev_ni / prev_assets: score += 1
        if cfo > ni: score += 1
        # Leverage / liquidity (3 points)
        if lt_debt < prev_lt_debt: score += 1
        if prev_cur_liab > 0 and cur_liab > 0:
            cur_ratio = cur_assets / cur_liab
            prev_ratio = prev_cur_assets / prev_cur_liab
            if cur_ratio > prev_ratio: score += 1
        if shares > 0 and prev_shares > 0 and shares <= prev_shares: score += 1
        # Operating efficiency (2 points)
        if prev_revenue > 0 and prev_gross > 0:
            gm = gross / revenue if revenue > 0 else 0
            prev_gm = prev_gross / prev_revenue
            if gm > prev_gm: score += 1
        if prev_assets > 0:
            at = revenue / avg_assets
            prev_at = prev_revenue / prev_assets
            if at > prev_at: score += 1
        return score
    except Exception:
        return None


def _f_verdict(f: int | None) -> str:
    if f is None:
        return "n/a"
    if f >= 7:
        return "strong"
    if f >= 4:
        return "average"
    return "weak"


def _beneish_m_score(
    cur_income: dict,
    prev_income: dict,
    cur_balance: dict,
    prev_balance: dict,
    cur_cash_flow: dict,
) -> float | None:
    """Beneish M-Score (earnings manipulation likelihood).

    M > -1.78 suggests manipulation. Computed from 8 indices (DSRI,
    GMI, AQI, SGI, DEPI, SGAI, LVGI, TATA). Returns None on any zero
    denominator.
    """
    try:
        revenue_t = _safe_float(cur_income.get("revenue"))
        revenue_tm1 = _safe_float(prev_income.get("revenue"))
        receivables_t = _safe_float(cur_balance.get("netReceivables"))
        receivables_tm1 = _safe_float(prev_balance.get("netReceivables"))
        cogs_t = _safe_float(cur_income.get("costOfRevenue"))
        cogs_tm1 = _safe_float(prev_income.get("costOfRevenue"))
        assets_t = _safe_float(cur_balance.get("totalAssets"))
        assets_tm1 = _safe_float(prev_balance.get("totalAssets"))
        ppe_t = _safe_float(cur_balance.get("propertyPlantEquipmentNet"))
        ppe_tm1 = _safe_float(prev_balance.get("propertyPlantEquipmentNet"))
        curr_assets_t = _safe_float(cur_balance.get("totalCurrentAssets"))
        curr_assets_tm1 = _safe_float(prev_balance.get("totalCurrentAssets"))
        depreciation_t = _safe_float(cur_cash_flow.get("depreciationAndAmortization"))
        sga_t = _safe_float(cur_income.get("sellingGeneralAndAdministrativeExpenses"))
        sga_tm1 = _safe_float(prev_income.get("sellingGeneralAndAdministrativeExpenses"))
        liab_t = _safe_float(cur_balance.get("totalLiabilities"))
        liab_tm1 = _safe_float(prev_balance.get("totalLiabilities"))
        ni_t = _safe_float(cur_income.get("netIncome"))
        cfo_t = _safe_float(cur_cash_flow.get("operatingCashFlow"))

        if revenue_t <= 0 or revenue_tm1 <= 0:
            return None
        if assets_t <= 0 or assets_tm1 <= 0:
            return None

        dsri_top = receivables_t / revenue_t if revenue_t else 0
        dsri_bot = receivables_tm1 / revenue_tm1 if revenue_tm1 else 0
        dsri = dsri_top / dsri_bot if dsri_bot > 0 else 1.0

        gm_t = (revenue_t - cogs_t) / revenue_t
        gm_tm1 = (revenue_tm1 - cogs_tm1) / revenue_tm1 if revenue_tm1 else 0
        gmi = gm_tm1 / gm_t if gm_t > 0 else 1.0

        aqi_t = 1 - (curr_assets_t + ppe_t) / assets_t
        aqi_tm1 = 1 - (curr_assets_tm1 + ppe_tm1) / assets_tm1
        aqi = aqi_t / aqi_tm1 if aqi_tm1 > 0 else 1.0

        sgi = revenue_t / revenue_tm1

        dep_tm1 = _safe_float(cur_cash_flow.get("depreciationAndAmortization")) / 2  # fallback
        depi = (dep_tm1 / (dep_tm1 + ppe_tm1)) / (depreciation_t / (depreciation_t + ppe_t)) if (depreciation_t + ppe_t) > 0 and (dep_tm1 + ppe_tm1) > 0 else 1.0

        sgai = (sga_t / revenue_t) / (sga_tm1 / revenue_tm1) if sga_tm1 > 0 and revenue_tm1 > 0 else 1.0

        lvgi = (liab_t / assets_t) / (liab_tm1 / assets_tm1) if assets_tm1 > 0 and liab_tm1 > 0 else 1.0

        tata = (ni_t - cfo_t) / assets_t

        m = (
            -4.84
            + 0.92 * dsri
            + 0.528 * gmi
            + 0.404 * aqi
            + 0.892 * sgi
            + 0.115 * depi
            - 0.172 * sgai
            + 4.679 * tata
            - 0.327 * lvgi
        )
        return round(m, 2)
    except Exception:
        return None


def _m_verdict(m: float | None) -> str:
    if m is None:
        return "n/a"
    if m > -1.78:
        return "flagged"  # possible manipulation
    return "clean"


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
    cash_flow_annual = fmp_client.get_cash_flow(symbol, period="annual", limit=10)
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

    # Fall back to Alpaca close when FMP is unavailable so the overview header
    # still shows a price even on a free-tier deployment.
    if header["price"] == 0.0:
        try:
            from src.data import client as price_client
            bars = price_client.get_bars(symbol, days=5)
            if bars is not None and not bars.empty:
                last_close = float(bars["close"].iloc[-1])
                header["price"] = last_close
                if header["last_close"] == 0.0:
                    header["last_close"] = last_close
        except Exception:
            pass

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

    # Piotroski F + Beneish M using the two most recent annual periods
    income_by_year = {r.get("date", "")[:4]: r for r in income_annual}
    cf_by_year = {r.get("date", "")[:4]: r for r in cash_flow_annual}
    years_sorted = sorted(income_by_year.keys(), reverse=True)
    piotroski_f = None
    beneish_m = None
    if len(years_sorted) >= 2:
        y_cur, y_prev = years_sorted[0], years_sorted[1]
        cur_i, prev_i = income_by_year.get(y_cur), income_by_year.get(y_prev)
        cur_b, prev_b = bs_by_year.get(y_cur), bs_by_year.get(y_prev)
        cur_cf = cf_by_year.get(y_cur)
        if cur_i and prev_i and cur_b and prev_b and cur_cf:
            piotroski_f = _piotroski_f_score(cur_i, prev_i, cur_b, prev_b, cur_cf)
            beneish_m = _beneish_m_score(cur_i, prev_i, cur_b, prev_b, cur_cf)

    # Weighted financials per-share (Sales / NI / FCF / Gross Profit per share)
    weighted = []
    for row in income_annual:
        y = row.get("date", "")[:4]
        shares = _safe_float(row.get("weightedAverageShsOut"))
        if shares <= 0:
            continue
        cf = cf_by_year.get(y, {})
        fcf = _safe_float(cf.get("operatingCashFlow")) - _safe_float(cf.get("capitalExpenditure"))
        weighted.append({
            "year": y,
            "sales_per_share": round(_safe_float(row.get("revenue")) / shares, 2),
            "net_income_per_share": round(_safe_float(row.get("netIncome")) / shares, 2),
            "fcf_per_share": round(fcf / shares, 2),
            "gross_profit_per_share": round(_safe_float(row.get("grossProfit")) / shares, 2),
        })
    weighted.sort(key=lambda r: r["year"])

    # Condensed statements for the Financial Statements tab
    def _income_row(r: dict) -> dict:
        return {
            "year": r.get("date", "")[:4],
            "revenue": _safe_float(r.get("revenue")),
            "gross_profit": _safe_float(r.get("grossProfit")),
            "operating_income": _safe_float(r.get("operatingIncome")),
            "net_income": _safe_float(r.get("netIncome")),
            "eps": _safe_float(r.get("eps")),
        }

    def _balance_row(r: dict) -> dict:
        return {
            "year": r.get("date", "")[:4],
            "total_assets": _safe_float(r.get("totalAssets")),
            "total_liabilities": _safe_float(r.get("totalLiabilities")),
            "total_equity": _safe_float(r.get("totalStockholdersEquity")),
            "cash": _safe_float(r.get("cashAndCashEquivalents")),
            "long_term_debt": _safe_float(r.get("longTermDebt")),
        }

    def _cashflow_row(r: dict) -> dict:
        cfo = _safe_float(r.get("operatingCashFlow"))
        capex = _safe_float(r.get("capitalExpenditure"))
        return {
            "year": r.get("date", "")[:4],
            "operating_cash_flow": cfo,
            "capex": capex,
            "free_cash_flow": cfo - capex,
            "financing_cash_flow": _safe_float(r.get("netCashUsedProvidedByFinancingActivities")),
        }

    statements = {
        "income": sorted(
            [_income_row(r) for r in income_annual], key=lambda x: x["year"]
        ),
        "balance_sheet": sorted(
            [_balance_row(r) for r in balance_annual], key=lambda x: x["year"]
        ),
        "cash_flow": sorted(
            [_cashflow_row(r) for r in cash_flow_annual], key=lambda x: x["year"]
        ),
    }

    return {
        "header": header,
        "income_series": income_series,
        "shares_series": shares_series,
        "weighted_financials": weighted,
        "fair_value": fair_value_block,
        "altman_z": {
            "series": altman_series,
            "latest": latest_z,
            "verdict": _z_verdict(latest_z),
        },
        "piotroski_f": {
            "score": piotroski_f,
            "verdict": _f_verdict(piotroski_f),
        },
        "beneish_m": {
            "score": beneish_m,
            "verdict": _m_verdict(beneish_m),
        },
        "statements": statements,
        "has_fundamentals": bool(income_annual and balance_annual),
    }
