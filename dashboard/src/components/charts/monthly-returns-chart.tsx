"use client";

import type { EChartsOption } from "echarts";

import { BaseChart } from "@/components/charts/base-chart";
import { CHART } from "@/lib/chart-colors";
import type { MonthlyReturn } from "@/lib/types";

export function MonthlyReturnsChart({ data }: { data: MonthlyReturn[] }) {
  const option: EChartsOption = {
    xAxis: {
      type: "category",
      data: data.map((d) => d.month),
      axisLine: { lineStyle: { color: CHART.axis } },
      axisLabel: { color: CHART.muted },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisLabel: { color: CHART.muted },
      splitLine: { lineStyle: { color: CHART.grid } },
    },
    series: [
      {
        name: "PnL",
        type: "bar",
        data: data.map((d) => ({
          value: d.pnl,
          itemStyle: { color: d.pnl >= 0 ? CHART.good : CHART.critical, borderRadius: [4, 4, 4, 4] },
        })),
        barMaxWidth: 32,
      },
    ],
  };

  return <BaseChart option={option} />;
}
