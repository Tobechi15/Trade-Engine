from __future__ import annotations

import logging
import statistics

from app.core.event_bus import Event
from app.core.events import EventType
from app.core.indicators import atr as _atr
from app.core.market_state import NoiseEnvelope
from app.core.time_service import TimeService
from app.services.market_data_service import MarketDataService
from app.strategies.base import Strategy

logger = logging.getLogger("strategy")


class NoiseBoundaryBreakout(Strategy):
    name = "noise"

    def __init__(self, *args, market_data_service: MarketDataService, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._market_data = market_data_service
        self._universe: list[str] = self.config.get("universe", ["SPY", "QQQ"])
        self._atr_period: int = self.config.get("atr_period", 14)
        self._envelope_width: float = self.config.get("envelope_width", 2.0)
        self._atr_target_multiplier: float = self.config.get("atr_target_multiplier", 2.0)
        self._max_trades: int = self.config.get("maximum_trades", 6)
        self._trades_today = 0

    def subscribed_events(self) -> list[EventType]:
        return [EventType.NEW_CANDLE, EventType.MARKET_OPEN, EventType.MARKET_CLOSE]

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        await self._build_envelopes()
        await self._market_data.start_streaming(self._universe)

    async def stop(self) -> None:
        pass

    async def _build_envelopes(self) -> None:
        history = await self._market_data.get_history(self._universe, days=14)
        for symbol, bars in history.items():
            if len(bars) < self._atr_period + 1:
                continue
            closes = [b.close for b in bars]
            mean = statistics.fmean(closes)
            std_dev = statistics.pstdev(closes) if len(closes) > 1 else 0.0
            atr = _atr(bars, self._atr_period)
            self._state.noise_boundaries[symbol] = NoiseEnvelope(
                symbol=symbol,
                mean=mean,
                std_dev=std_dev,
                atr=atr,
                upper=mean + self._envelope_width * std_dev,
                lower=mean - self._envelope_width * std_dev,
                updated_at=TimeService.now_utc(),
            )
            self._state.atr[symbol] = atr
        logger.info("noise envelopes built for %s", list(self._state.noise_boundaries.keys()))

    async def on_event(self, event: Event) -> None:
        if event.event_type == EventType.MARKET_OPEN:
            self._trades_today = 0
            await self._build_envelopes()
        elif event.event_type == EventType.NEW_CANDLE:
            await self._on_candle(event.payload)
        elif event.event_type == EventType.MARKET_CLOSE:
            for symbol, position in list(self._state.active_positions.items()):
                if position.get("strategy") == self.name:
                    await self.close_position(symbol, reason="eod_exit")

    async def _on_candle(self, payload: dict) -> None:
        symbol = payload["symbol"]
        envelope = self._state.noise_boundaries.get(symbol)
        if envelope is None or symbol not in self._universe:
            return
        price = payload["close"]

        position = self._state.active_positions.get(symbol)
        if position and position.get("strategy") == self.name:
            inside = envelope.lower <= price <= envelope.upper
            if inside:
                await self.close_position(symbol, reason="return_to_envelope")
            return

        if self._trades_today >= self._max_trades or symbol in self._open_trades:
            return

        direction: str | None = None
        if price > envelope.upper:
            direction = "long"
        elif price < envelope.lower:
            direction = "short"
        if direction is None:
            return

        atr = self._state.atr.get(symbol, envelope.atr) or (price * 0.005)
        stop_price = envelope.mean
        take_profit = price + atr * self._atr_target_multiplier if direction == "long" else price - atr * self._atr_target_multiplier

        await self.publish_signal(
            symbol=symbol, direction=direction, entry_price=price, stop_price=stop_price, take_profit_price=take_profit
        )
        self._trades_today += 1

    async def recover_state(self) -> None:
        await self._build_envelopes()
        await self._market_data.start_streaming(self._universe)
        logger.info("noise state recovered")
