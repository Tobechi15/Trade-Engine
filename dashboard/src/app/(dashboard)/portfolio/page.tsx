"use client";

import type { ColumnDef } from "@tanstack/react-table";

import { StatCard } from "@/components/stat-card";
import { DataTable } from "@/components/data-table";
import { Pnl, formatCurrency, formatPercent } from "@/components/pnl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExposurePieChart } from "@/components/charts/exposure-pie-chart";
import { usePortfolio, usePositions, useRiskCurrent } from "@/hooks/use-api";
import type { PositionRow } from "@/lib/types";

const columns: ColumnDef<PositionRow, unknown>[] = [
  { accessorKey: "symbol", header: "Ticker" },
  { accessorKey: "strategy", header: "Strategy", cell: ({ row }) => <span className="capitalize">{row.original.strategy}</span> },
  {
    accessorKey: "direction",
    header: "Direction",
    cell: ({ row }) => (
      <span className={row.original.direction === "long" ? "text-success" : "text-destructive"}>
        {row.original.direction.toUpperCase()}
      </span>
    ),
  },
  { accessorKey: "quantity", header: "Quantity" },
  { accessorKey: "entry_price", header: "Entry", cell: ({ row }) => `$${row.original.entry_price?.toFixed(2)}` },
  { accessorKey: "current_price", header: "Current", cell: ({ row }) => `$${row.original.current_price?.toFixed(2)}` },
  {
    id: "pnl",
    header: "PnL",
    cell: ({ row }) => {
      const { direction, quantity, entry_price, current_price } = row.original;
      const sign = direction === "long" ? 1 : -1;
      const pnl = sign * (current_price - entry_price) * quantity;
      return <Pnl value={pnl} />;
    },
  },
  {
    accessorKey: "opened_at",
    header: "Duration",
    cell: ({ row }) => {
      const opened = new Date(row.original.opened_at).getTime();
      const minutes = Math.max(0, Math.round((Date.now() - opened) / 60000));
      return `${minutes}m`;
    },
  },
];

export default function PortfolioPage() {
  const { data: portfolio } = usePortfolio();
  const { data: positions, isLoading } = usePositions();
  const { data: risk } = useRiskCurrent();

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">Portfolio</h1>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Equity" value={formatCurrency(portfolio?.equity)} />
        <StatCard label="Buying Power" value={formatCurrency(portfolio?.buying_power)} />
        <StatCard label="Available Cash" value={formatCurrency(portfolio?.cash)} />
        <StatCard label="Margin Used" value={formatCurrency(portfolio?.margin_used)} />
        <StatCard label="Open Risk (Notional)" value={formatCurrency(risk?.portfolio_notional)} />
        <StatCard label="Portfolio Exposure" value={formatPercent(portfolio?.total_exposure_pct)} />
        <StatCard label="Realized PnL (Today)" value={<Pnl value={portfolio?.realized_pnl_today} />} />
        <StatCard label="Unrealized PnL" value={<Pnl value={portfolio?.unrealized_pnl} />} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm">Open Positions</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-6 text-sm text-muted-foreground">Loading positions...</div>
            ) : (
              <DataTable columns={columns} data={positions ?? []} emptyMessage="No open positions." />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Exposure</CardTitle>
          </CardHeader>
          <CardContent>
            <ExposurePieChart
              longExposure={portfolio?.long_exposure ?? 0}
              shortExposure={portfolio?.short_exposure ?? 0}
              cash={portfolio?.cash ?? 0}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
