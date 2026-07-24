"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { StatCard } from "@/components/stat-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { formatPercent } from "@/components/pnl";
import {
  useEngineActions,
  useEngineStatus,
  useOrderActions,
  usePositionActions,
  useRisk,
  useRiskActions,
  useRiskCurrent,
} from "@/hooks/use-api";

export default function RiskPage() {
  const { data: risk } = useRisk();
  const { data: status } = useRiskCurrent();
  const { data: engine } = useEngineStatus();
  const { updateSettings, updateAllocation } = useRiskActions();
  const { pause, resume } = useEngineActions();
  const { closeAll } = usePositionActions();
  const { cancelAll } = useOrderActions();

  const [form, setForm] = useState({
    risk_per_trade_pct: 0,
    daily_loss_limit_pct: 0,
    max_concurrent_positions: 0,
    max_portfolio_exposure_pct: 0,
    max_spread_pct: 0,
  });
  const [allocation, setAllocation] = useState<Record<string, number>>({});

  // Seed the editable form from the server once the settings first load.
  // Guarded to run only once (not on every 15s poll) so it never clobbers
  // an in-progress edit with a background refetch.
  const seededRef = useRef(false);
  useEffect(() => {
    if (risk && !seededRef.current) {
      seededRef.current = true;
      setForm({
        risk_per_trade_pct: risk.risk_per_trade_pct,
        daily_loss_limit_pct: risk.daily_loss_limit_pct,
        max_concurrent_positions: risk.max_concurrent_positions,
        max_portfolio_exposure_pct: risk.max_portfolio_exposure_pct,
        max_spread_pct: risk.max_spread_pct,
      });
      setAllocation(risk.allocation);
    }
  }, [risk]);

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">Risk</h1>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Risk Per Trade" value={formatPercent(risk?.risk_per_trade_pct)} />
        <StatCard label="Daily Loss Limit" value={formatPercent(risk?.daily_loss_limit_pct)} />
        <StatCard label="Max Positions" value={status?.max_positions ?? "-"} />
        <StatCard
          label="Current Positions"
          value={status?.current_positions ?? "-"}
          tone={status && status.current_positions >= status.max_positions ? "warning" : "default"}
        />
        <StatCard
          label="Remaining Daily Loss"
          value={formatPercent(status?.remaining_daily_loss_pct)}
          tone={status?.daily_loss_hit ? "destructive" : "default"}
        />
        <StatCard label="Portfolio Exposure Cap" value={formatPercent(risk?.max_portfolio_exposure_pct)} />
        <StatCard label="Trading" value={status?.trading_enabled ? "Enabled" : "Disabled"} tone={status?.trading_enabled ? "success" : "destructive"} />
        <StatCard label="Engine" value={engine?.status ?? "-"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Risk Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <NumberField
              label="Risk Per Trade (%)"
              value={form.risk_per_trade_pct}
              onChange={(v) => setForm((f) => ({ ...f, risk_per_trade_pct: v }))}
            />
            <NumberField
              label="Daily Loss Limit (%)"
              value={form.daily_loss_limit_pct}
              onChange={(v) => setForm((f) => ({ ...f, daily_loss_limit_pct: v }))}
            />
            <NumberField
              label="Max Concurrent Positions"
              value={form.max_concurrent_positions}
              onChange={(v) => setForm((f) => ({ ...f, max_concurrent_positions: v }))}
            />
            <NumberField
              label="Max Portfolio Exposure (%)"
              value={form.max_portfolio_exposure_pct}
              onChange={(v) => setForm((f) => ({ ...f, max_portfolio_exposure_pct: v }))}
            />
            <NumberField
              label="Max Spread (%)"
              value={form.max_spread_pct}
              onChange={(v) => setForm((f) => ({ ...f, max_spread_pct: v }))}
              step={0.01}
            />
            <Button
              onClick={() =>
                updateSettings.mutate(form, {
                  onSuccess: () => toast.success("Risk settings updated"),
                  onError: (e) => toast.error(e instanceof Error ? e.message : "Update failed"),
                })
              }
              disabled={updateSettings.isPending}
            >
              Save Settings
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Strategy Allocation</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {Object.entries(allocation).map(([name, pct]) => (
              <NumberField
                key={name}
                label={`${name} (%)`}
                value={pct}
                onChange={(v) => setAllocation((a) => ({ ...a, [name]: v }))}
              />
            ))}
            <Button
              variant="secondary"
              onClick={() =>
                updateAllocation.mutate(allocation, {
                  onSuccess: () => toast.success("Allocation updated"),
                  onError: (e) => toast.error(e instanceof Error ? e.message : "Update failed"),
                })
              }
              disabled={updateAllocation.isPending}
            >
              Save Allocation
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Emergency Controls</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          {engine?.status === "paused" ? (
            <Button variant="secondary" onClick={() => resume.mutate()}>
              Resume Trading
            </Button>
          ) : (
            <ConfirmButton
              label="Pause Trading"
              description="This pauses all new trade entries immediately. Existing positions remain open."
              onConfirm={() => pause.mutate()}
            />
          )}
          <ConfirmButton
            label="Close All Positions"
            description="This immediately submits market orders to flatten every open position across all strategies."
            variant="destructive"
            onConfirm={() => closeAll.mutate()}
          />
          <ConfirmButton
            label="Cancel All Orders"
            description="This cancels every open order across all strategies."
            variant="destructive"
            onConfirm={() => cancelAll.mutate()}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
  step = 0.1,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input type="number" step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

function ConfirmButton({
  label,
  description,
  onConfirm,
  variant = "outline",
}: {
  label: string;
  description: string;
  onConfirm: () => void;
  variant?: "outline" | "destructive";
}) {
  return (
    <AlertDialog>
      <AlertDialogTrigger render={<Button variant={variant} />}>{label}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{label}?</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Back</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>Confirm</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
