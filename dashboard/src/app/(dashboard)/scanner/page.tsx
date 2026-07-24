"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { DataTable } from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useScanner } from "@/hooks/use-api";
import type { ScannerRow } from "@/lib/types";

type Filter = "all" | "qualified" | "high_rvol" | "low_spread";

const STATUS_VARIANT: Record<string, string> = {
  watching: "bg-muted text-muted-foreground",
  qualified: "bg-primary/15 text-primary",
  ignored: "bg-muted text-muted-foreground",
  entered: "bg-success/15 text-success",
  exited: "bg-secondary text-secondary-foreground",
};

const columns: ColumnDef<ScannerRow, unknown>[] = [
  { accessorKey: "symbol", header: "Ticker" },
  {
    accessorKey: "price",
    header: "Price",
    cell: ({ row }) => (row.original.price != null ? `$${row.original.price.toFixed(2)}` : "-"),
  },
  {
    accessorKey: "rvol",
    header: "RVOL",
    cell: ({ row }) => (row.original.rvol != null ? row.original.rvol.toFixed(2) : "-"),
  },
  {
    accessorKey: "spread_pct",
    header: "Spread",
    cell: ({ row }) => (row.original.spread_pct != null ? `${row.original.spread_pct.toFixed(3)}%` : "-"),
  },
  {
    id: "opening_range",
    header: "Opening Range",
    cell: ({ row }) => {
      const or = row.original.opening_range;
      if (!or) return "-";
      return `${or.low.toFixed(2)} - ${or.high.toFixed(2)}`;
    },
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium capitalize", STATUS_VARIANT[row.original.status])}>
        {row.original.status}
      </span>
    ),
  },
];

export default function ScannerPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const { data, isLoading } = useScanner();

  const filtered = useMemo(() => {
    if (!data) return [];
    switch (filter) {
      case "qualified":
        return data.filter((r) => r.status === "qualified" || r.status === "entered");
      case "high_rvol":
        return [...data].sort((a, b) => (b.rvol ?? 0) - (a.rvol ?? 0));
      case "low_spread":
        return [...data]
          .filter((r) => r.spread_pct !== null)
          .sort((a, b) => (a.spread_pct ?? 0) - (b.spread_pct ?? 0));
      default:
        return data;
    }
  }, [data, filter]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Scanner</h1>
        <Badge variant="outline">{data?.length ?? 0} symbols in universe</Badge>
      </div>

      <div className="flex flex-wrap gap-2">
        {(
          [
            ["all", "All"],
            ["qualified", "Qualified Only"],
            ["high_rvol", "High RVOL"],
            ["low_spread", "Low Spread"],
          ] as [Filter, string][]
        ).map(([key, label]) => (
          <Button key={key} size="sm" variant={filter === key ? "default" : "outline"} onClick={() => setFilter(key)}>
            {label}
          </Button>
        ))}
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 text-sm text-muted-foreground">Loading scanner...</div>
          ) : (
            <DataTable columns={columns} data={filtered} emptyMessage="Universe not built yet (pre-market prep runs at 08:00 ET)." />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
