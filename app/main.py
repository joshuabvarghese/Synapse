"""
Synapse v2 — SRE Incident Co-Pilot
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agentic RAG: Ollama tool-use loop · Postgres hybrid search (pgvector + FTS + RRF)
Streaming UI · Multi-turn conversation · Live KB ingestion via watchdog
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import random
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import requests
import streamlit as st
from psycopg2.extras import RealDictCursor

# ── Logging (Docker-friendly: timestamps + level on stdout) ───────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("synapse")


# ── Config (all overridable via environment) ──────────────────────────────────
PG = dict(
    host     = os.environ.get("POSTGRES_HOST",     "localhost"),
    user     = os.environ.get("POSTGRES_USER",     "ops"),
    password = os.environ.get("POSTGRES_PASSWORD", "ops"),
    dbname   = os.environ.get("POSTGRES_DB",       "synapse"),
    sslmode  = "disable",
)
OLLAMA_HOST  = os.environ.get("OLLAMA_HOST",  "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
EMBED_MODEL  = os.environ.get("EMBED_MODEL",  "nomic-embed-text")
KB_DIR       = Path(os.environ.get("KB_DIR",  "/kb"))

AGENT_MAX_STEPS = 8   # safety ceiling on agentic loop iterations


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Synapse",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,400;0,500;1,400&family=Syne:wght@300;400;500&display=swap');

html,body,[class*="css"]            { font-family:'Syne',sans-serif!important; background:#0c0f14!important }
code,pre,.mono                      { font-family:'JetBrains Mono',monospace!important }

section[data-testid="stSidebar"]    { background:#080b0f!important; border-right:1px solid #161c26 }
section[data-testid="stSidebar"] *  { color:#5a6478!important }
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { color:#8892a4!important; font-weight:400!important }

.stApp                              { background:#0c0f14 }
.stApp h1,.stApp h2,.stApp h3      { color:#c9d1e0!important; font-weight:300!important; letter-spacing:-0.3px }
.stApp p,.stApp li                  { color:#7a8499 }

[data-testid="metric-container"]    { background:#0f1318!important; border:1px solid #161c26!important; border-radius:6px!important; padding:14px 16px!important }
[data-testid="stMetricValue"]       { font-family:'JetBrains Mono'!important; font-size:22px!important; color:#c9d1e0!important }
[data-testid="stMetricLabel"]       { font-size:11px!important; color:#3d4557!important; text-transform:uppercase; letter-spacing:1.2px }

.stButton button                    { background:#0f1318!important; border:1px solid #161c26!important; color:#7a8499!important; font-family:'JetBrains Mono'!important; font-size:12px!important; border-radius:4px!important; transition:border-color .15s,color .15s!important }
.stButton button:hover              { border-color:#3d7aed!important; color:#3d7aed!important }
.stButton button:active             { transform:scale(.98)!important }

.stTextInput input                  { background:#0f1318!important; border:1px solid #161c26!important; color:#c9d1e0!important; font-family:'JetBrains Mono'!important; font-size:12px!important; border-radius:4px!important }
.stTextInput input:focus            { border-color:#3d7aed!important }

.log-wrap    { background:#080b0f; border:1px solid #161c26; border-radius:8px; padding:14px 16px; max-height:440px; overflow-y:auto; font-family:'JetBrains Mono',monospace; font-size:11.5px; line-height:1.9 }
.ll          { display:flex; gap:10px; border-bottom:1px solid #0f1318; padding:1px 0 }
.ts          { color:#2a3040; white-space:nowrap; min-width:70px }
.svc         { color:#2d5fb0; min-width:90px }
.E           { color:#c94040 } .W { color:#b07a2d } .I { color:#2a3040 }
.msg-E       { color:#c94040 } .msg-W { color:#b07a2d } .msg-I { color:#3d4557 }

.tool-call   { background:#080b0f; border:1px solid #161c26; border-left:2px solid #2d5fb0; border-radius:0 6px 6px 0; padding:8px 13px; margin:6px 0; font-family:'JetBrains Mono'; font-size:11px }
.tool-name   { color:#2d5fb0 }
.tool-args   { color:#3d4557 }
.tool-result { color:#2a7a40; white-space:pre-wrap; margin-top:4px }

.res-wrap    { background:#080b0f; border:1px solid #161c26; border-radius:8px; padding:16px }
.res-text    { font-size:13px; color:#8892a4; line-height:1.8; white-space:pre-wrap; font-family:'Syne',sans-serif }

.alert-bar   { background:#140a0a; border:1px solid #5a1a1a; border-radius:6px; padding:10px 16px; margin-bottom:14px; font-size:13px; color:#c94040; font-family:'JetBrains Mono' }
.status-ok   { background:#0c1a10; color:#2a7a40; font-size:11px; padding:2px 8px; border-radius:3px; font-family:'JetBrains Mono' }
.status-err  { background:#1a0c0c; color:#c94040; font-size:11px; padding:2px 8px; border-radius:3px; font-family:'JetBrains Mono' }
.status-warn { background:#1a150c; color:#b07a2d; font-size:11px; padding:2px 8px; border-radius:3px; font-family:'JetBrains Mono' }
.status-info { background:#0c1520; color:#2a5090; font-size:11px; padding:2px 8px; border-radius:3px; font-family:'JetBrains Mono' }

.inc-card    { background:#0f1318; border:1px solid #161c26; border-left:2px solid #1a4a8a; border-radius:0 6px 6px 0; padding:9px 13px; margin-bottom:7px }
.inc-card.p1 { border-left-color:#8a1a1a }
.inc-card.p2 { border-left-color:#8a5a1a }

.convo-user  { background:#0f1318; border:1px solid #161c26; border-radius:6px 6px 0 6px; padding:8px 12px; margin:6px 0; font-size:12px; color:#8892a4; font-family:'JetBrains Mono' }
.convo-asst  { background:#080b0f; border:1px solid #161c26; border-left:2px solid #2d5fb0; border-radius:0 6px 6px 6px; padding:8px 12px; margin:6px 0; font-size:12px; color:#7a8499; line-height:1.7; white-space:pre-wrap }

.empty-state { color:#2a3040; font-size:13px; text-align:center; padding:80px 0; font-family:'JetBrains Mono' }
.mttr-badge  { font-family:'JetBrains Mono'; font-size:11px; color:#2a4a70; background:#0c1520; padding:2px 8px; border-radius:3px; margin-left:6px }

div[data-testid="stExpander"] { background:#0f1318!important; border:1px solid #161c26!important; border-radius:6px!important }
hr { border-color:#161c26!important }
</style>
""", unsafe_allow_html=True)


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_conn() -> psycopg2.extensions.connection:
    """Open a fresh psycopg2 connection. Cheap; avoids stale-connection bugs."""
    return psycopg2.connect(**PG)


