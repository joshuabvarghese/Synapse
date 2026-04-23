# Synapse — Architecture & Design Notes

> A technical deep-dive into the decisions behind the system.
> Intended for code reviewers, interviewers, and curious engineers.

---

## Overview

Synapse is a **fully local, agentic SRE co-pilot**. When a production alert fires, it:

1. Queries live structured logs from Postgres
2. Searches a runbook knowledge base using hybrid vector + full-text retrieval
3. Executes diagnostic commands (kubectl, redis-cli, aws-cli) in a tool-use loop
4. Produces a structured incident resolution: root cause, exact commands, prevention, MTTR estimate
5. Stays available for multi-turn follow-up questions

Everything runs offline — no cloud API keys, no data egress. The LLM, embeddings, and database all run in Docker containers on the local machine.

---

## Architecture diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        Streamlit UI                         │
│   alert banner · live log stream · agent trace · follow-up  │
└──────────────────────┬──────────────────────────────────────┘
                       │
          ┌────────────▼─────────────┐
          │      Agentic Loop        │  up to 8 iterations
          │  (run_agent in main.py)  │
          └──┬──────────┬────────────┘
             │          │
    ┌────────▼──┐  ┌────▼──────────────────────┐
    │  Ollama   │  │       Tool Executor        │
    │  qwen2.5  │  │                            │
    │  coder:7b │  │  query_logs  →  Postgres   │
    │  tool-use │  │  search_kb   →  pgvector   │
    └──────┬────┘  │                + FTS + RRF │
           │       │  run_diagnostic → sim env  │
           └───────┴────────────────────────────┘
                              │
                   ┌──────────▼──────────┐
                   │     PostgreSQL 16    │
                   │                     │
                   │  system_logs        │  structured log events
                   │  incident_kb        │  runbooks + embeddings
                   │  resolution_log     │  audit trail / MTTR
                   └─────────────────────┘
```

---

## Component decisions

### Why Ollama instead of OpenAI/Anthropic?

**Fully offline operation** was a hard requirement. In a real SRE context, production incidents often involve sensitive infrastructure details — IP addresses, internal service names, auth tokens in logs — that you would not want to send to a third-party API. Ollama runs entirely on-premises and has zero egress.

`qwen2.5-coder:7b` was chosen as the default because:
- Strong tool-use reliability for a 7B model (critical for the agentic loop)
- Good at kubectl / AWS CLI / infra command generation
- 4 GB RAM footprint — fits on a developer laptop
- Swappable: the `OLLAMA_MODEL` env var accepts any Ollama-compatible model

### Why PostgreSQL for everything?

Rather than adding Redis, Elasticsearch, or a dedicated vector database, Synapse uses PostgreSQL 16 for all storage:

| Need | Solution | Extension/Feature |
|---|---|---|
| Structured logs | `system_logs` table | native SQL, GIN index on level+service |
| Vector similarity | `incident_kb.embedding` column | `pgvector` — HNSW index |
| Full-text search | `incident_kb.fts_vector` column | native `tsvector` + GIN |
| Audit trail | `resolution_log` table | native SQL |

This reduces operational complexity substantially — one database, one volume, one healthcheck.

### Why hybrid search (pgvector + FTS + RRF)?

Pure vector search excels at semantic similarity but misses precise keyword matches.
Pure full-text search misses semantically similar documents with different vocabulary.
Hybrid fusion consistently outperforms either signal alone on recall@K.

The fusion strategy used is **Reciprocal Rank Fusion (RRF)**:

```
score(d) = 1/(k + rank_vector(d)) + 1/(k + rank_fts(d))
```

where `k = 60` is the standard constant that prevents high-rank outliers from dominating. Documents not found by FTS get a rank penalty of 100 (effectively contributing `1/160`), which keeps the vector signal alive even when FTS produces no matches.

The FTS `tsvector` is maintained automatically by a `BEFORE INSERT OR UPDATE` trigger with weighted lexemes:
- Weight A — title (highest priority)
- Weight B — tags
- Weight C — resolution body

### Why HNSW over IVFFlat for the vector index?

`pgvector` offers two ANN index types:

| Index | Build time | Query time | Recall | Memory |
|---|---|---|---|---|
| IVFFlat | Fast | Fast | Lower (list-dependent) | Low |
| HNSW | Slower | Faster | Higher (graph-based) | Higher |

For a KB that is read far more than written (runbooks don't change often), HNSW's higher recall and faster query time are worth the build cost. The index is created with `m=16, ef_construction=64` — good defaults for up to ~50K vectors.

### Why `nomic-embed-text` for embeddings?

- **768 dimensions** — higher fidelity than all-MiniLM-L6-v2's 384 dims
- **8192 token context** — full runbooks fit in a single embedding call
- **Runs natively in Ollama** — no separate sentence-transformers process or Python dependency
- Open weights (Apache 2.0), strong MTEB benchmark scores

If the embedding model is changed, the `incident_kb` table must be cleared and re-indexed because the vector dimension would change.

### Why watchdog for KB ingestion?

The KB watcher (`watch_kb()`) uses the `watchdog` library to observe `kb/` for file changes. This means operators can add new runbooks at runtime — drop a `.md` file into `kb/`, and it is embedded and indexed within seconds, without a service restart.

The observer thread is started as a daemon thread so it does not prevent clean process exit. The observer itself is also set to `daemon = True`.

### Why Streamlit?

Streamlit allows a high-quality interactive UI to be built entirely in Python with no separate frontend build step. This is the right tradeoff for an offline, single-operator tool. The UI makes heavy use of `unsafe_allow_html=True` with custom CSS for a professional dark-mode terminal aesthetic — all dynamic content injected into HTML is passed through `html.escape()` first.

---

## Data flow: incident investigation

```
User clicks scenario button
    │
    ▼
