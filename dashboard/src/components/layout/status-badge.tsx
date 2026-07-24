import { cn } from "@/lib/utils";

type Health = "healthy" | "connected" | "running" | "warning" | "critical" | "disconnected" | "stopped" | string;

const STYLES: Record<string, string> = {
  healthy: "bg-success/15 text-success",
  connected: "bg-success/15 text-success",
  running: "bg-success/15 text-success",
  starting: "bg-warning/15 text-warning",
  recovering: "bg-warning/15 text-warning",
  paused: "bg-warning/15 text-warning",
  warning: "bg-warning/15 text-warning",
  critical: "bg-destructive/15 text-destructive",
  disconnected: "bg-destructive/15 text-destructive",
  stopped: "bg-destructive/15 text-destructive",
  unknown: "bg-muted text-muted-foreground",
};

export function StatusDot({ status }: { status: Health }) {
  const key = status?.toLowerCase?.() ?? "unknown";
  const dotColor =
    key in STYLES
      ? STYLES[key].includes("success")
        ? "bg-success"
        : STYLES[key].includes("warning")
          ? "bg-warning"
          : STYLES[key].includes("destructive")
            ? "bg-destructive"
            : "bg-muted-foreground"
      : "bg-muted-foreground";
  return <span className={cn("inline-block size-2 rounded-full", dotColor)} />;
}

export function StatusBadge({ label, status }: { label: string; status: Health }) {
  const key = status?.toLowerCase?.() ?? "unknown";
  const style = STYLES[key] ?? STYLES.unknown;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", style)}>
      <StatusDot status={status} />
      {label}: {status}
    </span>
  );
}
