"use client";

import { useState } from "react";
import Link from "next/link";
import {
  useAnalyzer,
  useMultiYearTrends,
  useInstrumentFundamentals,
  useInstrumentSeasonality,
  useInstrumentIndicators,
  useInstrumentChart,
  useInstrumentNews,
} from "@/hooks/use-trading";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, LabelList, LineChart, Line, ReferenceLine,
  ComposedChart, Area, Cell,
} from "recharts";

const TABS = [
  "Overview",
  "Seasonality",
  "Pattern",
  "Overbought - Oversold",
  "Fundamentals",
  "Financials",
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

type WeightedRow = {
  year: string;
  sales_per_share: number;
  net_income_per_share: number;
  fcf_per_share: number;
  gross_profit_per_share: number;
};

type Statements = {
  income: { year: string; revenue: number; gross_profit: number; operating_income: number; net_income: number; eps: number }[];
  balance_sheet: { year: string; total_assets: number; total_liabilities: number; total_equity: number; cash: number; long_term_debt: number }[];
  cash_flow: { year: string; operating_cash_flow: number; capex: number; free_cash_flow: number; financing_cash_flow: number }[];
};

type Fundamentals = {
  header: Header;
  income_series: IncomeRow[];
  shares_series: SharesRow[];
  weighted_financials: WeightedRow[];
  fair_value: FairValue;
  altman_z: Altman;
  piotroski_f: { score: number | null; verdict: string };
  beneish_m: { score: number | null; verdict: string };
  statements: Statements;
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
      {tab === "Seasonality" && <SeasonalityTab symbol={symbol} />}
      {tab === "Pattern" && <PatternTab symbol={symbol} />}
      {tab === "Overbought - Oversold" && <IndicatorsTab symbol={symbol} />}
      {tab === "Financials" && (
        <FinancialsTab fundamentals={fundamentals as Fundamentals | undefined} />
      )}
      {tab === "News" && <NewsTab symbol={symbol} />}
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

      <AgentPanel symbol={header?.symbol ?? "-"} />
    </div>
  );
}

/* --------------- AI Agent panel --------------- */

const AGENT_TOPICS: { key: string; label: string }[] = [
  { key: "whats_happening", label: "What's happening?" },
  { key: "business_simple", label: "Business explained simple" },
  { key: "competitors", label: "Competitors" },
  { key: "suppliers_clients", label: "Suppliers / Clients" },
  { key: "future_expectations", label: "Future Expectations" },
  { key: "full_analysis", label: "Full Analysis" },
  { key: "qualitative_scorecard", label: "Qualitative Scorecard" },
  { key: "investor_sentiment", label: "Investor Sentiment" },
];

type AgentResponse = {
  markdown?: string;
  error?: string;
  configure_hint?: string;
  model?: string;
  usage?: { input_tokens: number; output_tokens: number };
};

