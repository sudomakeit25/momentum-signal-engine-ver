from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Cache
    cache_dir: str = ".cache"
    cache_ttl_minutes: int = 15

    # Scanner defaults
    scan_min_price: float = 5.0
    scan_max_price: float = 500.0
    scan_min_volume: int = 500_000
    scan_top_n: int = 20

    # Risk defaults
    default_risk_pct: float = 2.0
    min_rr_ratio: float = 2.0

    # Intraday movers screener defaults (0.5-1% scalp framework)
    intraday_min_price: float = 20.0          # tighter spreads above $20
    intraday_min_avg_volume: int = 2_000_000  # 20-day average daily volume
    intraday_min_change_pct: float = 2.0      # |today's % change| — movement begets movement
    intraday_min_rvol: float = 1.5            # time-adjusted relative volume
    intraday_max_spread_pct: float = 0.1      # spread + slippage must stay < 0.1%
    intraday_min_rr: float = 1.5              # checklist: risk/reward at least 1:1.5
    intraday_box_bars: int = 8                # 8 x 5min = 40 min consolidation box
    intraday_top_n: int = 25
    # Forming-setup watches (alert before the trigger, with levels)
    intraday_box_min_day_range_mult: float = 2.2  # box must follow a real move
    intraday_watch_box_atr_frac: float = 0.12     # watch box height <= this share of ATR%
    intraday_watch_box_max_pct: float = 1.0       # and never taller than this % of price
    intraday_watch_min_prior_bars: int = 12       # 1h of session before the box (skip the opening range)
    intraday_vwap_near_pct: float = 0.15          # "at VWAP" threshold
    intraday_vwap_far_pct: float = 0.60           # must have been this far away earlier

    # Auto-trader: turns confirmed intraday setups into Alpaca PAPER bracket
    # orders. Master switch is off by default and can only be turned on
    # here (env var AUTO_TRADE_ENABLED); the API can pause it, never enable it.
    auto_trade_enabled: bool = False
    auto_trade_risk_per_trade_usd: float = 50.0    # dollars lost if the stop fills
    auto_trade_max_position_usd: float = 5000.0    # cap on position value
    auto_trade_max_trades_per_day: int = 5
    auto_trade_max_open_positions: int = 3
    auto_trade_daily_loss_limit_usd: float = 150.0  # account day P&L at which it halts
    auto_trade_allow_shorts: bool = False
    auto_trade_min_confidence: float = 0.6
    auto_trade_max_chase_frac: float = 0.25        # live price may drift this share of risk past entry
    auto_trade_min_rr_at_quote: float = 1.2        # reward:risk recomputed at the live quote
    auto_trade_require_earnings_check: bool = True  # no trade if the earnings calendar could not be read
    auto_trade_require_persistent_store: bool = True  # refuse to run without Redis (pause/halt must survive restarts)
    auto_trade_resume_key: str = ""                # secret (16+ chars) needed to resume a paused bot via the API
    auto_trade_last_entry_et: str = "15:30"        # no new entries from this time
    auto_trade_flatten_et: str = "15:45"           # close the bot's positions from this time

    # Keep-alive: a host that sleeps when idle (Render free plan) stops every
    # background loop. On weekdays inside this New York time window the app
    # requests its own public address so the host stays awake. It cannot
    # wake a sleeping host; .github/workflows/wake.yml does that.
    keep_alive_enabled: bool = True
    keep_alive_url: str = ""                 # blank = RENDER_EXTERNAL_URL (set by Render); no address = off
    keep_alive_start_et: str = "04:00"       # pre-market data starts at 4:00
    keep_alive_end_et: str = "16:15"         # after the close and the 15:45 auto-trader flatten
    keep_alive_interval_seconds: int = 300   # the host sleeps after 15 idle minutes

    # Twilio SMS
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""  # e.g. "+15551234567"

    # Email-to-SMS gateway (free alternative to Twilio)
    smtp_email: str = ""  # e.g. "yourname@gmail.com"
    smtp_password: str = ""  # Gmail app password (not your login password)

    # Upstash Redis (persistent config storage)
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # Polygon.io (Options Flow)
    polygon_api_key: str = ""

    # Financial Modeling Prep (Earnings)
    fmp_api_key: str = ""

    # Auth
    jwt_secret: str = "mse-default-secret-change-in-production"
    jwt_expiry_hours: int = 72

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
