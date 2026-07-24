"use client";

import type { EChartsOption } from "echarts";

import { BaseChart } from "@/components/charts/base-chart";
import { CHART } from "@/lib/chart-colors";
import type { EquityPoint } from "@/lib/types";

export function EquityCurveChart({ data }: { data: EquityPoint[] }) {
  const option: EChartsOption = {
    xAxis: {
      type: "category",
      data: data.map((d) => d.time),
      axisLine: { lineStyle: { color: CHART.axis } },
      axisLabel: { color: CHART.muted, formatter: (v: string) => new Date(v).toLocaleDateString() },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisLabel: { color: CHART.muted },
      splitLine: { lineStyle: { color: CHART.grid } },
    },
    series: [
      {
        name: "Equity",
        type: "line",
        data: data.map((d) => d.equity),
        showSymbol: false,
        lineStyle: { width: 2, color: CHART.categorical[0] },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: `${CHART.categorical[0]}55` },
              { offset: 1, color: `${CHART.categorical[0]}00` },
            ],
          },
        },
      },
    ],
  };

  return <BaseChart option={option} />;
}
