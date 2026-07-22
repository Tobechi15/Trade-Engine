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
- `BYBIT_API_KEY` / `BYBIT_API_SECRET` - Bybit TradFi credentials. **Verify `BYBIT_BASE_URL`, `BYBIT_WS_URL`, and the `CATEGORY` constant in `app/brokers/bybit_tradfi.py` against the current Bybit TradFi API docs before live trading** - TradFi (tokenized equities) is a newer product line and this adapter implements Bybit's standard V5 signing scheme with best-effort endpoint paths, flagged with `TODO` comments.
- `ALPACA_API_KEY` / `ALPACA_API_SECRET` - Alpaca market data credentials.
- `JWT_SECRET`, `OPERATOR_USERNAME`, `OPERATOR_PASSWORD` - dashboard login.

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

- **Broker/market-data adapters**: real Bybit TradFi + Alpaca clients (not mocks), behind `BrokerInterface` / `MarketDataInterface` so either can be swapped later.
- **Scanner universe selection**: ranks a configurable candidate pool (`app/strategies/orb.py: DEFAULT_CANDIDATES`) by premarket gap % and volume. There's no news/unusual-activity feed in the stack, so those filters from the spec are left as documented gaps rather than faked.
- **Risk Engine allocation model**: strategy allocation % and portfolio exposure % are both measured against position *notional* (qty × price) versus equity - a concrete, implementable reading of the spec's "ensure strategy has remaining capital."
- **Exits bypass the Risk Engine**: entries are risk-gated (`SIGNAL_GENERATED` → `RISK_APPROVED`); closes (stop/target brackets, time-based, manual, emergency) go straight to the Order Manager since flattening a position never increases risk.
- **`TRADE_ENTERED`/`TRADE_EXITED`**: published by each strategy (via the shared `Strategy` base class), which is what the event catalogue implies by grouping them under "Strategy Events" and by the strategy lifecycle ("Manage Position → Complete Trade → Performance Logging").
