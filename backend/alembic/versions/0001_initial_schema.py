"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-22

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("strategy", sa.String(), index=True),
        sa.Column("symbol", sa.String(), index=True),
        sa.Column("direction", sa.String()),
        sa.Column("signal_time", sa.DateTime(timezone=True)),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Float(), server_default="0"),
        sa.Column("risk_amount", sa.Float(), server_default="0"),
        sa.Column("reward_amount", sa.Float(), nullable=True),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("r_multiple", sa.Float(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("slippage", sa.Float(), nullable=True),
        sa.Column("commission", sa.Float(), nullable=True),
        sa.Column("exit_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("trade_id", sa.String(), sa.ForeignKey("trades.id"), nullable=True),
        sa.Column("broker_order_id", sa.String(), nullable=True, index=True),
        sa.Column("strategy", sa.String(), index=True),
        sa.Column("symbol", sa.String(), index=True),
        sa.Column("side", sa.String()),
        sa.Column("order_type", sa.String(), server_default="market"),
        sa.Column("quantity", sa.Float()),
        sa.Column("filled_quantity", sa.Float(), server_default="0"),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("stop_price", sa.Float(), nullable=True),
        sa.Column("take_profit_price", sa.Float(), nullable=True),
        sa.Column("avg_fill_price", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), index=True, server_default="pending"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "strategy_performance",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("strategy", sa.String(), unique=True, index=True),
        sa.Column("total_trades", sa.Integer(), server_default="0"),
        sa.Column("winning_trades", sa.Integer(), server_default="0"),
        sa.Column("losing_trades", sa.Integer(), server_default="0"),
        sa.Column("win_rate", sa.Float(), server_default="0"),
        sa.Column("profit_factor", sa.Float(), server_default="0"),
        sa.Column("sharpe_ratio", sa.Float(), server_default="0"),
        sa.Column("max_drawdown", sa.Float(), server_default="0"),
        sa.Column("expectancy", sa.Float(), server_default="0"),
        sa.Column("average_winner", sa.Float(), server_default="0"),
        sa.Column("average_loser", sa.Float(), server_default="0"),
        sa.Column("average_hold_time_seconds", sa.Float(), server_default="0"),
        sa.Column("average_slippage", sa.Float(), server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "risk_configuration",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("profile_name", sa.String(), server_default="Semi Aggressive"),
        sa.Column("risk_per_trade_pct", sa.Float(), server_default="1.25"),
        sa.Column("daily_loss_limit_pct", sa.Float(), server_default="4.0"),
        sa.Column("max_concurrent_positions", sa.Integer(), server_default="4"),
        sa.Column("max_portfolio_exposure_pct", sa.Float(), server_default="80.0"),
        sa.Column("max_strategy_allocation_pct", sa.Float(), server_default="50.0"),
        sa.Column("max_spread_pct", sa.Float(), server_default="0.15"),
        sa.Column("max_slippage_pct", sa.Float(), server_default="0.25"),
        sa.Column("strategy_allocation", sa.JSON(), nullable=True),
        sa.Column("trading_enabled", sa.Boolean(), server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "user_settings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("key", sa.String(), unique=True, index=True),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "daily_statistics",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("date", sa.String(), unique=True, index=True),
        sa.Column("starting_equity", sa.Float(), server_default="0"),
        sa.Column("ending_equity", sa.Float(), server_default="0"),
        sa.Column("realized_pnl", sa.Float(), server_default="0"),
        sa.Column("unrealized_pnl", sa.Float(), server_default="0"),
        sa.Column("trades_count", sa.Integer(), server_default="0"),
        sa.Column("winning_trades", sa.Integer(), server_default="0"),
        sa.Column("losing_trades", sa.Integer(), server_default="0"),
        sa.Column("max_drawdown", sa.Float(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("category", sa.String(), index=True),
        sa.Column("level", sa.String(), index=True),
        sa.Column("message", sa.String()),
        sa.Column("strategy", sa.String(), nullable=True, index=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), index=True, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("daily_statistics")
    op.drop_table("user_settings")
    op.drop_table("risk_configuration")
    op.drop_table("strategy_performance")
    op.drop_table("orders")
    op.drop_table("trades")
