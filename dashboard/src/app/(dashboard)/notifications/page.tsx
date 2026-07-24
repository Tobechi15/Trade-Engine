"use client";

import { AlertCircle, AlertTriangle, Info, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useNotificationActions, useNotifications } from "@/hooks/use-api";
import type { NotificationRow } from "@/lib/types";

const LEVEL_CONFIG: Record<NotificationRow["level"], { icon: typeof Info; className: string }> = {
  info: { icon: Info, className: "text-primary" },
  warning: { icon: AlertTriangle, className: "text-warning" },
  error: { icon: AlertCircle, className: "text-destructive" },
  critical: { icon: ShieldAlert, className: "text-destructive" },
};

export default function NotificationsPage() {
  const { data: notifications, isLoading } = useNotifications();
  const { markRead } = useNotificationActions();

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Notifications</h1>

      <Card>
        <CardContent className="divide-y divide-border p-0">
          {isLoading ? (
            <div className="p-6 text-sm text-muted-foreground">Loading notifications...</div>
          ) : !notifications?.length ? (
            <div className="p-6 text-sm text-muted-foreground">No notifications.</div>
          ) : (
            notifications.map((n) => {
              const config = LEVEL_CONFIG[n.level];
              const Icon = config.icon;
              return (
                <div key={n.id} className={cn("flex items-start gap-3 p-4", !n.read && "bg-muted/40")}>
                  <Icon className={cn("mt-0.5 size-4 shrink-0", config.className)} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm">{n.message}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {new Date(n.created_at).toLocaleString()} - {n.source}
                    </p>
                  </div>
                  {!n.read && (
                    <Button size="sm" variant="ghost" onClick={() => markRead.mutate(n.id)}>
                      Mark read
                    </Button>
                  )}
                </div>
              );
            })
          )}
        </CardContent>
      </Card>
    </div>
  );
}
