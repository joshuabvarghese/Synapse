# ⬡ Synapse

> **Agentic SRE incident co-pilot. Fully offline. No API keys.**

Synapse investigates production incidents autonomously. When an alert fires, it queries your logs, searches a runbook knowledge base using hybrid vector + full-text retrieval, runs diagnostic commands in a tool-use loop, and returns a structured resolution — root cause, exact commands, prevention, and MTTR — then stays available for multi-turn follow-up.

Everything runs in Docker on your machine. Zero data egress.

---

## Quickstart

```bash
git clone https://github.com/you/synapse && cd synapse
./start.sh
```

Opens at **http://localhost:8501**

First run pulls two models (~5 GB total, cached permanently in a Docker volume):
- `qwen2.5-coder:7b` — inference + tool-use
- `nomic-embed-text` — 768-dim embeddings

```bash
make up       # start everything
make status   # health check all services
make logs     # follow app logs
make shell    # psql into the database
make down     # stop (data preserved)
make reset    # wipe all volumes, start fresh
```

---

## How it works

```
Alert fires
    │
    ▼
Synapse Agent Loop  (qwen2.5-coder:7b + tool-use, up to 8 steps)
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

| Scenario | Severity | Service | What the agent finds |
|---|---|---|---|
| CPU runaway — nginx fork storm | P1 | nginx | `worker_processes=512` in ConfigMap; rolling restart + HPA |
| DB replica lag — checkout 500s | P1 | postgres | Aurora failover lag; promotes replica, rotates secret |
| Memory leak — auth-svc OOM | P2 | auth-svc | Unbounded `JWTCache`; sets eviction policy + restarts |
| Bad deploy — ConfigMap missing key | P2 | checkout | `DB_REPLICA_HOST` missing from v2.4.1; rollback to v2.4.0 |
| Redis cluster fail — cascade timeout | P2 | redis | Disk-full node; sentinel failover + circuit breaker reset |

---

## Stack

| Layer | Technology | Notes |
|---|---|---|
| LLM | Ollama `qwen2.5-coder:7b` | Strong tool-use at 4 GB RAM |
| Embeddings | `nomic-embed-text` (768-dim) | Runs in Ollama, no extra process |
| Vector search | PostgreSQL + pgvector HNSW | `m=16, ef_construction=64` |
| Full-text search | Postgres `tsvector` + GIN | Auto-maintained by trigger |
| Search fusion | Reciprocal Rank Fusion (RRF) | Outperforms either signal alone |
| Agent | Ollama tool-use loop | Up to 8 steps, full audit trail |
| Conversation | Multi-turn with full context | Incident + resolution in system prompt |
| KB watcher | `watchdog` file observer | Drop `.md` files → indexed in seconds |
| UI | Streamlit | Custom dark-mode terminal aesthetic |
| Infra | Docker Compose | Postgres 16, Ollama, Streamlit |

---

## Adding your own runbooks

Drop `.md` files into `kb/` — they are embedded and indexed automatically (no restart):

```markdown
## INC-2025-0099 · P1 · redis · cache, eviction

**Title:** Redis maxmemory hit — cache miss storm

**Resolution:**
Root cause: maxmemory-policy was set to noeviction. Under memory pressure,
all writes returned OOM errors, cascading to checkout timeouts.

Steps:
1. `redis-cli CONFIG SET maxmemory-policy allkeys-lru`
2. `redis-cli BGREWRITEAOF`
3. Verify hit rate recovers: `redis-cli INFO stats | grep keyspace`

MTTR: 4 minutes.
Prevention: Set maxmemory-policy in redis.conf before deployment.
```

---

## Changing the model

Set `OLLAMA_MODEL` in `.env` (copy from `.env.example`):

```bash
OLLAMA_MODEL=qwen2.5-coder:14b   # better reasoning, needs ~10 GB RAM
OLLAMA_MODEL=mistral-small        # alternative, strong structured output
OLLAMA_MODEL=llama3.1:8b          # general purpose, good tool-use
```

---

## Configuration

All settings via environment variables. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | Inference model |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model (must produce 768-dim vectors) |
| `POSTGRES_USER` | `ops` | Database user |
| `POSTGRES_PASSWORD` | `ops` | Database password |
| `APP_PORT` | `8501` | Streamlit port |

> **GPU (NVIDIA):** uncomment the `deploy` block in `docker-compose.yml`.

---

## Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for a full technical deep-dive: design decisions, the hybrid search implementation, why HNSW over IVFFlat, RRF math, and future directions.

---

## License

MIT
