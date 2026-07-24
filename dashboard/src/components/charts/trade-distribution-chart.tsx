"use client";

import { useMemo } from "react";
import type { EChartsOption } from "echarts";

import { BaseChart } from "@/components/charts/base-chart";
import { CHART } from "@/lib/chart-colors";
import type { TradeRow } from "@/lib/types";

const BUCKET_COUNT = 12;

export function TradeDistributionChart({ trades }: { trades: TradeRow[] }) {
  const { labels, counts } = useMemo(() => {
    const pnls = trades.map((t) => t.pnl ?? 0).filter((v) => Number.isFinite(v));
    if (pnls.length === 0) return { labels: [], counts: [] };
    const min = Math.min(...pnls, 0);
    const max = Math.max(...pnls, 0);
    const span = max - min || 1;
    const bucketSize = span / BUCKET_COUNT;
    const buckets = new Array(BUCKET_COUNT).fill(0);
    for (const pnl of pnls) {
      const idx = Math.min(BUCKET_COUNT - 1, Math.floor((pnl - min) / bucketSize));
      buckets[Math.max(0, idx)] += 1;
    }
    const bucketLabels = buckets.map((_, i) => {
      const start = min + i * bucketSize;
      return start >= 0 ? `+${start.toFixed(0)}` : start.toFixed(0);
    });
    return { labels: bucketLabels, counts: buckets };
  }, [trades]);

  const option: EChartsOption = {
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { lineStyle: { color: CHART.axis } },
      axisLabel: { color: CHART.muted, rotate: 45 },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisLabel: { color: CHART.muted },
      splitLine: { lineStyle: { color: CHART.grid } },
    },
    series: [
      {
        name: "Trades",
        type: "bar",
        data: counts.map((c, i) => ({
          value: c,
          itemStyle: { color: labels[i]?.startsWith("+") ? CHART.good : CHART.critical, borderRadius: [4, 4, 0, 0] },
        })),
        barMaxWidth: 28,
      },
    ],
  };

  return <BaseChart option={option} />;
}
