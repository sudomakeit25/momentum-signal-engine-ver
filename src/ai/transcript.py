"""Earnings-call transcript summarizer.

Fetches a transcript from FMP and asks Claude to produce a compact
analyst-style summary: key metrics mentioned, tone shifts, guidance,
and red flags. Falls back cleanly when Anthropic or FMP keys are
missing.
"""

from __future__ import annotations

import logging
import os

from src.data import fmp_client

logger = logging.getLogger("mse.transcript")

_SYSTEM_PROMPT = """You are an experienced equity analyst summarizing an
earnings call transcript for a retail trader reading a dashboard card.
Your task:

1. Produce a brief structured summary in Markdown.
2. Use these level-3 headings exactly: Business Highlights, Financial
   Metrics Called Out, Guidance & Outlook, Risk Factors / Red Flags,
   Analyst Tone.
3. Under each heading use 2-5 short bullets. Bold key numbers.
4. Keep the total under 400 words.
5. Do NOT editorialize. If the company didn't mention something, say so.
6. Do NOT give buy/sell recommendations."""


def summarize_transcript(symbol: str, quarter: int, year: int) -> dict:
    symbol = symbol.upper()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "error": "ANTHROPIC_API_KEY not configured on the server.",
            "configure_hint": "Add ANTHROPIC_API_KEY to enable transcript summaries.",
        }

    raw = fmp_client.get_earnings_transcript(symbol, quarter, year)
    content = raw.get("content") or ""
    if not content:
        return {
            "error": (
                f"No transcript available for {symbol} Q{quarter} {year}. "
                "Transcripts require FMP Starter plan or higher."
            ),
        }

    # Truncate long transcripts to keep token usage reasonable
    max_chars = 35_000
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars] + "\n\n[... transcript truncated ...]"

    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic SDK not installed"}

    user_prompt = (
        f"Summarize {symbol}'s Q{quarter} {year} earnings call transcript.\n\n"
        f"Transcript:\n{content}"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            cache_control={"type": "ephemeral"},
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        logger.warning("transcript summary failed for %s Q%s %s: %s", symbol, quarter, year, e)
        return {"error": f"API call failed: {e}"}

    body_parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            body_parts.append(block.text)

    usage = response.usage
    return {
        "symbol": symbol,
        "quarter": quarter,
        "year": year,
        "call_date": raw.get("date", "")[:10],
        "markdown": "\n\n".join(body_parts).strip(),
        "transcript_truncated": truncated,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_read": getattr(usage, "cache_read_input_tokens", 0),
        },
    }
