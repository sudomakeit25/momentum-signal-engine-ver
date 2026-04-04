"""Position sizing calculator."""

from src.data.models import PositionSize


def calculate_position_size(
    account_size: float,
    risk_pct: float,
    entry: float,
    stop_loss: float,
    target: float | None = None,
) -> PositionSize:
    """Calculate position size based on account risk.

    Args:
        account_size: Total account value in dollars.
        risk_pct: Percentage of account to risk per trade (e.g. 2.0 = 2%).
        entry: Entry price per share.
        stop_loss: Stop-loss price per share.
        target: Target price (defaults to 2:1 R:R if not provided).

    Returns:
        PositionSize with shares, dollar risk, position value.
    """
    risk_per_share = abs(entry - stop_loss)
    if risk_per_share <= 0:
        return PositionSize(
            symbol="",
            shares=0,
            entry_price=entry,
            stop_loss=stop_loss,
            target=target or entry,
            dollar_risk=0,
            position_value=0,
            rr_ratio=0,
        )

    dollar_risk = account_size * (risk_pct / 100)
    shares = int(dollar_risk / risk_per_share)

    if target is None:
        target = entry + 2 * risk_per_share  # Default 2:1 R:R

    rr_ratio = (target - entry) / risk_per_share if risk_per_share > 0 else 0

    return PositionSize(
        symbol="",
        shares=shares,
        entry_price=round(entry, 2),
        stop_loss=round(stop_loss, 2),
        target=round(target, 2),
        dollar_risk=round(dollar_risk, 2),
        position_value=round(shares * entry, 2),
        rr_ratio=round(rr_ratio, 2),
    )
