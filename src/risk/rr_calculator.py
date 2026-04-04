"""Risk/reward ratio calculator."""


def calculate_rr(entry: float, stop_loss: float, target: float) -> float:
    """Calculate risk/reward ratio.

    Args:
        entry: Entry price.
        stop_loss: Stop-loss price.
        target: Target price.

    Returns:
        R:R ratio (e.g. 2.0 means 2:1).
    """
    risk = abs(entry - stop_loss)
    reward = abs(target - entry)
    if risk <= 0:
        return 0.0
    return round(reward / risk, 2)


def rate_setup(rr_ratio: float) -> str:
    """Rate a setup based on its R:R ratio.

    Returns:
        Rating string: "poor", "decent", "good", or "excellent".
    """
    if rr_ratio < 1.5:
        return "poor"
    if rr_ratio < 2.0:
        return "decent"
    if rr_ratio < 3.0:
        return "good"
    return "excellent"


def find_target_for_rr(
    entry: float, stop_loss: float, desired_rr: float = 2.0
) -> float:
    """Calculate the target price needed to achieve a desired R:R.

    Args:
        entry: Entry price.
        stop_loss: Stop-loss price.
        desired_rr: Desired risk/reward ratio.

    Returns:
        Target price.
    """
    risk = abs(entry - stop_loss)
    return round(entry + risk * desired_rr, 2)
