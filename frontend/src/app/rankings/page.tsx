"use client";

import Link from "next/link";
import { ListOrdered } from "lucide-react";
import { useIndustryList } from "@/hooks/use-trading";
import { Skeleton } from "@/components/ui/skeleton";

export default function RankingsIndexPage() {
  const { data, isLoading } = useIndustryList();
  const industries = data ?? [];
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <ListOrdered className="h-5 w-5 text-cyan-400" />
        <div>
          <h1 className="text-lg font-bold">Industry Rankings</h1>
          <p className="text-xs text-zinc-500">
            Altman Z, Piotroski F, Beneish M and Value Generation label for
            every company in an industry.
          </p>
        </div>
      </div>
      {isLoading ? (
        <Skeleton className="h-48 w-full bg-zinc-800" />
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {industries.map((ind) => (
            <Link
              key={ind.slug}
              href={`/rankings/industry/${ind.slug}`}
              className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 text-sm text-zinc-200 transition hover:border-cyan-500/60 hover:text-cyan-300"
            >
              {ind.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
