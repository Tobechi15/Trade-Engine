"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Bell, LogOut, Menu, Activity } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { useAuthStore } from "@/lib/auth-store";
import { useEngineStatus, useHealth, useNotifications } from "@/hooks/use-api";
import { StatusBadge } from "@/components/layout/status-badge";
import { LiveClock } from "@/components/layout/live-clock";
import { NAV_ITEMS } from "@/components/layout/nav-items";
import { cn } from "@/lib/utils";

export function Topbar() {
  const router = useRouter();
  const pathname = usePathname();
  const logout = useAuthStore((s) => s.logout);
  const { data: engine } = useEngineStatus();
  const { data: health } = useHealth();
  const { data: notifications } = useNotifications(true);

  const unreadCount = notifications?.length ?? 0;

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border bg-background/80 px-4 backdrop-blur">
      <div className="flex items-center gap-3">
        <Sheet>
          <SheetTrigger render={<Button variant="ghost" size="icon" className="md:hidden" />}>
            <Menu className="size-5" />
          </SheetTrigger>
          <SheetContent side="left" className="w-56 p-0">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <div className="flex h-14 items-center gap-2 border-b border-border px-4">
              <Activity className="size-5 text-primary" />
              <span className="font-semibold">Trade Engine</span>
            </div>
            <nav className="space-y-1 p-2">
              {NAV_ITEMS.map((item) => {
                const active = pathname === item.href;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium",
                      active ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
                    )}
                  >
                    <Icon className="size-4" />
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </SheetContent>
        </Sheet>

        <StatusBadge label="Engine" status={engine?.status ?? "unknown"} />
        <div className="hidden items-center gap-2 lg:flex">
          <StatusBadge label="Broker" status={health?.broker ?? "unknown"} />
          <StatusBadge label="Data" status={health?.market_data ?? "unknown"} />
          <StatusBadge label="DB" status={health?.database ?? "unknown"} />
        </div>
      </div>

      <div className="flex items-center gap-3">
        <LiveClock />
        <Link href="/notifications" className="relative">
          <Button variant="ghost" size="icon">
            <Bell className="size-5" />
          </Button>
          {unreadCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-destructive text-[10px] font-semibold text-destructive-foreground">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </Link>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => {
            logout();
            router.replace("/login");
          }}
        >
          <LogOut className="size-4" />
        </Button>
      </div>
    </header>
  );
}