def q(sql: str, params=None) -> list:
    """Run a SELECT and return rows as RealDictRow list."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()


def exe(sql: str, params=None) -> None:
    """Run a DML statement with autocommit. Always closes the connection."""
    conn = get_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
    finally:
        conn.close()


def init_db() -> None:
    """
    Bootstrap all tables, indexes, and triggers.
    schema.sql is the canonical source; this function mirrors it so the app
    can self-heal even if the init script was not run (e.g. local dev without Docker).
    """
    statements = [
        "CREATE EXTENSION IF NOT EXISTS vector",

        """CREATE TABLE IF NOT EXISTS system_logs (
            id          BIGSERIAL   PRIMARY KEY,
            ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
            level       TEXT        NOT NULL,
            service     TEXT        NOT NULL,
            host        TEXT,
            message     TEXT        NOT NULL,
            status_code INT,
            latency_ms  INT,
            trace_id    TEXT
        )""",

        "CREATE INDEX IF NOT EXISTS idx_logs_ts      ON system_logs (ts DESC)",
        "CREATE INDEX IF NOT EXISTS idx_logs_service ON system_logs (service)",
        "CREATE INDEX IF NOT EXISTS idx_logs_level   ON system_logs (level)",

        """CREATE TABLE IF NOT EXISTS incident_kb (
            id          BIGSERIAL   PRIMARY KEY,
            inc_id      TEXT        UNIQUE NOT NULL,
            title       TEXT        NOT NULL,
            service     TEXT        NOT NULL,
            severity    TEXT        NOT NULL DEFAULT 'P2',
            tags        TEXT[]      NOT NULL DEFAULT '{}',
            resolution  TEXT        NOT NULL,
            source_file TEXT,
            embedding   VECTOR(768),
            fts_vector  TSVECTOR,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",

        """CREATE INDEX IF NOT EXISTS idx_kb_hnsw
           ON incident_kb USING hnsw (embedding vector_cosine_ops)
           WITH (m = 16, ef_construction = 64)""",

        "CREATE INDEX IF NOT EXISTS idx_kb_fts ON incident_kb USING gin (fts_vector)",
        "CREATE INDEX IF NOT EXISTS idx_kb_service ON incident_kb (service)",

        """CREATE OR REPLACE FUNCTION fn_kb_fts_update() RETURNS TRIGGER
           LANGUAGE plpgsql AS $$
           BEGIN
               NEW.fts_vector :=
                   setweight(to_tsvector('english', coalesce(NEW.title,'')), 'A') ||
                   setweight(to_tsvector('english', coalesce(array_to_string(NEW.tags,' '),'')), 'B') ||
                   setweight(to_tsvector('english', coalesce(NEW.resolution,'')), 'C');
               NEW.updated_at := now();
               RETURN NEW;
           END; $$""",

        "DROP TRIGGER IF EXISTS trg_kb_fts ON incident_kb",

        """CREATE TRIGGER trg_kb_fts
           BEFORE INSERT OR UPDATE ON incident_kb
           FOR EACH ROW EXECUTE FUNCTION fn_kb_fts_update()""",

        """CREATE TABLE IF NOT EXISTS resolution_log (
            id           BIGSERIAL   PRIMARY KEY,
            scenario_key TEXT        NOT NULL,
            severity     TEXT,
            service      TEXT,
            alert_text   TEXT        NOT NULL,
            resolution   TEXT,
            tool_steps   INT         NOT NULL DEFAULT 0,
            duration_ms  INT,
            resolved_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",

        "CREATE INDEX IF NOT EXISTS idx_res_log_ts ON resolution_log (resolved_at DESC)",
    ]
    conn = get_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)
        log.info("DB schema initialised (idempotent)")
    finally:
        conn.close()


# ── Ollama helpers ────────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    """Embed text with nomic-embed-text via Ollama → 768-dim vector."""
    resp = requests.post(
        f"{OLLAMA_HOST}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    # /api/embed returns {"embeddings": [[...]]}  (batch) or {"embedding": [...]} (legacy)
    embs = data.get("embeddings") or data.get("embedding")
    return embs[0] if isinstance(embs[0], list) else embs


def ollama_healthy() -> bool:
    """True if Ollama API is reachable."""
    try:
        return requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


def models_ready() -> dict[str, bool]:
    """Return which required models are already pulled."""
    try:
        tags  = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3).json().get("models", [])
        names = {m["name"].split(":")[0] for m in tags}
        return {
            "inference": any(n in names for n in ["qwen2.5-coder", "qwen2.5", "mistral", "llama3"]),
            "embed":     "nomic-embed-text" in names,
        }
    except Exception:
        return {"inference": False, "embed": False}


# ── KB ingestion ──────────────────────────────────────────────────────────────

def parse_kb(text: str) -> list[dict]:
    """
    Parse structured Markdown KB files.
    Expected block header format:
        ## INC-2024-0312 · P1 · nginx · cpu, kubernetes
    """
    incidents: list[dict] = []
    for block in re.split(r"\n(?=## INC-)", text):
        if not block.startswith("## INC-"):
            continue
        lines = block.strip().splitlines()
        parts = [p.strip() for p in lines[0].lstrip("#").split("·")]
        if len(parts) < 3:
            continue
        inc_id   = parts[0].strip()
        severity = parts[1].strip() if len(parts) > 1 else "P2"
        service  = parts[2].strip() if len(parts) > 2 else "unknown"
        tags     = [t.strip() for t in parts[3].split(",")] if len(parts) > 3 else []
        title    = inc_id
        for line in lines[1:]:
            m = re.match(r"\*\*Title:\*\*\s*(.+)", line)
            if m:
                title = m.group(1).strip()
                break
        resolution = "\n".join(lines[1:]).strip()
        incidents.append(
            dict(inc_id=inc_id, title=title, service=service,
                 severity=severity, tags=tags, resolution=resolution)
        )
    return incidents


def _kb_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def seed_kb() -> int:
    """
    Embed and index all *.md files in KB_DIR.
    Skips incidents already present (ON CONFLICT DO NOTHING).
    Returns the number of newly indexed incidents.
    """
    kb_files = list(KB_DIR.glob("*.md")) if KB_DIR.exists() else []
    if not kb_files:                                     # fallback for local dev
        kb_files = list(Path("/app/kb").glob("*.md"))
    new_count = 0
    for f in kb_files:
        for inc in parse_kb(f.read_text(encoding="utf-8")):
            if q("SELECT 1 FROM incident_kb WHERE inc_id=%s", (inc["inc_id"],)):
                continue
            text = f"{inc['title']}. {inc['resolution']}"
            emb  = embed(text)
            exe(
                "INSERT INTO incident_kb "
                "(inc_id, title, service, severity, tags, resolution, source_file, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (inc_id) DO NOTHING",
                (inc["inc_id"], inc["title"], inc["service"], inc["severity"],
                 inc["tags"], inc["resolution"], str(f), emb),
            )
            new_count += 1
            log.info("indexed KB incident: %s", inc["inc_id"])
    return new_count


def watch_kb() -> None:
    """
    Background thread: re-ingest KB when .md files are created or modified.
    Uses watchdog's Observer (which runs its own internal thread).
    """
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if str(event.src_path).endswith(".md"):
                log.info("KB file changed, re-indexing: %s", event.src_path)
                seed_kb()
        on_created = on_modified

    observer = Observer()
    observer.daemon = True          # don't block Python shutdown
    observer.schedule(_Handler(), str(KB_DIR), recursive=False)
    observer.start()
    log.info("KB watcher started on %s", KB_DIR)
    try:
        while observer.is_alive():
            observer.join(timeout=1)
    except Exception:
        pass


# ── Hybrid search ─────────────────────────────────────────────────────────────

def hybrid_search(query: str, top_k: int = 4) -> list:
    """
    Reciprocal Rank Fusion of two ranking signals:
      1. pgvector HNSW cosine similarity  (semantic relevance)
      2. Postgres tsvector full-text rank  (keyword precision)

    RRF score = 1/(k + rank_vec) + 1/(k + rank_fts)   where k=60 (standard)
    This consistently outperforms either signal alone on recall@K.
    """
    emb = embed(query)
    return q("""
        WITH vec AS (
            SELECT inc_id,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) AS rank
            FROM   incident_kb
            LIMIT  20
        ),
        fts AS (
            SELECT inc_id,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank_cd(fts_vector, plainto_tsquery('english', %s)) DESC
                   ) AS rank
            FROM   incident_kb
            WHERE  fts_vector @@ plainto_tsquery('english', %s)
            LIMIT  20
        ),
        rrf AS (
            SELECT v.inc_id,
                   (1.0 / (60 + v.rank) + 1.0 / (60 + COALESCE(f.rank, 100))) AS score
            FROM   vec v
            LEFT JOIN fts f USING (inc_id)
        )
        SELECT k.inc_id, k.title, k.service, k.severity, k.tags,
               k.resolution, r.score AS similarity
        FROM   rrf r
        JOIN   incident_kb k USING (inc_id)
        ORDER  BY r.score DESC
        LIMIT  %s
    """, (emb, query, query, top_k))


# ── Diagnostic simulator ──────────────────────────────────────────────────────

def simulate_diagnostic(command: str, scenario_key: str) -> str:
    """
    Return realistic terminal output for a given command + active scenario.
    In a real deployment this would shell out to kubectl / redis-cli / aws-cli.
    """
    cmd = command.lower().strip()
    sc  = SCENARIOS.get(scenario_key, {})
    svc = sc.get("service", "unknown")
    now = datetime.utcnow().strftime("%H:%M:%S")

    # kubectl top pods
    if "top pod" in cmd:
        if scenario_key == "cpu_runaway":
            return (
                "NAME                              CPU(cores)   MEMORY(bytes)\n"
                "nginx-deploy-7f9b2-xkp4q          971m         312Mi\n"
                "nginx-deploy-7f9b2-m3rz1          989m         298Mi\n"
                "nginx-deploy-7f9b2-c9wq8          CrashLoopBackOff"
            )
        if scenario_key == "memory_leak":
            return (
                "NAME                              CPU(cores)   MEMORY(bytes)\n"
                "auth-svc-76f9-kpx2m               312m         14200Mi\n"
                "auth-svc-76f9-rtzq1               287m         13890Mi"
            )
        return (
            f"NAME                              CPU(cores)   MEMORY(bytes)\n"
            f"{svc}-deploy-ab1cd                 {random.randint(30, 80)}m          "
            f"{random.randint(100, 400)}Mi"
        )

    # kubectl get pods
    if "get pod" in cmd:
        if scenario_key == "cpu_runaway":
            return (
                "NAME                          READY   STATUS             RESTARTS\n"
                "nginx-deploy-7f9b2-xkp4q      0/1     CrashLoopBackOff   6\n"
                "nginx-deploy-7f9b2-m3rz1      0/1     CrashLoopBackOff   4\n"
                "nginx-deploy-7f9b2-c9wq8      1/1     Running            0"
            )
        if scenario_key == "bad_deploy":
            return (
                "NAME                          READY   STATUS    RESTARTS\n"
                "checkout-deploy-v241-aab12    0/1     Running   0\n"
                "checkout-deploy-v241-bcd34    0/1     Running   0\n"
                "checkout-deploy-v241-efg56    1/1     Running   0\n"
                "checkout-deploy-v240-xyz99    1/1     Running   0  (previous)"
            )
        return (
            f"NAME                          READY   STATUS    RESTARTS\n"
            f"{svc}-deploy-ab1cd-xk1          1/1     Running   0"
        )

    # kubectl rollout
    if "rollout" in cmd:
        if "undo" in cmd or "restart" in cmd:
            return (
                f"deployment.apps/{svc} restarted\n"
                "Waiting for rollout to finish: 0 of 3 updated replicas are available..."
            )
        if "status" in cmd:
            return f'deployment "{svc}" successfully rolled out'
        return f"deployment.apps/{svc} rolled out"

    # kubectl logs
    if "logs" in cmd:
        if scenario_key == "cpu_runaway":
            return (
                f"[{now}] ERROR nginx worker_0: CPU 97% accept() loop stalled\n"
                f"[{now}] ERROR nginx worker_processes=512 — expected 'auto'\n"
                f"[{now}] WARN  nginx OOM killer invoked on worker_2"
            )
        if scenario_key == "memory_leak":
            return (
                f"[{now}] WARN  JWTCache: size=14.2GB entries=2847301\n"
                f"[{now}] ERROR java.lang.OutOfMemoryError: Java heap space\n"
                f"[{now}] ERROR heap: 94% used, GC pause 2.1s"
            )
        return f"[{now}] INFO  {svc}: serving requests normally"

    # kubectl describe
    if "describe" in cmd:
        return (
            f"Name: {svc}-deploy-7f9b2-xkp4q\n"
            f"Status: CrashLoopBackOff\n"
            f"Events:\n"
            f"  {now}  Warning  BackOff     kubelet  Back-off restarting failed container\n"
            f"  {now}  Warning  OOMKilling  kernel   Out of memory: Kill process"
        )

    # kubectl patch / set image
    if "patch" in cmd or "set image" in cmd:
        return f"deployment.apps/{svc} patched"

    # kubectl autoscale / hpa
    if "autoscale" in cmd or "hpa" in cmd:
        return f"horizontalpodautoscaler.autoscaling/{svc} created\nMin: 2  Max: 8  CPU target: 70%"

    # aws rds
    if "aws rds" in cmd:
        if "failover" in cmd:
            return (
                '{\n  "DBCluster": {\n'
                '    "Status": "failing-over",\n'
                '    "ReaderEndpoint": "prod-aurora-cluster.cluster-ro-xyz.ap-southeast-2.rds.amazonaws.com"\n'
                "  }\n}"
            )
        return '{"DBCluster": {"Status": "available", "ReplicaLag": "0ms"}}'

    # redis-cli
    if "redis-cli" in cmd or "redis" in cmd:
        if "cluster failover" in cmd:
            return "OK\n# Failover started. New primary: 10.0.1.8:6379"
        if "config set" in cmd:
            return "OK"
        if "bgrewriteaof" in cmd:
            return "Background append only file rewriting started"
        if "info" in cmd:
            return (
                "# Stats\nkeyspace_hits:48291\nkeyspace_misses:512\n"
                "# Memory\nused_memory_human:2.41G\nmaxmemory_policy:allkeys-lru"
            )

    # psql / pg_isready
    if "psql" in cmd or "pg_isready" in cmd:
        return "synapse:5432 - accepting connections"

    # curl health check
    if "curl" in cmd and "health" in cmd:
        return 'HTTP/1.1 200 OK\n{"status":"ok"}'

    # generic fallback
    return f"$ {command}\n[{now}] Command executed successfully"


# ── Agentic tool definitions ──────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_logs",
            "description": (
                "Query recent structured system logs from PostgreSQL. "
                "Filter by service name or log level to find relevant error patterns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string",  "description": "Service name to filter on (optional)"},
                    "level":   {"type": "string",  "description": "Log level: ERROR, WARN, or INFO (optional)"},
                    "limit":   {"type": "integer", "description": "Max rows to return (default 15)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": (
                "Search the incident knowledge base using hybrid pgvector + full-text search. "
                "Returns past incidents ranked by semantic and keyword relevance. "
                "Use this to find proven resolutions for similar issues."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string",  "description": "Describe the current issue"},
                    "top_k": {"type": "integer", "description": "Number of results to return (default 3)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_diagnostic",
            "description": (
                "Execute a diagnostic or remediation command against the production environment. "
                "Supports: kubectl, redis-cli, aws, psql, curl. "
                "Always state your reason. Use this to confirm root cause and verify fixes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Full command string to run"},
                    "reason":  {"type": "string", "description": "Why you are running this command"},
                },
                "required": ["command", "reason"],
            },
        },
    },
]


def execute_tool(name: str, args: dict, scenario_key: str) -> str:
    """Dispatch a tool call and return its string result."""
    if name == "query_logs":
        service = args.get("service")
        level   = args.get("level")
        limit   = int(args.get("limit", 15))
        sql     = "SELECT ts, level, service, message FROM system_logs WHERE 1=1"
        params: list = []
        if service:
            sql += " AND service ILIKE %s"
            params.append(f"%{service}%")
        if level:
            sql += " AND level = %s"
            params.append(level.upper())
        sql += " ORDER BY ts DESC LIMIT %s"
        params.append(limit)
        rows = q(sql, params)
        if not rows:
            return "No log entries found matching those filters."
        return "\n".join(
            f"[{r['ts'].strftime('%H:%M:%S')}] {r['level']:<5} {r['service']:<15} {r['message']}"
            for r in rows
        )

    if name == "search_kb":
        query = args.get("query", "")
        top_k = int(args.get("top_k", 3))
        hits  = hybrid_search(query, top_k=top_k)
        if not hits:
            return "No matching incidents found in knowledge base."
        out = []
        for h in hits:
            out.append(
                f"[{h['inc_id']}] {h['title']}  (rrf_score={float(h['similarity']):.3f})\n"
                f"  Severity: {h['severity']} | Service: {h['service']}\n"
                f"  Resolution: {h['resolution'][:500]}..."
            )
        return "\n\n".join(out)

    if name == "run_diagnostic":
        return simulate_diagnostic(args.get("command", ""), scenario_key)

    return f"[error] Unknown tool: {name}"


# ── Agentic loop ──────────────────────────────────────────────────────────────

def run_agent(
    scenario_key: str,
    alert_text: str,
    trace_container,
    _result_container,   # kept for API compatibility; result written to session_state
) -> None:
    """
    Iterative tool-use loop:
      1. Send alert + system prompt to the LLM
      2. LLM chooses tools → execute → append results → repeat
      3. When LLM emits a response with no tool calls → final resolution

    All state is written to st.session_state so Streamlit can re-render it
    after st.rerun().
    """
    sc = SCENARIOS[scenario_key]
    t0 = time.monotonic()

    messages = [
        {
            "role": "system",
            "content": (
                "You are Synapse, an expert SRE incident co-pilot with direct access to "
                "production systems via tools. Work methodically:\n"
                "1. Call query_logs to see what is happening right now\n"
                "2. Call search_kb to find similar past incidents and their proven resolutions\n"
                "3. Call run_diagnostic to gather evidence and confirm root cause\n"
                "4. Call run_diagnostic again to apply the fix and verify recovery\n\n"
                "When you have enough evidence, provide a final structured resolution containing:\n"
                "- Root cause (cite specific log lines or diagnostic output)\n"
                "- Step-by-step remediation with exact, copy-pasteable commands\n"
                "- Prevention recommendation\n"
                "- Estimated MTTR\n\n"
                "Be concise and precise. Commands must be exact and immediately runnable."
            ),
        },
        {
            "role": "user",
            "content": (
                f"ALERT: {alert_text}\n"
                f"Service: {sc['service']} | Severity: {sc['severity']}\n\n"
                "Investigate this incident. Use your tools to diagnose and resolve it."
            ),
        },
    ]

    steps_html: list[str] = []

    for step in range(AGENT_MAX_STEPS):
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={"model": OLLAMA_MODEL, "messages": messages, "tools": TOOLS, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            st.session_state.resolution_text = f"⚠ Agent communication error: {exc}"
            st.session_state.agent_trace     = steps_html
            return

        msg        = resp.json()["message"]
        tool_calls = msg.get("tool_calls") or []
        messages.append(msg)

        # No more tool calls → LLM has reached a conclusion
        if not tool_calls:
            duration_ms = int((time.monotonic() - t0) * 1000)
            final_text  = msg.get("content", "").strip()

            st.session_state.resolution_text = final_text
            st.session_state.agent_trace     = steps_html
            st.session_state.agent_steps     = step + 1
            st.session_state.agent_duration_ms = duration_ms

            # Persist to audit log (non-fatal if it fails)
            try:
                exe(
                    "INSERT INTO resolution_log "
                    "(scenario_key, severity, service, alert_text, resolution, tool_steps, duration_ms) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (scenario_key, sc["severity"], sc["service"],
                     alert_text, final_text, step + 1, duration_ms),
                )
            except Exception as exc:
                log.warning("Could not write resolution_log: %s", exc)
            return

        # Execute each tool call and append results to the message thread
        for tc in tool_calls:
            fn     = tc["function"]
            name   = fn["name"]
            raw    = fn.get("arguments", {})
            args   = raw if isinstance(raw, dict) else json.loads(raw)
            result = execute_tool(name, args, scenario_key)

            messages.append({"role": "tool", "content": result})

            # Render a trace card (HTML is safe — we control result content)
            args_str       = ", ".join(f"{k}={json.dumps(v)}" for k, v in args.items())
            result_preview = result[:320] + ("…" if len(result) > 320 else "")
            steps_html.append(
                f'<div class="tool-call">'
                f'<span class="tool-name">⟶ {html.escape(name)}</span>'
                f'<span class="tool-args"> ({html.escape(args_str)})</span>'
                f'<div class="tool-result">{html.escape(result_preview)}</div>'
                f'</div>'
            )
            trace_container.markdown("".join(steps_html), unsafe_allow_html=True)

    # Reached max steps without a clean conclusion
    st.session_state.resolution_text = (
        "Agent reached the maximum step limit. "
        "Review the tool trace above for findings — the root cause evidence is likely there."
    )
    st.session_state.agent_trace = steps_html


# ── Scenarios ─────────────────────────────────────────────────────────────────

SCENARIOS: dict[str, dict] = {
    "cpu_runaway": {
        "label": "CPU runaway — nginx fork storm",
        "icon": "🔥", "severity": "P1", "service": "nginx",
        "alert": "[P1] CPU 97% prod-{1,2,3} · nginx workers unresponsive · HAProxy circuit open",
        "metrics": ("97%", "61%", "8,200ms"),
        "logs": [
            ("ERROR", "nginx",       "worker_0: CPU 94% — accept() loop stalled"),
            ("ERROR", "nginx",       "worker_1: CPU 97% — accept() loop stalled"),
            ("ERROR", "nginx",       "worker_2: CPU 99% — OOM killer invoked"),
            ("WARN",  "api-gateway", "upstream timeout: nginx→api 3,002ms [threshold 1,000ms]"),
            ("ERROR", "k8s",         "pod nginx-deploy-7f9b2 — CrashLoopBackOff [restarts:6]"),
            ("ERROR", "k8s",         "pod nginx-deploy-4a1c9 — CrashLoopBackOff [restarts:4]"),
            ("WARN",  "haproxy",     "backend nginx_pool: 2/4 DOWN, circuit OPEN"),
            ("ERROR", "slo-mon",     "slo:availability=0.74 < 0.999 [5m window] — BREACH"),
        ],
    },
    "db_replica_lag": {
        "label": "DB replica lag — checkout 500s",
        "icon": "🐢", "severity": "P1", "service": "postgres",
        "alert": "[P1] Postgres replica lag 8.4s · checkout 500 rate 42% · SLO breach",
        "metrics": ("31%", "42%", "6,100ms"),
        "logs": [
            ("ERROR", "checkout",  "NullPointerException: row.get('user_id') is None [read: replica]"),
            ("ERROR", "checkout",  "NullPointerException: row.get('cart_total') is None [read: replica]"),
            ("ERROR", "checkout",  "GET /api/v2/checkout 500 — stale read, lag=8412ms"),
            ("WARN",  "postgres",  "streaming_replication: lag=8412ms primary_lsn=A1/B7 replica=A0/C2"),
            ("ERROR", "sentry",    "CheckoutService: 1,847 NullPointerException in 60s"),
            ("WARN",  "postgres",  "autovacuum: table 'orders' dead_tup_ratio=0.41 [threshold 0.2]"),
            ("ERROR", "pagerduty", "P1 created: checkout.http_500_rate=0.42 > 0.05 [5m]"),
            ("WARN",  "haproxy",   "server postgres_replica1 DOWN — health check 3/3 failed"),
        ],
    },
    "memory_leak": {
        "label": "Memory leak — auth-svc OOM",
        "icon": "💧", "severity": "P2", "service": "auth-svc",
        "alert": "[P2] auth-svc heap 94% · JWTCache 14GB · OOM imminent · HPA maxed",
        "metrics": ("78%", "18%", "9,800ms"),
        "logs": [
            ("WARN",  "auth-svc",    "JWTCache: size=14.2GB entries=2,847,301 — no eviction policy"),
            ("WARN",  "auth-svc",    "JWTCache: size=14.8GB — GC pause 2.1s"),
            ("ERROR", "auth-svc",    "java.lang.OutOfMemoryError: Java heap space [heap: 94%]"),
            ("ERROR", "k8s",         "pod auth-svc-76f9 OOMKilled [exit:137] — restarting"),
            ("WARN",  "api-gateway", "auth upstream: 3 consecutive 503s — weight→0"),
            ("ERROR", "checkout",    "AuthClient: token validation timeout [12s, auth unreachable]"),
            ("WARN",  "k8s",         "HPA: auth-svc at max replicas (5/5) — cannot scale"),
            ("ERROR", "slo-mon",     "slo:auth.validate_token p99=9800ms > 200ms — BREACH"),
        ],
    },
    "bad_deploy": {
        "label": "Bad deploy — ConfigMap missing key",
        "icon": "💥", "severity": "P2", "service": "checkout",
        "alert": "[P2] checkout error rate 0.2%→28% post-deploy v2.4.1 [12:47 UTC]",
        "metrics": ("42%", "28%", "2,100ms"),
        "logs": [
            ("ERROR", "checkout", "ConfigError: DB_REPLICA_HOST not in env — initialized None"),
            ("ERROR", "checkout", "NullPointerException: db_client.connect() on None [db_client.py:84]"),
            ("ERROR", "checkout", "GET /api/v2/checkout 500 [52ms] — unhandled exception"),
            ("ERROR", "checkout", "GET /api/v2/orders   500 [48ms] — unhandled exception"),
            ("WARN",  "k8s",      "rollout checkout v2.4.1: 3/6 pods Ready — stalling"),
            ("ERROR", "sentry",   "checkout: 923 ConfigError exceptions since deploy 12:47"),
            ("WARN",  "argocd",   "health: checkout Degraded — readiness probe failing [3/6]"),
            ("INFO",  "k8s",      "rollout history: v2.4.0 [last-stable] v2.4.1 [current]"),
        ],
    },
    "redis_cascade": {
        "label": "Redis cluster fail — cascade timeout",
        "icon": "⛓", "severity": "P2", "service": "redis",
        "alert": "[P2] Redis node 10.0.1.7 disk-full · cluster FAIL · inventory→checkout cascade",
        "metrics": ("55%", "31%", "5,400ms"),
        "logs": [
            ("ERROR", "redis",     "CLUSTER FAIL — node 10.0.1.7:6379 unreachable [15s]"),
            ("ERROR", "inventory", "RedisConnectionError: [Errno 110] Connection timed out [10.0.1.7:6379]"),
            ("WARN",  "inventory", "cache MISS fallback postgres: stock_levels [4,200ms]"),
            ("WARN",  "inventory", "circuit breaker: redis OPEN — all reads→DB"),
            ("ERROR", "checkout",  "InventoryClient: check_stock() timeout 5,000ms — rejecting order"),
            ("WARN",  "checkout",  "GET /api/v2/checkout 503 — inventory unavailable"),
            ("ERROR", "slo-mon",   "slo:checkout_success_rate=0.68 < 0.995 [5m] — BREACH"),
            ("WARN",  "redis",     "sentinel: promoting 10.0.1.8:6379 as primary [election 2.1s]"),
        ],
    },
}


# ── Log helpers ───────────────────────────────────────────────────────────────

def inject_logs(scenario: dict) -> None:
    """Write synthetic log events for the active scenario into system_logs."""
    now = datetime.utcnow()
    for i, (level, service, message) in enumerate(scenario["logs"]):
        ts = now - timedelta(seconds=len(scenario["logs"]) - i)
        exe(
            "INSERT INTO system_logs "
            "(ts, level, service, host, message, status_code, latency_ms, trace_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (ts, level, service, f"prod-{random.randint(1, 3)}.internal",
             message, 500 if level == "ERROR" else 200,
             random.randint(50, 9_000), uuid.uuid4().hex[:16]),
        )


def recent_logs(limit: int = 50) -> list:
    return q(
        "SELECT ts, level, service, message FROM system_logs ORDER BY ts DESC LIMIT %s",
        (limit,),
    )


def resolution_count() -> int:
    """How many incidents have been resolved this session (from audit log)."""
    try:
        return q("SELECT COUNT(*) AS c FROM resolution_log")[0]["c"]
    except Exception:
        return 0


# ── Session-state bootstrap ───────────────────────────────────────────────────

if "initialized" not in st.session_state:
    st.session_state.update(
        initialized       = False,
        scenario          = None,
        resolution_text   = None,
        agent_trace       = [],
        agent_steps       = 0,
        agent_duration_ms = 0,
        conversation      = [],
        db_ok             = False,
        db_err            = "",
    )

if not st.session_state.initialized:
    try:
        init_db()
        seed_kb()
        threading.Thread(target=watch_kb, daemon=True).start()
        st.session_state.db_ok       = True
        st.session_state.initialized = True
    except Exception as exc:
        st.session_state.db_err = str(exc)
        log.exception("Startup failed: %s", exc)


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⬡ Synapse")
    st.caption("SRE incident co-pilot · agentic · offline")
    st.divider()

    # ── Stack health ─────────────────────────────────────────────────────────
    st.markdown("### stack")
    db_ok = st.session_state.db_ok
    ol_ok = ollama_healthy()
    ready = models_ready() if ol_ok else {"inference": False, "embed": False}
    kb_cnt = q("SELECT COUNT(*) AS c FROM incident_kb")[0]["c"] if db_ok else 0
    res_cnt = resolution_count() if db_ok else 0

    def _badge(ok: bool, label_ok: str, label_fail: str) -> str:
        cls = "status-ok" if ok else "status-err"
        txt = label_ok if ok else label_fail
        return f'<span class="{cls}">{txt}</span>'

    def _badge_warn(ok: bool, label_ok: str, label_warn: str) -> str:
        cls = "status-ok" if ok else "status-warn"
        txt = label_ok if ok else label_warn
        return f'<span class="{cls}">{txt}</span>'

    st.markdown(_badge(db_ok, "● postgres · pgvector · fts", "✕ postgres offline"), unsafe_allow_html=True)
    st.markdown(_badge_warn(ready["inference"], f"● {OLLAMA_MODEL}", f"◌ {OLLAMA_MODEL} pulling…"), unsafe_allow_html=True)
    st.markdown(_badge_warn(ready["embed"], f"● {EMBED_MODEL}", f"◌ {EMBED_MODEL} pulling…"), unsafe_allow_html=True)
    st.markdown(f'<span class="status-info">● {kb_cnt} incidents · hybrid RRF search</span>', unsafe_allow_html=True)
    if res_cnt:
        st.markdown(f'<span class="status-info">● {res_cnt} resolutions logged</span>', unsafe_allow_html=True)

    if st.session_state.db_err:
        st.error(f"DB error: {st.session_state.db_err}")

    st.divider()

    # ── Scenario picker ───────────────────────────────────────────────────────
    st.markdown("### simulate incident")

    for key, sc in SCENARIOS.items():
        if st.button(f"{sc['icon']}  {sc['label']}", key=f"sc_{key}", use_container_width=True):
            if not db_ok:
                st.error("Postgres not connected — check `make status`")
            elif not (ready["inference"] and ready["embed"]):
                st.warning("Models still pulling. Check `make logs` and retry in a moment.")
            else:
                with st.spinner("injecting logs…"):
                    inject_logs(sc)
                st.session_state.update(
                    scenario          = key,
                    resolution_text   = None,
                    agent_trace       = [],
                    agent_steps       = 0,
                    agent_duration_ms = 0,
                    conversation      = [],
                )
                st.rerun()

    if st.session_state.scenario:
        st.divider()
        if st.button("✓ resolved — reset", use_container_width=True):
            st.session_state.update(
                scenario          = None,
                resolution_text   = None,
                agent_trace       = [],
                agent_steps       = 0,
                agent_duration_ms = 0,
                conversation      = [],
            )
            st.rerun()

    st.divider()

    # ── KB info ───────────────────────────────────────────────────────────────
    st.markdown("### knowledge base")
    st.caption(f"`kb/` — {kb_cnt} incidents indexed. Drop `.md` files in; they auto-embed live.")


# ── Main layout ───────────────────────────────────────────────────────────────

active = st.session_state.scenario
sc     = SCENARIOS.get(active) if active else None

# Header row
h1, h2 = st.columns([3, 1])
with h1:
    st.markdown("## Synapse")
with h2:
    st.markdown("<br>", unsafe_allow_html=True)
    if active:
        st.markdown(f'<span class="status-err">● INCIDENT · {sc["severity"]}</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-ok">● nominal</span>', unsafe_allow_html=True)

# Alert banner
if active and sc:
    st.markdown(f'<div class="alert-bar">⚠ {html.escape(sc["alert"])}</div>', unsafe_allow_html=True)

# Metrics row
m_cpu, m_err, m_lat, m_resolved = st.columns(4)
cpu, err, lat = sc["metrics"] if sc else ("21%", "0.08%", "134ms")
with m_cpu:
    st.metric("CPU — prod cluster", cpu)
with m_err:
    st.metric("error rate (5m)", err)
with m_lat:
    st.metric("p99 latency", lat)
with m_resolved:
    st.metric("resolutions logged", str(res_cnt) if db_ok else "—")

st.divider()

# ── Two-column body ───────────────────────────────────────────────────────────
left, right = st.columns([1.1, 0.9], gap="large")

# ── Left: live log stream ─────────────────────────────────────────────────────
with left:
    st.markdown("#### system\\_logs")
    st.caption("postgres · ordered by ts desc · auto-refreshes on scenario change")
    logs = recent_logs(50) if db_ok else []
    if logs:
        rows = []
        for entry in logs:
            ts  = entry["ts"].strftime("%H:%M:%S") if hasattr(entry["ts"], "strftime") else str(entry["ts"])
            lv  = entry["level"]
            cls = {"ERROR": "E", "WARN": "W"}.get(lv, "I")
            rows.append(
                f'<div class="ll">'
                f'<span class="ts">{ts}</span>'
                f'<span class="{cls}">{lv:<5}</span>'
                f'<span class="svc">{html.escape(entry["service"][:14])}</span>'
                f'<span class="msg-{cls}">{html.escape(entry["message"])}</span>'
                f'</div>'
            )
        st.markdown(f'<div class="log-wrap">{"".join(rows)}</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="log-wrap"><span class="I">← trigger a scenario to populate logs</span></div>',
            unsafe_allow_html=True,
        )

# ── Right: agentic co-pilot ───────────────────────────────────────────────────
with right:
    st.markdown("#### incident co-pilot")

    if not active:
        st.markdown('<div class="empty-state">← trigger a scenario</div>', unsafe_allow_html=True)
    else:
        # Run the agent if we don't have a resolution yet
        if st.session_state.resolution_text is None:
            trace_box  = st.empty()
            result_box = st.empty()
            with st.spinner(f"⬡ Synapse investigating with {OLLAMA_MODEL}…"):
                run_agent(active, sc["alert"], trace_box, result_box)
            st.rerun()

        # Agent trace (collapsible)
        if st.session_state.agent_trace:
            steps = st.session_state.agent_steps
            dur   = st.session_state.agent_duration_ms
            label = f"agent trace — {steps} tool call{'s' if steps != 1 else ''}"
            if dur:
                label += f" · {dur / 1000:.1f}s"
            with st.expander(label, expanded=False):
                st.markdown("".join(st.session_state.agent_trace), unsafe_allow_html=True)

        # Resolution panel — LLM output is plain text; escape before rendering
        res_text = st.session_state.resolution_text or ""
        if res_text:
            st.markdown(
                f'<div class="res-wrap">'
                f'<div class="res-text">{html.escape(res_text)}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── Multi-turn follow-up conversation ─────────────────────────────────────────

if active and st.session_state.resolution_text:
    st.divider()
    st.markdown("#### follow-up")
    st.caption("Ask anything about this incident — Synapse has full context")

    for msg in st.session_state.conversation:
        role_cls = "convo-user" if msg["role"] == "user" else "convo-asst"
        # Escape content before injecting into HTML
        safe_content = html.escape(msg["content"])
        st.markdown(f'<div class="{role_cls}">{safe_content}</div>', unsafe_allow_html=True)

    user_input = st.text_input(
        "",
        placeholder="e.g. what if the rollback fails? / how do we prevent this? / write a post-mortem",
        key="followup",
        label_visibility="collapsed",
    )

    if user_input and user_input.strip():
        st.session_state.conversation.append({"role": "user", "content": user_input.strip()})

        # Full context: system prompt + incident + resolution + history
        history = [
            {
                "role": "system",
                "content": (
                    f"You are Synapse, an expert SRE co-pilot. The current incident is:\n"
                    f"Alert: {sc['alert']}\n"
                    f"Service: {sc['service']} | Severity: {sc['severity']}\n\n"
                    f"Resolution reached:\n{st.session_state.resolution_text}\n\n"
                    "Answer follow-up questions concisely. "
                    "For commands, provide exact runnable syntax. "
                    "For post-mortems, use standard 5-whys + timeline + action items format."
                ),
            }
        ] + [{"role": m["role"], "content": m["content"]} for m in st.session_state.conversation]

        try:
            with st.spinner("thinking…"):
                resp = requests.post(
                    f"{OLLAMA_HOST}/api/chat",
                    json={"model": OLLAMA_MODEL, "messages": history, "stream": False},
                    timeout=90,
                )
                resp.raise_for_status()
                answer = resp.json()["message"]["content"].strip()
        except requests.exceptions.RequestException as exc:
            answer = f"⚠ Communication error: {exc}"

        st.session_state.conversation.append({"role": "assistant", "content": answer})
        st.rerun()
