"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { PositionSize } from "@/types/api";

interface PositionSizeParams {
  account: number;
  risk: number;
  entry: number;
  stop: number;
  target?: number;
}

export function usePositionSize(params: PositionSizeParams, enabled = false) {
  return useQuery({
    queryKey: ["position-size", params],
    queryFn: () =>
      apiFetch<PositionSize>("/risk/position-size", {
        account: params.account,
        risk: params.risk,
        entry: params.entry,
        stop: params.stop,
        target: params.target,
      }),
    enabled,
  });
}
