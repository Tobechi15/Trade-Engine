"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";

import { DataTable } from "@/components/data-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import { useOrderActions, useOrders } from "@/hooks/use-api";
import type { OrderRow } from "@/lib/types";

const STATUS_STYLE: Record<string, string> = {
  pending: "bg-muted text-muted-foreground",
  submitted: "bg-primary/15 text-primary",
  partially_filled: "bg-warning/15 text-warning",
  filled: "bg-success/15 text-success",
  cancelled: "bg-muted text-muted-foreground",
  rejected: "bg-destructive/15 text-destructive",
};

export default function OrdersPage() {
  const { data: orders, isLoading } = useOrders();
  const { cancel, cancelAll } = useOrderActions();

  const columns: ColumnDef<OrderRow, unknown>[] = [
    { accessorKey: "order_id", header: "Order ID", cell: ({ row }) => row.original.order_id.slice(0, 8) },
    { accessorKey: "strategy", header: "Strategy", cell: ({ row }) => <span className="capitalize">{row.original.strategy}</span> },
    { accessorKey: "symbol", header: "Ticker" },
    {
      accessorKey: "side",
      header: "Side",
      cell: ({ row }) => (
        <span className={row.original.side === "buy" ? "text-success" : "text-destructive"}>
          {row.original.side.toUpperCase()}
        </span>
      ),
    },
    { accessorKey: "quantity", header: "Quantity" },
    {
      accessorKey: "entry_price",
      header: "Entry",
      cell: ({ row }) => (row.original.entry_price != null ? `$${row.original.entry_price.toFixed(2)}` : "-"),
    },
    {
      accessorKey: "stop_price",
      header: "Stop",
      cell: ({ row }) => (row.original.stop_price != null ? `$${row.original.stop_price.toFixed(2)}` : "-"),
    },
    {
      accessorKey: "take_profit_price",
      header: "Take Profit",
      cell: ({ row }) => (row.original.take_profit_price != null ? `$${row.original.take_profit_price.toFixed(2)}` : "-"),
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => (
        <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium capitalize", STATUS_STYLE[row.original.status])}>
          {row.original.status.replace("_", " ")}
        </span>
      ),
    },
    {
      accessorKey: "broker_order_id",
      header: "Broker Order ID",
      cell: ({ row }) => <span className="font-mono text-xs text-muted-foreground">{row.original.broker_order_id ?? "-"}</span>,
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) =>
        ["pending", "submitted", "partially_filled"].includes(row.original.status) ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              cancel.mutate(row.original.order_id, {
                onSuccess: () => toast.success(`Order ${row.original.order_id.slice(0, 8)} cancelled`),
                onError: (e) => toast.error(e instanceof Error ? e.message : "Cancel failed"),
              });
            }}
          >
            Cancel
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Orders</h1>
        <AlertDialog>
          <AlertDialogTrigger render={<Button variant="destructive" size="sm" />}>Cancel All</AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Cancel all open orders?</AlertDialogTitle>
              <AlertDialogDescription>
                This cancels every open order across all strategies. This cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Back</AlertDialogCancel>
              <AlertDialogAction
                onClick={() =>
                  cancelAll.mutate(undefined, {
                    onSuccess: () => toast.success("All open orders cancelled"),
                    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
                  })
                }
              >
                Confirm
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 text-sm text-muted-foreground">Loading orders...</div>
          ) : (
            <DataTable columns={columns} data={orders ?? []} emptyMessage="No orders yet." />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
