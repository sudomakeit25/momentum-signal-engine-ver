"use client";

import { FileText } from "lucide-react";

const CHANGELOG = [
  {
    version: "0.9.0",
    date: "2026-04-05",
    changes: [
      "Added 30 advanced features: VIX integration, gap scanner, unusual volume, short squeeze, Bollinger squeeze, MACD divergence, golden/death cross, ATR ranking",
      "Fibonacci retracement, volume profile, Ichimoku cloud, pivot points, gap fill probability",
      "Portfolio analytics: heat map, Sharpe ratio, beta, drawdown, concentration alerts, income tracker",
      "Cmd+K command palette for quick symbol/page search",
      "Price ticker bar with live prices",
      "CSV export and print report utilities",
      "Market breadth dashboard with advance/decline, % above SMAs",
      "Economic calendar, crypto fear & greed index",
      "Telegram and Discord notification channels",
      "Morning briefing and end-of-day report generators",
      "Alert cooldown system, custom alert rules, multi-channel routing",
      "RSS feed of signals, iCal feed of earnings",
    ],
  },
  {
    version: "0.8.0",
    date: "2026-04-05",
    changes: [
      "Paper trading via Alpaca (positions, orders, buy/sell from UI)",
      "Custom screener with user-defined filters",
      "Multi-timeframe analysis (weekly/daily/hourly)",
      "Community feed with posts, likes, comments",
      "Shareable signal links with view count",
      "Options strategy builder with P&L chart (9 strategies)",
    ],
  },
  {
    version: "0.7.0",
    date: "2026-04-05",
    changes: [
      "Signal Leaderboard with live accuracy tracking and weekly performance",
      "Multi-user auth (JWT + bcrypt, per-user Redis storage)",
      "Login rate limiting (5 attempts / 15 min lockout)",
      "Account page with profile, name editing, password change",
      "Auth credentials moved from URL params to JSON body",
    ],
  },
  {
    version: "0.6.0",
    date: "2026-04-05",
    changes: [
      "News Sentiment Scanner (Yahoo Finance, MarketWatch, CNBC RSS)",
      "Sector Flow Dashboard (dark pool + options + momentum by sector)",
      "Correlation Alerts (15 pairs, divergence detection)",
      "Market Regime Detector (SPY trend/volatility/breadth classification)",
    ],
  },
  {
    version: "0.5.0",
    date: "2026-04-04",
    changes: [
      "Trade Journal with Alpaca import, P&L tracking, R-multiples",
      "Signal Backtester (walk-forward test generated signals)",
      "Alert History (every SMS logged with delivery status)",
      "Watchlist Alerts (server-side, SMS for watched stocks)",
    ],
  },
  {
    version: "0.4.0",
    date: "2026-04-04",
    changes: [
      "Dark Pool Tracker (FINRA short volume, accumulation detection)",
      "Earnings Whisper Engine (FMP conviction scoring, insider trades)",
      "Options Flow Scanner (Polygon.io, unusual Vol/OI, P/C ratio)",
      "Smart Money convergence dashboard",
    ],
  },
  {
    version: "0.3.0",
    date: "2026-04-04",
    changes: [
      "Upstash Redis for persistent notification config",
      "Parallelized SPY + batch stock fetch (faster scanner)",
      "Loading message during initial scan",
    ],
  },
  {
    version: "0.1.0",
    date: "2026-02-08",
    changes: [
      "Initial release: momentum scanner, signal generator, chart analysis",
      "SMS alerts (Twilio + email-to-SMS gateway)",
      "30+ API endpoints, background refresh loop",
      "Next.js 14 frontend with dark mode",
    ],
  },
];

export default function ChangelogPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <FileText className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Changelog</h1>
      </div>

      {CHANGELOG.map((release) => (
        <div key={release.version} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <div className="flex items-center gap-3">
            <span className="rounded bg-cyan-400/10 px-2 py-0.5 text-sm font-bold text-cyan-400">
              v{release.version}
            </span>
            <span className="text-xs text-zinc-500">{release.date}</span>
          </div>
          <ul className="mt-3 space-y-1">
            {release.changes.map((change, i) => (
              <li key={i} className="text-sm text-zinc-400 before:content-['-_'] before:text-zinc-600">
                {change}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
