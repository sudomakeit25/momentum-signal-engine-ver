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
  Grid3x3,
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
} from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/scanner", label: "Scanner", icon: ScanSearch },
  { href: "/watchlist", label: "Watchlist", icon: Eye },
  { href: "/chart/SPY", label: "Charts", icon: CandlestickChart },
  { href: "/portfolio", label: "Portfolio", icon: Wallet },
  { href: "/alerts", label: "Price Alerts", icon: Bell },
  { href: "/signals-history", label: "Signal History", icon: History },
  { href: "/performance", label: "Performance", icon: BarChart2 },
  { href: "/position-sizer", label: "Position Sizer", icon: Calculator },
  { href: "/backtest", label: "Backtest", icon: BarChart3 },
  { href: "/heatmap", label: "Heatmap", icon: LayoutGrid },
  { href: "/sectors", label: "Sectors", icon: TrendingUp },
  { href: "/correlation", label: "Correlation", icon: Grid3x3 },
  { href: "/risk-report", label: "Risk Report", icon: ShieldAlert },
  { href: "/smart-money", label: "Smart Money", icon: Target },
  { href: "/options-flow", label: "Options Flow", icon: Activity },
  { href: "/dark-pool", label: "Dark Pool", icon: Layers },
  { href: "/earnings", label: "Earnings", icon: Calendar },
  { href: "/journal", label: "Trade Journal", icon: BookMarked },
  { href: "/alert-history", label: "Alert History", icon: ClipboardList },
  { href: "/signal-backtest", label: "Signal Backtest", icon: FlaskConical },
  { href: "/leaderboard", label: "Leaderboard", icon: Trophy },
  { href: "/notifications", label: "Notifications", icon: Send },
  { href: "/guide", label: "Guide", icon: BookOpen },
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

        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          {NAV_ITEMS.map((item) => {
            const isActive =
              pathname === item.href || pathname.startsWith(item.href.split("/").slice(0, 2).join("/"));
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "border-l-2 border-cyan-400 bg-zinc-800/50 text-cyan-400"
                    : "text-zinc-400 hover:bg-zinc-800/30 hover:text-zinc-200"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
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
