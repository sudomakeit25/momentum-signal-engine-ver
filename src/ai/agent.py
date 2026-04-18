"""AI Agent — 8 topic cards for the instrument page.

Each topic has its own prompt. The system prompt is shared and cached
so 8 button clicks on the same ticker benefit from prompt caching.

Requires ANTHROPIC_API_KEY. Returns a structured response with markdown
body + token usage so the UI can render the message and the caller can
audit cost.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("mse.ai_agent")

_SYSTEM_PROMPT = """You are an experienced equity research analyst helping
a retail trader understand a specific US public company. You will answer
focused questions about a single stock. Follow these rules:

1. Be concise. Use short bullet lists or numbered lists wherever possible.
   The reader is glancing at a dashboard card, not reading a long memo.
2. Stick to facts that were true as of your training cutoff, and clearly
   flag anything that may be stale ("as of early 2025").
3. Use plain English. No dense finance jargon without a one-line definition.
4. If a question is unanswerable (e.g. the company is too new or private
   subsidiary details are not public), say so in one sentence and stop.
5. Do NOT give buy / sell recommendations. Describe the business; let the
   reader decide.
6. Output must be Markdown. Use bold for key numbers and bullet lists for
   anything enumerated. No headings above level 3.
7. Keep responses under 250 words unless the topic is "Full Analysis",
   which may go up to 500 words."""

AGENT_TOPICS: dict[str, dict] = {
    "whats_happening": {
        "label": "What's happening?",
        "prompt_template": (
            "Summarize what is driving {symbol} ({name}) right now in 3-5 bullets."
            " Focus on the most recent quarter's earnings, any announcements,"
            " and recent price action context. Be specific with numbers where"
            " relevant."
        ),
    },
    "business_simple": {
        "label": "Business explained simple",
        "prompt_template": (
            "Explain what {symbol} ({name}) does in language a high school"
            " student would understand. Cover: (1) what they sell, (2) who"
            " pays for it, (3) how they make money, (4) what makes them"
            " different from competitors. Keep it to 4 short paragraphs"
            " or an easy bullet list."
        ),
    },
    "competitors": {
        "label": "Competitors",
        "prompt_template": (
            "List the 5-7 most important direct competitors to {symbol} ({name})."
            " For each, one line on how they compete. End with a one-sentence"
            " note on whether {symbol} is gaining or losing share in its main"
            " market."
        ),
    },
    "suppliers_clients": {
        "label": "Suppliers / Clients",
        "prompt_template": (
            "Describe the key supplier and customer relationships for"
            " {symbol} ({name}). Cover: (1) top 3 input / upstream dependencies,"
            " (2) top 3 customer segments or named large customers, (3) any"
            " known concentration risk (e.g., one customer over 20% of revenue)."
        ),
    },
    "future_expectations": {
        "label": "Future Expectations",
        "prompt_template": (
            "What are the forward-looking themes for {symbol} ({name})? Cover:"
            " (1) consensus revenue and EPS growth trajectory over the next"
            " 2 years, (2) 2-3 key catalysts (product launches, contracts,"
            " regulatory), (3) 2 risks the bull case depends on not happening."
            " Flag any of this that is uncertain."
        ),
    },
    "full_analysis": {
        "label": "Full Analysis",
        "prompt_template": (
            "Provide a structured one-page investment brief on {symbol} ({name})."
            " Include these short sections (use level 3 headings):"
            " Business, Moat, Financial Health, Valuation Context, Key Risks,"
            " Bull Case, Bear Case. Keep each section to 2-4 bullets."
        ),
    },
    "qualitative_scorecard": {
        "label": "Qualitative Scorecard",
        "prompt_template": (
            "Score {symbol} ({name}) from 1 (poor) to 5 (excellent) on each"
            " of these qualitative dimensions and give a one-sentence reason"
            " for each: Management, Moat, Growth Runway, Capital Allocation,"
            " Culture, Competitive Position. End with a single composite"
            " rating out of 5."
        ),
    },
    "investor_sentiment": {
        "label": "Investor Sentiment",
        "prompt_template": (
            "Describe current investor sentiment around {symbol} ({name})."
            " Cover: (1) how the stock is broadly perceived (darling / falling"
            " knife / show-me), (2) typical bull and bear narratives, (3)"
            " any notable institutional positioning or famous investor theses."
            " Note if sentiment diverges from fundamentals."
        ),
    },
}


def list_topics() -> list[dict]:
    return [{"key": k, "label": v["label"]} for k, v in AGENT_TOPICS.items()]


def run_agent(symbol: str, topic: str, company_name: str | None = None) -> dict:
    """Run one AI agent topic for a symbol.

    Returns {"markdown", "usage", "model"} on success, or {"error"} when
    the API key is missing or the call fails.
    """
    if topic not in AGENT_TOPICS:
        return {"error": f"unknown topic '{topic}'", "available": list(AGENT_TOPICS.keys())}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "error": "ANTHROPIC_API_KEY is not configured on the server.",
            "configure_hint": "Add ANTHROPIC_API_KEY to Render environment to enable AI analysis.",
        }

    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic SDK not installed"}

    prompt = AGENT_TOPICS[topic]["prompt_template"].format(
        symbol=symbol.upper(),
        name=(company_name or symbol.upper()),
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            cache_control={"type": "ephemeral"},  # caches the stable system prompt
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        logger.warning("AI agent call failed for %s/%s: %s", symbol, topic, e)
        return {"error": f"API call failed: {e}"}

    body_parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            body_parts.append(block.text)
    markdown = "\n\n".join(body_parts).strip()

    usage = response.usage
    return {
        "markdown": markdown,
        "model": response.model,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_read": getattr(usage, "cache_read_input_tokens", 0),
            "cache_creation": getattr(usage, "cache_creation_input_tokens", 0),
        },
    }
