"use client";

import { useState } from "react";
import { Calculator } from "lucide-react";
import { usePositionSize } from "@/hooks/use-position-size";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

function formatCurrency(val: number): string {
  return val.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

function rateSetup(rr: number): { label: string; color: string } {
  if (rr >= 3) return { label: "Excellent", color: "text-emerald-400" };
  if (rr >= 2) return { label: "Good", color: "text-emerald-400" };
  if (rr >= 1.5) return { label: "Decent", color: "text-yellow-400" };
  return { label: "Poor", color: "text-red-400" };
}

export default function PositionSizerPage() {
  const [account, setAccount] = useState(100000);
  const [risk, setRisk] = useState(2);
  const [entry, setEntry] = useState(50);
  const [stop, setStop] = useState(47);
  const [target, setTarget] = useState<number | undefined>(undefined);
  const [enabled, setEnabled] = useState(false);

  const { data, isLoading } = usePositionSize(
    { account, risk, entry, stop, target: target || undefined },
    enabled
  );

  const handleCalculate = () => {
    setEnabled(true);
  };

  // Price ladder calculations
  const riskPerShare = Math.abs(entry - stop);
  const effectiveTarget = target || entry + 2 * riskPerShare;
  const rewardPerShare = effectiveTarget - entry;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Calculator className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Position Size Calculator</h1>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Form */}
        <Card className="border-zinc-800 bg-zinc-900/50">
          <CardHeader>
            <CardTitle className="text-sm text-zinc-300">Parameters</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label className="text-xs text-zinc-400">Account Size ($)</Label>
                <Input
                  type="number"
                  value={account}
                  onChange={(e) => {
                    setAccount(Number(e.target.value));
                    setEnabled(false);
                  }}
                  className="bg-zinc-900"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-zinc-400">Risk per Trade (%)</Label>
                <Input
                  type="number"
                  step="0.5"
                  value={risk}
                  onChange={(e) => {
                    setRisk(Number(e.target.value));
                    setEnabled(false);
                  }}
                  className="bg-zinc-900"
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-1">
                <Label className="text-xs text-zinc-400">Entry Price ($)</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={entry}
                  onChange={(e) => {
                    setEntry(Number(e.target.value));
                    setEnabled(false);
                  }}
                  className="bg-zinc-900"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-zinc-400">Stop Loss ($)</Label>
                <Input
                  type="number"
                  step="0.01"
                  value={stop}
                  onChange={(e) => {
                    setStop(Number(e.target.value));
                    setEnabled(false);
                  }}
                  className="bg-zinc-900"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-zinc-400">
                  Target ($) <span className="text-zinc-600">optional</span>
                </Label>
                <Input
                  type="number"
                  step="0.01"
                  placeholder="Auto 2:1"
                  value={target ?? ""}
                  onChange={(e) => {
                    const v = e.target.value ? Number(e.target.value) : undefined;
                    setTarget(v);
                    setEnabled(false);
                  }}
                  className="bg-zinc-900"
                />
              </div>
            </div>

            <Button onClick={handleCalculate} className="w-full bg-cyan-600 hover:bg-cyan-700">
              Calculate Position Size
            </Button>
          </CardContent>
        </Card>

        {/* Results */}
        <div className="space-y-4">
          {data && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Card className="border-zinc-800 bg-zinc-900/50">
                  <CardContent className="p-4">
                    <div className="text-xs text-zinc-500">Shares to Buy</div>
                    <div className="text-3xl font-bold text-cyan-400">
                      {data.shares}
                    </div>
                  </CardContent>
                </Card>
                <Card className="border-zinc-800 bg-zinc-900/50">
                  <CardContent className="p-4">
                    <div className="text-xs text-zinc-500">Position Value</div>
                    <div className="text-2xl font-bold">
                      {formatCurrency(data.position_value)}
                    </div>
                  </CardContent>
                </Card>
                <Card className="border-zinc-800 bg-zinc-900/50">
                  <CardContent className="p-4">
                    <div className="text-xs text-zinc-500">Dollar Risk</div>
                    <div className="text-2xl font-bold text-red-400">
                      {formatCurrency(data.dollar_risk)}
                    </div>
                  </CardContent>
                </Card>
                <Card className="border-zinc-800 bg-zinc-900/50">
                  <CardContent className="p-4">
                    <div className="text-xs text-zinc-500">Risk:Reward</div>
                    <div
                      className={`text-2xl font-bold ${rateSetup(data.rr_ratio).color}`}
                    >
                      {data.rr_ratio.toFixed(1)}:1
                    </div>
                    <div className={`text-xs ${rateSetup(data.rr_ratio).color}`}>
                      {rateSetup(data.rr_ratio).label}
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* R:R Visual Bar */}
              <Card className="border-zinc-800 bg-zinc-900/50">
                <CardContent className="p-4">
                  <div className="mb-2 text-xs text-zinc-500">
                    Risk vs Reward
                  </div>
                  <div className="flex h-8 overflow-hidden rounded">
                    <div
                      className="flex items-center justify-center bg-red-500/30 text-xs font-medium text-red-400"
                      style={{
                        width: `${(riskPerShare / (riskPerShare + rewardPerShare)) * 100}%`,
                      }}
                    >
                      -${riskPerShare.toFixed(2)}
                    </div>
                    <div
                      className="flex items-center justify-center bg-emerald-500/30 text-xs font-medium text-emerald-400"
                      style={{
                        width: `${(rewardPerShare / (riskPerShare + rewardPerShare)) * 100}%`,
                      }}
                    >
                      +${rewardPerShare.toFixed(2)}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Price Ladder */}
              <Card className="border-zinc-800 bg-zinc-900/50">
                <CardContent className="p-4">
                  <div className="mb-3 text-xs text-zinc-500">Price Ladder</div>
                  <div className="relative flex flex-col gap-1 pl-4">
                    {/* Target */}
                    <div className="flex items-center gap-3">
                      <div className="h-0.5 w-12 bg-emerald-500" />
                      <span className="text-sm font-mono text-emerald-400">
                        ${data.target.toFixed(2)}
                      </span>
                      <span className="text-xs text-zinc-500">Target</span>
                    </div>
                    <div className="ml-6 text-[10px] text-emerald-500/60">
                      +${(data.target - data.entry_price).toFixed(2)} (
                      {(((data.target - data.entry_price) / data.entry_price) * 100).toFixed(1)}%)
                    </div>
                    {/* Entry */}
                    <div className="flex items-center gap-3">
                      <div className="h-0.5 w-12 bg-zinc-300" />
                      <span className="text-sm font-mono text-zinc-100">
                        ${data.entry_price.toFixed(2)}
                      </span>
                      <span className="text-xs text-zinc-500">Entry</span>
                    </div>
                    <div className="ml-6 text-[10px] text-red-500/60">
                      -${(data.entry_price - data.stop_loss).toFixed(2)} (
                      {(((data.entry_price - data.stop_loss) / data.entry_price) * 100).toFixed(1)}%)
                    </div>
                    {/* Stop */}
                    <div className="flex items-center gap-3">
                      <div className="h-0.5 w-12 bg-red-500" />
                      <span className="text-sm font-mono text-red-400">
                        ${data.stop_loss.toFixed(2)}
                      </span>
                      <span className="text-xs text-zinc-500">Stop Loss</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </>
          )}

          {!data && !isLoading && (
            <div className="flex h-64 items-center justify-center rounded-lg border border-zinc-800 text-zinc-500">
              Enter parameters and click Calculate
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