inject_logs()
  └─ Writes 8 structured log events to system_logs
     (simulates what a real log shipper like Fluent Bit would do)

st.session_state.scenario = key
st.rerun()
    │
    ▼
run_agent() — iterative tool-use loop
  │
  ├─ Step 1: LLM sees alert text → calls query_logs(service, level="ERROR")
  │   └─ execute_tool → SQL query → returns last N log lines
  │
  ├─ Step 2: LLM calls search_kb(query="<error description>")
  │   └─ execute_tool → embed(query) → hybrid_search() → RRF ranked results
  │
  ├─ Step 3: LLM calls run_diagnostic("kubectl top pods -n prod")
  │   └─ execute_tool → simulate_diagnostic() → realistic terminal output
  │
  ├─ Step 4: LLM calls run_diagnostic("kubectl rollout restart ...")
  │   └─ apply fix → verify
  │
  └─ Step 5: No more tool_calls in response → final resolution text
      └─ Written to st.session_state.resolution_text
      └─ Written to resolution_log table (audit trail)

User reads resolution in UI
    │
    ▼
Multi-turn follow-up
  └─ Full context (alert + resolution + history) sent with each question
```

---

## Known limitations and future directions

**What this is not (yet):**
- The diagnostic runner is a simulator. A production version would use a `subprocess` executor with kubectl context injection, or a server-side agent with proper RBAC.
- Log injection is synthetic. Real deployment would replace `inject_logs()` with a Fluent Bit → Postgres pipeline or a Kafka consumer.
- No authentication. A production deployment would sit behind an identity proxy (Tailscale, OAuth, etc.)

**Natural next steps:**
- Replace `simulate_diagnostic` with real `subprocess` + kubectl calls (already structured for this — just swap the function body)
- Add a `kb/upload` endpoint so operators can paste runbooks from the UI
- Streaming agent trace — currently the trace updates per tool call; it could stream token-by-token from the final resolution
- MTTR dashboard — `resolution_log` already captures duration; a simple chart over time would be compelling
- Slack integration — post the resolution to the incident channel on completion

---

## File structure

```
Synapse/
├── docker-compose.yml          # Service orchestration (postgres, ollama, app)
├── .env.example                # All environment variable defaults documented
├── Makefile                    # Developer ergonomics: up, down, reset, logs, status, lint
├── start.sh                    # One-command startup with readiness polling
├── stop.sh                     # Graceful shutdown
├── ruff.toml                   # Linting config (Python 3.11, line-length 120)
│
├── app/
│   ├── main.py                 # All application logic (~950 lines)
│   ├── schema.sql              # Canonical DB schema (run by Docker on first boot)
│   ├── Dockerfile              # Python 3.11-slim, HEALTHCHECK, non-root user
│   ├── requirements.txt        # Pinned Python dependencies
│   └── .dockerignore
│
└── kb/
    └── incidents.md            # Seed knowledge base (5 real-world incident runbooks)
```
