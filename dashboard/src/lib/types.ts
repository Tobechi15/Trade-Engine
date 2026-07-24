export interface HealthStatus {
  engine: string;
  broker: string;
  market_data: string;
  database: string;
  scheduler: string;
}

export interface EngineStatusPayload {
  status: "stopped" | "starting" | "running" | "paused" | "recovering";
  version: string;
  uptime_seconds: number;
  broker: string;
  market_data: string;
  scheduler: string;
}

export interface StrategySummary {
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
}

export interface StrategyMetrics {
  strategy: string;
  total_trades: number;
  winning_trades?: number;
  losing_trades?: number;
  win_rate: number;
  profit_factor?: number;
  sharpe_ratio?: number;
  max_drawdown?: number;
  expectancy: number;
  average_winner?: number;
  average_loser?: number;
  average_hold_time_seconds?: number;
}

export interface ScannerRow {
  symbol: string;
  price: number | null;
  spread_pct: number | null;
  rvol: number | null;
  opening_range: { high: number; low: number; midpoint: number } | null;
  status: "watching" | "qualified" | "ignored" | "entered" | "exited";
}

export interface OrderRow {
  order_id: string;
  broker_order_id: string | null;
  strategy: string;
  symbol: string;
  side: string;
  quantity: number;
  filled_quantity: number;
  entry_price: number | null;
  stop_price: number | null;
  take_profit_price: number | null;
  status: string;
  created_at: string | null;
}

export interface PositionRow {
  symbol: string;
  strategy: string;
  direction: "long" | "short";
  quantity: number;
  entry_price: number;
  current_price: number;
  opened_at: string;
}

export interface PortfolioSnapshot {
  equity: number;
  buying_power: number;
  cash: number;
  margin_used: number;
  unrealized_pnl: number;
  realized_pnl_today: number;
  open_positions: number;
  updated_at: string | null;
  long_exposure: number;
  short_exposure: number;
  total_exposure_pct: number;
}

export interface DailyStatRow {
  date: string;
  starting_equity: number;
  ending_equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  trades_count: number;
  winning_trades: number;
  losing_trades: number;
  max_drawdown: number;
}

export interface RiskSettings {
  risk_per_trade_pct: number;
  daily_loss_limit_pct: number;
  max_concurrent_positions: number;
  max_portfolio_exposure_pct: number;
  max_strategy_allocation_pct: number;
  max_spread_pct: number;
  max_slippage_pct: number;
  trading_enabled: boolean;
  allocation: Record<string, number>;
}

export interface RiskStatus {
  trading_enabled: boolean;
  daily_loss_hit: boolean;
  daily_realized_pnl: number;
  remaining_daily_loss_pct: number | null;
  current_positions: number;
  max_positions: number;
  portfolio_notional: number;
  disabled_strategies: string[];
}

export interface AnalyticsOverview {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  max_drawdown: number;
  expectancy: number;
  average_winner: number;
  average_loser: number;
  average_hold_time_seconds: number;
}

export interface EquityPoint {
  time: string;
  equity: number;
}

export interface MonthlyReturn {
  month: string;
  pnl: number;
}

export interface TradeRow {
  id: string;
  strategy: string;
  symbol: string;
  direction: string;
  entry_price: number | null;
  exit_price: number | null;
  quantity: number;
  pnl: number | null;
  r_multiple: number | null;
  exit_reason: string | null;
  entry_time: string | null;
  exit_time: string | null;
}

export interface LogRow {
  id: string;
  time: string | null;
  category: string;
  level: string;
  message: string;
  strategy: string | null;
  context: Record<string, unknown>;
}

export interface NotificationRow {
  id: string;
  level: "info" | "warning" | "error" | "critical";
  message: string;
  event_type: string;
  source: string;
  created_at: string;
  read: boolean;
}

export interface RecoveryStatus {
  broker: string;
  market_data: string;
  database: string;
  scheduler: string;
  reconnect_attempts: Record<string, number>;
}

export interface RecoveryHistoryItem {
  timestamp: string;
  component: string;
  failure_type: string;
  recovery_duration_seconds: number;
  result: string;
}
