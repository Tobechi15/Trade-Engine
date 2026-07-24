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

- `DATABASE_URL` - your Neon Postgres connection string (`postgresql+asyncpg://...`)
- `BYBIT_API_KEY` / `BYBIT_API_SECRET` - Bybit credentials, used for **both** execution and market data. Bybit TradFi (tokenized US stocks/ETFs) trades as USDT-settled linear perpetuals on the standard V5 API (`category=linear`, symbols like `SPYUSDT`) - confirmed against Bybit's TradFi announcements and API docs. Symbol translation (`SPY` ↔ `SPYUSDT`) happens only inside `app/core/bybit_symbols.py`, used by both adapters.
- `JWT_SECRET`, `OPERATOR_USERNAME`, `OPERATOR_PASSWORD` - dashboard login.

**Instrument coverage caveat**: as of mid-2026 Bybit TradFi lists only ~20 US stocks + a handful of ETFs/commodities (see `app/strategies/orb.py: DEFAULT_CANDIDATES`) - well short of the 30-40 symbol universe the ORB spec assumes, and Bybit TradFi perpetual volume won't resemble NYSE/Nasdaq consolidated tape volume. `universe_size` and `min_premarket_volume` in `app/data/strategies.yaml` are placeholders to retune once you've observed real volume on these instruments; check `GET /v5/market/instruments-info?category=linear` for the current list before relying on it.

## Database

```bash
alembic upgrade head
```

## Run

```bash
uvicorn app.main:app --reload
```

The API serves on `http://localhost:8000`. Docs at `/docs`. The trading engine boots automatically on app startup (see `app/main.py` lifespan) - if the broker/DB aren't reachable yet, the API still serves and `/api/v1/health` reports what's down.

## Tests

```bash
pytest
```

## Notable design decisions

- **Broker/market-data adapters**: real Bybit clients for both (not mocks), behind `BrokerInterface` / `MarketDataInterface` so either can be swapped later. One account/API key pair covers execution and market data.
- **Scanner universe selection**: ranks a configurable candidate pool (`app/strategies/orb.py: DEFAULT_CANDIDATES`) by premarket gap % and volume. There's no news/unusual-activity feed in the stack, so those filters from the spec are left as documented gaps rather than faked.
- **Risk Engine allocation model**: strategy allocation % and portfolio exposure % are both measured against position *notional* (qty × price) versus equity - a concrete, implementable reading of the spec's "ensure strategy has remaining capital."
- **Exits bypass the Risk Engine**: entries are risk-gated (`SIGNAL_GENERATED` → `RISK_APPROVED`); closes (stop/target brackets, time-based, manual, emergency) go straight to the Order Manager since flattening a position never increases risk.
- **`TRADE_ENTERED`/`TRADE_EXITED`**: published by each strategy (via the shared `Strategy` base class), which is what the event catalogue implies by grouping them under "Strategy Events" and by the strategy lifecycle ("Manage Position → Complete Trade → Performance Logging").
