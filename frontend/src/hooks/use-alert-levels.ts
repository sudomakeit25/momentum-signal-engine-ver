"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { AlertLevel } from "@/components/notifications/price-alerts-card";

export function useAlertLevels() {
  return useQuery({
    queryKey: ["alert-levels"],
    queryFn: () => apiFetch<{ ok: boolean; levels: AlertLevel[] }>("/alerts/levels"),
    staleTime: 60 * 1000,
  });
}
