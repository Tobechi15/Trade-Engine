"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSettings, useStrategies } from "@/hooks/use-api";

export default function SettingsPage() {
  const { data: settings } = useSettings();
  const { data: strategies } = useStrategies();

  const broker = (settings?.broker as { environment?: string; paper_trading?: boolean }) ?? {};
  const marketData = (settings?.market_data as { provider?: string }) ?? {};

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">Settings</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Broker</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Row label="Environment" value={broker.environment ?? "-"} />
          <Row label="Mode" value={broker.paper_trading ? "Paper Trading" : "Live Trading"} />
          <p className="pt-2 text-xs text-muted-foreground">
            API keys are configured server-side via environment variables and are never exposed to the dashboard.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Market Data</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Row label="Provider" value={marketData.provider ?? "-"} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Risk</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          <p className="text-muted-foreground">
            Risk limits and strategy allocation are managed on the{" "}
            <Link href="/risk" className="text-primary underline underline-offset-2">
              Risk
            </Link>{" "}
            page.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Strategy Settings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {strategies?.map((s) => (
            <div key={s.name} className="flex items-center justify-between rounded-md border border-border px-3 py-2">
              <span className="font-medium capitalize">{s.name}</span>
              <Badge variant={s.enabled ? "default" : "secondary"}>{s.enabled ? "Enabled" : "Disabled"}</Badge>
            </div>
          ))}
          <p className="text-xs text-muted-foreground">
            Manage individual strategy parameters on the{" "}
            <Link href="/strategies" className="text-primary underline underline-offset-2">
              Strategies
            </Link>{" "}
            page.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
