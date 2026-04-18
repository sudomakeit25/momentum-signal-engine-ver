"use client";

import { useState } from "react";
import Link from "next/link";
import {
  useAnalyzer,
  useMultiYearTrends,
  useInstrumentFundamentals,
} from "@/hooks/use-trading";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, LabelList,
} from "recharts";

const TABS = [
  "Overview",
  "Seasonality",
  "Pattern",
  "Overbought - Oversold",
  "Fundamentals",
  "News",
] as const;

type Tab = typeof TABS[number];

type Header = {
  symbol: string;
  name: string;
  logo: string;
  sector: string;
  industry: string;
  country: string;
  exchange: string;
  market_cap: number;
  price: number;
  last_close: number;
  eps_ttm: number;
  pe_ttm: number;
  dividend_yield_pct: number;
  shareholders_yield_pct: number;
  next_earnings: string;
};

type IncomeRow = {
  year: string;
  revenue: number;
  net_income: number;
  gross_profit: number;
  operating_income: number;
};

type SharesRow = {
  year: string;
  shares_outstanding: number;
  market_cap: number;
  enterprise_value: number;
};

type FairValue = {
  method: string | null;
  fair_value: number | null;
  current_price: number | null;
  deviation_pct: number | null;
};

type Altman = {
  series: { year: string; z_score: number | null; verdict: string }[];
  latest: number | null;
  verdict: string;
};

type Fundamentals = {
  header: Header;
  income_series: IncomeRow[];
  shares_series: SharesRow[];
  fair_value: FairValue;
  altman_z: Altman;
  has_fundamentals: boolean;
};

