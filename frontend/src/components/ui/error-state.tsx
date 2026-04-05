"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ErrorState({
  message,
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded-lg border border-red-800/30 bg-red-900/10 p-8 text-center">
      <AlertTriangle className="mx-auto h-8 w-8 text-red-400" />
      <p className="mt-3 text-sm text-zinc-300">
        {message || "Something went wrong loading this data."}
      </p>
      {onRetry && (
        <Button
          variant="outline"
          size="sm"
          onClick={onRetry}
          className="mt-3 gap-2 text-xs"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Try Again
        </Button>
      )}
    </div>
  );
}
