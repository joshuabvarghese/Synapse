"""
Centralised configuration.

All values are read from environment variables with safe defaults.
Import this module; never call os.environ directly elsewhere.
"""
from __future__ import annotations

import os
from pathlib import Path


# ── Database ──────────────────────────────────────────────────────────────────

PG_HOST     = os.environ.get("POSTGRES_HOST",     "localhost")
PG_USER     = os.environ.get("POSTGRES_USER",     "ops")
PG_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "ops")
PG_DB       = os.environ.get("POSTGRES_DB",       "synapse")
PG_SSLMODE  = "disable"

PG_DSN: dict[str, str] = dict(
    host     = PG_HOST,
    user     = PG_USER,
    password = PG_PASSWORD,
    dbname   = PG_DB,
    sslmode  = PG_SSLMODE,
)

PG_POOL_MIN = 2
PG_POOL_MAX = 10

# ── Ollama ────────────────────────────────────────────────────────────────────

OLLAMA_HOST  = os.environ.get("OLLAMA_HOST",  "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
EMBED_MODEL  = os.environ.get("EMBED_MODEL",  "nomic-embed-text")

OLLAMA_EMBED_TIMEOUT   = 30                                                # seconds
OLLAMA_CHAT_TIMEOUT    = int(os.environ.get("OLLAMA_CHAT_TIMEOUT", "300"))  # seconds — CPU inference can be slow
OLLAMA_HEALTH_TIMEOUT  = 3                                                 # seconds
AGENT_MAX_STEPS        = int(os.environ.get("AGENT_MAX_STEPS", "10"))

# ── Knowledge base ────────────────────────────────────────────────────────────

KB_DIR          = Path(os.environ.get("KB_DIR", "/kb"))
KB_FALLBACK_DIR = Path("/app/kb")
RRF_K           = 60    # Reciprocal Rank Fusion constant
HYBRID_TOP_K    = 4     # default results returned by hybrid_search

# ── Auto-refresh ──────────────────────────────────────────────────────────────

AUTO_REFRESH_INTERVAL = 5   # seconds
LOG_TAIL_LIMIT        = 50
LOG_TIMELINE_LIMIT    = 100