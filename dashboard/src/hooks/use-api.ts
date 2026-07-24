"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api-client";
import { useAuthStore } from "@/lib/auth-store";
import type {
  AnalyticsOverview,
  EngineStatusPayload,
  EquityPoint,
  HealthStatus,
  LogRow,
  MonthlyReturn,
  NotificationRow,
  OrderRow,
  PortfolioSnapshot,
  PositionRow,
  RecoveryHistoryItem,
  RecoveryStatus,
  RiskSettings,
  RiskStatus,
  ScannerRow,
  StrategyMetrics,
  StrategySummary,
  DailyStatRow,
  TradeRow,
} from "@/lib/types";

const REFRESH_MS = 15_000; // fallback poll; WS invalidation supersedes this in practice

function useAuthed() {
  return Boolean(useAuthStore((s) => s.token));
}

export function useHealth() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<HealthStatus>("/api/v1/health"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useEngineStatus() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["engine"],
    queryFn: () => api.get<EngineStatusPayload>("/api/v1/engine/status"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useEngineActions() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["engine"] });
  const start = useMutation({ mutationFn: () => api.post("/api/v1/engine/start"), onSuccess: invalidate });
  const pause = useMutation({ mutationFn: () => api.post("/api/v1/engine/pause"), onSuccess: invalidate });
  const resume = useMutation({ mutationFn: () => api.post("/api/v1/engine/resume"), onSuccess: invalidate });
  const stop = useMutation({ mutationFn: () => api.post("/api/v1/engine/stop"), onSuccess: invalidate });
  return { start, pause, resume, stop };
}

export function useScanner(qualifiedOnly = false) {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["scanner", qualifiedOnly],
    queryFn: () => api.get<ScannerRow[]>(qualifiedOnly ? "/api/v1/scanner/qualified" : "/api/v1/scanner"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useStrategies() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["strategies"],
    queryFn: () => api.get<StrategySummary[]>("/api/v1/strategies"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useStrategyMetrics(name: string) {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["strategies", name, "metrics"],
    queryFn: () => api.get<StrategyMetrics>(`/api/v1/strategies/${name}/metrics`),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useStrategyActions() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["strategies"] });
  const enable = useMutation({
    mutationFn: (name: string) => api.post(`/api/v1/strategies/${name}/enable`),
    onSuccess: invalidate,
  });
  const disable = useMutation({
    mutationFn: (name: string) => api.post(`/api/v1/strategies/${name}/disable`),
    onSuccess: invalidate,
  });
  const reload = useMutation({
    mutationFn: (name: string) => api.post(`/api/v1/strategies/${name}/reload`),
    onSuccess: invalidate,
  });
  return { enable, disable, reload };
}

export function useOrders() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["orders"],
    queryFn: () => api.get<OrderRow[]>("/api/v1/orders"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useOpenOrders() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["orders", "open"],
    queryFn: () => api.get<Record<string, unknown>[]>("/api/v1/orders/open"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useOrderActions() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["orders"] });
  const cancel = useMutation({
    mutationFn: (orderId: string) => api.post(`/api/v1/orders/${orderId}/cancel`),
    onSuccess: invalidate,
  });
  const cancelAll = useMutation({ mutationFn: () => api.post("/api/v1/orders/cancel-all"), onSuccess: invalidate });
  return { cancel, cancelAll };
}

export function usePositions() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["positions"],
    queryFn: () => api.get<PositionRow[]>("/api/v1/positions"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function usePositionActions() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["positions"] });
    queryClient.invalidateQueries({ queryKey: ["portfolio"] });
  };
  const closeOne = useMutation({
    mutationFn: (symbol: string) => api.post(`/api/v1/positions/${symbol}/close`),
    onSuccess: invalidate,
  });
  const closeAll = useMutation({ mutationFn: () => api.post("/api/v1/positions/close-all"), onSuccess: invalidate });
  return { closeOne, closeAll };
}

export function usePortfolio() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["portfolio"],
    queryFn: () => api.get<PortfolioSnapshot>("/api/v1/portfolio"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function usePortfolioStatistics(limit = 30) {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["portfolio", "statistics", limit],
    queryFn: () => api.get<DailyStatRow[]>(`/api/v1/portfolio/statistics?limit=${limit}`),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useRisk() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["risk"],
    queryFn: () => api.get<RiskSettings>("/api/v1/risk"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useRiskCurrent() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["risk", "current"],
    queryFn: () => api.get<RiskStatus>("/api/v1/risk/current"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useRiskActions() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["risk"] });
  const updateSettings = useMutation({
    mutationFn: (payload: Partial<RiskSettings>) => api.put<RiskSettings>("/api/v1/risk/settings", payload),
    onSuccess: invalidate,
  });
  const updateAllocation = useMutation({
    mutationFn: (allocation: Record<string, number>) =>
      api.put<Record<string, number>>("/api/v1/risk/allocation", { allocation }),
    onSuccess: invalidate,
  });
  return { updateSettings, updateAllocation };
}

export function useAnalyticsOverview() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["analytics"],
    queryFn: () => api.get<AnalyticsOverview>("/api/v1/analytics"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useEquityCurve() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["analytics", "equity-curve"],
    queryFn: () => api.get<EquityPoint[]>("/api/v1/analytics/equity-curve"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useMonthlyReturns() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["analytics", "monthly"],
    queryFn: () => api.get<MonthlyReturn[]>("/api/v1/analytics/monthly"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useTrades(strategy?: string) {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["analytics", "trades", strategy ?? "all"],
    queryFn: () => api.get<TradeRow[]>(`/api/v1/analytics/trades${strategy ? `?strategy=${strategy}` : ""}`),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useLogs(filters: { category?: string; level?: string; strategy?: string } = {}) {
  const enabled = useAuthed();
  const params = new URLSearchParams(
    Object.entries(filters).filter(([, v]) => Boolean(v)) as [string, string][],
  ).toString();
  return useQuery({
    queryKey: ["logs", filters],
    queryFn: () => api.get<LogRow[]>(`/api/v1/logs${params ? `?${params}` : ""}`),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useNotifications(unreadOnly = false) {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["notifications", unreadOnly],
    queryFn: () => api.get<NotificationRow[]>(`/api/v1/notifications?unread_only=${unreadOnly}`),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useNotificationActions() {
  const queryClient = useQueryClient();
  const markRead = useMutation({
    mutationFn: (id: string) => api.post(`/api/v1/notifications/read/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
  return { markRead };
}

export function useRecoveryStatus() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["recovery"],
    queryFn: () => api.get<RecoveryStatus>("/api/v1/recovery/status"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useRecoveryHistory() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["recovery", "history"],
    queryFn: () => api.get<RecoveryHistoryItem[]>("/api/v1/recovery/history"),
    refetchInterval: REFRESH_MS,
    enabled,
  });
}

export function useRecoveryActions() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["recovery"] });
  const reconnect = useMutation({ mutationFn: () => api.post("/api/v1/recovery/reconnect"), onSuccess: invalidate });
  const rebuildState = useMutation({
    mutationFn: () => api.post("/api/v1/recovery/rebuild-state"),
    onSuccess: invalidate,
  });
  return { reconnect, rebuildState };
}

export function useSettings() {
  const enabled = useAuthed();
  return useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<Record<string, unknown>>("/api/v1/settings"),
    enabled,
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, unknown>) => api.put("/api/v1/settings", { values }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
}
