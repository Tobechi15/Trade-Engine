"use client";

import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";

import { DataTable } from "@/components/data-table";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { useLogs } from "@/hooks/use-api";
import type { LogRow } from "@/lib/types";

const CATEGORIES = ["system", "broker", "market_data", "strategy", "orders", "risk", "recovery", "performance"];
const LEVELS = ["INFO", "WARNING", "ERROR", "CRITICAL"];

const LEVEL_STYLE: Record<string, string> = {
  INFO: "text-muted-foreground",
  WARNING: "text-warning",
  ERROR: "text-destructive",
  CRITICAL: "text-destructive font-semibold",
};

export default function LogsPage() {
  const [category, setCategory] = useState<string>("all");
  const [level, setLevel] = useState<string>("all");
  const [search, setSearch] = useState("");

  const { data: logs, isLoading } = useLogs({
    category: category === "all" ? undefined : category,
    level: level === "all" ? undefined : level,
  });

  const filtered = (logs ?? []).filter((l) => l.message.toLowerCase().includes(search.toLowerCase()));

  const columns: ColumnDef<LogRow, unknown>[] = [
    {
      accessorKey: "time",
      header: "Time",
      cell: ({ row }) => (row.original.time ? new Date(row.original.time).toLocaleString() : "-"),
    },
    { accessorKey: "category", header: "Category" },
    {
      accessorKey: "level",
      header: "Level",
      cell: ({ row }) => <span className={cn("font-medium", LEVEL_STYLE[row.original.level])}>{row.original.level}</span>,
    },
    { accessorKey: "message", header: "Message" },
    { accessorKey: "strategy", header: "Strategy", cell: ({ row }) => row.original.strategy ?? "-" },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Logs</h1>

      <div className="flex flex-wrap gap-2">
        <Select value={category} onValueChange={(value) => setCategory(value ?? "all")}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All categories</SelectItem>
            {CATEGORIES.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={level} onValueChange={(value) => setLevel(value ?? "all")}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Level" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All levels</SelectItem>
            {LEVELS.map((l) => (
              <SelectItem key={l} value={l}>
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Input
          placeholder="Search messages..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64"
        />
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 text-sm text-muted-foreground">Loading logs...</div>
          ) : (
            <DataTable columns={columns} data={filtered} emptyMessage="No logs match these filters." />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
