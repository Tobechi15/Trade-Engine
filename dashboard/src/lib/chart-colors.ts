// Validated dark-mode palette (see dataviz skill references/palette.md).
// Dashboard is dark-by-default, so chart code is written against the dark
// column throughout; these are concrete hex values (not CSS vars) because
// ECharts needs literal colors.
export const CHART = {
  surface: "#1a1a19",
  textPrimary: "#ffffff",
  textSecondary: "#c3c2b7",
  muted: "#898781",
  grid: "#2c2c2a",
  axis: "#383835",
  // Categorical slots 1-3 (validated all-pairs safe as a subset of 3)
  categorical: ["#3987e5", "#d95926", "#199e70"],
  // Status palette (fixed, not themed) - used for PnL sign / health states
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#e66767",
  neutral: "#383835",
} as const;

export const STRATEGY_COLORS: Record<string, string> = {
  orb: CHART.categorical[0],
  noise: CHART.categorical[1],
  bias: CHART.categorical[2],
};