function AgentPanel({ symbol }: { symbol: string }) {
  const [active, setActive] = useState<string>("");
  const [response, setResponse] = useState<AgentResponse | null>(null);
  const [loading, setLoading] = useState(false);

  async function run(topic: string) {
    setActive(topic);
    setLoading(true);
    setResponse(null);
    try {
      const r = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/instrument/${symbol}/agent/${topic}`,
      );
      const json = (await r.json()) as AgentResponse;
      setResponse(json);
    } catch (e) {
      setResponse({ error: (e as Error).message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-lg border border-indigo-900/40 bg-gradient-to-br from-zinc-950 to-indigo-950/30 p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-xs font-semibold uppercase tracking-wider text-indigo-300">
          AI Agent
        </div>
        <div className="text-[10px] text-zinc-500">
          Powered by Claude. Cached 24h per topic to control cost.
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {AGENT_TOPICS.map((t) => (
          <button
            key={t.key}
            onClick={() => run(t.key)}
            disabled={loading && active === t.key}
            className={cn(
              "rounded-md border p-2 text-xs transition",
              active === t.key
                ? "border-indigo-500 bg-indigo-600/20 text-indigo-200"
                : "border-zinc-700 bg-zinc-900/50 text-zinc-200 hover:border-indigo-500/60 hover:text-indigo-200",
            )}
          >
            {loading && active === t.key ? "Thinking..." : t.label}
          </button>
        ))}
      </div>

      {response && (
        <div className="mt-3 rounded-md border border-zinc-800 bg-zinc-900/70 p-3">
          {response.error ? (
            <div className="text-sm text-amber-300">
              {response.error}
              {response.configure_hint && (
                <div className="mt-1 text-xs text-amber-200/80">{response.configure_hint}</div>
              )}
            </div>
          ) : (
            <>
              <div className="mb-2 flex items-center justify-between text-[10px] text-zinc-500">
                <span>{AGENT_TOPICS.find((t) => t.key === active)?.label}</span>
                {response.usage && (
                  <span>
                    {response.usage.input_tokens} in / {response.usage.output_tokens} out
                  </span>
                )}
              </div>
              <MarkdownLite text={response.markdown ?? ""} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

function MarkdownLite({ text }: { text: string }) {
  // Minimal markdown rendering — bold, bullets, numbered lists, h3
  const lines = text.split(/\r?\n/);
  const out: React.ReactNode[] = [];
  let inList: "ul" | "ol" | null = null;
  let buffer: React.ReactNode[] = [];

  function flush() {
    if (buffer.length === 0) return;
    if (inList === "ul") out.push(<ul key={out.length} className="ml-4 list-disc space-y-0.5 text-sm">{buffer}</ul>);
    else if (inList === "ol") out.push(<ol key={out.length} className="ml-4 list-decimal space-y-0.5 text-sm">{buffer}</ol>);
    else out.push(<div key={out.length} className="space-y-1 text-sm text-zinc-200">{buffer}</div>);
    buffer = [];
  }

  function render(line: string): React.ReactNode {
    // **bold**
    const parts: React.ReactNode[] = [];
    const regex = /\*\*([^*]+)\*\*/g;
    let last = 0;
    let m: RegExpExecArray | null;
    let i = 0;
    while ((m = regex.exec(line))) {
      if (m.index > last) parts.push(line.slice(last, m.index));
      parts.push(<strong key={i++} className="font-semibold text-indigo-200">{m[1]}</strong>);
      last = m.index + m[0].length;
    }
    if (last < line.length) parts.push(line.slice(last));
    return parts;
  }

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flush();
      inList = null;
      continue;
    }
    if (/^###\s+/.test(line)) {
      flush();
      inList = null;
      out.push(
        <h3 key={out.length} className="mt-3 text-xs font-semibold uppercase text-indigo-300">
          {line.replace(/^###\s+/, "")}
        </h3>
      );
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      if (inList !== "ul") { flush(); inList = "ul"; }
      buffer.push(<li key={buffer.length}>{render(line.replace(/^[-*]\s+/, ""))}</li>);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      if (inList !== "ol") { flush(); inList = "ol"; }
      buffer.push(<li key={buffer.length}>{render(line.replace(/^\d+\.\s+/, ""))}</li>);
      continue;
    }
    if (inList) { flush(); inList = null; }
    buffer.push(<p key={buffer.length}>{render(line)}</p>);
  }
  flush();
  return <>{out}</>;
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

      {/* Piotroski F + Beneish M */}
      {(fundamentals.piotroski_f.score !== null || fundamentals.beneish_m.score !== null) && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <SolidityCard
            title="Piotroski F-Score"
            latest={fundamentals.piotroski_f.score !== null ? fundamentals.piotroski_f.score.toString() : "--"}
            verdict={fundamentals.piotroski_f.verdict}
            description={
              fundamentals.piotroski_f.verdict === "strong"
                ? "Strong fundamentals (7-9). High-quality company."
                : fundamentals.piotroski_f.verdict === "average"
                ? "Average fundamentals (4-6)."
                : fundamentals.piotroski_f.verdict === "weak"
                ? "Weak fundamentals (0-3). Red flags."
                : "No data."
            }
          />
          <SolidityCard
            title="Beneish M-Score"
            latest={
              fundamentals.beneish_m.score !== null
                ? fundamentals.beneish_m.score.toFixed(2)
                : "--"
            }
            verdict={fundamentals.beneish_m.verdict}
            description={
              fundamentals.beneish_m.verdict === "flagged"
                ? "M > -1.78: possible earnings manipulation."
                : fundamentals.beneish_m.verdict === "clean"
                ? "M <= -1.78: no manipulation flags."
                : "No data."
            }
          />
        </div>
      )}
    </div>
  );
}

function SolidityCard({
  title,
  latest,
  verdict,
  description,
}: {
  title: string;
  latest: string;
  verdict: string;
  description: string;
}) {
  const bg =
    verdict === "strong" || verdict === "clean"
      ? "border-emerald-500/30 bg-emerald-500/10"
      : verdict === "average"
      ? "border-amber-500/30 bg-amber-500/10"
      : verdict === "weak" || verdict === "flagged"
      ? "border-red-500/30 bg-red-500/10"
      : "border-zinc-700 bg-zinc-900/50";
  const color =
    verdict === "strong" || verdict === "clean"
      ? "text-emerald-400"
      : verdict === "average"
      ? "text-amber-400"
      : verdict === "weak" || verdict === "flagged"
      ? "text-red-400"
      : "text-zinc-400";
  return (
    <div className={cn("rounded-lg border p-4", bg)}>
      <div className="text-[10px] uppercase opacity-80">{title}</div>
      <div className={cn("mt-1 text-3xl font-bold", color)}>{latest}</div>
      <div className="mt-1 text-xs opacity-80">{description}</div>
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

/* --------------- Seasonality --------------- */

type SeasonalityMonth = {
  label: string;
  avg_pct: number | null;
  median_pct: number | null;
  win_rate: number | null;
  sample_size: number;
};

function SeasonalityTab({ symbol }: { symbol: string }) {
  const { data, isLoading } = useInstrumentSeasonality(symbol);
  if (isLoading) return <Skeleton className="h-64 w-full bg-zinc-800" />;
  if (!data) return null;
  const err = data.error as string | undefined;
  if (err) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
        {err}
      </div>
    );
  }
  const months = (data.months as SeasonalityMonth[]) ?? [];
  const heatmap = (data.heatmap as Record<string, number | string>[]) ?? [];
  const best = data.best_month as SeasonalityMonth | null;
  const worst = data.worst_month as SeasonalityMonth | null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="text-[10px] uppercase text-zinc-500">Years covered</div>
          <div className="mt-1 font-mono text-lg">{String(data.years_covered ?? 0)}</div>
        </div>
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3">
          <div className="text-[10px] uppercase text-emerald-300">Best month</div>
          <div className="mt-1 font-mono text-lg text-emerald-200">
            {best ? `${best.label} (+${best.avg_pct?.toFixed(2)}%)` : "-"}
          </div>
          <div className="text-[10px] text-emerald-300/80">
            {best && best.win_rate !== null ? `win rate ${best.win_rate}%` : ""}
          </div>
        </div>
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3">
          <div className="text-[10px] uppercase text-red-300">Worst month</div>
          <div className="mt-1 font-mono text-lg text-red-200">
            {worst ? `${worst.label} (${worst.avg_pct?.toFixed(2)}%)` : "-"}
          </div>
          <div className="text-[10px] text-red-300/80">
            {worst && worst.win_rate !== null ? `win rate ${worst.win_rate}%` : ""}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
          Average monthly return (all years)
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={months} margin={{ top: 20, right: 16, left: 8, bottom: 4 }}>
            <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
            <XAxis dataKey="label" stroke="#71717a" fontSize={11} />
            <YAxis
              stroke="#71717a"
              fontSize={11}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }}
              formatter={(v) => `${Number(v).toFixed(2)}%`}
            />
            <ReferenceLine y={0} stroke="#71717a" />
            <Bar dataKey="avg_pct">
              {months.map((m, i) => (
                <Cell
                  key={i}
                  fill={
                    m.avg_pct === null
                      ? "#3f3f46"
                      : m.avg_pct >= 0
                      ? "#34d399"
                      : "#f87171"
                  }
                />
              ))}
              <LabelList
                dataKey="avg_pct"
                position="top"
                formatter={(v) => (v === null ? "" : `${Number(v).toFixed(1)}%`)}
                style={{ fontSize: 10, fill: "#a1a1aa" }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {heatmap.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
            Year × Month heatmap (% return)
          </div>
          <div className="overflow-x-auto">
            <table className="text-xs font-mono">
              <thead>
                <tr>
                  <th className="p-2 text-zinc-400">Year</th>
                  {[
                    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
                  ].map((m) => (
                    <th key={m} className="px-2 py-1 text-zinc-400">{m}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {heatmap.map((row) => (
                  <tr key={String(row.year)}>
                    <td className="px-2 py-1 text-right text-zinc-400">{String(row.year)}</td>
                    {[
                      "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
                    ].map((m) => {
                      const v = row[m] as number | undefined;
                      return (
                        <td
                          key={m}
                          className="px-2 py-1 text-center"
                          style={{
                            background: heatCellBg(v),
                            color: v === undefined ? "#52525b" : "#fafafa",
                            minWidth: 46,
                          }}
                        >
                          {v === undefined ? "-" : `${v.toFixed(1)}%`}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function heatCellBg(v: number | undefined): string {
  if (v === undefined) return "transparent";
  const clamped = Math.max(-10, Math.min(10, v)) / 10;
  if (clamped > 0) return `rgba(52, 211, 153, ${0.15 + clamped * 0.5})`;
  return `rgba(248, 113, 113, ${0.15 - clamped * 0.5})`;
}

/* --------------- Pattern tab --------------- */

type Level = { price: number; level_type?: string; strength?: number; touches?: number };
type Trendline = { start_price: number; end_price: number; trend_type: string; touches?: number };
type Pattern = { pattern_type: string; confidence: number; description?: string; bias?: string };

type ChartPayload = {
  technical_analysis: {
    support_levels?: Level[];
    resistance_levels?: Level[];
    trendlines?: Trendline[];
    patterns?: Pattern[];
    trend_summary?: string;
  } | null;
};

function PatternTab({ symbol }: { symbol: string }) {
  const { data, isLoading } = useInstrumentChart(symbol);
  if (isLoading) return <Skeleton className="h-64 w-full bg-zinc-800" />;
  const payload = data as ChartPayload | undefined;
  const ta = payload?.technical_analysis;
  if (!ta) {
    return (
      <div className="rounded-lg border border-zinc-800 p-8 text-center text-sm text-zinc-500">
        No technical analysis available for this symbol.
      </div>
    );
  }
  const supports = ta.support_levels ?? [];
  const resistances = ta.resistance_levels ?? [];
  const trendlines = ta.trendlines ?? [];
  const patterns = ta.patterns ?? [];

  return (
    <div className="space-y-4">
      {ta.trend_summary && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="mb-1 text-xs font-semibold uppercase text-zinc-400">
            Trend Summary
          </div>
          <div className="text-sm text-zinc-200">{ta.trend_summary}</div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
            Support / Resistance
          </div>
          {supports.length === 0 && resistances.length === 0 ? (
            <div className="text-xs text-zinc-500">none detected</div>
          ) : (
            <ul className="space-y-1 text-sm">
              {resistances.slice(0, 4).map((lv, i) => (
                <li key={`r${i}`} className="flex justify-between">
                  <span className="text-red-400">resistance</span>
                  <span className="font-mono">${lv.price.toFixed(2)}</span>
                </li>
              ))}
              {supports.slice(0, 4).map((lv, i) => (
                <li key={`s${i}`} className="flex justify-between">
                  <span className="text-emerald-400">support</span>
                  <span className="font-mono">${lv.price.toFixed(2)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
            Trendlines
          </div>
          {trendlines.length === 0 ? (
            <div className="text-xs text-zinc-500">none detected</div>
          ) : (
            <ul className="space-y-1 text-sm">
              {trendlines.slice(0, 6).map((tl, i) => (
                <li key={i} className="flex justify-between">
                  <span
                    className={cn(
                      tl.trend_type === "uptrend" ? "text-emerald-400" : "text-red-400"
                    )}
                  >
                    {tl.trend_type}
                  </span>
                  <span className="font-mono">
                    ${tl.start_price.toFixed(2)} → ${tl.end_price.toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
            Chart Patterns
          </div>
          {patterns.length === 0 ? (
            <div className="text-xs text-zinc-500">none detected</div>
          ) : (
            <ul className="space-y-2 text-sm">
              {patterns.map((p, i) => (
                <li key={i}>
                  <div className="flex justify-between">
                    <span className="text-zinc-200">{p.pattern_type.replace(/_/g, " ")}</span>
                    <span
                      className={cn(
                        "text-xs font-mono",
                        p.bias === "bullish" ? "text-emerald-400" : "text-red-400"
                      )}
                    >
                      {(p.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  {p.description && (
                    <div className="text-xs text-zinc-500">{p.description}</div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

/* --------------- Overbought-Oversold tab --------------- */

type IndSeries = {
  snapshot: {
    rsi: number | null;
    macd_line: number | null;
    macd_signal: number | null;
    macd_hist: number | null;
    bb_upper: number | null;
    bb_lower: number | null;
    bb_pct: number | null;
  };
  series: {
    date: string; close: number;
    rsi: number | null; macd: number | null;
    macd_signal: number | null; macd_hist: number | null;
    bb_upper: number | null; bb_lower: number | null;
  }[];
  verdict: string;
};

const VERDICT_CLASS: Record<string, string> = {
  overbought: "text-red-400",
  bullish: "text-emerald-300",
  neutral: "text-zinc-300",
  bearish: "text-orange-300",
  oversold: "text-emerald-400",
};

function IndicatorsTab({ symbol }: { symbol: string }) {
  const { data, isLoading } = useInstrumentIndicators(symbol);
  if (isLoading) return <Skeleton className="h-96 w-full bg-zinc-800" />;
  const d = data as IndSeries | undefined;
  if (!d || !d.series) return null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="text-[10px] uppercase text-zinc-500">RSI (14)</div>
          <div className="mt-1 font-mono text-lg">
            {d.snapshot.rsi !== null ? d.snapshot.rsi.toFixed(1) : "-"}
          </div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="text-[10px] uppercase text-zinc-500">MACD Hist</div>
          <div
            className={cn(
              "mt-1 font-mono text-lg",
              d.snapshot.macd_hist !== null && d.snapshot.macd_hist >= 0
                ? "text-emerald-400"
                : "text-red-400"
            )}
          >
            {d.snapshot.macd_hist !== null ? d.snapshot.macd_hist.toFixed(3) : "-"}
          </div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="text-[10px] uppercase text-zinc-500">BB Position</div>
          <div className="mt-1 font-mono text-lg">
            {d.snapshot.bb_pct !== null
              ? `${(d.snapshot.bb_pct * 100).toFixed(0)}%`
              : "-"}
          </div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="text-[10px] uppercase text-zinc-500">Verdict</div>
          <div className={cn("mt-1 text-lg font-semibold uppercase", VERDICT_CLASS[d.verdict])}>
            {d.verdict}
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">RSI (14)</div>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={d.series} margin={{ top: 5, right: 16, left: 8, bottom: 4 }}>
            <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
            <XAxis dataKey="date" stroke="#71717a" fontSize={10} tick={false} />
            <YAxis stroke="#71717a" fontSize={11} domain={[0, 100]} />
            <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }} />
            <ReferenceLine y={70} stroke="#f87171" strokeDasharray="3 3" />
            <ReferenceLine y={30} stroke="#34d399" strokeDasharray="3 3" />
            <Line type="monotone" dataKey="rsi" stroke="#a78bfa" dot={false} strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">MACD</div>
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={d.series} margin={{ top: 5, right: 16, left: 8, bottom: 4 }}>
            <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
            <XAxis dataKey="date" stroke="#71717a" fontSize={10} tick={false} />
            <YAxis stroke="#71717a" fontSize={11} />
            <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }} />
            <ReferenceLine y={0} stroke="#52525b" />
            <Bar dataKey="macd_hist" fill="#34d39955" />
            <Line type="monotone" dataKey="macd" stroke="#60a5fa" dot={false} strokeWidth={1.5} />
            <Line type="monotone" dataKey="macd_signal" stroke="#f59e0b" dot={false} strokeWidth={1.5} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
          Price with Bollinger Bands
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={d.series} margin={{ top: 5, right: 16, left: 8, bottom: 4 }}>
            <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
            <XAxis dataKey="date" stroke="#71717a" fontSize={10} tick={false} />
            <YAxis stroke="#71717a" fontSize={11} />
            <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }} />
            <Area type="monotone" dataKey="bb_upper" stroke="#3f3f46" fill="#27272a66" />
            <Area type="monotone" dataKey="bb_lower" stroke="#3f3f46" fill="#09090b" />
            <Line type="monotone" dataKey="close" stroke="#06b6d4" dot={false} strokeWidth={1.5} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* --------------- Financial Statements tab --------------- */

function FinancialsTab({ fundamentals }: { fundamentals: Fundamentals | undefined }) {
  if (!fundamentals) return null;
  const { statements, weighted_financials, has_fundamentals } = fundamentals;
  if (!has_fundamentals) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
        Financial statements require an FMP Starter plan or higher. Data will
        populate automatically once the key is upgraded.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Weighted Financials per-share chart */}
      {weighted_financials.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
            Weighted Financials (per share)
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={weighted_financials} margin={{ top: 20, right: 16, left: 8, bottom: 4 }}>
              <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
              <XAxis dataKey="year" stroke="#71717a" fontSize={11} />
              <YAxis stroke="#71717a" fontSize={11} />
              <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }} />
              <Bar dataKey="sales_per_share" fill="#f59e0b" name="Sales/Sh" />
              <Bar dataKey="net_income_per_share" fill="#60a5fa" name="NI/Sh" />
              <Bar dataKey="fcf_per_share" fill="#34d399" name="FCF/Sh" />
              <Bar dataKey="gross_profit_per_share" fill="#a78bfa" name="GP/Sh" />
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-zinc-400">
            <LegendDot color="#f59e0b" label="Sales / Share" />
            <LegendDot color="#60a5fa" label="Net Income / Share" />
            <LegendDot color="#34d399" label="Free Cash Flow / Share" />
            <LegendDot color="#a78bfa" label="Gross Profit / Share" />
          </div>
        </div>
      )}

      {/* Income Statement */}
      <StatementTable
        title="Income Statement"
        rows={statements.income}
        columns={[
          { key: "revenue", label: "Revenue" },
          { key: "gross_profit", label: "Gross Profit" },
          { key: "operating_income", label: "Operating Income" },
          { key: "net_income", label: "Net Income" },
          { key: "eps", label: "EPS", format: "plain" },
        ]}
      />

      <StatementTable
        title="Balance Sheet"
        rows={statements.balance_sheet}
        columns={[
          { key: "total_assets", label: "Assets" },
          { key: "total_liabilities", label: "Liabilities" },
          { key: "total_equity", label: "Equity" },
          { key: "cash", label: "Cash" },
          { key: "long_term_debt", label: "LT Debt" },
        ]}
      />

      <StatementTable
        title="Cash Flow"
        rows={statements.cash_flow}
        columns={[
          { key: "operating_cash_flow", label: "CFO" },
          { key: "capex", label: "CapEx" },
          { key: "free_cash_flow", label: "FCF" },
          { key: "financing_cash_flow", label: "CFF" },
        ]}
      />
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

type ColDef = { key: string; label: string; format?: "plain" | "money" };

function StatementTable({
  title,
  rows,
  columns,
}: {
  title: string;
  rows: Record<string, number | string>[];
  columns: ColDef[];
}) {
  if (!rows.length) return null;
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">{title}</div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b border-zinc-800 text-left text-zinc-400">
              <th className="px-2 py-1">Metric</th>
              {rows.map((r) => (
                <th key={String(r.year)} className="px-2 py-1 text-right">{String(r.year)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {columns.map((col) => (
              <tr key={col.key} className="border-b border-zinc-800/50">
                <td className="px-2 py-1 text-zinc-300">{col.label}</td>
                {rows.map((r) => {
                  const raw = r[col.key];
                  const n = typeof raw === "number" ? raw : 0;
                  const formatted =
                    col.format === "plain" ? n.toFixed(2) : fmtMoney(n);
                  return (
                    <td
                      key={String(r.year)}
                      className={cn(
                        "px-2 py-1 text-right",
                        n < 0 ? "text-red-400" : "text-zinc-200"
                      )}
                    >
                      {formatted}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* --------------- News tab --------------- */

type NewsArticle = {
  source: string; title: string; description: string; link: string;
  pub_date: string; sentiment_score: number; sentiment: string;
};

function NewsTab({ symbol }: { symbol: string }) {
  const { data, isLoading } = useInstrumentNews(symbol);
  if (isLoading) return <Skeleton className="h-64 w-full bg-zinc-800" />;
  const articles = ((data as { articles: NewsArticle[] } | undefined)?.articles) ?? [];
  if (articles.length === 0) {
    return (
      <div className="rounded-lg border border-zinc-800 p-8 text-center text-sm text-zinc-500">
        No news mentioning {symbol} in the recent feed.
      </div>
    );
  }
  return (
    <ul className="space-y-2">
      {articles.map((a, i) => (
        <li key={i} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <div className="flex items-center justify-between gap-3">
            <a
              href={a.link}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-cyan-400 hover:underline"
            >
              {a.title}
            </a>
            <span
              className={cn(
                "rounded px-1.5 py-0.5 text-[10px] font-mono uppercase",
                a.sentiment === "positive" && "bg-emerald-500/20 text-emerald-300",
                a.sentiment === "negative" && "bg-red-500/20 text-red-300",
                a.sentiment === "neutral" && "bg-zinc-700 text-zinc-300",
              )}
            >
              {a.sentiment} {a.sentiment_score > 0 ? "+" : ""}{a.sentiment_score.toFixed(1)}
            </span>
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            {a.source} · {a.pub_date?.slice(0, 16)}
          </div>
          {a.description && (
            <p className="mt-1 text-xs text-zinc-400 line-clamp-2">{a.description}</p>
          )}
        </li>
      ))}
    </ul>
  );
}
