"use client";

import Link from "next/link";
import { Activity, Zap, Target, Layers, TrendingUp, Shield, BarChart2, Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";

const FEATURES = [
  { icon: Zap, title: "Advanced Signals", desc: "VIX, gaps, unusual volume, short squeeze, MACD divergence, golden cross" },
  { icon: Target, title: "Smart Money", desc: "Dark pool + options flow + earnings convergence dashboard" },
  { icon: Layers, title: "Multi-Timeframe", desc: "Weekly, daily, hourly analysis with alignment detection" },
  { icon: TrendingUp, title: "Sector Rotation", desc: "Track money flow between sectors in real time" },
  { icon: Shield, title: "Risk Analytics", desc: "Portfolio heat map, Sharpe ratio, beta, drawdown, concentration alerts" },
  { icon: BarChart2, title: "Market Breadth", desc: "Advance/decline, % above SMAs, 52-week highs/lows, yield curve" },
  { icon: Trophy, title: "Signal Leaderboard", desc: "Live accuracy tracking with verified win rates by setup type" },
  { icon: Activity, title: "Paper Trading", desc: "Execute trades via Alpaca directly from signals" },
];

export default function LandingPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-12 py-12">
      {/* Hero */}
      <div className="text-center space-y-4">
        <div className="flex items-center justify-center gap-3">
          <Activity className="h-10 w-10 text-cyan-400" />
          <h1 className="text-4xl font-bold text-zinc-100">Momentum Signal Engine</h1>
        </div>
        <p className="text-lg text-zinc-400 max-w-2xl mx-auto">
          Professional stock trading analysis platform. Scan 150+ stocks for momentum setups,
          track smart money flows, and get SMS alerts when signals fire.
        </p>
        <div className="flex items-center justify-center gap-3 pt-4">
          <Link href="/login"><Button size="lg">Get Started Free</Button></Link>
          <Link href="/scanner"><Button size="lg" variant="outline">View Scanner</Button></Link>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
          <p className="text-3xl font-bold text-cyan-400">150+</p>
          <p className="text-xs text-zinc-500">Stocks Scanned</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
          <p className="text-3xl font-bold text-emerald-400">80+</p>
          <p className="text-xs text-zinc-500">API Endpoints</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
          <p className="text-3xl font-bold text-amber-400">35+</p>
          <p className="text-xs text-zinc-500">Dashboard Pages</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center">
          <p className="text-3xl font-bold text-zinc-300">$0</p>
          <p className="text-xs text-zinc-500">Free to Use</p>
        </div>
      </div>

      {/* Features Grid */}
      <div className="space-y-4">
        <h2 className="text-xl font-bold text-center text-zinc-200">Features</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {FEATURES.map((f) => (
            <div key={f.title} className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <f.icon className="h-5 w-5 text-cyan-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-zinc-200">{f.title}</p>
                <p className="text-xs text-zinc-500">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* CTA */}
      <div className="rounded-lg border border-cyan-800/30 bg-cyan-900/10 p-8 text-center space-y-3">
        <p className="text-lg font-bold text-zinc-200">Ready to find your next trade?</p>
        <p className="text-sm text-zinc-400">Free SMS alerts. No credit card required.</p>
        <Link href="/login"><Button size="lg">Create Account</Button></Link>
      </div>

      <div className="text-center text-xs text-zinc-600">
        <Link href="/leaderboard" className="hover:text-zinc-400">View Signal Leaderboard</Link>
        {" | "}
        <Link href="/changelog" className="hover:text-zinc-400">Changelog</Link>
      </div>
    </div>
  );
}
