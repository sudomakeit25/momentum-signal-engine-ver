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
  useMarketNews,
  useInstrumentInsider,
  useInstrumentEvents,
  useTranscriptList,
} from "@/hooks/use-trading";
import { useWatchlist } from "@/hooks/use-watchlist";
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
  "Insider",
  "Transcripts",
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
  peter_lynch: number | null;
  peter_lynch_deviation_pct: number | null;
  dcf: number | null;
  dcf_deviation_pct: number | null;
  growth_assumption_pct: number;
};

type KeyMetrics = {
  gross_margin_pct: number | null;
  operating_margin_pct: number | null;
  net_margin_pct: number | null;
  roe_pct: number | null;
  roa_pct: number | null;
  debt_to_equity: number | null;
  interest_coverage: number | null;
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
  shareholders_yield_pct: number | null;
  key_metrics: KeyMetrics;
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

const CURRENCY_BY_SUFFIX: Record<string, string> = {
  PA: "EUR", DE: "EUR", AS: "EUR", BR: "EUR", MI: "EUR", MC: "EUR", VI: "EUR",
  L: "GBP",
  TO: "CAD", V: "CAD",
  SW: "CHF",
  TA: "ILS",
  HK: "HKD",
  T: "JPY",
  TW: "TWD",
  SS: "CNY", SZ: "CNY",
  KS: "KRW",
  AX: "AUD",
  SA: "BRL",
  MX: "MXN",
  NS: "INR",
  ST: "SEK", OL: "NOK", HE: "EUR", CO: "DKK",
};

function currencyForSymbol(symbol: string): string {
  const parts = symbol.split(".");
  if (parts.length === 2) {
    const suffix = parts[1].toUpperCase();
    if (suffix in CURRENCY_BY_SUFFIX) return CURRENCY_BY_SUFFIX[suffix];
  }
  if (symbol.includes("/")) return "USD";  // crypto pairs vs USD
  return "USD";
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
          {(() => {
            const ccy = currencyForSymbol(symbol);
            if (ccy === "USD") return null;
            return (
              <span className="rounded-full border border-indigo-500/40 bg-indigo-500/10 px-2 py-0.5 font-mono text-indigo-300">
                {ccy}
              </span>
            );
          })()}
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
      {tab === "Insider" && <InsiderTab symbol={symbol} />}
      {tab === "Transcripts" && <TranscriptsTab symbol={symbol} />}
      {tab === "News" && <NewsTab symbol={symbol} />}
    </div>
  );
}

/* --------------- Insider tab --------------- */

type InsiderTrade = {
  filing_date: string;
  transaction_date: string;
  reporter_name: string;
  reporter_title: string;
  transaction_type: string;
  shares: number;
  price: number;
  value: number;
  acquired_disposed: string;
  link: string;
};

