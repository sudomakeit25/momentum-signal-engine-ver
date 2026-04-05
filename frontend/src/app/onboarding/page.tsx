"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, ArrowRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";

const STEPS = [
  {
    title: "Welcome to MSE",
    description: "Momentum Signal Engine scans 150+ stocks for high-probability trading setups using technical analysis, dark pool data, options flow, and more.",
    action: "Let's get started",
  },
  {
    title: "Core Features",
    description: "Start with the Scanner to see today's top momentum stocks. Each stock gets a score based on EMA alignment, relative strength, volume, and breakout patterns.",
    links: [
      { href: "/scanner", label: "Open Scanner" },
      { href: "/smart-money", label: "Smart Money Dashboard" },
    ],
  },
  {
    title: "Set Up Alerts",
    description: "Get SMS alerts when new signals fire. Go to Notifications, enter your phone number and carrier, enable auto-alerts, and you're set.",
    links: [
      { href: "/notifications", label: "Configure Notifications" },
    ],
  },
  {
    title: "Advanced Tools",
    description: "Explore dark pool data, options flow, earnings conviction scores, multi-timeframe analysis, and the signal leaderboard.",
    links: [
      { href: "/dark-pool", label: "Dark Pool" },
      { href: "/options-flow", label: "Options Flow" },
      { href: "/leaderboard", label: "Leaderboard" },
    ],
  },
  {
    title: "You're All Set!",
    description: "Tip: Press Cmd+K anytime to quickly search for symbols or pages. The scanner refreshes every 2 minutes automatically.",
    action: "Go to Scanner",
  },
];

export default function OnboardingPage() {
  const [step, setStep] = useState(0);
  const router = useRouter();
  const current = STEPS[step];

  function next() {
    if (step === STEPS.length - 1) {
      router.push("/scanner");
    } else {
      setStep(step + 1);
    }
  }

  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <div className="w-full max-w-md space-y-6">
        {/* Progress */}
        <div className="flex items-center gap-1">
          {STEPS.map((_, i) => (
            <div key={i} className={`h-1 flex-1 rounded-full ${i <= step ? "bg-cyan-400" : "bg-zinc-800"}`} />
          ))}
        </div>

        {/* Step Content */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-6 space-y-4">
          {step === 0 && <Activity className="h-10 w-10 text-cyan-400" />}
          {step === STEPS.length - 1 && <Check className="h-10 w-10 text-emerald-400" />}

          <h1 className="text-xl font-bold text-zinc-200">{current.title}</h1>
          <p className="text-sm text-zinc-400">{current.description}</p>

          {current.links && (
            <div className="flex flex-wrap gap-2">
              {current.links.map((l) => (
                <Link key={l.href} href={l.href} className="rounded-md bg-zinc-800 px-3 py-1.5 text-xs text-cyan-400 hover:bg-zinc-700">
                  {l.label}
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between">
          <button onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0} className="text-xs text-zinc-500 hover:text-zinc-300 disabled:invisible">
            Back
          </button>
          <div className="text-xs text-zinc-600">{step + 1} / {STEPS.length}</div>
          <Button size="sm" onClick={next} className="gap-1">
            {current.action || "Next"} <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
