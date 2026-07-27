# Trading Engine Backend

Python 3.12+ (spec calls for 3.13; code is 3.12-compatible), FastAPI, async SQLAlchemy, event-driven trading engine. See `/docs` at the repo root for the full specification this implements.

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # then fill in real values
```

Required values in `.env` before the engine can actually trade:

- `DATABASE_URL` - your Neon Postgres connection string (`postgresql+asyncpg://...`). Paste Neon's copy-pasted string as-is (`?sslmode=require&channel_binding=require` included) - `app/db/base.py` sanitizes it for asyncpg automatically.
- `BYBIT_API_KEY` / `BYBIT_API_SECRET` - **execution only**. Bybit TradFi (tokenized US stocks/ETFs) trades as USDT-settled linear perpetuals on the standard V5 API (`category=linear`, symbols like `SPYUSDT`) - confirmed against Bybit's TradFi announcements and API docs.
- `ALPACA_API_KEY` / `ALPACA_API_SECRET` - **market data only**. [Alpaca](https://alpaca.markets) is used for historical bars, live streaming (bars + quotes), and the dynamic scan universe (most-actives screener).
- `JWT_SECRET`, `OPERATOR_USERNAME`, `OPERATOR_PASSWORD` - dashboard login.

**Two different providers, two different symbol universes**: Alpaca covers the whole US equities market; Bybit TradFi currently lists ~300 stocks/ETFs/forex/commodities. `BrokerInterface.get_tradeable_symbols()` (fetched once at startup into `MarketState.tradeable_symbols`) is used to filter ORB's dynamically-discovered scan universe down to what Bybit can actually execute - see `app/strategies/orb.py: build_universe()`.

**Things I could not verify against a live response** (this environment's outbound requests to both `api.bybit.com` and `alpaca.markets` were geo-blocked, so these are the best-documented values from Alpaca's docs, not a live-tested response):
- Bybit's `symbolType` field on `/v5/market/instruments-info` (used to filter stocks/ETFs out of the crypto-perp-heavy `linear` category) - see `app/brokers/bybit_tradfi.py: TRADFI_SYMBOL_TYPES`.
- The most-actives screener response shape (`most_actives` key) - see `app/market_data/alpaca.py: get_active_symbols()`.
- The exact WebSocket error codes for entitlement rejection (Alpaca's docs list `409` as "insufficient subscription" - the plan/feed mismatch case - which this adapter maps to `ProviderAuthError` along with `402`/`403`/`404`/`405`).
- Alpaca doesn't carry macro indices (VIX, NYSE $ADD breadth) via the stocks API - `get_index_value()` always returns `None` and is unused now. `gap_fill` and `breadth_pullback` no longer depend on it: `gap_fill`'s regime filter is 20-day annualized Parkinson historical volatility on the target symbol itself (`app/core/indicators.py: parkinson_volatility()`), and `breadth_pullback`'s breadth filter is sector-ETF trend alignment (XLK/XLF/XLY/XLE vs. their own session VWAP, `app/strategies/breadth_pullback.py: _sector_alignment()`) - both computed locally from bars already being fetched, no extra API dependency.

Confirmed via direct doc fetches (`docs.alpaca.markets`): the REST base (`data.alpaca.markets`), `APCA-API-KEY-ID`/`APCA-API-SECRET-KEY` auth headers, the multi-symbol bars endpoint shape (`/v2/stocks/bars`, keyed by symbol, `next_page_token` pagination), and the WebSocket protocol (`wss://stream.data.alpaca.markets/v2/{feed}`, `auth`/`subscribe` action messages) - and Bybit TradFi's ~300-instrument catalog, `category=linear`, `{TICKER}USDT` symbol format.

**Alpaca's free "Basic" plan has real plan limits** (confirmed via `docs.alpaca.markets/us/docs/about-market-data-api`): real-time data is IEX-only (not the full consolidated tape - that needs `sip`, which requires the paid Algo Trader Plus plan at $99/mo), WebSocket subscriptions are capped at 30 symbols, the most recent 15 minutes of historical bars are restricted, and the REST rate limit is 200 req/min (vs 10,000 req/min on Algo Trader Plus). `ALPACA_FEED` defaults to `iex` for exactly this reason - don't set it to `sip` on a Basic key. There is no code fix for this - a plan/cost decision, not a bug. Until upgraded, the engine degrades gracefully rather than erroring:
- `get_active_symbols()` falls back to the static `DEFAULT_CANDIDATES` list if the screener endpoint 401s/403s.
- `stream()`/`stream_fills()` raise `ProviderAuthError` (`app/core/exceptions.py`) on any auth/entitlement rejection - handshake-level or app-level, for both Alpaca and Bybit (including the deterministic case of simply not having Bybit keys configured, checked before any network call). `RecoveryService` backs this off for a full hour and logs/notifies only once per outage instead of retrying every 30s forever (that tight retry loop is what originally tripped a rate limit on the previous market data provider).
- None of this makes IEX-only data equivalent to full-tape intraday trading - it just means the engine runs without spamming errors while you decide whether/when to upgrade.

## Database

```bash
alembic upgrade head
```

## Run

```bash
uvicorn app.main:app --reload --no-access-log
```

The API serves on `http://localhost:8000`. Docs at `/docs`. The trading engine boots automatically on app startup (see `app/main.py` lifespan) - if the broker/DB aren't reachable yet, the API still serves and `/api/v1/health` reports what's down.

## Tests

```bash
pytest
```

## Strategies

| Name | File | Universe | Timeframe |
|---|---|---|---|
| `orb` | `strategies/orb.py` | Dynamic (top active, Alpaca) | 1-minute |
| `noise` | `strategies/noise.py` | SPY, QQQ | 1-minute |
| `bias` | `strategies/bias.py` | SPY, QQQ | 1-minute |
| `vwap_reversion` | `strategies/vwap_reversion.py` | SPY, QQQ | 5-minute |
| `gap_fill` | `strategies/gap_fill.py` | SPY, QQQ | 5-minute |
| `breadth_pullback` | `strategies/breadth_pullback.py` | SPY, QQQ | 5-minute |

Every strategy can be individually enabled/disabled/reloaded at runtime - `POST /api/v1/strategies/{name}/enable|disable|reload`, wired straight to `StrategyManager` (`app/services/strategy_manager.py`), and already surfaced as a toggle on the dashboard's Strategies page (fully data-driven off the strategy list, no per-strategy dashboard code).

Configuration for all six lives in `app/data/strategies.yaml`.

### Shared indicators (`app/core/indicators.py`)

`vwap_reversion`, `gap_fill`, and `breadth_pullback` all trade 5-minute candles built by resampling the engine's native 1-minute `NEW_CANDLE` stream (`BarResampler`, bucketed on session-open-aligned boundaries) rather than requiring a second live subscription - Alpaca's WebSocket only pushes 1-minute bars in real time; 5-minute history is fetched directly via REST where needed. Also here: `VWAPState` (session VWAP + volume-weighted std-dev bands) and Wilder's `adx()`/`atr()`.

### Partial exits

`gap_fill`'s 50%-at-75%-fill-then-breakeven exit needed generic partial-close support, so `OrderManager.close_position(..., fraction=0.5)` now tags the order `intent="partial_exit"`; `PositionManager` reduces the position instead of removing it; and `Strategy._on_order_filled`/`_on_position_closed` accumulate realized PnL across the partial + final legs so `TRADE_EXITED` reports one correct total (not just the last leg). Reusable by any future strategy needing scaled-out exits.

## Notable design decisions

- **Scanner universe selection**: ranks a dynamically-fetched candidate pool (Alpaca's most-actives screener, by volume) by premarket gap % and volume. There's no news/unusual-activity feed in the stack, so those filters from the spec are left as documented gaps rather than faked.
- **Risk Engine allocation model**: strategy allocation % and portfolio exposure % are both measured against position *notional* (qty × price) versus equity - a concrete, implementable reading of the spec's "ensure strategy has remaining capital."
- **Exits bypass the Risk Engine**: entries are risk-gated (`SIGNAL_GENERATED` → `RISK_APPROVED`); closes (stop/target brackets, time-based, partial, manual, emergency) go straight to the Order Manager since reducing a position never increases risk.
- **`TRADE_ENTERED`/`TRADE_EXITED`**: published by each strategy (via the shared `Strategy` base class), which is what the event catalogue implies by grouping them under "Strategy Events" and by the strategy lifecycle ("Manage Position → Complete Trade → Performance Logging").
- **`gap_fill`'s stop uses daily ATR(14), not intraday**: at the 09:35 decision point there's only one 5-minute bar of the current session - nowhere near enough for an intraday ATR(14).
