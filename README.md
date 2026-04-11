# ⬡ Synapse

> Agentic SRE incident co-pilot. Fully offline. No API keys. MIT licensed.

**v2 upgrades over v1:**
- **Agentic tool-use loop** — model calls `query_logs`, `search_kb`, `run_diagnostic` iteratively before concluding
- **qwen2.5-coder:7b** — replaces llama3.2:3b; significantly better at kubectl/infra commands and structured reasoning
- **nomic-embed-text** — 768-dim embeddings via Ollama (replaces sentence-transformers all-MiniLM-L6-v2)
- **Hybrid search** — pgvector cosine + Postgres FTS fused with Reciprocal Rank Fusion (RRF)
- **Multi-turn conversation** — follow-up questions after the initial resolution
- **Auto-ingesting KB watcher** — `kb/` directory is watched; new `.md` files are embedded and indexed live

---

## Quickstart

```bash
./start.sh
```

Opens at **http://localhost:8501**

First run pulls two models (~5GB total, cached after that):
- `qwen2.5-coder:7b` — inference + tool-use
- `nomic-embed-text` — embeddings

```bash
make up      # start everything
make status  # check health
make logs    # follow app logs
make down    # stop
make reset   # wipe all data and start fresh
```

---

## How it works

```
Alert fires
    │
    ▼
Synapse Agent Loop (qwen2.5-coder:7b + tool-use)
    ├─→ query_logs(service, level)      → recent errors from Postgres
    ├─→ search_kb(query)                → hybrid pgvector + FTS → RRF fusion
    ├─→ run_diagnostic(kubectl/redis/aws) → simulate against live env
    └─→ run_diagnostic(verify fix)
    │
    ▼
Structured resolution: root cause · runbook · prevention · MTTR
    │
    ▼
Multi-turn follow-up conversation
```

---

## Demo scenarios

| Scenario | Severity | Service |
|---|---|---|
| CPU runaway — nginx fork storm | P1 | nginx |
| DB replica lag — checkout 500s | P1 | postgres |
| Memory leak — auth-svc OOM | P2 | auth-svc |
| Bad deploy — ConfigMap missing key | P2 | checkout |
| Redis cluster fail — cascade timeout | P2 | redis |

---

## Stack

| Component | Tech | v1 → v2 |
|---|---|---|
| LLM | Ollama `qwen2.5-coder:7b` | ↑ from llama3.2:3b |
| Embeddings | `nomic-embed-text` (768-dim, via Ollama) | ↑ from all-MiniLM-L6-v2 (384-dim) |
| Vector search | PostgreSQL 16 + pgvector HNSW | same |
| Full-text search | Postgres tsvector + GIN index | ✨ new |
| Search fusion | Reciprocal Rank Fusion (RRF) | ✨ new |
| Agent | Ollama tool-use loop (up to 8 steps) | ✨ new |
| Conversation | Multi-turn follow-up | ✨ new |
| KB watcher | watchdog file observer | ✨ new |
| Dashboard | Streamlit | same |

---

## Adding your own incidents

Drop `.md` files into `kb/` — they're embedded and indexed automatically (no restart needed):

```
## INC-2025-0099 · P1 · redis · cache, eviction

**Title:** Redis maxmemory hit — cache miss storm

**Resolution:**
Root cause: ...
Steps:
1. `redis-cli INFO memory`
2. `redis-cli FLUSHDB ASYNC`
```

---

## Changing the model

Edit `OLLAMA_MODEL` in `docker-compose.yml`:

```yaml
OLLAMA_MODEL: qwen2.5-coder:7b   # default — good tool-use, 4GB RAM
OLLAMA_MODEL: qwen2.5-coder:14b  # better reasoning, needs 10GB RAM
OLLAMA_MODEL: mistral-small      # alternative, strong at structured output
```

---

## License

MIT
