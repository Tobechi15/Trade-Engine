from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    strategy: Mapped[str] = mapped_column(String, index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    direction: Mapped[str] = mapped_column(String)  # long | short

    signal_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)

    risk_amount: Mapped[float] = mapped_column(Float, default=0.0)
    reward_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    r_multiple: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slippage: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    orders: Mapped[list["Order"]] = relationship(back_populates="trade")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    trade_id: Mapped[str | None] = mapped_column(ForeignKey("trades.id"), nullable=True)
    trade: Mapped["Trade | None"] = relationship(back_populates="orders")

    broker_order_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    strategy: Mapped[str] = mapped_column(String, index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    side: Mapped[str] = mapped_column(String)  # buy | sell
    order_type: Mapped[str] = mapped_column(String, default="market")

    quantity: Mapped[float] = mapped_column(Float)
    filled_quantity: Mapped[float] = mapped_column(Float, default=0.0)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    # pending | submitted | partially_filled | filled | cancelled | rejected

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class StrategyPerformance(Base):
    __tablename__ = "strategy_performance"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    strategy: Mapped[str] = mapped_column(String, unique=True, index=True)

    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    expectancy: Mapped[float] = mapped_column(Float, default=0.0)
    average_winner: Mapped[float] = mapped_column(Float, default=0.0)
    average_loser: Mapped[float] = mapped_column(Float, default=0.0)
    average_hold_time_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    average_slippage: Mapped[float] = mapped_column(Float, default=0.0)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RiskConfiguration(Base):
    __tablename__ = "risk_configuration"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    profile_name: Mapped[str] = mapped_column(String, default="Semi Aggressive")

    risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=1.25)
    daily_loss_limit_pct: Mapped[float] = mapped_column(Float, default=4.0)
    max_concurrent_positions: Mapped[int] = mapped_column(Integer, default=4)
    max_portfolio_exposure_pct: Mapped[float] = mapped_column(Float, default=80.0)
    max_strategy_allocation_pct: Mapped[float] = mapped_column(Float, default=50.0)
    max_spread_pct: Mapped[float] = mapped_column(Float, default=0.15)
    max_slippage_pct: Mapped[float] = mapped_column(Float, default=0.25)

    strategy_allocation: Mapped[dict] = mapped_column(JSON, default=dict)
    # e.g. {"orb": 50, "noise": 30, "bias": 20}

    trading_enabled: Mapped[bool] = mapped_column(default=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String, unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DailyStatistics(Base):
    __tablename__ = "daily_statistics"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    date: Mapped[str] = mapped_column(String, unique=True, index=True)  # YYYY-MM-DD (exchange date)

    starting_equity: Mapped[float] = mapped_column(Float, default=0.0)
    ending_equity: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    trades_count: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    category: Mapped[str] = mapped_column(String, index=True)
    # system | broker | market_data | strategy | orders | risk | recovery | performance
    level: Mapped[str] = mapped_column(String, index=True)  # INFO | WARNING | ERROR | CRITICAL
    message: Mapped[str] = mapped_column(String)
    strategy: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    context: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
