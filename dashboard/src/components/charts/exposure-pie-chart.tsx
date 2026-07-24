"use client";

import type { EChartsOption } from "echarts";

import { BaseChart } from "@/components/charts/base-chart";
import { CHART } from "@/lib/chart-colors";

export function ExposurePieChart({
  longExposure,
  shortExposure,
  cash,
}: {
  longExposure: number;
  shortExposure: number;
  cash: number;
}) {
  const data = [
    { name: "Long", value: longExposure, itemStyle: { color: CHART.good } },
    { name: "Short", value: shortExposure, itemStyle: { color: CHART.critical } },
    { name: "Cash", value: Math.max(cash, 0), itemStyle: { color: CHART.muted } },
  ].filter((d) => d.value > 0);

  const option: EChartsOption = {
    tooltip: { trigger: "item" },
    legend: {
      bottom: 0,
      textStyle: { color: CHART.textSecondary },
    },
    series: [
      {
        type: "pie",
        radius: ["45%", "70%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: CHART.surface, borderWidth: 2 },
        label: { color: CHART.textSecondary },
        data,
      },
    ],
  };

  return <BaseChart option={option} height={260} />;
}
