from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    timezone: str = "UTC"
    exchange_timezone: str = "America/New_York"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    operator_username: str = "admin"
    operator_password: str = "change-me"

    database_url: str = "postgresql+asyncpg://user:password@localhost/trade_engine"

    # Bybit: execution only (market data comes from Massive - see below).
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    bybit_env: str = "demo"
    bybit_base_url: str = "https://api-demo.bybit.com"
    bybit_ws_url: str = "wss://stream-demo.bybit.com/v5/private"
    bybit_recv_window: int = 5000

    # Massive (formerly Polygon.io): market data only.
    massive_api_key: str = ""
    massive_base_url: str = "https://api.massive.com"
    massive_ws_url: str = "wss://socket.massive.com/stocks"

    risk_per_trade_pct: float = 1.25
    daily_loss_limit_pct: float = 4.0
    max_concurrent_positions: int = 4
    max_portfolio_exposure_pct: float = 80.0
    max_strategy_allocation_pct: float = 50.0
    max_spread_pct: float = 0.15

    dashboard_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
