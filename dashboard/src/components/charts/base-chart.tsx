"use client";

import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";

import { CHART } from "@/lib/chart-colors";

export function BaseChart({ option, height = 280 }: { option: EChartsOption; height?: number }) {
  const merged: EChartsOption = {
    backgroundColor: "transparent",
    textStyle: { color: CHART.textSecondary, fontFamily: "inherit" },
    grid: { left: 48, right: 16, top: 24, bottom: 32, containLabel: true },
    tooltip: {
      trigger: "axis",
      backgroundColor: CHART.surface,
      borderColor: CHART.axis,
      textStyle: { color: CHART.textPrimary },
    },
    ...option,
  };

  return <ReactECharts option={merged} style={{ height }} notMerge lazyUpdate opts={{ renderer: "svg" }} />;
}
