"""
Ollama API client.

Provides stateless functions for embedding and chat inference.
All network I/O is contained here; callers never import ``requests`` directly.
"""
from __future__ import annotations

import logging

import requests

from core.config import (
    EMBED_MODEL,
    OLLAMA_CHAT_TIMEOUT,
    OLLAMA_EMBED_TIMEOUT,
    OLLAMA_HEALTH_TIMEOUT,
    OLLAMA_HOST,
    OLLAMA_MODEL,
)

logger = logging.getLogger(__name__)


# ── Embeddings ────────────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    """Return a 768-dim embedding vector for *text* using nomic-embed-text."""
    resp = requests.post(
        f"{OLLAMA_HOST}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=OLLAMA_EMBED_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    embs = data.get("embeddings") or data.get("embedding")
    # Ollama may return [[...]] or [...]
    return embs[0] if isinstance(embs[0], list) else embs


# ── Health ────────────────────────────────────────────────────────────────────

def is_healthy() -> bool:
    """Return True if the Ollama daemon is reachable."""
    try:
        return requests.get(f"{OLLAMA_HOST}/api/tags", timeout=OLLAMA_HEALTH_TIMEOUT).status_code == 200
    except Exception:
        return False


def models_ready() -> dict[str, bool]:
    """
    Return a dict with ``inference`` and ``embed`` booleans indicating
    which models are already pulled on the Ollama host.
    """
    try:
        tags  = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=OLLAMA_HEALTH_TIMEOUT).json().get("models", [])
        names = {m["name"].split(":")[0] for m in tags}
        return {
            "inference": any(n in names for n in ["qwen2.5-coder", "qwen2.5"]),
            "embed":     "nomic-embed-text" in names,
        }
    except Exception:
        return {"inference": False, "embed": False}


# ── Chat ──────────────────────────────────────────────────────────────────────

def chat(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    model: str = OLLAMA_MODEL,
) -> dict:
    """
    Send a chat request to Ollama and return the parsed message dict.

    Parameters
    ----------
    messages:
        Full conversation history in Ollama format.
    tools:
        Optional tool definitions for function-calling.
    model:
        Model identifier (defaults to ``OLLAMA_MODEL``).
    """
    payload: dict = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools

    resp = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json=payload,
        timeout=OLLAMA_CHAT_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["message"]
