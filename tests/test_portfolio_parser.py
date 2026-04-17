"""Unit tests for portfolio_parser."""

from src.scanner.portfolio_parser import parse_portfolio_text


def _by_symbol(rows: list[dict]) -> dict[str, dict]:
    return {r["symbol"]: r for r in rows}


class TestSameLineShares:
    def test_ticker_with_shares_same_line(self):
        out = parse_portfolio_text("MU 900 shares")
        assert out == [{"symbol": "MU", "shares": 900.0}]

    def test_comma_separated_shares(self):
        out = parse_portfolio_text("RKLB 10,400 shares")
        assert out == [{"symbol": "RKLB", "shares": 10400.0}]

    def test_fractional_shares(self):
        out = parse_portfolio_text("KNTK 36.55 shares")
        assert out == [{"symbol": "KNTK", "shares": 36.55}]


class TestMultiLineRobinhoodFormat:
    def test_robinhood_layout(self):
        text = """RKLB
10,400 shares
$85.48
MU
900 shares
$459.30
"""
        rows = _by_symbol(parse_portfolio_text(text))
        assert rows["RKLB"]["shares"] == 10400.0
        assert rows["MU"]["shares"] == 900.0

    def test_shares_within_two_lines(self):
        text = "AAPL\n\n100 shares"
        assert parse_portfolio_text(text) == [{"symbol": "AAPL", "shares": 100.0}]


class TestDeduplicationAndOrdering:
    def test_duplicates_collapsed_preserving_order(self):
        out = parse_portfolio_text("AAPL\nMSFT\nAAPL\nNVDA")
        assert [r["symbol"] for r in out] == ["AAPL", "MSFT", "NVDA"]

    def test_plain_ticker_list(self):
        out = parse_portfolio_text("AAPL, MSFT, NVDA")
        assert [r["symbol"] for r in out] == ["AAPL", "MSFT", "NVDA"]


class TestBlacklist:
    def test_noise_words_skipped(self):
        # "USD" and "CASH" should not be returned as tickers
        out = parse_portfolio_text("CASH $50,000\nUSD\nMU 900 shares")
        syms = [r["symbol"] for r in out]
        assert "CASH" not in syms
        assert "USD" not in syms
        assert "MU" in syms

    def test_buy_sell_action_words_ignored(self):
        out = parse_portfolio_text("BUY MU 100 shares")
        # "BUY" is blacklisted; MU should still be picked up
        assert out == [{"symbol": "MU", "shares": 100.0}]


class TestEmpty:
    def test_empty_string(self):
        assert parse_portfolio_text("") == []

    def test_all_blacklisted(self):
        assert parse_portfolio_text("CASH\nUSD\nTOTAL") == []
