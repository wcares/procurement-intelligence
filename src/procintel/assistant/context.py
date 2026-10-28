"""Context guard: stop a conversation before it outgrows the model's window (the local servers run 8,192 tokens)."""
from __future__ import annotations

import os

WINDOW = int(os.environ.get("PROCINTEL_CHAT_WINDOW_TOKENS", "8192"))   # the model's context, set with llama-server -c
OUTPUT_RESERVE = 700                                                      # room kept for the model's own answer
WARN_AT = 0.8                                                             # share of the budget at which the UI warns
CHARS_PER_TOKEN = 3.2                                                     # cautious: counts more tokens than there are


def estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1


def usage(fixed_prompt: str, history: list[dict]) -> dict:
    """Tokens the next call would send, the budget, and whether the conversation is full or close to it."""
    used = estimate_tokens(fixed_prompt) + sum(estimate_tokens(m["content"]) + 4 for m in history)
    budget = WINDOW - OUTPUT_RESERVE
    return {"used": used, "budget": budget, "warn": used >= WARN_AT * budget, "full": used >= budget}
