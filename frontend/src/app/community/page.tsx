"use client";

import { useState } from "react";
import { MessageSquare, Heart, Send } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useCommunityFeed } from "@/hooks/use-trading";
import { apiPost } from "@/lib/api";
import { useAuth, getAuthToken } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import Link from "next/link";

export default function CommunityPage() {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const { data: feed, isLoading } = useCommunityFeed(50);
  const [content, setContent] = useState("");
  const [symbol, setSymbol] = useState("");

  async function handlePost() {
    if (!content.trim()) return;
    const token = getAuthToken();
    if (!token) return;
    await fetch(new URL("/community/post", process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").toString(), {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ content: content.trim(), symbol: symbol.toUpperCase() }),
    });
    setContent("");
    setSymbol("");
    queryClient.invalidateQueries({ queryKey: ["community-feed"] });
  }

  async function handleLike(postId: string) {
    await apiPost(`/community/post/${postId}/like`);
    queryClient.invalidateQueries({ queryKey: ["community-feed"] });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <MessageSquare className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Community</h1>
      </div>

      {/* Post Form */}
      {isAuthenticated ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-2">
          <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder="Share a trade idea, analysis, or insight..." className="w-full rounded-md border border-zinc-700 bg-zinc-900 p-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-cyan-400 focus:outline-none" rows={3} maxLength={500} />
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="Symbol (optional)" className="h-7 w-28 bg-zinc-900 text-xs" />
              <span className="text-xs text-zinc-600">{content.length}/500</span>
            </div>
            <Button size="sm" onClick={handlePost} disabled={!content.trim()} className="gap-1"><Send className="h-3 w-3" />Post</Button>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-center text-sm text-zinc-500">
          <Link href="/login" className="text-cyan-400 hover:underline">Sign in</Link> to post in the community.
        </div>
      )}

      {/* Feed */}
      {isLoading ? <div className="space-y-3">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-24 bg-zinc-800" />)}</div>
      : feed && feed.length > 0 ? (
        <div className="space-y-3">
          {feed.map((post, i) => (
            <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-zinc-200">{String(post.user_name)}</span>
                    {String(post.symbol) && <Link href={`/chart/${String(post.symbol)}`} className="text-xs text-cyan-400 hover:underline">${String(post.symbol)}</Link>}
                    <span className="text-xs text-zinc-600">{new Date(String(post.created_at)).toLocaleDateString()}</span>
                  </div>
                  <p className="mt-2 text-sm text-zinc-300">{String(post.content)}</p>
                </div>
              </div>
              <div className="mt-3 flex items-center gap-4">
                <button onClick={() => handleLike(String(post.id))} className="flex items-center gap-1 text-xs text-zinc-500 hover:text-red-400 transition-colors">
                  <Heart className="h-3.5 w-3.5" />{String(post.likes || 0)}
                </button>
                <span className="text-xs text-zinc-600">{((post.comments as unknown[]) || []).length} comments</span>
              </div>
              {/* Comments */}
              {((post.comments as Record<string, unknown>[]) || []).length > 0 && (
                <div className="mt-2 space-y-1 border-t border-zinc-800 pt-2">
                  {(post.comments as Record<string, unknown>[]).map((c, j) => (
                    <div key={j} className="text-xs"><span className="text-zinc-400">{String(c.user_name)}: </span><span className="text-zinc-500">{String(c.content)}</span></div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : <div className="rounded-lg border border-zinc-800 p-12 text-center text-zinc-500">No posts yet. Be the first to share!</div>}
    </div>
  );
}
