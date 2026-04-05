"""Sector mappings for the stock universe."""

SECTORS: dict[str, list[str]] = {
    "Technology": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
                   "NFLX", "CRM", "ADBE", "ORCL", "AVGO", "QCOM", "INTC", "MU"],
    "Fintech": ["SHOP", "SQ", "PYPL", "COIN", "MARA", "RIOT", "SOFI", "PLTR"],
    "Cloud/Cyber": ["SNOW", "DDOG", "NET", "CRWD", "ZS", "PANW", "ABNB", "UBER"],
    "Consumer": ["DASH", "RBLX", "U", "TTD", "ENPH", "SEDG", "FSLR", "CEG",
                 "WMT", "COST", "HD", "LOW", "TGT", "NKE", "SBUX", "MCD",
                 "PG", "KO", "PEP", "CL", "EL", "MNST"],
    "Healthcare": ["LLY", "UNH", "JNJ", "PFE", "ABBV", "MRK", "BMY", "AMGN",
                   "TMO", "ABT", "DHR", "ISRG", "MDT", "GILD", "VRTX", "REGN"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "OXY", "DVN", "MPC", "PSX",
               "EOG", "HES", "VLO", "HAL"],
    "Financials": ["JPM", "BAC", "GS", "MS", "WFC", "C", "SCHW", "BLK",
                   "AXP", "COF", "ICE", "CME", "SPGI", "MMC"],
    "Industrials": ["CAT", "DE", "HON", "GE", "RTX", "LMT", "BA", "NOC",
                    "UNP", "UPS", "FDX", "WM", "EMR", "ITW"],
    "Telecom/Media": ["DIS", "CMCSA", "T", "VZ", "CHTR", "TMUS"],
    "Semiconductors": ["LRCX", "KLAC", "AMAT", "MRVL", "ON", "SWKS", "TXN"],
    "Software": ["NOW", "INTU", "WDAY", "TEAM", "ZM", "OKTA", "MDB", "HUBS"],
    "Real Estate/Utilities": ["AMT", "PLD", "CCI", "EQIX", "NEE", "DUK", "SO", "AEP"],
    "Materials": ["LIN", "APD", "SHW", "ECL", "NEM", "FCX"],
}

SYMBOL_TO_SECTOR: dict[str, str] = {}
for sector, symbols in SECTORS.items():
    for sym in symbols:
        SYMBOL_TO_SECTOR[sym] = sector


def get_sector(symbol: str) -> str:
    return SYMBOL_TO_SECTOR.get(symbol, "Other")
