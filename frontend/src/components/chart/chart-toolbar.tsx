"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { DEFAULT_UNIVERSE } from "@/lib/constants";

interface ChartToolbarProps {
  days: number;
  onDaysChange: (days: number) => void;
  indicators: {
    ema9: boolean;
    ema21: boolean;
    ema50: boolean;
    ema200: boolean;
    vwap: boolean;
    rs: boolean;
  };
  onIndicatorToggle: (key: string, val: boolean) => void;
  analysis: {
    sr: boolean;
    trendlines: boolean;
    patterns: boolean;
    projections: boolean;
  };
  onAnalysisToggle: (key: string, val: boolean) => void;
}

const DAY_OPTIONS = [30, 60, 90, 200, 365];

export function ChartToolbar({
  days,
  onDaysChange,
  indicators,
  onIndicatorToggle,
  analysis,
  onAnalysisToggle,
}: ChartToolbarProps) {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);

  const filtered = search
    ? DEFAULT_UNIVERSE.filter((s) =>
        s.toLowerCase().startsWith(search.toLowerCase())
      ).slice(0, 8)
    : [];

  const handleSelect = (sym: string) => {
    setSearch("");
    setShowSuggestions(false);
    router.push(`/chart/${sym}`);
  };

  return (
    <div className="flex flex-wrap items-center gap-4">
      {/* Symbol search */}
      <div className="relative">
        <Search className="absolute left-2 top-2 h-3.5 w-3.5 text-zinc-500" />
        <Input
          placeholder="Search symbol..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setShowSuggestions(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && search) {
              handleSelect(search.toUpperCase());
            }
          }}
          className="h-8 w-40 bg-zinc-900 pl-7 text-sm"
        />
        {showSuggestions && filtered.length > 0 && (
          <div className="absolute left-0 top-9 z-50 w-40 rounded-md border border-zinc-700 bg-zinc-900 py-1 shadow-lg">
            {filtered.map((s) => (
              <button
                key={s}
                onClick={() => handleSelect(s)}
                className="block w-full px-3 py-1 text-left text-sm text-zinc-300 hover:bg-zinc-800"
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Day selector */}
      <div className="flex gap-1">
        {DAY_OPTIONS.map((d) => (
          <Button
            key={d}
            variant={days === d ? "default" : "outline"}
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => onDaysChange(d)}
          >
            {d}D
          </Button>
        ))}
      </div>

      {/* Indicator toggles */}
      <div className="flex items-center gap-3">
        {[
          { key: "ema9", label: "EMA9", color: "text-cyan-400" },
          { key: "ema21", label: "EMA21", color: "text-yellow-400" },
          { key: "ema50", label: "EMA50", color: "text-orange-400" },
          { key: "ema200", label: "EMA200", color: "text-red-400" },
          { key: "vwap", label: "VWAP", color: "text-purple-400" },
          { key: "rs", label: "RS", color: "text-pink-400" },
        ].map(({ key, label, color }) => (
          <div key={key} className="flex items-center gap-1">
            <Switch
              id={key}
              checked={indicators[key as keyof typeof indicators]}
              onCheckedChange={(val) => onIndicatorToggle(key, val)}
              className="h-4 w-7"
            />
            <Label htmlFor={key} className={`text-[10px] ${color}`}>
              {label}
            </Label>
          </div>
        ))}
      </div>

      {/* Technical analysis toggles */}
      <div className="flex items-center gap-3 border-l border-zinc-700 pl-3">
        {[
          { key: "sr", label: "S/R", color: "text-blue-400" },
          { key: "trendlines", label: "Trends", color: "text-green-400" },
          { key: "patterns", label: "Patterns", color: "text-violet-400" },
          { key: "projections", label: "Targets", color: "text-amber-400" },
        ].map(({ key, label, color }) => (
          <div key={key} className="flex items-center gap-1">
            <Switch
              id={`ta-${key}`}
              checked={analysis[key as keyof typeof analysis]}
              onCheckedChange={(val) => onAnalysisToggle(key, val)}
              className="h-4 w-7"
            />
            <Label htmlFor={`ta-${key}`} className={`text-[10px] ${color}`}>
              {label}
            </Label>
          </div>
        ))}
      </div>
    </div>
  );
}