function fmtMoney(n: number) {
  if (!n) return "--";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toFixed(2)}`;
}

function fmtShares(n: number) {
  if (!n) return "--";
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  return n.toFixed(0);
}

function verdictColor(v: string) {
  if (v === "safe") return "text-emerald-400";
  if (v === "grey") return "text-amber-400";
  if (v === "distress") return "text-red-400";
  return "text-zinc-500";
}

function verdictLabel(v: string) {
  if (v === "safe") return "Low risk of bankruptcy";
  if (v === "grey") return "Grey zone (moderate risk)";
  if (v === "distress") return "Distress zone (high risk)";
  return "No data";
}

export default function InstrumentPage({
  params,
}: {
  params: { symbol: string };
}) {
  const symbol = params.symbol.toUpperCase();
  const [tab, setTab] = useState<Tab>("Overview");

  const { data: fundamentals, isLoading: fLoading } =
    useInstrumentFundamentals(symbol);
  const { data: analyzer } = useAnalyzer(symbol);
  const { data: trends } = useMultiYearTrends(symbol);

  const header = (fundamentals as Fundamentals | undefined)?.header;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        {header?.logo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={header.logo} alt={symbol} className="h-10 w-10 rounded-full bg-white" />
        ) : (
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-zinc-800 text-xs font-bold text-cyan-400">
            {symbol.slice(0, 3)}
          </div>
        )}
        <div>
          <h1 className="text-xl font-bold">{header?.name || symbol}</h1>
          <div className="text-xs text-zinc-500">
            {symbol} {header?.exchange && `· ${header.exchange}`}
          </div>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2 text-xs">
          {header?.sector && (
            <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-zinc-300">
              {header.sector}
            </span>
          )}
          {header?.industry && (
            <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-zinc-300">
              {header.industry}
            </span>
          )}
          {header?.country && (
            <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-zinc-400">
              {header.country}
            </span>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 border-b border-zinc-800">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-3 py-1.5 text-xs transition",
              tab === t
                ? "border-b-2 border-cyan-500 text-cyan-400"
                : "text-zinc-400 hover:text-zinc-200",
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "Overview" && (
        <OverviewTab
          header={header}
          analyzer={analyzer as Record<string, unknown> | undefined}
          trends={trends as Record<string, unknown> | undefined}
        />
      )}
      {tab === "Fundamentals" && (
        <FundamentalsTab
          fundamentals={fundamentals as Fundamentals | undefined}
          loading={fLoading}
        />
      )}
      {(tab === "Seasonality" || tab === "Pattern" || tab === "Overbought - Oversold" || tab === "News") && (
        <PlaceholderTab tab={tab} symbol={symbol} />
      )}
    </div>
  );
}

/* --------------- Overview --------------- */

function OverviewTab({
  header,
  analyzer,
  trends,
}: {
  header: Header | undefined;
  analyzer: Record<string, unknown> | undefined;
  trends: Record<string, unknown> | undefined;
}) {
  const returns = (trends?.returns as Record<string, number | null> | undefined) ?? {};
  const verdict = analyzer?.verdict as string | undefined;
  const grade = analyzer?.grade as string | undefined;
  const score = analyzer?.composite_score as number | undefined;

  return (
    <div className="space-y-4">
      {/* Verdict strip */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="text-[10px] uppercase text-zinc-500">Analyzer</div>
            <div className="mt-1 flex items-baseline gap-3">
              <span className="text-2xl font-bold text-cyan-400">{grade ?? "-"}</span>
              <span className="font-mono text-lg">{score !== undefined ? score.toFixed(0) : "-"}</span>
              <span className="text-xs text-zinc-400">
                {verdict?.replace("_", " ") || "no verdict"}
              </span>
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase text-zinc-500">Regime</div>
            <div className="mt-1 text-sm text-zinc-200">
              {(trends?.regime as string)?.replace(/_/g, " ") ?? "-"}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase text-zinc-500">Price</div>
            <div className="mt-1 font-mono text-lg">
              {header?.price ? `$${header.price.toFixed(2)}` : "--"}
            </div>
          </div>
        </div>
      </div>

      {/* Returns grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-6">
        <ReturnTile label="Price" value={header?.price ? `$${header.price.toFixed(2)}` : "--"} />
        <ReturnTile label="1Y" value={fmtPctOrDash(returns["1y_pct"])} sign />
        <ReturnTile label="3Y" value={fmtPctOrDash(returns["3y_pct"])} sign />
        <ReturnTile label="5Y" value={fmtPctOrDash(returns["5y_pct"])} sign />
        <ReturnTile
          label="Market Cap"
          value={header?.market_cap ? fmtMoney(header.market_cap) : "--"}
        />
        <ReturnTile
          label="P/E (TTM)"
          value={header?.pe_ttm ? header.pe_ttm.toFixed(2) : "--"}
        />
      </div>

      {/* AI agent placeholder */}
      <div className="rounded-lg border border-zinc-800 bg-gradient-to-br from-zinc-950 to-indigo-950/30 p-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-indigo-300">
          AI Agent (coming soon)
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {[
            "What's happening?",
            "Business explained simple",
            "Competitors",
            "Suppliers / Clients",
            "Future Expectations",
            "Full Analysis",
            "Qualitative Scorecard",
            "Investor Sentiment",
          ].map((label) => (
            <button
              key={label}
              disabled
              className="cursor-not-allowed rounded-md border border-zinc-700 bg-zinc-900/50 p-2 text-xs text-zinc-400 opacity-70"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ReturnTile({
  label,
  value,
  sign,
}: {
  label: string;
  value: string;
  sign?: boolean;
}) {
  const isPos = sign && value.startsWith("+");
  const isNeg = sign && value.startsWith("-");
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="text-[10px] uppercase text-zinc-500">{label}</div>
      <div
        className={cn(
          "mt-1 font-mono text-base",
          isPos && "text-emerald-400",
          isNeg && "text-red-400",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function fmtPctOrDash(v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

/* --------------- Fundamentals --------------- */

function FundamentalsTab({
  fundamentals,
  loading,
}: {
  fundamentals: Fundamentals | undefined;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-40 w-full bg-zinc-800" />
        ))}
      </div>
    );
  }
  if (!fundamentals) return null;

  const { header, income_series, shares_series, fair_value, altman_z, has_fundamentals } =
    fundamentals;

  return (
    <div className="space-y-4">
      {/* Key metrics row */}
      <div className="grid grid-cols-2 gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 sm:grid-cols-4 lg:grid-cols-8">
        <MetricCell label="Market Cap" value={header.market_cap ? fmtMoney(header.market_cap) : "--"} />
        <MetricCell label="Last Close" value={header.last_close ? `$${header.last_close.toFixed(2)}` : "--"} />
        <MetricCell label="EPS (TTM)" value={header.eps_ttm ? header.eps_ttm.toFixed(2) : "--"} />
        <MetricCell label="P/E (TTM)" value={header.pe_ttm ? header.pe_ttm.toFixed(2) : "--"} />
        <MetricCell
          label="Dividend Yield"
          value={header.dividend_yield_pct ? `${header.dividend_yield_pct.toFixed(2)}%` : "--"}
        />
        <MetricCell
          label="Shareholders Yield"
          value={
            header.shareholders_yield_pct
              ? `${header.shareholders_yield_pct.toFixed(2)}%`
              : "--"
          }
        />
        <MetricCell
          label="Next Earnings"
          value={header.next_earnings ? String(header.next_earnings).slice(0, 10) : "--"}
        />
        <MetricCell label="Exchange" value={header.exchange || "--"} />
      </div>

      {!has_fundamentals && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
          Fundamentals (income statement, balance sheet, enterprise value) require
          an FMP Starter plan or higher. Once <code>FMP_API_KEY</code> is
          provisioned with a paid plan the charts below will populate automatically.
          The linked{" "}
          <Link href="/analyzer" className="underline">
            Analyzer
          </Link>{" "}
          page still works with price-based signals from Alpaca.
        </div>
      )}

      {/* Sales vs Net Income */}
      {income_series.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-xs font-semibold uppercase text-zinc-400">
              Sales vs Net Income
            </div>
            <span className="text-[10px] text-zinc-500">annual</span>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={income_series} margin={{ top: 20, right: 16, left: 8, bottom: 4 }}>
              <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
              <XAxis dataKey="year" stroke="#71717a" fontSize={11} />
              <YAxis
                stroke="#71717a"
                fontSize={11}
                tickFormatter={(v) => fmtMoney(Number(v))}
              />
              <Tooltip
                contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }}
                formatter={(v) => fmtMoney(Number(v))}
              />
              <Bar dataKey="revenue" fill="#60a5fa" name="Sales">
                <LabelList
                  dataKey="revenue"
                  position="top"
                  formatter={(v) => fmtMoney(Number(v))}
                  style={{ fill: "#60a5fa", fontSize: 10 }}
                />
              </Bar>
              <Bar dataKey="net_income" fill="#34d399" name="Net Income">
                <LabelList
                  dataKey="net_income"
                  position="top"
                  formatter={(v) => fmtMoney(Number(v))}
                  style={{ fill: "#34d399", fontSize: 10 }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Shares Outstanding */}
      {shares_series.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
            Shares Outstanding
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={shares_series} margin={{ top: 20, right: 16, left: 8, bottom: 4 }}>
              <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
              <XAxis dataKey="year" stroke="#71717a" fontSize={11} />
              <YAxis
                stroke="#71717a"
                fontSize={11}
                tickFormatter={(v) => fmtShares(Number(v))}
              />
              <Tooltip
                contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }}
                formatter={(v) => fmtShares(Number(v))}
              />
              <Bar dataKey="shares_outstanding" fill="#06b6d4">
                <LabelList
                  dataKey="shares_outstanding"
                  position="top"
                  formatter={(v) => fmtShares(Number(v))}
                  style={{ fill: "#06b6d4", fontSize: 10 }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Fair value */}
      {fair_value.fair_value !== null && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="text-[10px] uppercase text-zinc-500">Fair Value (EV/Sales)</div>
            <div className="mt-2 font-mono text-2xl text-zinc-100">
              ${fair_value.fair_value.toFixed(2)}
            </div>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="text-[10px] uppercase text-zinc-500">Current Price</div>
            <div className="mt-2 font-mono text-2xl text-zinc-100">
              {fair_value.current_price !== null
                ? `$${fair_value.current_price.toFixed(2)}`
                : "--"}
            </div>
          </div>
          <div
            className={cn(
              "rounded-lg border p-4",
              fair_value.deviation_pct !== null && fair_value.deviation_pct > 0
                ? "border-red-500/30 bg-red-500/10 text-red-200"
                : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200",
            )}
          >
            <div className="text-[10px] uppercase opacity-70">vs Fair Value</div>
            <div className="mt-2 font-mono text-2xl">
              {fair_value.deviation_pct !== null
                ? `${fair_value.deviation_pct > 0 ? "+" : ""}${fair_value.deviation_pct.toFixed(2)}%`
                : "--"}
            </div>
            <div className="mt-1 text-[10px] opacity-80">
              {fair_value.deviation_pct !== null && fair_value.deviation_pct > 0
                ? "above fair value (overvalued)"
                : "below fair value (undervalued)"}
            </div>
          </div>
        </div>
      )}

      {/* Altman Z-Score */}
      {altman_z.series.length > 0 && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 lg:col-span-2">
            <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
              Altman Z-Score
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={altman_z.series} margin={{ top: 20, right: 16, left: 8, bottom: 4 }}>
                <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
                <XAxis dataKey="year" stroke="#71717a" fontSize={11} />
                <YAxis stroke="#71717a" fontSize={11} />
                <Tooltip
                  contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }}
                />
                <Bar dataKey="z_score" fill="#34d399">
                  <LabelList
                    dataKey="z_score"
                    position="top"
                    style={{ fill: "#34d399", fontSize: 10 }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div
            className={cn(
              "flex flex-col justify-center rounded-lg border p-6 text-center",
              altman_z.verdict === "safe" && "border-emerald-500/30 bg-emerald-500/10",
              altman_z.verdict === "grey" && "border-amber-500/30 bg-amber-500/10",
              altman_z.verdict === "distress" && "border-red-500/30 bg-red-500/10",
            )}
          >
            <div className="text-[10px] uppercase opacity-70">Altman Z-Score (latest)</div>
            <div className={cn("mt-2 text-4xl font-bold", verdictColor(altman_z.verdict))}>
              {altman_z.latest !== null ? altman_z.latest.toFixed(2) : "--"}
            </div>
            <div className="mt-2 text-xs opacity-80">{verdictLabel(altman_z.verdict)}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase text-zinc-500">{label}</div>
      <div className="mt-1 font-mono text-sm text-zinc-100">{value}</div>
    </div>
  );
}

/* --------------- Placeholder tabs --------------- */

function PlaceholderTab({ tab, symbol }: { tab: string; symbol: string }) {
  const links: Record<string, string> = {
    Seasonality: "",
    Pattern: `/technical?symbol=${symbol}`,
    "Overbought - Oversold": `/technical?symbol=${symbol}`,
    News: `/news`,
  };
  const link = links[tab];
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-8 text-center">
      <div className="mb-2 text-sm font-semibold text-zinc-200">{tab} coming soon</div>
      <div className="text-xs text-zinc-500">
        {link ? (
          <>
            Closest existing page:{" "}
            <Link href={link} className="text-cyan-400 hover:underline">
              {link}
            </Link>
          </>
        ) : (
          "This tab will be implemented in Phase 2."
        )}
      </div>
    </div>
  );
}
