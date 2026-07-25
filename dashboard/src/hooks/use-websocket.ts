"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useAuthStore } from "@/lib/auth-store";

function resolveWsUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_WS_URL;
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  // Default: derive from the API URL (http->ws, https->wss) so there's a
  // single source of truth instead of two URLs that can drift out of sync.
  let url = explicit || apiUrl.replace(/^http/, "ws").replace(/\/$/, "") + "/ws";

  // Defensive: a page served over HTTPS can never open a plain ws://
  // connection - browsers block it as "mixed content" and silently refuse
  // to connect. If NEXT_PUBLIC_WS_URL was set to ws:// by mistake (e.g. a
  // Vercel env var copied from local dev), upgrade it rather than fail.
  if (typeof window !== "undefined" && window.location.protocol === "https:" && url.startsWith("ws://")) {
    url = url.replace(/^ws:\/\//, "wss://");
  }

  return url;
}

const WS_URL = resolveWsUrl();

// Real-time updates arrive over one WebSocket connection; rather than
// patching every cache shape by hand, each event type just invalidates the
// React Query keys it affects, so the next render always shows fresh data
// without a fixed polling interval driving it (per DASHBOARD.md: "polling
// should be avoided whenever possible").
const EVENT_INVALIDATIONS: Record<string, string[][]> = {
  NEW_QUOTE: [["scanner"]],
  NEW_CANDLE: [["scanner"]],
  VOLUME_UPDATE: [["scanner"]],
  OPENING_RANGE_READY: [["scanner"], ["strategies"]],
  SIGNAL_GENERATED: [["scanner"], ["strategies"]],
  SIGNAL_REJECTED: [["logs"]],
  ORDER_SUBMITTED: [["orders"]],
  ORDER_FILLED: [["orders"], ["positions"], ["portfolio"]],
  ORDER_PARTIALLY_FILLED: [["orders"]],
  ORDER_CANCELLED: [["orders"]],
  ORDER_REJECTED: [["orders"], ["logs"]],
  POSITION_OPENED: [["positions"], ["portfolio"]],
  POSITION_UPDATED: [["positions"], ["portfolio"]],
  POSITION_CLOSED: [["positions"], ["portfolio"], ["analytics"]],
  TRADE_ENTERED: [["portfolio"], ["analytics"]],
  TRADE_EXITED: [["portfolio"], ["analytics"], ["logs"]],
  RISK_APPROVED: [["orders"], ["risk"]],
  RISK_REJECTED: [["logs"], ["notifications"], ["risk"]],
  DAILY_LOSS_HIT: [["risk"], ["notifications"]],
  MAX_EXPOSURE_HIT: [["risk"]],
  MARKET_OPEN: [["engine"], ["strategies"]],
  MARKET_CLOSE: [["engine"], ["strategies"], ["portfolio"]],
  ENGINE_STARTED: [["engine"]],
  ENGINE_STOPPED: [["engine"]],
  ENGINE_PAUSED: [["engine"]],
  ENGINE_RESUMED: [["engine"]],
  RECOVERY_STARTED: [["recovery"], ["notifications"]],
  RECOVERY_COMPLETED: [["recovery"], ["notifications"]],
  RECOVERY_FAILED: [["recovery"], ["notifications"]],
  BROKER_RECONNECTED: [["recovery"], ["notifications"], ["engine"]],
  MARKET_DATA_RECONNECTED: [["recovery"], ["notifications"], ["engine"]],
  STATE_RESTORED: [["recovery"]],
  INFO_NOTIFICATION: [["notifications"]],
  WARNING_NOTIFICATION: [["notifications"]],
  ERROR_NOTIFICATION: [["notifications"]],
  CRITICAL_NOTIFICATION: [["notifications"]],
};

export function useWebSocketConnection() {
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let reconnectDelay = 1000;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      if (cancelled) return;
      const ws = new WebSocket(`${WS_URL}?token=${encodeURIComponent(token as string)}`);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectDelay = 1000;
        setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          const eventType = message?.payload?.event_type as string | undefined;
          const keys = eventType ? EVENT_INVALIDATIONS[eventType] : undefined;
          if (keys) {
            for (const key of keys) queryClient.invalidateQueries({ queryKey: key });
          }
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (cancelled) return;
        reconnectTimer = setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 30_000);
      };

      ws.onerror = () => ws.close();
    }

    connect();
    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [token, queryClient]);

  return connected;
}
