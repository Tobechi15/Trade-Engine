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

    # Bybit: execution only (market data comes from Alpaca - see below).
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    bybit_env: str = "demo"
    bybit_base_url: str = "https://api-demo.bybit.com"
    bybit_ws_url: str = "wss://stream-demo.bybit.com/v5/private"
    bybit_recv_window: int = 5000
    # When true, orders are simulated locally (never sent to Bybit) using a
    # virtual balance - lets a mainnet API key be used for read-only calls
    # (e.g. tradeable symbols) without ever risking real capital. Demo
    # trading (BYBIT_ENV=demo) requires demo-specific API keys, so this is
    # the option for running against mainnet with a mainnet-only key.
    paper_trading: bool = False
    paper_starting_equity: float = 100_000.0

    # Alpaca: market data only.
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_data_base_url: str = "https://data.alpaca.markets"
    alpaca_stream_base_url: str = "wss://stream.data.alpaca.markets/v2"
    # "iex" = free/Basic plan (real-time, IEX exchange only). "sip" = full
    # consolidated tape, requires the paid Algo Trader Plus plan - using it
    # on a Basic key gets rejected as a ProviderAuthError.
    alpaca_feed: str = "iex"

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
