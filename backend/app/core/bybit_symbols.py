"""Symbol convention shared by both Bybit adapters (broker + market data).

Bybit TradFi lists US stocks/ETFs as USDT-settled linear perpetuals, e.g.
"SPY" trades as "SPYUSDT". The rest of the engine (strategies, risk engine,
DB, dashboard) only ever sees the plain ticker - this translation happens
at the Bybit API boundary only.
"""

SUFFIX = "USDT"


def to_bybit_symbol(ticker: str) -> str:
    return f"{ticker.upper()}{SUFFIX}"


def from_bybit_symbol(symbol: str) -> str:
    if symbol.endswith(SUFFIX):
        return symbol[: -len(SUFFIX)]
    return symbol