function InsiderTab({ symbol }: { symbol: string }) {
  const { data, isLoading } = useInstrumentInsider(symbol);
  if (isLoading) return <Skeleton className="h-64 w-full bg-zinc-800" />;
  const trades = ((data as { trades: InsiderTrade[] } | undefined)?.trades) ?? [];

  if (trades.length === 0) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
        No insider transactions available. Requires FMP Starter plan for the
        insider-trading endpoint — data will populate automatically once
        configured.
      </div>
    );
  }

  // Aggregate buys vs sells over last 6 months
  const now = Date.now();
  const sixMonthsMs = 180 * 24 * 60 * 60 * 1000;
  const recent = trades.filter((t) => {
    const d = new Date(t.filing_date).getTime();
    return d && now - d < sixMonthsMs;
  });
  const buyValue = recent
    .filter((t) => (t.acquired_disposed || "").toUpperCase().startsWith("A"))
    .reduce((a, b) => a + b.value, 0);
  const sellValue = recent
    .filter((t) => (t.acquired_disposed || "").toUpperCase().startsWith("D"))
    .reduce((a, b) => a + b.value, 0);
  const netValue = buyValue - sellValue;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3">
          <div className="text-[10px] uppercase text-emerald-300">Buys (6mo)</div>
          <div className="mt-1 font-mono text-lg text-emerald-200">
            {fmtMoney(buyValue)}
          </div>
        </div>
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3">
          <div className="text-[10px] uppercase text-red-300">Sells (6mo)</div>
          <div className="mt-1 font-mono text-lg text-red-200">
            {fmtMoney(sellValue)}
          </div>
        </div>
        <div
          className={cn(
            "rounded-lg border p-3",
            netValue >= 0
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
              : "border-red-500/30 bg-red-500/10 text-red-200",
          )}
        >
          <div className="text-[10px] uppercase opacity-80">Net (6mo)</div>
          <div className="mt-1 font-mono text-lg">
            {netValue >= 0 ? "+" : ""}
            {fmtMoney(netValue)}
          </div>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-zinc-800">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900/50 text-left text-[10px] uppercase text-zinc-400">
              <th className="px-3 py-2">Filed</th>
              <th className="px-3 py-2">Reporter</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2 text-right">Shares</th>
              <th className="px-3 py-2 text-right">Price</th>
              <th className="px-3 py-2 text-right">Value</th>
              <th className="px-3 py-2">A/D</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => {
              const isBuy = (t.acquired_disposed || "").toUpperCase().startsWith("A");
              return (
                <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                  <td className="px-3 py-1.5 font-mono text-zinc-400">
                    {t.filing_date}
                  </td>
                  <td className="px-3 py-1.5 text-zinc-200">{t.reporter_name || "-"}</td>
                  <td className="px-3 py-1.5 text-zinc-400">{t.reporter_title || "-"}</td>
                  <td className="px-3 py-1.5 text-zinc-400">{t.transaction_type || "-"}</td>
                  <td className="px-3 py-1.5 text-right font-mono">
                    {t.shares ? t.shares.toLocaleString() : "-"}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-zinc-300">
                    {t.price ? `$${t.price.toFixed(2)}` : "-"}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono">
                    {t.value ? fmtMoney(t.value) : "-"}
                  </td>
                  <td className={cn(
                    "px-3 py-1.5 font-semibold",
                    isBuy ? "text-emerald-400" : "text-red-400",
                  )}>
                    {isBuy ? "Buy" : "Sell"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
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

      <EventsPanel symbol={header?.symbol ?? "-"} />

      <AgentPanel symbol={header?.symbol ?? "-"} />
    </div>
  );
}

/* --------------- Events panel --------------- */

type EventsPayload = {
  next_earnings: { date: string; eps_estimated: number | null; revenue_estimated: number | null } | null;
  recent_earnings: {
    date: string; eps: number | null; eps_estimated: number | null;
    revenue: number | null; surprise_pct: number | null;
  }[];
  recent_dividends: {
    date: string; dividend: number | null;
    record_date: string | null; payment_date: string | null;
  }[];
  recent_splits: {
    date: string; ratio: string | null;
    numerator: number | null; denominator: number | null;
  }[];
};

function EventsPanel({ symbol }: { symbol: string }) {
  const { data } = useInstrumentEvents(symbol);
  const d = data as EventsPayload | undefined;
  if (!d) return null;
  const hasAny =
    d.next_earnings !== null ||
    d.recent_earnings.length > 0 ||
    d.recent_dividends.length > 0 ||
    d.recent_splits.length > 0;
  if (!hasAny) return null;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-xs font-semibold uppercase text-zinc-400">Key Events</div>
        {d.next_earnings && (
          <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-200">
            Next earnings: {d.next_earnings.date}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div>
          <div className="mb-1 text-[10px] uppercase text-zinc-500">Recent earnings</div>
          {d.recent_earnings.length === 0 ? (
            <div className="text-xs text-zinc-500">no data</div>
          ) : (
            <ul className="space-y-1 text-xs">
              {d.recent_earnings.slice(0, 4).map((e) => (
                <li key={e.date} className="flex items-center justify-between">
                  <span className="font-mono text-zinc-400">{e.date}</span>
                  <span>
                    <span className="font-mono text-zinc-200">
                      {e.eps !== null ? `$${e.eps.toFixed(2)}` : "-"}
                    </span>
                    {e.surprise_pct !== null && (
                      <span className={cn(
                        "ml-2 font-mono text-[10px]",
                        e.surprise_pct >= 0 ? "text-emerald-400" : "text-red-400",
                      )}>
                        {e.surprise_pct >= 0 ? "+" : ""}{e.surprise_pct.toFixed(1)}%
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <div className="mb-1 text-[10px] uppercase text-zinc-500">Dividends</div>
          {d.recent_dividends.length === 0 ? (
            <div className="text-xs text-zinc-500">none</div>
          ) : (
            <ul className="space-y-1 text-xs">
              {d.recent_dividends.slice(0, 4).map((x) => (
                <li key={x.date} className="flex items-center justify-between">
                  <span className="font-mono text-zinc-400">{x.date}</span>
                  <span className="font-mono text-emerald-300">
                    {x.dividend !== null ? `$${x.dividend.toFixed(3)}` : "-"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <div className="mb-1 text-[10px] uppercase text-zinc-500">Splits</div>
          {d.recent_splits.length === 0 ? (
            <div className="text-xs text-zinc-500">none in recent history</div>
          ) : (
            <ul className="space-y-1 text-xs">
              {d.recent_splits.map((s) => (
                <li key={s.date} className="flex items-center justify-between">
                  <span className="font-mono text-zinc-400">{s.date}</span>
                  <span className="font-mono text-zinc-200">
                    {s.ratio ?? (s.numerator && s.denominator ? `${s.numerator}:${s.denominator}` : "-")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
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

      {/* Valuation methods */}
      {(fair_value.fair_value !== null ||
        fair_value.peter_lynch !== null ||
        fair_value.dcf !== null) && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-xs font-semibold uppercase text-zinc-400">
              Fair Value Estimates (current: ${fair_value.current_price?.toFixed(2) ?? "--"})
            </div>
            <div className="text-[10px] text-zinc-500">
              Growth assumption: {fair_value.growth_assumption_pct.toFixed(1)}%/yr
            </div>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <ValuationCard
              label="EV / Sales"
              value={fair_value.fair_value}
              deviation={fair_value.deviation_pct}
            />
            <ValuationCard
              label="Peter Lynch"
              value={fair_value.peter_lynch}
              deviation={fair_value.peter_lynch_deviation_pct}
              note="EPS × (growth + yield), capped at 30"
            />
            <ValuationCard
              label="DCF"
              value={fair_value.dcf}
              deviation={fair_value.dcf_deviation_pct}
              note="10y projection, 10% discount, 2.5% terminal"
            />
          </div>
        </div>
      )}

      {/* Key metrics + shareholders yield */}
      {(fundamentals.shareholders_yield_pct !== null ||
        Object.values(fundamentals.key_metrics).some((v) => v !== null)) && (
        <div className="grid grid-cols-2 gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 sm:grid-cols-4 lg:grid-cols-8">
          <MetricCell
            label="Gross Margin"
            value={fmtPctMaybe(fundamentals.key_metrics.gross_margin_pct)}
          />
          <MetricCell
            label="Op Margin"
            value={fmtPctMaybe(fundamentals.key_metrics.operating_margin_pct)}
          />
          <MetricCell
            label="Net Margin"
            value={fmtPctMaybe(fundamentals.key_metrics.net_margin_pct)}
          />
          <MetricCell
            label="ROE"
            value={fmtPctMaybe(fundamentals.key_metrics.roe_pct)}
          />
          <MetricCell
            label="ROA"
            value={fmtPctMaybe(fundamentals.key_metrics.roa_pct)}
          />
          <MetricCell
            label="Debt/Equity"
            value={
              fundamentals.key_metrics.debt_to_equity !== null
                ? fundamentals.key_metrics.debt_to_equity.toFixed(2)
                : "--"
            }
          />
          <MetricCell
            label="Int Coverage"
            value={
              fundamentals.key_metrics.interest_coverage !== null
                ? `${fundamentals.key_metrics.interest_coverage.toFixed(1)}×`
                : "--"
            }
          />
          <MetricCell
            label="Shareholders Yield"
            value={
              fundamentals.shareholders_yield_pct !== null
                ? `${fundamentals.shareholders_yield_pct.toFixed(2)}%`
                : "--"
            }
          />
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

function ValuationCard({
  label,
  value,
  deviation,
  note,
}: {
  label: string;
  value: number | null;
  deviation: number | null;
  note?: string;
}) {
  const hasValue = value !== null;
  const isOver = deviation !== null && deviation > 0;
  return (
    <div
      className={cn(
        "rounded-md border p-3",
        !hasValue
          ? "border-zinc-800 bg-zinc-900/50"
          : isOver
          ? "border-red-500/30 bg-red-500/10"
          : "border-emerald-500/30 bg-emerald-500/10",
      )}
    >
      <div className="flex items-center justify-between text-[10px] uppercase opacity-80">
        <span>{label}</span>
        <span>
          {deviation !== null
            ? `${deviation > 0 ? "+" : ""}${deviation.toFixed(1)}%`
            : "—"}
        </span>
      </div>
      <div className="mt-1 font-mono text-2xl">
        {hasValue ? `$${value.toFixed(2)}` : "n/a"}
      </div>
      {note && <div className="mt-1 text-[10px] opacity-70">{note}</div>}
    </div>
  );
}

function fmtPctMaybe(v: number | null): string {
  if (v === null) return "--";
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

/* --------------- Seasonality --------------- */

type SeasonalityMonth = {
  month: number;
  label: string;
  avg_pct: number | null;
  median_pct: number | null;
  win_rate: number | null;
  sample_size: number;
};

type HeatmapRow = { year: number } & Record<string, number | undefined>;

const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function SeasonalityTab({ symbol }: { symbol: string }) {
  const { data, isLoading } = useInstrumentSeasonality(symbol);
  const [sampleSize, setSampleSize] = useState<number | "all">("all");
  const [showCharts, setShowCharts] = useState(false);

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

  const fullHeatmap = ((data.heatmap as HeatmapRow[]) ?? []).slice().sort(
    (a, b) => (b.year as number) - (a.year as number),
  );

  const rows =
    sampleSize === "all" ? fullHeatmap : fullHeatmap.slice(0, sampleSize as number);

  // Recompute aggregates from the filtered rows so the top row reflects
  // exactly the selected sample.
  const aggregates: SeasonalityMonth[] = MONTH_LABELS.map((label, i) => {
    const values: number[] = [];
    for (const row of rows) {
      const v = row[label];
      if (typeof v === "number") values.push(v);
    }
    if (!values.length) {
      return { month: i + 1, label, avg_pct: null, median_pct: null, win_rate: null, sample_size: 0 };
    }
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    const wins = values.filter((v) => v > 0).length;
    return {
      month: i + 1,
      label,
      avg_pct: avg,
      median_pct: null,
      win_rate: (wins / values.length) * 100,
      sample_size: values.length,
    };
  });

  const sampleOptions: (number | "all")[] = [5, 10, 15, 20, 25, "all"];

  function csvEscape(s: string): string {
    return s.includes(",") ? `"${s}"` : s;
  }
  function downloadCsv() {
    const header = ["Year", ...MONTH_LABELS];
    const lines: string[] = [header.join(",")];
    lines.push(
      [
        "Probability %",
        ...aggregates.map((m) =>
          m.win_rate !== null ? `${m.win_rate.toFixed(0)}%` : "--"
        ),
      ].join(",")
    );
    lines.push(
      [
        "Average return %",
        ...aggregates.map((m) =>
          m.avg_pct !== null ? `${m.avg_pct.toFixed(2)}%` : "--"
        ),
      ].join(",")
    );
    for (const row of rows) {
      lines.push(
        [
          String(row.year),
          ...MONTH_LABELS.map((m) =>
            typeof row[m] === "number" ? `${(row[m] as number).toFixed(2)}%` : "--"
          ),
        ].map(csvEscape).join(",")
      );
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${symbol}-seasonality.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded-md border border-zinc-700">
          {sampleOptions.map((opt) => (
            <button
              key={String(opt)}
              onClick={() => setSampleSize(opt)}
              className={cn(
                "px-3 py-1 text-xs transition",
                sampleSize === opt
                  ? "bg-cyan-600 text-white"
                  : "bg-zinc-900 text-zinc-300 hover:bg-zinc-800",
              )}
            >
              {opt === "all" ? "All" : opt}
            </button>
          ))}
        </div>
        <span className="text-[10px] text-zinc-500">
          {rows.length} {rows.length === 1 ? "year" : "years"} loaded
        </span>
        <div className="ml-auto flex gap-2">
          <button
            onClick={downloadCsv}
            className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
          >
            Download CSV
          </button>
          <button
            onClick={() => setShowCharts((v) => !v)}
            className={cn(
              "rounded-md border px-3 py-1 text-xs",
              showCharts
                ? "border-cyan-500 bg-cyan-600 text-white"
                : "border-zinc-700 bg-zinc-900 text-zinc-200 hover:bg-zinc-800",
            )}
          >
            {showCharts ? "Hide" : "Show"} Seasonality Charts
          </button>
        </div>
      </div>

      {/* Main table — Probability row, Average return row, then per-year rows */}
      <div className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-900/50">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b border-zinc-800 bg-zinc-900/80">
              <th className="px-3 py-2 text-left text-[10px] uppercase text-zinc-400">
                Year
              </th>
              {MONTH_LABELS.map((m) => (
                <th
                  key={m}
                  className="px-2 py-2 text-[10px] uppercase text-zinc-400"
                  style={{ minWidth: 60 }}
                >
                  {m}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-zinc-800 bg-zinc-900/40 font-semibold">
              <td className="px-3 py-2 text-left text-zinc-300">Probability %</td>
              {aggregates.map((m) => (
                <td
                  key={m.label}
                  className="px-2 py-2 text-center"
                  style={{ background: probabilityCellBg(m.win_rate) }}
                >
                  {m.win_rate !== null ? (
                    <span className={cn(
                      "inline-flex items-center gap-0.5",
                      m.win_rate >= 50 ? "text-emerald-300" : "text-red-300",
                    )}>
                      {m.win_rate >= 50 ? "▲" : "▼"} {m.win_rate.toFixed(0)}%
                    </span>
                  ) : "--"}
                </td>
              ))}
            </tr>
            <tr className="border-b-2 border-zinc-700 bg-zinc-900/60 font-semibold">
              <td className="px-3 py-2 text-left text-zinc-300">Average return %</td>
              {aggregates.map((m) => (
                <td
                  key={m.label}
                  className="px-2 py-2 text-center"
                  style={{ background: heatCellBg(m.avg_pct ?? undefined) }}
                >
                  {m.avg_pct !== null
                    ? `${m.avg_pct > 0 ? "+" : ""}${m.avg_pct.toFixed(2)}%`
                    : "--"}
                </td>
              ))}
            </tr>
            {rows.map((row) => (
              <tr key={row.year} className="border-b border-zinc-800/60 hover:bg-zinc-800/30">
                <td className="px-3 py-2 text-left text-zinc-400">{row.year}</td>
                {MONTH_LABELS.map((m) => {
                  const v = row[m] as number | undefined;
                  return (
                    <td
                      key={m}
                      className="px-2 py-2 text-center"
                      style={{ background: heatCellBg(v) }}
                    >
                      {v === undefined
                        ? <span className="text-zinc-600">--</span>
                        : <span className={v >= 0 ? "text-emerald-200" : "text-red-200"}>
                            {v > 0 ? "+" : ""}{v.toFixed(2)}%
                          </span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Optional charts section */}
      {showCharts && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
            Average monthly return ({sampleSize === "all" ? "all years" : `last ${sampleSize}`})
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={aggregates} margin={{ top: 20, right: 16, left: 8, bottom: 4 }}>
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
                {aggregates.map((m, i) => (
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
      )}
    </div>
  );
}

function probabilityCellBg(v: number | null): string {
  if (v === null) return "transparent";
  // 0-100 → green for >=50, red for <50
  if (v >= 50) {
    const strength = Math.min(1, (v - 50) / 50);
    return `rgba(52, 211, 153, ${0.12 + strength * 0.4})`;
  }
  const strength = Math.min(1, (50 - v) / 50);
  return `rgba(248, 113, 113, ${0.12 + strength * 0.4})`;
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
    dpo_20: number | null;
    dpo_50: number | null;
    stoch_k: number | null;
    stoch_d: number | null;
    williams_r: number | null;
    roc_10: number | null;
    roc_21: number | null;
    roc_63: number | null;
  };
  series: {
    date: string; close: number;
    rsi: number | null; macd: number | null;
    macd_signal: number | null; macd_hist: number | null;
    bb_upper: number | null; bb_lower: number | null;
    dpo_20: number | null;
    stoch_k: number | null; stoch_d: number | null;
    williams_r: number | null;
    roc_21: number | null;
  }[];
  verdict: string;
  mood: { score: number | null; label: string };
  wyckoff?: { phase: string; description: string };
};

const WYCKOFF_COLORS: Record<string, string> = {
  markup: "bg-emerald-500/20 text-emerald-200 border-emerald-500/40",
  accumulation: "bg-sky-500/20 text-sky-200 border-sky-500/40",
  distribution: "bg-amber-500/20 text-amber-200 border-amber-500/40",
  markdown: "bg-red-500/20 text-red-200 border-red-500/40",
  neutral: "bg-zinc-700/30 text-zinc-300 border-zinc-500/40",
};

const MOOD_COLORS: Record<string, string> = {
  extreme_greed: "bg-red-500/30 text-red-200 border-red-500/50",
  greed: "bg-orange-500/20 text-orange-200 border-orange-500/40",
  bullish: "bg-emerald-500/20 text-emerald-200 border-emerald-500/40",
  neutral: "bg-zinc-700/40 text-zinc-200 border-zinc-500/40",
  bearish: "bg-sky-500/20 text-sky-200 border-sky-500/40",
  fear: "bg-indigo-500/20 text-indigo-200 border-indigo-500/40",
  extreme_fear: "bg-purple-500/30 text-purple-200 border-purple-500/50",
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
  const err = (data as { error?: string } | undefined)?.error;
  if (err) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
        {err}. For forex / commodity / index instruments, historical data
        requires FMP Starter plan — panels will populate automatically once
        configured.
      </div>
    );
  }
  if (!d || !d.series) return null;

  return (
    <div className="space-y-4">
      {/* Market Mood Meter */}
      <MoodMeter score={d.mood?.score ?? null} label={d.mood?.label ?? "neutral"} />

      {/* Wyckoff phase */}
      {d.wyckoff && (
        <div
          className={cn(
            "rounded-lg border p-4",
            WYCKOFF_COLORS[d.wyckoff.phase] ?? WYCKOFF_COLORS.neutral,
          )}
        >
          <div className="mb-1 flex items-center justify-between">
            <div className="text-[10px] uppercase tracking-wider opacity-80">
              Wyckoff Phase
            </div>
            <div className="text-xs uppercase opacity-90">{d.wyckoff.phase}</div>
          </div>
          <p className="text-xs opacity-90">{d.wyckoff.description}</p>
          <p className="mt-1 text-[10px] opacity-70">
            Simplified: price trend + volume expansion + A/D line slope over
            the last 30 bars. Markup / Markdown = confirmed trend. Accumulation
            / Distribution = transition zones. Neutral = inconclusive.
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <StatTile label="RSI (14)" value={d.snapshot.rsi} fmt="fixed1" />
        <StatTile label="Stoch %K" value={d.snapshot.stoch_k} fmt="fixed1" />
        <StatTile label="Williams %R" value={d.snapshot.williams_r} fmt="fixed1" />
        <StatTile label="DPO (20)" value={d.snapshot.dpo_20} fmt="fixed2" />
        <StatTile label="Speed 21d" value={d.snapshot.roc_21} fmt="pct" />
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

      {/* Stochastic */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
          Stochastic Oscillator (14, 3)
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={d.series} margin={{ top: 5, right: 16, left: 8, bottom: 4 }}>
            <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
            <XAxis dataKey="date" stroke="#71717a" fontSize={10} tick={false} />
            <YAxis stroke="#71717a" fontSize={11} domain={[0, 100]} />
            <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }} />
            <ReferenceLine y={80} stroke="#f87171" strokeDasharray="3 3" />
            <ReferenceLine y={20} stroke="#34d399" strokeDasharray="3 3" />
            <Line type="monotone" dataKey="stoch_k" stroke="#60a5fa" dot={false} strokeWidth={1.5} />
            <Line type="monotone" dataKey="stoch_d" stroke="#f59e0b" dot={false} strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
        <div className="mt-1 flex gap-3 text-[10px] text-zinc-400">
          <LegendDot color="#60a5fa" label="%K" />
          <LegendDot color="#f59e0b" label="%D (signal)" />
        </div>
      </div>

      {/* DPO */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
          Detrended Price Oscillator (20)
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <ComposedChart data={d.series} margin={{ top: 5, right: 16, left: 8, bottom: 4 }}>
            <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
            <XAxis dataKey="date" stroke="#71717a" fontSize={10} tick={false} />
            <YAxis stroke="#71717a" fontSize={11} />
            <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }} />
            <ReferenceLine y={0} stroke="#52525b" />
            <Bar dataKey="dpo_20" fill="#a78bfa55" />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="mt-1 text-[10px] text-zinc-500">
          Positive bars = price above its trend; negative = below. Use for cycle timing.
        </p>
      </div>

      {/* Speed (ROC) */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="mb-2 text-xs font-semibold uppercase text-zinc-400">
          Speed (Rate of Change, 21d)
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={d.series} margin={{ top: 5, right: 16, left: 8, bottom: 4 }}>
            <CartesianGrid stroke="#27272a" strokeDasharray="2 4" />
            <XAxis dataKey="date" stroke="#71717a" fontSize={10} tick={false} />
            <YAxis stroke="#71717a" fontSize={11} tickFormatter={(v) => `${v}%`} />
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }}
              formatter={(v) => `${Number(v).toFixed(2)}%`}
            />
            <ReferenceLine y={0} stroke="#52525b" />
            <Line type="monotone" dataKey="roc_21" stroke="#34d399" dot={false} strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
        <div className="mt-1 grid grid-cols-3 gap-2 text-center text-xs">
          <SpeedTile label="10d" value={d.snapshot.roc_10} />
          <SpeedTile label="21d" value={d.snapshot.roc_21} />
          <SpeedTile label="63d" value={d.snapshot.roc_63} />
        </div>
      </div>
    </div>
  );
}

function MoodMeter({ score, label }: { score: number | null; label: string }) {
  const cls = MOOD_COLORS[label] ?? MOOD_COLORS.neutral;
  const pct = score !== null ? Math.max(0, Math.min(100, score)) : 50;
  return (
    <div className={cn("rounded-lg border p-4", cls)}>
      <div className="mb-1 flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-wider opacity-80">Market Mood Meter</div>
        <div className="text-xs uppercase opacity-90">
          {label.replace(/_/g, " ")}
        </div>
      </div>
      <div className="flex items-baseline gap-3">
        <div className="font-mono text-3xl font-bold">
          {score !== null ? score.toFixed(1) : "--"}
        </div>
        <div className="text-xs opacity-80">/ 100</div>
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-zinc-900/60">
        <div
          className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-emerald-400 to-red-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-2 text-[10px] opacity-80">
        Composite of RSI, Stochastic, Williams %R, Bollinger position, 10d
        momentum, MACD histogram (normalized). 80+ = extreme greed, below 20 =
        extreme fear.
      </p>
    </div>
  );
}

function StatTile({
  label,
  value,
  fmt,
}: {
  label: string;
  value: number | null;
  fmt: "fixed1" | "fixed2" | "pct";
}) {
  let display = "-";
  let color = "";
  if (value !== null && value !== undefined) {
    if (fmt === "fixed1") display = value.toFixed(1);
    else if (fmt === "fixed2") display = value.toFixed(2);
    else if (fmt === "pct") {
      display = `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
      color = value >= 0 ? "text-emerald-400" : "text-red-400";
    }
  }
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
      <div className="text-[10px] uppercase text-zinc-500">{label}</div>
      <div className={cn("mt-1 font-mono text-lg", color)}>{display}</div>
    </div>
  );
}

function SpeedTile({ label, value }: { label: string; value: number | null }) {
  if (value === null || value === undefined) return null;
  const positive = value >= 0;
  return (
    <div className={cn(
      "rounded border p-1",
      positive ? "border-emerald-500/30 bg-emerald-500/10" : "border-red-500/30 bg-red-500/10"
    )}>
      <div className="text-[10px] uppercase opacity-70">{label}</div>
      <div className={cn("font-mono text-sm", positive ? "text-emerald-300" : "text-red-300")}>
        {positive ? "+" : ""}{value.toFixed(1)}%
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

/* --------------- Transcripts tab --------------- */

type TranscriptQuarter = { quarter: number; year: number; date: string };
type TranscriptSummary = {
  markdown?: string;
  quarter?: number;
  year?: number;
  call_date?: string;
  transcript_truncated?: boolean;
  error?: string;
  configure_hint?: string;
  usage?: { input_tokens: number; output_tokens: number };
};

function TranscriptsTab({ symbol }: { symbol: string }) {
  const { data: listData, isLoading } = useTranscriptList(symbol);
  const quarters =
    ((listData as { quarters: TranscriptQuarter[] } | undefined)?.quarters) ?? [];
  const [selected, setSelected] = useState<TranscriptQuarter | null>(null);
  const [summary, setSummary] = useState<TranscriptSummary | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadSummary(q: TranscriptQuarter) {
    setSelected(q);
    setSummary(null);
    setLoading(true);
    try {
      const r = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/instrument/${symbol}/transcript/${q.year}/${q.quarter}`,
      );
      const json = (await r.json()) as TranscriptSummary;
      setSummary(json);
    } catch (e) {
      setSummary({ error: (e as Error).message });
    } finally {
      setLoading(false);
    }
  }

  if (isLoading) return <Skeleton className="h-64 w-full bg-zinc-800" />;
  if (quarters.length === 0) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
        No earnings-call transcripts available. Requires FMP Starter plan for
        the transcript endpoint — data will populate automatically once
        configured.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {quarters.map((q) => {
          const active = selected && selected.year === q.year && selected.quarter === q.quarter;
          return (
            <button
              key={`${q.year}-${q.quarter}`}
              onClick={() => loadSummary(q)}
              className={cn(
                "rounded-md border px-3 py-1 text-xs transition",
                active
                  ? "border-indigo-500 bg-indigo-600 text-white"
                  : "border-zinc-700 bg-zinc-900 text-zinc-200 hover:border-indigo-500/60",
              )}
            >
              Q{q.quarter} {q.year}
              {q.date && <span className="ml-1 text-[10px] opacity-70">{q.date.slice(5)}</span>}
            </button>
          );
        })}
      </div>

      {loading && <Skeleton className="h-64 w-full bg-zinc-800" />}

      {!loading && summary && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-4">
          {summary.error ? (
            <div className="text-sm text-amber-300">
              {summary.error}
              {summary.configure_hint && (
                <div className="mt-1 text-xs text-amber-200/80">{summary.configure_hint}</div>
              )}
            </div>
          ) : (
            <>
              <div className="mb-2 flex items-center justify-between text-[10px] text-zinc-500">
                <span>
                  {symbol} Q{summary.quarter} {summary.year} call{" "}
                  {summary.call_date && `(${summary.call_date})`}
                  {summary.transcript_truncated && " · transcript truncated"}
                </span>
                {summary.usage && (
                  <span>
                    {summary.usage.input_tokens} in / {summary.usage.output_tokens} out
                  </span>
                )}
              </div>
              <MarkdownLite text={summary.markdown ?? ""} />
            </>
          )}
        </div>
      )}

      {!loading && !summary && (
        <div className="rounded-lg border border-zinc-800 p-8 text-center text-sm text-zinc-500">
          Pick a quarter above to generate an AI summary (cached 7 days per
          quarter).
        </div>
      )}
    </div>
  );
}

/* --------------- News tab (Webull-style) --------------- */

type NewsArticle = {
  source: string; title: string; description: string; link: string;
  pub_date: string; sentiment_score: number; sentiment: string;
  symbols?: string[];
};

type NewsSubTab = "symbol" | "market" | "watchlist";

function NewsTab({ symbol }: { symbol: string }) {
  const [sub, setSub] = useState<NewsSubTab>("symbol");
  const { symbols: watchlist } = useWatchlist();
  const { data: symbolData, isLoading: symbolLoading } = useInstrumentNews(symbol, sub === "symbol");
  const { data: marketData, isLoading: marketLoading } = useMarketNews(sub !== "symbol");

  const symbolArticles = ((symbolData as { articles: NewsArticle[] } | undefined)?.articles) ?? [];
  const allArticles = ((marketData as { articles: NewsArticle[] } | undefined)?.articles) ?? [];
  const watchlistArticles = allArticles.filter(
    (a) => a.symbols?.some((s) => watchlist.includes(s)),
  );

  const isLoading =
    (sub === "symbol" && symbolLoading) ||
    (sub !== "symbol" && marketLoading);
  const articles =
    sub === "symbol" ? symbolArticles
    : sub === "market" ? allArticles
    : watchlistArticles;

  return (
    <div className="space-y-3">
      {/* Sub-tabs */}
      <div className="flex items-center gap-4 border-b border-zinc-800">
        {[
          { key: "symbol", label: `${symbol} News`, count: symbolArticles.length },
          { key: "market", label: "Market News", count: allArticles.length },
          { key: "watchlist", label: "Watchlist News", count: watchlistArticles.length },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setSub(t.key as NewsSubTab)}
            className={cn(
              "relative px-1 py-2 text-xs transition",
              sub === t.key
                ? "text-cyan-400"
                : "text-zinc-400 hover:text-zinc-200",
            )}
          >
            {t.label}
            {t.count > 0 && (
              <span className="ml-1 text-[10px] text-zinc-500">({t.count})</span>
            )}
            {sub === t.key && (
              <span className="absolute inset-x-0 bottom-0 h-0.5 bg-cyan-500" />
            )}
          </button>
        ))}
      </div>

      {isLoading && <Skeleton className="h-64 w-full bg-zinc-800" />}

      {!isLoading && articles.length === 0 && (
        <div className="rounded-lg border border-zinc-800 p-8 text-center text-sm text-zinc-500">
          {sub === "symbol"
            ? `No news mentioning ${symbol} in the recent feed.`
            : sub === "watchlist"
            ? watchlist.length === 0
              ? "Your watchlist is empty. Add symbols to see filtered news."
              : "No recent news for your watchlist symbols."
            : "No articles available."}
        </div>
      )}

      {!isLoading && articles.length > 0 && (
        <ul className="divide-y divide-zinc-800 rounded-lg border border-zinc-800 bg-zinc-900/30">
          {articles.map((a, i) => (
            <li key={i} className="flex items-start gap-3 px-3 py-3 hover:bg-zinc-800/30">
              <SentimentBadge sentiment={a.sentiment} />
              <div className="flex-1 min-w-0">
                <a
                  href={a.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-sm text-zinc-100 hover:text-cyan-300"
                >
                  {a.title}
                </a>
                {a.description && (
                  <p className="mt-0.5 text-xs text-zinc-500 line-clamp-1">
                    {a.description}
                  </p>
                )}
                {sub !== "symbol" && a.symbols && a.symbols.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {a.symbols.slice(0, 5).map((s) => (
                      <Link
                        key={s}
                        href={`/instrument/${s}`}
                        className="rounded bg-zinc-800 px-1 py-0 text-[10px] font-mono text-cyan-400 hover:bg-zinc-700"
                      >
                        {s}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex-shrink-0 whitespace-nowrap text-[10px] text-zinc-500">
                {a.source} · {timeAgo(a.pub_date)}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SentimentBadge({ sentiment }: { sentiment: string }) {
  const cfg: Record<string, { label: string; cls: string }> = {
    positive: { label: "Positive", cls: "bg-sky-500/20 text-sky-300" },
    negative: { label: "Negative", cls: "bg-red-500/20 text-red-300" },
    neutral: { label: "Neutral", cls: "bg-zinc-700/50 text-zinc-300" },
  };
  const c = cfg[sentiment] ?? cfg.neutral;
  return (
    <span
      className={cn(
        "flex-shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium",
        c.cls,
      )}
    >
      {c.label}
    </span>
  );
}

function timeAgo(iso: string | undefined): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (!t) return "";
  const diff = Date.now() - t;
  const h = Math.floor(diff / (1000 * 60 * 60));
  if (h < 1) return "just now";
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}
