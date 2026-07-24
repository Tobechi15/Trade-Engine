import { cn } from "@/lib/utils";

export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value.toFixed(digits)}%`;
}

export function Pnl({ value, digits = 2 }: { value: number | null | undefined; digits?: number }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="text-muted-foreground">-</span>;
  }
  const positive = value > 0;
  const negative = value < 0;
  return (
    <span
      className={cn(
        "tabular-nums font-medium",
        positive && "text-success",
        negative && "text-destructive",
        !positive && !negative && "text-muted-foreground",
      )}
    >
      {positive ? "+" : ""}
      {value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}
    </span>
  );
}
