"""Multi-channel notification system.

Features 41-50: Telegram, Discord, push notifications, email digest,
morning briefing, EOD report, custom rules, escalation, cooldown, routing.
"""

import json
import logging
from datetime import datetime, timezone

import requests

from src.data.redis_store import _get_redis

logger = logging.getLogger("mse.channels")

_COOLDOWN_KEY = "mse:alert_cooldown"


# --- 41. Telegram Bot ---

def send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    """Send a message via Telegram bot."""
    if not bot_token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)
        return False


# --- 42. Discord Webhook ---

def send_discord(webhook_url: str, message: str, embeds: list[dict] | None = None) -> bool:
    """Send a message via Discord webhook."""
    if not webhook_url:
        return False
    try:
        payload: dict = {"content": message}
        if embeds:
            payload["embeds"] = embeds
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return 200 <= resp.status_code < 300
    except Exception as e:
        logger.warning("Discord send failed: %s", e)
        return False


# --- 45. Morning Briefing ---

def generate_morning_briefing(scan_results: list, regime: dict, news: list) -> str:
    """Generate a morning briefing summary."""
    lines = ["*Morning Briefing*\n"]

    # Market regime
    if regime:
        lines.append(f"Market: {regime.get('regime', 'unknown').replace('_', ' ').upper()}")
        lines.append(f"SPY: ${regime.get('spy_price', 0)} ({regime.get('spy_change_20d', 0):+.1f}% 20d)\n")

    # Top movers
    if scan_results:
        lines.append("*Top Momentum:*")
        for r in scan_results[:5]:
            sym = r.symbol if hasattr(r, 'symbol') else r.get('symbol', '')
            score = r.score if hasattr(r, 'score') else r.get('score', 0)
            change = r.change_pct if hasattr(r, 'change_pct') else r.get('change_pct', 0)
            lines.append(f"  {sym}: Score {score:.0f} ({change:+.1f}%)")

    # News sentiment
    if news:
        bullish = sum(1 for n in news if n.get("sentiment") == "bullish")
        bearish = sum(1 for n in news if n.get("sentiment") == "bearish")
        lines.append(f"\nNews: {bullish} bullish, {bearish} bearish articles")

    return "\n".join(lines)


# --- 46. End of Day Report ---

def generate_eod_report(scan_results: list, alerts_today: list, positions: list) -> str:
    """Generate end-of-day summary."""
    lines = ["*End of Day Report*\n"]

    # Positions summary
    if positions:
        total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)
        lines.append(f"Positions: {len(positions)}")
        lines.append(f"Day P&L: ${total_pnl:,.2f}\n")

    # Alerts sent today
    if alerts_today:
        lines.append(f"Alerts dispatched: {len(alerts_today)}")
        for a in alerts_today[:5]:
            lines.append(f"  {a.get('symbol', '')} {a.get('action', '')} @ ${a.get('entry', 0):.2f}")

    # Top signals
    if scan_results:
        lines.append(f"\nTop signals: {len(scan_results)} stocks with momentum")

    return "\n".join(lines)


# --- 47. Custom Alert Rules ---

def evaluate_custom_rules(rules: list[dict], scan_data: list[dict]) -> list[dict]:
    """Evaluate user-defined alert rules against scan data.

    Rules format: [{"field": "score", "operator": ">", "value": 80, "symbol": ""}]
    """
    triggered = []
    for rule in rules:
        field = rule.get("field", "")
        op = rule.get("operator", "")
        value = rule.get("value", 0)
        symbol_filter = rule.get("symbol", "").upper()

        for stock in scan_data:
            sym = stock.get("symbol", "")
            if symbol_filter and sym != symbol_filter:
                continue

            actual = stock.get(field, 0)
            try:
                actual = float(actual)
                value = float(value)
            except (TypeError, ValueError):
                continue

            match = False
            if op == ">" and actual > value:
                match = True
            elif op == "<" and actual < value:
                match = True
            elif op == ">=" and actual >= value:
                match = True
            elif op == "<=" and actual <= value:
                match = True
            elif op == "==" and actual == value:
                match = True

            if match:
                triggered.append({
                    "rule": rule,
                    "symbol": sym,
                    "field": field,
                    "actual": actual,
                    "message": f"{sym}: {field} is {actual} ({op} {value})",
                })

    return triggered


# --- 49. Alert Cooldown ---

def check_cooldown(symbol: str, cooldown_minutes: int = 60) -> bool:
    """Check if a symbol is in cooldown period. Returns True if OK to alert."""
    redis = _get_redis()
    if not redis:
        return True

    try:
        data = redis.get(_COOLDOWN_KEY)
        cooldowns = json.loads(data) if data else {}
        last = cooldowns.get(symbol, "")
        if last:
            last_dt = datetime.fromisoformat(last)
            now = datetime.now(timezone.utc)
            if (now - last_dt).total_seconds() < cooldown_minutes * 60:
                return False
        return True
    except Exception:
        return True


def set_cooldown(symbol: str) -> None:
    """Set cooldown for a symbol after alerting."""
    redis = _get_redis()
    if not redis:
        return

    try:
        data = redis.get(_COOLDOWN_KEY)
        cooldowns = json.loads(data) if data else {}
        cooldowns[symbol] = datetime.now(timezone.utc).isoformat()
        # Cleanup old entries (>24h)
        now = datetime.now(timezone.utc)
        cooldowns = {
            k: v for k, v in cooldowns.items()
            if (now - datetime.fromisoformat(v)).total_seconds() < 86400
        }
        redis.set(_COOLDOWN_KEY, json.dumps(cooldowns))
    except Exception:
        pass


# --- 50. Multi-channel Routing ---

def route_alert(signal: dict, config: dict) -> dict:
    """Route an alert to the appropriate channel based on config.

    Config: {"sms_symbols": ["AAPL"], "telegram_symbols": ["*"], "discord_min_score": 80}
    """
    results = {"sms": False, "telegram": False, "discord": False}
    sym = signal.get("symbol", "")
    score = signal.get("confidence", 0) * 100

    # SMS routing
    sms_syms = config.get("sms_symbols", ["*"])
    if "*" in sms_syms or sym in sms_syms:
        results["sms"] = True

    # Telegram routing
    tg_syms = config.get("telegram_symbols", [])
    if "*" in tg_syms or sym in tg_syms:
        results["telegram"] = True

    # Discord routing (score-based)
    discord_min = config.get("discord_min_score", 0)
    if score >= discord_min:
        results["discord"] = True

    return results
