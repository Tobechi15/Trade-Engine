from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.event_bus import EventBus
from app.core.events import EventType
from app.core.market_state import MarketState
from app.db.base import SessionLocal
from app.db.models import RiskConfiguration
from sqlalchemy import select

logger = logging.getLogger("risk")


@dataclass(slots=True)
class RiskSettings:
    risk_per_trade_pct: float = 1.25
    daily_loss_limit_pct: float = 4.0
    max_concurrent_positions: int = 4
    max_portfolio_exposure_pct: float = 80.0
    max_strategy_allocation_pct: float = 50.0
    max_spread_pct: float = 0.15
    max_slippage_pct: float = 0.25
    strategy_allocation: dict[str, float] = field(
        default_factory=lambda: {
            "orb": 30.0,
            "noise": 15.0,
            "bias": 10.0,
            "vwap_reversion": 15.0,
            "gap_fill": 15.0,
            "breadth_pullback": 15.0,
        }
    )
    trading_enabled: bool = True
    disabled_strategies: set[str] = field(default_factory=set)


@dataclass(slots=True)
class RiskDecision:
    approved: bool
    reason: str | None = None
    rejected_rule: str | None = None
    quantity: float | None = None


class RiskEngine:
    """Every order must pass through here. No strategy may submit orders
    directly to the broker. This is the last line of defense for capital
    preservation, per RISK_ENGINE.md."""

    def __init__(self, event_bus: EventBus, market_state: MarketState) -> None:
        self._bus = event_bus
        self._state = market_state
        self.settings = RiskSettings()
        self._daily_starting_equity: float = 0.0
        self._daily_realized_pnl: float = 0.0
        self._daily_loss_hit = False

        self._bus.subscribe(EventType.SIGNAL_GENERATED, self._on_signal)
        self._bus.subscribe(EventType.MARKET_OPEN, self._on_market_open)
        self._bus.subscribe(EventType.TRADE_EXITED, self._on_trade_exited)

    async def load_settings(self) -> None:
        async with SessionLocal() as session:
            row = (await session.execute(select(RiskConfiguration))).scalars().first()
            if row is None:
                row = RiskConfiguration(strategy_allocation=self.settings.strategy_allocation)
                session.add(row)
                await session.commit()
                await session.refresh(row)
            self.settings = RiskSettings(
                risk_per_trade_pct=row.risk_per_trade_pct,
                daily_loss_limit_pct=row.daily_loss_limit_pct,
                max_concurrent_positions=row.max_concurrent_positions,
                max_portfolio_exposure_pct=row.max_portfolio_exposure_pct,
                max_strategy_allocation_pct=row.max_strategy_allocation_pct,
                max_spread_pct=row.max_spread_pct,
                max_slippage_pct=row.max_slippage_pct,
                # Merge, not replace: a persisted row created before a
                # strategy existed must not silently zero out its
                # allocation forever - RiskEngine._on_signal() treats a
                # missing key as 0% allowed notional, which rejects every
                # signal from that strategy with no visible error beyond
                # "allocation exhausted" (confirmed: this is exactly what
                # happened to vwap_reversion/gap_fill/breadth_pullback
                # after they were added later than this table's first
                # row). Values explicitly set in the row still win.
                strategy_allocation={**self.settings.strategy_allocation, **(row.strategy_allocation or {})},
                trading_enabled=row.trading_enabled,
            )

    async def save_settings(self) -> None:
        async with SessionLocal() as session:
            row = (await session.execute(select(RiskConfiguration))).scalars().first()
            if row is None:
                row = RiskConfiguration()
                session.add(row)
            row.risk_per_trade_pct = self.settings.risk_per_trade_pct
            row.daily_loss_limit_pct = self.settings.daily_loss_limit_pct
            row.max_concurrent_positions = self.settings.max_concurrent_positions
            row.max_portfolio_exposure_pct = self.settings.max_portfolio_exposure_pct
            row.max_strategy_allocation_pct = self.settings.max_strategy_allocation_pct
            row.max_spread_pct = self.settings.max_spread_pct
            row.max_slippage_pct = self.settings.max_slippage_pct
            row.strategy_allocation = self.settings.strategy_allocation
            row.trading_enabled = self.settings.trading_enabled
            await session.commit()

    async def _on_market_open(self, _event) -> None:
        self._daily_starting_equity = self._state.account_snapshot.equity
        self._daily_realized_pnl = 0.0
        self._daily_loss_hit = False

    async def _on_trade_exited(self, event) -> None:
        pnl = float(event.payload.get("pnl", 0.0) or 0.0)
        self._daily_realized_pnl += pnl
        if self._daily_starting_equity <= 0:
            return
        loss_pct = -self._daily_realized_pnl / self._daily_starting_equity * 100
        if loss_pct >= self.settings.daily_loss_limit_pct and not self._daily_loss_hit:
            self._daily_loss_hit = True
            await self._bus.publish(
                EventType.DAILY_LOSS_HIT,
                source="risk_engine",
                payload={"loss_pct": loss_pct, "limit_pct": self.settings.daily_loss_limit_pct},
            )

    def _strategy_notional(self, strategy: str) -> float:
        return sum(
            abs(p.get("quantity", 0) * p.get("current_price", p.get("entry_price", 0)))
            for p in self._state.active_positions.values()
            if p.get("strategy") == strategy
        )

    def _portfolio_notional(self) -> float:
        return sum(
            abs(p.get("quantity", 0) * p.get("current_price", p.get("entry_price", 0)))
            for p in self._state.active_positions.values()
        )

    def evaluate(self, signal: dict) -> RiskDecision:
        """Runs the full validation pipeline against a signal payload.

        Expected signal keys: strategy, symbol, direction (long|short),
        entry_price, stop_price, take_profit_price (optional),
        allow_duplicate (optional bool).
        """
        strategy = signal["strategy"]
        symbol = signal["symbol"]
        entry_price = float(signal["entry_price"])
        stop_price = float(signal["stop_price"])

        # 1. Trading enabled
        if not self.settings.trading_enabled:
            return RiskDecision(False, "Trading disabled", "trading_enabled")
        if self._daily_loss_hit:
            return RiskDecision(False, "Daily loss limit reached", "daily_loss")

        # 2. Market open
        from app.core.market_calendar import market_calendar

        if not market_calendar.is_open():
            return RiskDecision(False, "Market closed", "market_open")

        # 3. Strategy enabled
        if strategy in self.settings.disabled_strategies:
            return RiskDecision(False, f"Strategy {strategy} disabled", "strategy_enabled")

        # 4. Daily loss (redundant guard, in case flag not yet set this tick)
        if self._daily_starting_equity > 0:
            loss_pct = -self._daily_realized_pnl / self._daily_starting_equity * 100
            if loss_pct >= self.settings.daily_loss_limit_pct:
                return RiskDecision(False, "Daily loss limit reached", "daily_loss")

        # 5. Maximum positions
        if len(self._state.active_positions) >= self.settings.max_concurrent_positions:
            return RiskDecision(False, "Maximum concurrent positions reached", "max_positions")

        # Position sizing
        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            return RiskDecision(False, "Invalid stop distance", "position_sizing")
        equity = self._state.account_snapshot.equity or self._daily_starting_equity
        if equity <= 0:
            return RiskDecision(False, "No equity available", "position_sizing")
        risk_amount = equity * (self.settings.risk_per_trade_pct / 100)
        quantity = risk_amount / stop_distance
        notional = quantity * entry_price

        # 6. Strategy allocation
        allocation_pct = self.settings.strategy_allocation.get(strategy, 0.0)
        allowed_notional = equity * (allocation_pct / 100)
        if self._strategy_notional(strategy) + notional > allowed_notional:
            return RiskDecision(False, f"{strategy} allocation exhausted", "strategy_allocation")

        # 7. Portfolio exposure
        max_exposure_notional = equity * (self.settings.max_portfolio_exposure_pct / 100)
        if self._portfolio_notional() + notional > max_exposure_notional:
            return RiskDecision(False, "Portfolio exposure limit exceeded", "portfolio_exposure")

        # 8. Spread filter
        quote = self._state.live_quotes.get(symbol)
        if quote is not None and quote.price > 0:
            spread_pct = (quote.ask - quote.bid) / quote.price * 100
            if spread_pct > self.settings.max_spread_pct:
                return RiskDecision(False, f"Spread {spread_pct:.3f}% exceeds max", "spread_filter")

            # 9. Slippage filter (heuristic: half-spread as expected slippage)
            estimated_slippage_pct = spread_pct / 2
            if estimated_slippage_pct > self.settings.max_slippage_pct:
                return RiskDecision(False, "Estimated slippage exceeds max", "slippage_filter")

        # 10. Margin check
        buying_power = self._state.account_snapshot.buying_power
        if buying_power and notional > buying_power:
            return RiskDecision(False, "Insufficient buying power", "margin_check")

        # 11. Duplicate position
        if symbol in self._state.active_positions and not signal.get("allow_duplicate", False):
            return RiskDecision(False, f"Position already open in {symbol}", "duplicate_position")

        return RiskDecision(True, quantity=quantity)

    async def _on_signal(self, event) -> None:
        signal = event.payload
        decision = self.evaluate(signal)
        if decision.approved:
            await self._bus.publish(
                EventType.RISK_APPROVED,
                source="risk_engine",
                payload={**signal, "quantity": decision.quantity},
            )
        else:
            logger.info(
                "signal rejected",
                extra={
                    "strategy": signal.get("strategy"),
                    "symbol": signal.get("symbol"),
                    "reason": decision.reason,
                    "rule": decision.rejected_rule,
                },
            )
            await self._bus.publish(
                EventType.RISK_REJECTED,
                source="risk_engine",
                payload={**signal, "reason": decision.reason, "rejected_rule": decision.rejected_rule},
            )
            if decision.rejected_rule == "portfolio_exposure":
                await self._bus.publish(EventType.MAX_EXPOSURE_HIT, source="risk_engine", payload=signal)

    # --- Emergency controls (dashboard) ---
    def pause_trading(self) -> None:
        self.settings.trading_enabled = False

    def resume_trading(self) -> None:
        self.settings.trading_enabled = True

    def disable_strategy(self, strategy: str) -> None:
        self.settings.disabled_strategies.add(strategy)

    def enable_strategy(self, strategy: str) -> None:
        self.settings.disabled_strategies.discard(strategy)

    def status(self) -> dict:
        remaining_loss_pct = None
        if self._daily_starting_equity > 0:
            loss_pct = max(0.0, -self._daily_realized_pnl / self._daily_starting_equity * 100)
            remaining_loss_pct = max(0.0, self.settings.daily_loss_limit_pct - loss_pct)
        return {
            "trading_enabled": self.settings.trading_enabled,
            "daily_loss_hit": self._daily_loss_hit,
            "daily_realized_pnl": self._daily_realized_pnl,
            "remaining_daily_loss_pct": remaining_loss_pct,
            "current_positions": len(self._state.active_positions),
            "max_positions": self.settings.max_concurrent_positions,
            "portfolio_notional": self._portfolio_notional(),
            "disabled_strategies": sorted(self.settings.disabled_strategies),
        }
