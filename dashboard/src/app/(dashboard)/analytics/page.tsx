"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { StatCard } from "@/components/stat-card";
import { DataTable } from "@/components/data-table";
import { Pnl, formatPercent } from "@/components/pnl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EquityCurveChart } from "@/components/charts/equity-curve-chart";
import { MonthlyReturnsChart } from "@/components/charts/monthly-returns-chart";
import { TradeDistributionChart } from "@/components/charts/trade-distribution-chart";
import {
  useAnalyticsOverview,
  useEquityCurve,
  useMonthlyReturns,
  useStrategies,
  useStrategyMetrics,
  useTrades,
} from "@/hooks/use-api";
import type { TradeRow } from "@/lib/types";

const tradeColumns: ColumnDef<TradeRow, unknown>[] = [
  { accessorKey: "strategy", header: "Strategy", cell: ({ row }) => <span className="capitalize">{row.original.strategy}</span> },
  { accessorKey: "symbol", header: "Ticker" },
  { accessorKey: "direction", header: "Direction" },
  { accessorKey: "quantity", header: "Qty" },
  { accessorKey: "entry_price", header: "Entry", cell: ({ row }) => row.original.entry_price?.toFixed(2) ?? "-" },
  { accessorKey: "exit_price", header: "Exit", cell: ({ row }) => row.original.exit_price?.toFixed(2) ?? "-" },
  { accessorKey: "pnl", header: "PnL", cell: ({ row }) => <Pnl value={row.original.pnl} /> },
  { accessorKey: "r_multiple", header: "R", cell: ({ row }) => (row.original.r_multiple != null ? `${row.original.r_multiple.toFixed(2)}R` : "-") },
  { accessorKey: "exit_reason", header: "Exit Reason" },
];

function StrategyComparisonRow({ name }: { name: string }) {
  const { data } = useStrategyMetrics(name);
  return (
    <tr className="border-t border-border">
      <td className="px-3 py-2 font-medium capitalize">{name}</td>
      <td className="px-3 py-2 tabular-nums">{data?.total_trades ?? "-"}</td>
      <td className="px-3 py-2 tabular-nums">{formatPercent(data?.win_rate)}</td>
      <td className="px-3 py-2 tabular-nums">{data ? (data.expectancy * data.total_trades).toFixed(2) : "-"}</td>
      <td className="px-3 py-2 tabular-nums">{data?.profit_factor?.toFixed(2) ?? "-"}</td>
      <td className="px-3 py-2 tabular-nums">{data?.max_drawdown?.toFixed(2) ?? "-"}</td>
    </tr>
  );
}

export default function AnalyticsPage() {
  const { data: overview } = useAnalyticsOverview();
  const { data: equityCurve } = useEquityCurve();
  const { data: monthly } = useMonthlyReturns();
  const { data: trades } = useTrades();
  const { data: strategies } = useStrategies();

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">Analytics</h1>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatCard label="Win Rate" value={formatPercent(overview?.win_rate)} />
        <StatCard label="Profit Factor" value={overview?.profit_factor?.toFixed(2) ?? "-"} />
        <StatCard label="Sharpe Ratio" value={overview?.sharpe_ratio?.toFixed(2) ?? "-"} />
        <StatCard label="Max Drawdown" value={overview?.max_drawdown?.toFixed(2) ?? "-"} tone="warning" />
        <StatCard label="Expectancy" value={<Pnl value={overview?.expectancy} />} />
        <StatCard label="Average Winner" value={<Pnl value={overview?.average_winner} />} />
        <StatCard label="Average Loser" value={<Pnl value={overview?.average_loser} />} />
        <StatCard
          label="Avg Hold Time"
          value={overview ? `${Math.round(overview.average_hold_time_seconds / 60)}m` : "-"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Equity Curve</CardTitle>
          </CardHeader>
          <CardContent>
            <EquityCurveChart data={equityCurve ?? []} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Monthly Returns</CardTitle>
          </CardHeader>
          <CardContent>
            <MonthlyReturnsChart data={monthly ?? []} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Strategy Comparison</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground">
                <th className="px-3 py-2 font-medium">Strategy</th>
                <th className="px-3 py-2 font-medium">Trades</th>
                <th className="px-3 py-2 font-medium">Win Rate</th>
                <th className="px-3 py-2 font-medium">PnL</th>
                <th className="px-3 py-2 font-medium">Profit Factor</th>
                <th className="px-3 py-2 font-medium">Max Drawdown</th>
              </tr>
            </thead>
            <tbody>
              {strategies?.map((s) => (
                <StrategyComparisonRow key={s.name} name={s.name} />
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Trade Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          <TradeDistributionChart trades={trades ?? []} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Recent Trades</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <DataTable columns={tradeColumns} data={trades ?? []} emptyMessage="No trades yet." />
        </CardContent>
      </Card>
    </div>
  );
}
