"use client";

import { useState } from "react";
import { MessageCircle, X, Send } from "lucide-react";
import { apiPostJson } from "@/lib/api";

export function FeedbackWidget() {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [rating, setRating] = useState(0);
  const [sent, setSent] = useState(false);

  async function submit() {
    if (!message.trim()) return;
    await apiPostJson("/feedback", {
      type: "general",
      message: message.trim(),
      page: typeof window !== "undefined" ? window.location.pathname : "",
      rating,
    }).catch(() => {});
    setSent(true);
    setTimeout(() => { setSent(false); setOpen(false); setMessage(""); setRating(0); }, 2000);
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="fixed bottom-4 right-4 z-50 rounded-full bg-cyan-600 p-3 text-white shadow-lg hover:bg-cyan-500 transition-colors md:bottom-6 md:right-6">
        <MessageCircle className="h-5 w-5" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 w-72 rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl md:bottom-6 md:right-6">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
        <span className="text-sm font-medium text-zinc-300">Feedback</span>
        <button onClick={() => setOpen(false)} className="text-zinc-500 hover:text-zinc-300"><X className="h-4 w-4" /></button>
      </div>
      <div className="p-4 space-y-3">
        {sent ? (
          <p className="text-sm text-emerald-400 text-center py-4">Thanks for your feedback!</p>
        ) : (
          <>
            <div className="flex gap-1 justify-center">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} onClick={() => setRating(n)} className={`text-lg ${n <= rating ? "text-amber-400" : "text-zinc-700"}`}>*</button>
              ))}
            </div>
            <textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="What can we improve?" className="w-full rounded border border-zinc-700 bg-zinc-800 p-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-cyan-400 focus:outline-none" rows={3} />
            <button onClick={submit} disabled={!message.trim()} className="flex w-full items-center justify-center gap-1 rounded bg-cyan-600 px-3 py-1.5 text-sm text-white hover:bg-cyan-500 disabled:opacity-50">
              <Send className="h-3.5 w-3.5" /> Submit
            </button>
          </>
        )}
      </div>
    </div>
  );
}
