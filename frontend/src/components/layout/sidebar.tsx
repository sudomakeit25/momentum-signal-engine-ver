"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import {
  ScanSearch,
  CandlestickChart,
  Calculator,
  BarChart3,
  BarChart2,
  Activity,
  BookOpen,
  Sun,
  Moon,
  Menu,
  X,
  LayoutGrid,
  Eye,
  TrendingUp,
  Wallet,
  Bell,
  History,
  ShieldAlert,
  Calendar,
  Send,
  Layers,
  Target,
  BookMarked,
  ClipboardList,
  FlaskConical,
  Trophy,
  LogIn,
  LogOut,
  User,
  Newspaper,
  GitCompareArrows,
  Gauge,
  DollarSign,
  SlidersHorizontal,
  MessageSquare,
  Wrench,
  Zap,
  Crosshair,
  PieChart,
  FileText,
  Globe,
  ArrowLeftRight,
  Rocket,
  Microscope,
  LineChart,
  Search,
  Briefcase,
  ListOrdered,
} from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";

interface NavSection {
  label: string;
  items: { href: string; label: string; icon: typeof ScanSearch }[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    label: "Trade",
    items: [
      { href: "/scanner", label: "Scanner", icon: ScanSearch },
      { href: "/instrument", label: "Instrument Search", icon: Rocket },
      { href: "/custom-screener", label: "Custom Screener", icon: SlidersHorizontal },
      { href: "/screener-presets", label: "Preset Screeners", icon: Rocket },
      { href: "/stock-screener", label: "Stock Screener", icon: Search },
      { href: "/signals-advanced", label: "Advanced Signals", icon: Zap },
      { href: "/chart/SPY", label: "Charts", icon: CandlestickChart },
      { href: "/watchlist", label: "Watchlist", icon: Eye },
      { href: "/holdings", label: "My Holdings", icon: Briefcase },
      { href: "/trading", label: "Paper Trading", icon: DollarSign },
      { href: "/portfolio", label: "Portfolio", icon: Wallet },
      { href: "/portfolio-analytics", label: "Analytics", icon: PieChart },
      { href: "/position-sizer", label: "Position Sizer", icon: Calculator },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { href: "/smart-money", label: "Smart Money", icon: Target },
      { href: "/market-regime", label: "Market Regime", icon: Gauge },
      { href: "/dark-pool", label: "Dark Pool", icon: Layers },
      { href: "/options-flow", label: "Options Flow", icon: Activity },
      { href: "/earnings", label: "Earnings", icon: Calendar },
      { href: "/news", label: "News Sentiment", icon: Newspaper },
    ],
  },
  {
    label: "Analysis",
    items: [
      { href: "/multi-tf", label: "Multi-Timeframe", icon: Layers },
      { href: "/analyzer", label: "Stock Analyzer", icon: Microscope },
      { href: "/trends", label: "Multi-Year Trends", icon: LineChart },
      { href: "/technical", label: "Technical Tools", icon: Crosshair },
      { href: "/sector-flow", label: "Sector Flow", icon: TrendingUp },
      { href: "/sector-map", label: "Sector Map", icon: Activity },
      { href: "/rankings", label: "Industry Rankings", icon: ListOrdered },
      { href: "/correlations", label: "Correlations", icon: GitCompareArrows },
      { href: "/options-builder", label: "Options Builder", icon: Wrench },
      { href: "/heatmap", label: "Heatmap", icon: LayoutGrid },
      { href: "/market-breadth", label: "Market Breadth", icon: BarChart2 },
      { href: "/global-markets", label: "Global Markets", icon: Globe },
      { href: "/compare", label: "Compare Stocks", icon: ArrowLeftRight },
      { href: "/risk-report", label: "Risk Report", icon: ShieldAlert },
    ],
  },
  {
    label: "History",
    items: [
      { href: "/journal", label: "Trade Journal", icon: BookMarked },
      { href: "/signals-history", label: "Signal History", icon: History },
      { href: "/alert-history", label: "Alert History", icon: ClipboardList },
      { href: "/performance", label: "Performance", icon: BarChart2 },
    ],
  },
  {
    label: "Social",
    items: [
      { href: "/community", label: "Community", icon: MessageSquare },
      { href: "/leaderboard", label: "Leaderboard", icon: Trophy },
    ],
  },
  {
    label: "Tools",
    items: [
      { href: "/backtest", label: "Backtest", icon: BarChart3 },
      { href: "/signal-backtest", label: "Signal Backtest", icon: FlaskConical },
      { href: "/alerts", label: "Price Alerts", icon: Bell },
      { href: "/notifications", label: "Notifications", icon: Send },
      { href: "/changelog", label: "Changelog", icon: FileText },
      { href: "/guide", label: "Guide", icon: BookOpen },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const { user, isAuthenticated, logout } = useAuth();

  useEffect(() => { setMounted(true); }, []);

  return (
    <>
      {/* Mobile top bar */}
      <div className="fixed left-0 right-0 top-0 z-50 flex h-14 items-center gap-2 border-b border-border bg-background px-4 md:hidden">
        <button onClick={() => setOpen(!open)} className="text-zinc-400">
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
        <Activity className="h-5 w-5 text-cyan-400" />
        <span className="text-sm font-bold tracking-tight">Momentum Engine</span>
      </div>

      {/* Overlay */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed left-0 top-0 z-50 flex h-screen w-60 flex-col border-r border-border bg-background transition-transform md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-14 items-center gap-2 border-b border-border px-4">
          <Activity className="h-5 w-5 text-cyan-400" />
          <span className="text-sm font-bold tracking-tight">
            Momentum Engine
          </span>
        </div>

        <nav className="flex-1 overflow-y-auto p-3">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label} className="mb-3">
              <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">
                {section.label}
              </p>
              <div className="space-y-0.5">
                {section.items.map((item) => {
                  const isActive =
                    pathname === item.href || pathname.startsWith(item.href.split("/").slice(0, 2).join("/"));
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setOpen(false)}
                      className={cn(
                        "flex items-center gap-3 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                        isActive
                          ? "border-l-2 border-cyan-400 bg-zinc-800/50 text-cyan-400"
                          : "text-zinc-400 hover:bg-zinc-800/30 hover:text-zinc-200"
                      )}
                    >
                      <item.icon className="h-3.5 w-3.5" />
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="space-y-3 border-t border-border p-4">
          {mounted && isAuthenticated && user ? (
            <div className="flex items-center justify-between rounded-md px-3 py-2">
              <Link
                href="/account"
                onClick={() => setOpen(false)}
                className="flex items-center gap-2 hover:opacity-80 transition-opacity"
              >
                <User className="h-4 w-4 text-cyan-400" />
                <span className="text-xs font-medium text-zinc-300 truncate max-w-[120px]">
                  {user.name || user.email}
                </span>
              </Link>
              <button
                onClick={logout}
                className="text-zinc-500 hover:text-zinc-300 transition-colors"
                title="Sign out"
              >
                <LogOut className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : mounted ? (
            <Link
              href="/login"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-zinc-400 transition-colors hover:bg-zinc-800/30 hover:text-zinc-200"
            >
              <LogIn className="h-4 w-4" />
              Sign In
            </Link>
          ) : null}
          <button
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-zinc-400 transition-colors hover:bg-zinc-800/30 hover:text-zinc-200"
          >
            {!mounted ? (
              <Moon className="h-4 w-4" />
            ) : resolvedTheme === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
            {!mounted ? "Dark Mode" : resolvedTheme === "dark" ? "Light Mode" : "Dark Mode"}
          </button>
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            MSE v0.1.0
          </div>
        </div>
      </aside>
    </>
  );
}
