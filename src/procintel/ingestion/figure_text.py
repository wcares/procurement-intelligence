"""A short text description of a figure image, written by a vision model served over an OpenAI-compatible API.

Off unless PROCINTEL_VISION_MODEL is set, so a deployment without a vision model still keeps figures and captions.
Any server that takes image_url content works (llama-server with --mmproj, Ollama, vLLM, a hosted API):

    PROCINTEL_VISION_MODEL=qwen3-vl-8b
    PROCINTEL_VISION_API_BASE=http://127.0.0.1:8083/v1
    PROCINTEL_VISION_API_KEY=local            (optional)

Measured 2026-10-31 with Qwen3-VL-8B (Q-gguf + projector) on two report charts, 8 s each: the kind of figure, the
title and the axis labels came out right; a year range, a line colour and a "levels off" date did not. The prompt
therefore asks for kind, topic and overall shape only, and the text is stored as a machine description beside the
caption and the image, never in place of them.
"""
from __future__ import annotations

import base64
import os

import requests

PROMPT = ("This figure is from a World Bank project report. In two sentences say what kind of figure it is "
          "(chart, map, photo, diagram, table image), what it is about according to its title and labels, and its "
          "overall shape or content. Use only what is printed or visible. Do not state numbers, years or "
          "values, and do not name colours.")
TIMEOUT = 300


def configured() -> bool:
    return bool(os.environ.get("PROCINTEL_VISION_MODEL") and os.environ.get("PROCINTEL_VISION_API_BASE"))


def model_name() -> str:
    return os.environ.get("PROCINTEL_VISION_MODEL", "")


def describe(png: bytes, caption: str | None = None) -> str:
    """The model's description of the image ('' when no vision model is configured). Raises on a server error."""
    if not configured():
        return ""
    text = PROMPT + (f' Its printed caption: "{caption}".' if caption else "")
    body = {"model": model_name(), "max_tokens": 200, "temperature": 0,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}]}]}
    key = os.environ.get("PROCINTEL_VISION_API_KEY", "local")
    r = requests.post(os.environ["PROCINTEL_VISION_API_BASE"].rstrip("/") + "/chat/completions", json=body,
                      headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    r.raise_for_status()
    return (r.json()["choices"][0]["message"]["content"] or "").strip()
