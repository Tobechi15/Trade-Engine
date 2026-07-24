"use client";

import { RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Pnl, formatPercent } from "@/components/pnl";
import { useStrategies, useStrategyActions, useStrategyMetrics } from "@/hooks/use-api";
import type { StrategySummary } from "@/lib/types";

function StrategyCard({ strategy }: { strategy: StrategySummary }) {
  const { data: metrics } = useStrategyMetrics(strategy.name);
  const { enable, disable, reload } = useStrategyActions();

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base capitalize">{strategy.name}</CardTitle>
        <div className="flex items-center gap-2">
          <Switch
            checked={strategy.enabled}
            onCheckedChange={(checked) =>
              checked ? enable.mutate(strategy.name) : disable.mutate(strategy.name)
            }
          />
          <Button size="icon-sm" variant="outline" onClick={() => reload.mutate(strategy.name)} disabled={reload.isPending}>
            <RefreshCw className={reload.isPending ? "size-3.5 animate-spin" : "size-3.5"} />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <Metric label="Trades" value={metrics?.total_trades ?? "-"} />
          <Metric label="Win Rate" value={formatPercent(metrics?.win_rate)} />
          <Metric
            label="Total PnL"
            value={<Pnl value={metrics ? metrics.expectancy * metrics.total_trades : undefined} />}
          />
          <Metric label="Expectancy" value={<Pnl value={metrics?.expectancy} />} />
        </div>

        <div>
          <div className="mb-1.5 text-xs font-medium text-muted-foreground">Configuration</div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(strategy.config)
              .filter(([key]) => key !== "enabled")
              .map(([key, value]) => (
                <Badge key={key} variant="secondary" className="font-mono text-[11px]">
                  {key}: {Array.isArray(value) ? value.join(",") : String(value)}
                </Badge>
              ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-medium tabular-nums">{value}</div>
    </div>
  );
}

export default function StrategiesPage() {
  const { data: strategies, isLoading } = useStrategies();

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Strategies</h1>
      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-56 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {strategies?.map((s) => (
            <StrategyCard key={s.name} strategy={s} />
          ))}
        </div>
      )}
    </div>
  );
}
