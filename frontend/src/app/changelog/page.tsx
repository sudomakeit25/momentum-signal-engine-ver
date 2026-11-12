"use client";

import { FileText } from "lucide-react";

const CHANGELOG = [
  {
    version: "0.13.0",
    date: "2026-11-11",
    changes: [
      "Telegram alerts: signals (with entry, stop and target), intraday patterns and forming-setup watches go to a Telegram bot; a send that fails is retried for up to 30 minutes; set up on the Notifications page",
      "The server now stays awake on weekdays from 4:00 AM to 4:15 PM New York time, so intraday alerts, the scorecard and the paper auto-trader run for the whole session",
      "Catalyst Watch: position in the 52-week range, the move after each of the last four earnings reports, and EARLY MOVE now requires beating the market by 4 points",
      "Recent performance on every chart page: the last 5, 10 or 20 sessions day by day, the same window for peers and the market, and headlines from the biggest days",
      "Auto-trader History: every paper trade the bot made, how it ended (target, stop or end of day close), profit or loss in dollars and in multiples of the risk, with totals by day and by setup",
      "Telegram morning check at 9:25 AM New York time on trading days: server memory, data delay, auto-trader state and whether alerts are on, so a server that is down gets noticed before the open",
      "Telegram notice when the server restarts during the day, saying whether it was a deploy, an unexpected restart or a wake after being down",
      "Alert settings are locked: changing them or sending test messages needs the settings key (SETTINGS_KEY on the server); the saved phone number and webhook address are shown partly hidden and are no longer written to the server logs",
      "Fixed: a failed text alert could stall the intraday scan for over two minutes",
      "Fixed: the server ran out of memory and restarted about a dozen times during the session; heavy scans now run one at a time, the Spike Watch volume profile is built in small pieces and saved, and Spike Watch is skipped when memory is tight so alerts and the auto-trader keep running",
      "Fixed: exit and warning signals in Telegram showed a stop and target of $0.00; they are now labelled as having no trade levels",
      "Known limit: text alerts through the email gateway fail on the current hosting plan, which blocks outbound email; use Telegram",
    ],
  },
  {
    version: "0.12.0",
    date: "2026-11-10",
    changes: [
      "Catalyst Watch: companies about to report with heavy short interest, and companies that just reported and jumped on volume",
      "Spike Watch: pre-market gaps with the reason attached, volume spikes, failed breakouts, exhaustion days, stretched stocks, and peers that have not followed a group leader",
      "Scorecard: measures whether each type of alert worked, at 15 minutes, 1 hour, the close, and 1 and 5 days later",
      "News headline shown next to each intraday mover, so you can see why it is moving",
      "Earnings check now uses Nasdaq's calendar and covers the whole market",
      "Market data delay is now measured and shown: prices are about 15 minutes behind on the current data plan, stated on the intraday pages and in intraday text alerts",
      "Fixed: ten signal pages (short squeeze, unusual volume, gaps and others) were returning errors or the wrong data",
      "Fixed: the stock screener now says when its data source is down, where it used to report that no stocks matched",
      "Fixed: alerts had stopped in production because the Redis database was archived; restored",
      "Known limit: the Spike Watch detectors are new and unproven, so they send no alerts yet",
      "Known limit: the stock screener is often empty because Yahoo Finance rate-limits the server",
      "Known limit: company profiles, statements and the dynamic scan universe need a paid FMP plan",
    ],
  },
  {
    version: "0.11.0",
    date: "2026-11-10",
    changes: [
      "Paper auto-trader: turns confirmed intraday setups into Alpaca paper orders with a stop and target",
      "Limits: risk per trade, positions per day, daily loss halt, no trades on companies about to report, no new entries late in the day",
      "Closes its own positions before the bell, and never touches positions it did not open",
      "Status panel with a Pause button on the Intraday Movers page",
      "Off unless switched on in the server settings; refuses to run on anything but the paper account",
      "Known limit: its signals come from prices about 15 minutes old on the current data plan",
    ],
  },
  {
    version: "0.10.0",
    date: "2026-11-09",
    changes: [
      "Intraday Movers: stocks moving hard today on heavy volume, with spread, range and VWAP distance",
      "Setups with entry, stop and target: range breakout, VWAP reclaim and rejection, higher low",
      "Early warnings for setups still forming: an intact tight range, or price back at VWAP",
      "Text alerts for new setups, once per stock and setup per day",
      "Earnings flag on stocks reporting today or tomorrow",
    ],
  },
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
