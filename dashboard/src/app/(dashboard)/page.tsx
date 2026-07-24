"use client";

import { useMemo } from "react";
import { AlertTriangle } from "lucide-react";

import { StatCard } from "@/components/stat-card";
import { StatusBadge } from "@/components/layout/status-badge";
import { Pnl, formatCurrency } from "@/components/pnl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAnalyticsOverview,
  useEngineStatus,
  useHealth,
  useMonthlyReturns,
  useOpenOrders,
  usePortfolio,
  usePortfolioStatistics,
  usePositions,
  useScanner,
  useStrategies,
} from "@/hooks/use-api";

function currentMonthKey(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export default function OverviewPage() {
  const { data: engine } = useEngineStatus();
  const { data: health } = useHealth();
  const { data: portfolio } = usePortfolio();
  const { data: positions } = usePositions();
  const { data: openOrders } = useOpenOrders();
  const { data: strategies } = useStrategies();
  const { data: scanner } = useScanner();
  const { data: analytics } = useAnalyticsOverview();
  const { data: monthly } = useMonthlyReturns();
  const { data: dailyStats } = usePortfolioStatistics(7);

  const weeklyPnl = useMemo(() => (dailyStats ?? []).reduce((sum, d) => sum + d.realized_pnl, 0), [dailyStats]);
  const monthlyPnl = useMemo(
    () => monthly?.find((m) => m.month === currentMonthKey())?.pnl ?? 0,
    [monthly],
  );
  const todayPnl = (portfolio?.realized_pnl_today ?? 0) + (portfolio?.unrealized_pnl ?? 0);

  const topMovers = useMemo(() => {
    return [...(scanner ?? [])]
      .filter((r) => r.rvol !== null)
      .sort((a, b) => (b.rvol ?? 0) - (a.rvol ?? 0))
      .slice(0, 5);
  }, [scanner]);

  const activeStrategies = strategies?.filter((s) => s.enabled) ?? [];

  return (
    <div className="space-y-6">
      {engine?.status === "recovering" && (
        <div className="flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
          <AlertTriangle className="size-4" />
          Engine is recovering state - trading is paused until synchronization completes.
        </div>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold text-muted-foreground">System Health</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
          <HealthCard label="Broker" status={health?.broker} />
          <HealthCard label="Market Data" status={health?.market_data} />
          <HealthCard label="Database" status={health?.database} />
          <HealthCard label="Scheduler" status={health?.scheduler} />
          <HealthCard label="Engine" status={health?.engine} />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-muted-foreground">Performance Snapshot</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCard label="Today's PnL" value={<Pnl value={todayPnl} />} />
          <StatCard label="Weekly PnL" value={<Pnl value={weeklyPnl} />} />
          <StatCard label="Monthly PnL" value={<Pnl value={monthlyPnl} />} />
          <StatCard label="Current Drawdown" value={formatCurrency(analytics?.max_drawdown)} tone="warning" />
          <StatCard label="Open Positions" value={positions?.length ?? 0} />
          <StatCard label="Open Orders" value={openOrders?.length ?? 0} />
          <StatCard label="Winning Trades" value={analytics?.winning_trades ?? 0} tone="success" />
          <StatCard label="Losing Trades" value={analytics?.losing_trades ?? 0} tone="destructive" />
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Active Strategies</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {!strategies ? (
              <Skeleton className="h-16 w-full" />
            ) : activeStrategies.length === 0 ? (
              <p className="text-sm text-muted-foreground">No strategies enabled.</p>
            ) : (
              activeStrategies.map((s) => (
                <div key={s.name} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                  <span className="text-sm font-medium capitalize">{s.name}</span>
                  <StatusBadge label="" status="running" />
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Today&apos;s Top Movers (by RVOL)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {!scanner ? (
              <Skeleton className="h-16 w-full" />
            ) : topMovers.length === 0 ? (
              <p className="text-sm text-muted-foreground">No scanner data yet.</p>
            ) : (
              topMovers.map((row) => (
                <div key={row.symbol} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                  <span className="text-sm font-medium">{row.symbol}</span>
                  <span className="text-sm tabular-nums text-muted-foreground">
                    RVOL {row.rvol?.toFixed(2)}
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function HealthCard({ label, status }: { label: string; status?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs font-medium text-muted-foreground">{label}</div>
        <div className="mt-2">
          <StatusBadge label="" status={status ?? "unknown"} />
        </div>
      </CardContent>
    </Card>
  );
}
