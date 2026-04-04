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

    # Twilio SMS
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""  # e.g. "+15551234567"

    # Email-to-SMS gateway (free alternative to Twilio)
    smtp_email: str = ""  # e.g. "yourname@gmail.com"
    smtp_password: str = ""  # Gmail app password (not your login password)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
