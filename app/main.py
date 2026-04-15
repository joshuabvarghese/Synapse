"""
Synapse v2 — SRE Incident Co-Pilot
Agentic RAG: Ollama tool-use loop · Postgres hybrid search (pgvector + FTS + RRF)
Streaming responses · Multi-turn conversation · Auto-ingesting KB watcher
"""
import hashlib
import json
import os
import random
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import psycopg2
import requests
import streamlit as st
from psycopg2.extras import RealDictCursor

# ── Config ────────────────────────────────────────────────────────────────────
PG = dict(
    host     = os.environ.get("POSTGRES_HOST", "localhost"),
    user     = os.environ.get("POSTGRES_USER", "ops"),
    password = os.environ.get("POSTGRES_PASSWORD", "ops"),
    dbname   = os.environ.get("POSTGRES_DB", "synapse"),
    sslmode  = "disable",
)
OLLAMA_HOST  = os.environ.get("OLLAMA_HOST",  "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
EMBED_MODEL  = os.environ.get("EMBED_MODEL",  "nomic-embed-text")
KB_DIR       = Path(os.environ.get("KB_DIR",  "/kb"))

# ── Page ──────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Synapse", page_icon="⬡", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,400;0,500;1,400&family=Syne:wght@300;400;500&display=swap');

html,body,[class*="css"]            { font-family:'Syne',sans-serif!important; background:#0c0f14!important }
code,pre,.mono                      { font-family:'JetBrains Mono',monospace!important }

section[data-testid="stSidebar"]          { background:#080b0f!important; border-right:1px solid #161c26 }
section[data-testid="stSidebar"] *        { color:#5a6478!important }
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3       { color:#8892a4!important; font-weight:400!important }
section[data-testid="stSidebar"] .stButton button { width:100% }

.stApp                  { background:#0c0f14 }
.stApp h1,.stApp h2,.stApp h3 { color:#c9d1e0!important; font-weight:300!important; letter-spacing:-0.3px }
.stApp p,.stApp li      { color:#7a8499 }

[data-testid="metric-container"] {
    background:#0f1318!important; border:1px solid #161c26!important;
    border-radius:6px!important; padding:14px 16px!important }
[data-testid="stMetricValue"] { font-family:'JetBrains Mono'!important; font-size:22px!important; color:#c9d1e0!important }
[data-testid="stMetricLabel"] { font-size:11px!important; color:#3d4557!important; text-transform:uppercase; letter-spacing:1.2px }

.stButton button {
    background:#0f1318!important; border:1px solid #161c26!important;
    color:#7a8499!important; font-family:'JetBrains Mono'!important;
    font-size:12px!important; border-radius:4px!important;
    transition:border-color .15s,color .15s!important }
.stButton button:hover  { border-color:#3d7aed!important; color:#3d7aed!important }
.stButton button:active { transform:scale(.98)!important }

.stTextInput input {
    background:#0f1318!important; border:1px solid #161c26!important;
    color:#c9d1e0!important; font-family:'JetBrains Mono'!important; font-size:12px!important;
    border-radius:4px!important }
.stTextInput input:focus { border-color:#3d7aed!important }

.log-wrap {
    background:#080b0f; border:1px solid #161c26; border-radius:8px;
    padding:14px 16px; max-height:420px; overflow-y:auto;
    font-family:'JetBrains Mono',monospace; font-size:11.5px; line-height:1.9 }
.ll  { display:flex; gap:10px; border-bottom:1px solid #0f1318; padding:1px 0 }
.ts  { color:#2a3040; white-space:nowrap; min-width:70px }
.svc { color:#2d5fb0; min-width:90px }
.E   { color:#c94040 } .W { color:#b07a2d } .I { color:#2a3040 }
.msg-E { color:#c94040 } .msg-W { color:#b07a2d } .msg-I { color:#3d4557 }

.tool-call {
    background:#080b0f; border:1px solid #161c26; border-left:2px solid #2d5fb0;
    border-radius:0 6px 6px 0; padding:8px 13px; margin:6px 0;
    font-family:'JetBrains Mono'; font-size:11px }
.tool-name  { color:#2d5fb0 }
.tool-args  { color:#3d4557 }
.tool-result { color:#2a7a40; white-space:pre-wrap; margin-top:4px }

.agent-step {
    background:#0f1318; border:1px solid #161c26; border-radius:6px;
    padding:10px 14px; margin-bottom:8px }
.step-label { font-size:10px; color:#2a3040; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px }

.res-wrap    { background:#080b0f; border:1px solid #161c26; border-radius:8px; padding:16px }
.root-hyp    { background:#0c0f1a; border-left:2px solid #2d3fb0; border-radius:0 4px 4px 0;
               padding:10px 13px; font-size:13px; color:#8892a4; line-height:1.65; margin-bottom:14px }
.step-row    { display:flex; gap:12px; margin-bottom:13px; align-items:flex-start }
.step-n      { width:20px; height:20px; border-radius:50%; background:#0c1a10; border:1px solid #1a4a22;
               color:#2a7a40; font-size:10px; font-family:'JetBrains Mono'; display:flex;
               align-items:center; justify-content:center; flex-shrink:0; margin-top:2px }
.step-title  { font-size:12.5px; color:#8892a4; margin-bottom:5px; font-weight:500 }
.step-cmd    { background:#060810; border:1px solid #161c26; border-radius:4px; padding:7px 10px;
               font-family:'JetBrains Mono'; font-size:11px; color:#2d5fb0; white-space:pre; overflow-x:auto }
.step-why    { font-size:11px; color:#2a3040; margin-top:4px }
.prevent     { background:#0a1a0c; border-left:2px solid #1a4a22; border-radius:0 4px 4px 0;
               padding:8px 12px; font-size:12px; color:#2a7a40; margin-top:12px;
               font-family:'JetBrains Mono' }
.mttr-badge  { font-family:'JetBrains Mono'; font-size:11px; color:#2a4a70; background:#0c1520;
               padding:2px 8px; border-radius:3px; margin-left:8px }
.conf-badge  { font-family:'JetBrains Mono'; font-size:11px; padding:2px 8px; border-radius:3px }
.conf-high   { background:#0c1a10; color:#2a7a40 }
.conf-medium { background:#1a150c; color:#8a6a2a }
.conf-low    { background:#1a0c0c; color:#8a2a2a }

.alert-bar   { background:#140a0a; border:1px solid #5a1a1a; border-radius:6px;
               padding:10px 16px; margin-bottom:14px; font-size:13px; color:#c94040;
               font-family:'JetBrains Mono' }
.status-ok   { background:#0c1a10; color:#2a7a40; font-size:11px; padding:2px 8px;
               border-radius:3px; font-family:'JetBrains Mono' }
.status-err  { background:#1a0c0c; color:#c94040; font-size:11px; padding:2px 8px;
               border-radius:3px; font-family:'JetBrains Mono' }
.status-warn { background:#1a150c; color:#b07a2d; font-size:11px; padding:2px 8px;
               border-radius:3px; font-family:'JetBrains Mono' }
.status-info { background:#0c1520; color:#2a5090; font-size:11px; padding:2px 8px;
               border-radius:3px; font-family:'JetBrains Mono' }

.inc-card      { background:#0f1318; border:1px solid #161c26; border-left:2px solid #1a4a8a;
                 border-radius:0 6px 6px 0; padding:9px 13px; margin-bottom:7px }
.inc-card.p1   { border-left-color:#8a1a1a }
.inc-card.p2   { border-left-color:#8a5a1a }
.inc-title     { font-size:12.5px; color:#8892a4; margin-bottom:3px }
.inc-meta      { font-size:11px; font-family:'JetBrains Mono'; color:#2a3a50 }
.sim-score     { color:#1a4a8a }
.tag           { background:#0c1520; color:#2a4a70; font-size:10px; padding:1px 5px;
                 border-radius:3px; margin-left:4px }

.convo-user    { background:#0f1318; border:1px solid #161c26; border-radius:6px 6px 0 6px;
                 padding:8px 12px; margin:6px 0; font-size:12px; color:#8892a4;
                 font-family:'JetBrains Mono' }
.convo-asst    { background:#080b0f; border:1px solid #161c26; border-left:2px solid #2d5fb0;
                 border-radius:0 6px 6px 6px; padding:8px 12px; margin:6px 0;
                 font-size:12px; color:#7a8499; line-height:1.7 }

div[data-testid="stExpander"] { background:#0f1318!important; border:1px solid #161c26!important; border-radius:6px!important }
hr { border-color:#161c26!important }
</style>
""", unsafe_allow_html=True)


# ── DB helpers ────────────────────────────────────────────────────────────────
def get_conn():
    """Open a fresh connection each call (cheap with psycopg2; avoids stale-connection bugs)."""
    return psycopg2.connect(**PG)

def q(sql, params=None):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or [])
            return cur.fetchall()

def exe(sql, params=None):
    conn = get_conn()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(sql, params or [])
    conn.close()


# ── Ollama helpers ────────────────────────────────────────────────────────────
def embed(text: str) -> list[float]:
    """Embed text via Ollama nomic-embed-text (768-dim)."""
    resp = requests.post(
        f"{OLLAMA_HOST}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    # Ollama /api/embed returns {"embeddings": [[...]]}
    embs = data.get("embeddings") or data.get("embedding")
    return embs[0] if isinstance(embs[0], list) else embs

def ollama_healthy() -> bool:
    try:
        return requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3).status_code == 200
    except Exception:
        return False

def models_ready() -> dict[str, bool]:
    """Check which models are pulled."""
    try:
        tags = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3).json().get("models", [])
        names = {m["name"].split(":")[0] for m in tags}
        return {
            "inference": any(n in names for n in ["qwen2.5-coder", "qwen2.5"]),
            "embed":     "nomic-embed-text" in names,
        }
    except Exception:
        return {"inference": False, "embed": False}


# ── KB ingestion ──────────────────────────────────────────────────────────────
def parse_kb(text: str) -> list[dict]:
    incidents = []
    for block in re.split(r'\n(?=## INC-)', text):
        if not block.startswith("## INC-"):
            continue
        lines  = block.strip().splitlines()
        parts  = [p.strip() for p in lines[0].lstrip("#").split("·")]
        if len(parts) < 3:
            continue
        inc_id   = parts[0].strip()
        severity = parts[1].strip() if len(parts) > 1 else "P2"
        service  = parts[2].strip() if len(parts) > 2 else "unknown"
        tags     = [t.strip() for t in parts[3].split(",")] if len(parts) > 3 else []
        title    = inc_id
        for line in lines[1:]:
            m = re.match(r'\*\*Title:\*\*\s*(.+)', line)
            if m:
                title = m.group(1).strip()
                break
        resolution = "\n".join(lines[1:]).strip()
        incidents.append(dict(inc_id=inc_id, title=title, service=service,
                              severity=severity, tags=tags, resolution=resolution))
    return incidents

def _kb_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()

def seed_kb():
    """Embed and index kb/*.md files. Skips already-indexed incidents."""
    kb_files = list(KB_DIR.glob("*.md")) if KB_DIR.exists() else []
    if not kb_files:
        kb_files = list(Path("/app/kb").glob("*.md"))
    for f in kb_files:
        for inc in parse_kb(f.read_text()):
            exists = q("SELECT 1 FROM incident_kb WHERE inc_id=%s", (inc["inc_id"],))
            if exists:
                continue
            text = f"{inc['title']}. {inc['resolution']}"
            emb  = embed(text)
            exe(
                "INSERT INTO incident_kb (inc_id,title,service,severity,tags,resolution,source_file,embedding) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (inc_id) DO NOTHING",
                (inc["inc_id"], inc["title"], inc["service"], inc["severity"],
                 inc["tags"], inc["resolution"], str(f), emb),
            )

def watch_kb():
    """Background thread: re-ingest KB when files change."""
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.src_path.endswith(".md"):
                seed_kb()
        on_created = on_modified

    obs = Observer()
    obs.schedule(Handler(), str(KB_DIR), recursive=False)
    obs.start()


# ── Hybrid search: pgvector + Postgres FTS, fused with RRF ───────────────────
def hybrid_search(query: str, top_k: int = 4) -> list:
    """
    Reciprocal Rank Fusion of:
      1. pgvector HNSW cosine similarity
      2. Postgres full-text search (tsvector GIN)
    k=60 is the standard RRF constant.
    """
    emb = embed(query)
    results = q("""
        WITH vec AS (
            SELECT inc_id,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) AS vec_rank
            FROM incident_kb
            LIMIT 20
        ),
        fts AS (
            SELECT inc_id,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank(fts_vector, plainto_tsquery('english', %s)) DESC
                   ) AS fts_rank
            FROM incident_kb
            WHERE fts_vector @@ plainto_tsquery('english', %s)
            LIMIT 20
        ),
        rrf AS (
            SELECT v.inc_id,
                   (1.0/(60+v.vec_rank) + 1.0/(60+COALESCE(f.fts_rank,100))) AS score
            FROM vec v
            LEFT JOIN fts f USING (inc_id)
        )
        SELECT k.inc_id, k.title, k.service, k.severity, k.tags, k.resolution,
               r.score AS similarity
        FROM rrf r
        JOIN incident_kb k USING (inc_id)
        ORDER BY r.score DESC
        LIMIT %s
    """, (emb, query, query, top_k))
    return results


# ── Diagnostic simulator ──────────────────────────────────────────────────────
# Returns realistic terminal output per active scenario + command pattern.
def simulate_diagnostic(command: str, scenario_key: str) -> str:
    cmd = command.lower().strip()
    sc  = SCENARIOS.get(scenario_key, {})
    svc = sc.get("service", "unknown")
    now = datetime.utcnow().strftime("%H:%M:%S")

    # kubectl top pods
    if "top pod" in cmd:
        if scenario_key == "cpu_runaway":
            return ("NAME                              CPU(cores)   MEMORY(bytes)\n"
                    "nginx-deploy-7f9b2-xkp4q          971m         312Mi\n"
                    "nginx-deploy-7f9b2-m3rz1          989m         298Mi\n"
                    "nginx-deploy-7f9b2-c9wq8          CrashLoopBackOff")
        if scenario_key == "memory_leak":
            return ("NAME                              CPU(cores)   MEMORY(bytes)\n"
                    "auth-svc-76f9-kpx2m               312m         14200Mi\n"
                    "auth-svc-76f9-rtzq1               287m         13890Mi")
        return (f"NAME                              CPU(cores)   MEMORY(bytes)\n"
                f"{svc}-deploy-ab1cd                 {random.randint(30,80)}m  {random.randint(100,400)}Mi")

    # kubectl get pods
    if "get pod" in cmd:
        if scenario_key == "cpu_runaway":
            return ("NAME                          READY   STATUS             RESTARTS\n"
                    "nginx-deploy-7f9b2-xkp4q      0/1     CrashLoopBackOff   6\n"
                    "nginx-deploy-7f9b2-m3rz1      0/1     CrashLoopBackOff   4\n"
                    "nginx-deploy-7f9b2-c9wq8      1/1     Running            0")
        if scenario_key == "bad_deploy":
            return ("NAME                          READY   STATUS    RESTARTS\n"
                    "checkout-deploy-v241-aab12    0/1     Running   0\n"
                    "checkout-deploy-v241-bcd34    0/1     Running   0\n"
                    "checkout-deploy-v241-efg56    1/1     Running   0\n"
                    "checkout-deploy-v240-xyz99    1/1     Running   0  (previous)")
        return (f"NAME                          READY   STATUS    RESTARTS\n"
                f"{svc}-deploy-ab1cd-xk1          1/1     Running   0")

    # kubectl rollout
    if "rollout" in cmd:
        if "undo" in cmd or "restart" in cmd:
            return f"deployment.apps/{svc} restarted\nWaiting for rollout to finish: 0 of 3 updated replicas are available..."
        if "status" in cmd:
            return f"deployment \"{svc}\" successfully rolled out"
        return f"deployment.apps/{svc} rolled out"

    # kubectl logs
    if "logs" in cmd:
        if scenario_key == "cpu_runaway":
            return (f"[{now}] ERROR nginx worker_0: CPU 97% accept() loop stalled\n"
                    f"[{now}] ERROR nginx worker_processes=512 — expected 'auto'\n"
                    f"[{now}] WARN  nginx OOM killer invoked on worker_2")
        if scenario_key == "memory_leak":
            return (f"[{now}] WARN  JWTCache: size=14.2GB entries=2847301\n"
                    f"[{now}] ERROR java.lang.OutOfMemoryError: Java heap space\n"
                    f"[{now}] ERROR heap: 94% used, GC pause 2.1s")
        return f"[{now}] INFO  {svc}: serving requests normally"

    # kubectl describe
    if "describe" in cmd:
        return (f"Name: {svc}-deploy-7f9b2-xkp4q\n"
                f"Status: CrashLoopBackOff\n"
                f"Events:\n"
                f"  {now}  Warning  BackOff  kubelet  Back-off restarting failed container\n"
                f"  {now}  Warning  OOMKilling  kernel  Out of memory: Kill process")

    # kubectl patch / set image
    if "patch" in cmd or "set image" in cmd:
        return f"deployment.apps/{svc} patched"

    # kubectl autoscale / hpa
    if "autoscale" in cmd or "hpa" in cmd:
        return f"horizontalpodautoscaler.autoscaling/{svc} created\nMin: 2  Max: 8  CPU target: 70%"

    # aws rds
    if "aws rds" in cmd:
        if "failover" in cmd:
            return ("{\n"
                    '  "DBCluster": {\n'
                    '    "Status": "failing-over",\n'
                    '    "ReaderEndpoint": "prod-aurora-cluster.cluster-ro-xyz.ap-southeast-2.rds.amazonaws.com"\n'
                    "  }\n}")
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
            return ("# Stats\nkeyspace_hits:48291\nkeyspace_misses:512\n"
                    "# Memory\nused_memory_human:2.41G\nmaxmemory_policy:allkeys-lru")

    # psql / postgres
    if "psql" in cmd or "pg_isready" in cmd:
        return "synapse:5432 - accepting connections"

    # curl health check
    if "curl" in cmd and "health" in cmd:
        return 'HTTP/1.1 200 OK\n{"status":"ok"}'

    # etcdctl
    if "etcdctl" in cmd:
        if "member list" in cmd:
            return ("8e9e05c52164694d, started, etcd-1, https://10.0.0.1:2380\n"
                    "91bc3c398fb3c146, started, etcd-2, https://10.0.0.2:2380\n"
                    "fd422379fda50e48, failed,  etcd-3, https://10.0.0.3:2380")
        return "Member removed\nMember added"

    # generic fallback
    return f"$ {command}\n[{now}] Command executed successfully"


# ── Agentic tool definitions ──────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_logs",
            "description": (
                "Query recent system logs from PostgreSQL. "
                "Use to find specific error patterns, filter by service or log level."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string",  "description": "Filter by service name (optional)"},
                    "level":   {"type": "string",  "description": "ERROR, WARN, or INFO (optional)"},
                    "limit":   {"type": "integer", "description": "Max rows (default 15)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": (
                "Search the incident knowledge base using hybrid vector + full-text search. "
                "Use to find past incidents similar to the current one."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string",  "description": "Describe the issue to search for"},
                    "top_k": {"type": "integer", "description": "Number of results (default 3)"},
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
                "Run a diagnostic command against the production environment. "
                "Supports: kubectl, redis-cli, aws, psql, curl. "
                "Use to investigate root cause and verify fixes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Full command to run"},
                    "reason":  {"type": "string", "description": "Why you are running this"},
                },
                "required": ["command", "reason"],
            },
        },
    },
]

def execute_tool(name: str, args: dict, scenario_key: str) -> str:
    if name == "query_logs":
        service = args.get("service")
        level   = args.get("level")
        limit   = args.get("limit", 15)
        sql     = "SELECT ts, level, service, message FROM system_logs WHERE 1=1"
        params  = []
        if service:
            sql += " AND service ILIKE %s"
            params.append(f"%{service}%")
        if level:
            sql += " AND level=%s"
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
        top_k = args.get("top_k", 3)
        hits  = hybrid_search(query, top_k=top_k)
        if not hits:
            return "No matching incidents found in knowledge base."
        out = []
        for h in hits:
            out.append(
                f"[{h['inc_id']}] {h['title']} (score={float(h['similarity']):.3f})\n"
                f"  Severity: {h['severity']} | Service: {h['service']}\n"
                f"  Resolution summary: {h['resolution'][:400]}..."
            )
        return "\n\n".join(out)

    if name == "run_diagnostic":
        cmd = args.get("command", "")
        return simulate_diagnostic(cmd, scenario_key)

    return f"Unknown tool: {name}"


# ── Agentic loop ──────────────────────────────────────────────────────────────
def run_agent(scenario_key: str, alert_text: str, trace_container, result_container):
    """
    Multi-step agentic loop:
    1. Start with alert + initial context
    2. LLM chooses tools (query_logs, search_kb, run_diagnostic)
    3. Execute tools, append results, repeat
    4. When LLM stops calling tools → stream final resolution
    """
    sc = SCENARIOS[scenario_key]
    messages = [
        {
            "role": "system",
            "content": (
                "You are Synapse, an expert SRE incident co-pilot with direct access to "
                "production systems via tools. Work methodically:\n"
                "1. query_logs to see what's happening right now\n"
                "2. search_kb to find similar past incidents and their resolutions\n"
                "3. run_diagnostic to gather evidence and confirm root cause\n"
                "4. run_diagnostic again to apply the fix and verify recovery\n"
                "After using tools, provide a structured resolution with:\n"
                "- Root cause (citing specific log lines)\n"
                "- Step-by-step remediation with exact commands\n"
                "- Prevention recommendation\n"
                "- Estimated MTTR\n"
                "Be concise and precise. Commands must be exact and runnable."
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

    steps_html  = []
    max_steps   = 8

    for step in range(max_steps):
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "tools": TOOLS, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        msg = resp.json()["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            # Final answer — stream it word by word into result_container
            final_text = msg.get("content", "").strip()
            st.session_state.resolution_text = final_text
            st.session_state.agent_trace     = steps_html
            return

        # Execute each tool call, show in trace
        for tc in tool_calls:
            fn   = tc["function"]
            name = fn["name"]
            raw  = fn.get("arguments", {})
            args = raw if isinstance(raw, dict) else json.loads(raw)

            result = execute_tool(name, args, scenario_key)

            # Append tool result to messages
            messages.append({"role": "tool", "content": result})

            # Build trace card
            args_str   = ", ".join(f"{k}={json.dumps(v)}" for k, v in args.items())
            result_preview = result[:300] + ("…" if len(result) > 300 else "")
            steps_html.append(
                f'<div class="tool-call">'
                f'<span class="tool-name">⟶ {name}</span>'
                f'<span class="tool-args"> ({args_str})</span>'
                f'<div class="tool-result">{result_preview}</div>'
                f'</div>'
            )

            # Live-update trace
            trace_container.markdown(
                "".join(steps_html), unsafe_allow_html=True
            )

    # Safety fallback if max steps hit
    st.session_state.resolution_text = "Agent reached max steps. Review the trace above for findings."
    st.session_state.agent_trace     = steps_html


# ── Scenarios ─────────────────────────────────────────────────────────────────
SCENARIOS = {
    "cpu_runaway": {
        "label": "CPU runaway — nginx fork storm",
        "icon": "🔥", "severity": "P1", "service": "nginx",
        "alert": "[P1] CPU 97% prod-{1,2,3} · nginx workers unresponsive · HAProxy circuit open",
        "metrics": ("97%", "61%", "8,200ms"),
        "logs": [
            ("ERROR","nginx",       "worker_0: CPU 94% — accept() loop stalled"),
            ("ERROR","nginx",       "worker_1: CPU 97% — accept() loop stalled"),
            ("ERROR","nginx",       "worker_2: CPU 99% — OOM killer invoked"),
            ("WARN", "api-gateway", "upstream timeout: nginx→api 3,002ms [threshold 1,000ms]"),
            ("ERROR","k8s",         "pod nginx-deploy-7f9b2 — CrashLoopBackOff [restarts:6]"),
            ("ERROR","k8s",         "pod nginx-deploy-4a1c9 — CrashLoopBackOff [restarts:4]"),
            ("WARN", "haproxy",     "backend nginx_pool: 2/4 DOWN, circuit OPEN"),
            ("ERROR","slo-mon",     "slo:availability=0.74 < 0.999 [5m window] — BREACH"),
        ],
    },
    "db_replica_lag": {
        "label": "DB replica lag — checkout 500s",
        "icon": "🐢", "severity": "P1", "service": "postgres",
        "alert": "[P1] Postgres replica lag 8.4s · checkout 500 rate 42% · SLO breach",
        "metrics": ("31%", "42%", "6,100ms"),
        "logs": [
            ("ERROR","checkout",   "NullPointerException: row.get('user_id') is None [read: replica]"),
            ("ERROR","checkout",   "NullPointerException: row.get('cart_total') is None [read: replica]"),
            ("ERROR","checkout",   "GET /api/v2/checkout 500 — stale read, lag=8412ms"),
            ("WARN", "postgres",   "streaming_replication: lag=8412ms primary_lsn=A1/B7 replica=A0/C2"),
            ("ERROR","sentry",     "CheckoutService: 1,847 NullPointerException in 60s"),
            ("WARN", "postgres",   "autovacuum: table 'orders' dead_tup_ratio=0.41 [threshold 0.2]"),
            ("ERROR","pagerduty",  "P1 created: checkout.http_500_rate=0.42 > 0.05 [5m]"),
            ("WARN", "haproxy",    "server postgres_replica1 DOWN — health check 3/3 failed"),
        ],
    },
    "memory_leak": {
        "label": "Memory leak — auth-svc OOM",
        "icon": "💧", "severity": "P2", "service": "auth-svc",
        "alert": "[P2] auth-svc heap 94% · JWTCache 14GB · OOM imminent · HPA maxed",
        "metrics": ("78%", "18%", "9,800ms"),
        "logs": [
            ("WARN", "auth-svc",    "JWTCache: size=14.2GB entries=2,847,301 — no eviction policy"),
            ("WARN", "auth-svc",    "JWTCache: size=14.8GB — GC pause 2.1s"),
            ("ERROR","auth-svc",    "java.lang.OutOfMemoryError: Java heap space [heap: 94%]"),
            ("ERROR","k8s",         "pod auth-svc-76f9 OOMKilled [exit:137] — restarting"),
            ("WARN", "api-gateway", "auth upstream: 3 consecutive 503s — weight→0"),
            ("ERROR","checkout",    "AuthClient: token validation timeout [12s, auth unreachable]"),
            ("WARN", "k8s",         "HPA: auth-svc at max replicas (5/5) — cannot scale"),
            ("ERROR","slo-mon",     "slo:auth.validate_token p99=9800ms > 200ms — BREACH"),
        ],
    },
    "bad_deploy": {
        "label": "Bad deploy — ConfigMap missing key",
        "icon": "💥", "severity": "P2", "service": "checkout",
        "alert": "[P2] checkout error rate 0.2%→28% post-deploy v2.4.1 [12:47 UTC]",
        "metrics": ("42%", "28%", "2,100ms"),
        "logs": [
            ("ERROR","checkout", "ConfigError: DB_REPLICA_HOST not in env — initialized None"),
            ("ERROR","checkout", "NullPointerException: db_client.connect() on None [db_client.py:84]"),
            ("ERROR","checkout", "GET /api/v2/checkout 500 [52ms] — unhandled exception"),
            ("ERROR","checkout", "GET /api/v2/orders   500 [48ms] — unhandled exception"),
            ("WARN", "k8s",      "rollout checkout v2.4.1: 3/6 pods Ready — stalling"),
            ("ERROR","sentry",   "checkout: 923 ConfigError exceptions since deploy 12:47"),
            ("WARN", "argocd",   "health: checkout Degraded — readiness probe failing [3/6]"),
            ("INFO", "k8s",      "rollout history: v2.4.0 [last-stable] v2.4.1 [current]"),
        ],
    },
    "redis_cascade": {
        "label": "Redis cluster fail — cascade timeout",
        "icon": "⛓", "severity": "P2", "service": "redis",
        "alert": "[P2] Redis node 10.0.1.7 disk-full · cluster FAIL · inventory→checkout cascade",
        "metrics": ("55%", "31%", "5,400ms"),
        "logs": [
            ("ERROR","redis",      "CLUSTER FAIL — node 10.0.1.7:6379 unreachable [15s]"),
            ("ERROR","inventory",  "RedisConnectionError: [Errno 110] Connection timed out [10.0.1.7:6379]"),
            ("WARN", "inventory",  "cache MISS fallback postgres: stock_levels [4,200ms]"),
            ("WARN", "inventory",  "circuit breaker: redis OPEN — all reads→DB"),
            ("ERROR","checkout",   "InventoryClient: check_stock() timeout 5,000ms — rejecting order"),
            ("WARN", "checkout",   "GET /api/v2/checkout 503 — inventory unavailable"),
            ("ERROR","slo-mon",    "slo:checkout_success_rate=0.68 < 0.995 [5m] — BREACH"),
            ("WARN", "redis",      "sentinel: promoting 10.0.1.8:6379 as primary [election 2.1s]"),
        ],
    },
}


# ── Log helpers ───────────────────────────────────────────────────────────────
def inject_logs(scenario: dict):
    now = datetime.utcnow()
    for i, (level, service, message) in enumerate(scenario["logs"]):
        ts = now - timedelta(seconds=len(scenario["logs"]) - i)
        exe(
            "INSERT INTO system_logs (ts,level,service,host,message,status_code,latency_ms,trace_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (ts, level, service, f"prod-{random.randint(1,3)}.internal", message,
             500 if level == "ERROR" else 200,
             random.randint(50, 9000), uuid.uuid4().hex[:16]),
        )

def recent_logs(limit=50):
    return q("SELECT ts, level, service, message FROM system_logs ORDER BY ts DESC LIMIT %s", (limit,))


# ── Startup init ──────────────────────────────────────────────────────────────
if "initialized" not in st.session_state:
    st.session_state.initialized     = False
    st.session_state.scenario        = None
    st.session_state.resolution_text = None
    st.session_state.agent_trace     = []
    st.session_state.conversation    = []   # multi-turn history
    st.session_state.db_ok           = False
    st.session_state.db_err          = ""

if not st.session_state.initialized:
    try:
        seed_kb()
        threading.Thread(target=watch_kb, daemon=True).start()
        st.session_state.db_ok      = True
        st.session_state.initialized = True
    except Exception as e:
        st.session_state.db_err = str(e)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⬡ Synapse")
    st.caption("SRE incident co-pilot · agentic · offline")
    st.divider()

    st.markdown("### stack")
    db_ok  = st.session_state.db_ok
    ol_ok  = ollama_healthy()
    ready  = models_ready() if ol_ok else {"inference": False, "embed": False}
    kb_cnt = q("SELECT COUNT(*) AS c FROM incident_kb")[0]["c"] if db_ok else 0

    st.markdown(f'<span class="{"status-ok" if db_ok else "status-err"}">{"● postgres+pgvector+fts" if db_ok else "✕ postgres offline"}</span>', unsafe_allow_html=True)
    st.markdown(f'<span class="{"status-ok" if ready["inference"] else "status-warn"}">{"● " + OLLAMA_MODEL if ready["inference"] else "◌ " + OLLAMA_MODEL + " pulling…"}</span>', unsafe_allow_html=True)
    st.markdown(f'<span class="{"status-ok" if ready["embed"] else "status-warn"}">{"● " + EMBED_MODEL if ready["embed"] else "◌ " + EMBED_MODEL + " pulling…"}</span>', unsafe_allow_html=True)
    st.markdown(f'<span class="status-info">● {kb_cnt} incidents · hybrid search</span>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### simulate incident")

    for key, sc in SCENARIOS.items():
        if st.button(f"{sc['icon']}  {sc['label']}", key=f"sc_{key}"):
            if not db_ok:
                st.error("Postgres not connected")
            elif not (ready["inference"] and ready["embed"]):
                st.warning("Models still pulling — wait and retry")
            else:
                with st.spinner("injecting logs…"):
                    inject_logs(sc)

                st.session_state.scenario        = key
                st.session_state.resolution_text = None
                st.session_state.agent_trace     = []
                st.session_state.conversation    = []
                st.rerun()

    if st.session_state.scenario:
        st.divider()
        if st.button("✓ resolved — reset", use_container_width=True):
            st.session_state.scenario        = None
            st.session_state.resolution_text = None
            st.session_state.agent_trace     = []
            st.session_state.conversation    = []
            st.rerun()

    st.divider()
    st.markdown("### knowledge base")
    st.caption(f"`kb/` — {kb_cnt} incidents indexed. Drop `.md` files in and they auto-embed.")


# ── Main ──────────────────────────────────────────────────────────────────────
active = st.session_state.scenario
sc     = SCENARIOS.get(active) if active else None

h1, h2 = st.columns([3, 1])
with h1:
    st.markdown("## Synapse")
with h2:
    st.markdown("<br>", unsafe_allow_html=True)
    if active:
        st.markdown(f'<span class="status-err">● INCIDENT · {sc["severity"]}</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-ok">● nominal</span>', unsafe_allow_html=True)

if active and sc:
    st.markdown(f'<div class="alert-bar">⚠ {sc["alert"]}</div>', unsafe_allow_html=True)

m_cpu, m_err, m_lat, m_kb = st.columns(4)
cpu, err, lat = sc["metrics"] if sc else ("21%", "0.08%", "134ms")
with m_cpu:
    st.metric("CPU — prod cluster", cpu)
with m_err:
    st.metric("error rate (5m)", err)
with m_lat:
    st.metric("p99 latency", lat)
with m_kb:
    kb_count = q("SELECT COUNT(*) AS c FROM incident_kb")[0]["c"] if db_ok else "—"
    st.metric("KB incidents", str(kb_count))

st.divider()

left, right = st.columns([1.1, 0.9], gap="large")

# ── Left: live logs ───────────────────────────────────────────────────────────
with left:
    st.markdown("#### system\\_logs")
    st.caption("postgres · ordered by ts desc")
    logs = recent_logs(50) if db_ok else []
    if logs:
        rows = []
        for l in logs:
            ts  = l["ts"].strftime("%H:%M:%S") if hasattr(l["ts"], "strftime") else str(l["ts"])
            lv  = l["level"]
            cls = {"ERROR": "E", "WARN": "W"}.get(lv, "I")
            rows.append(
                f'<div class="ll">'
                f'<span class="ts">{ts}</span>'
                f'<span class="{cls}">{lv:<5}</span>'
                f'<span class="svc">{l["service"][:14]}</span>'
                f'<span class="msg-{cls}">{l["message"]}</span>'
                f'</div>'
            )
        st.markdown(f'<div class="log-wrap">{"".join(rows)}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="log-wrap"><span class="I">← trigger a scenario to populate logs</span></div>', unsafe_allow_html=True)

# ── Right: agentic co-pilot ───────────────────────────────────────────────────
with right:
    st.markdown("#### incident co-pilot")

    if not active:
        st.markdown(
            '<div style="color:#2a3040;font-size:13px;text-align:center;padding:80px 0;'
            'font-family:JetBrains Mono">← trigger a scenario</div>',
            unsafe_allow_html=True,
        )
    else:
        # Run agent if not yet done
        if st.session_state.resolution_text is None:
            trace_box  = st.empty()
            result_box = st.empty()
            with st.spinner(f"⬡ Synapse investigating with {OLLAMA_MODEL}…"):
                run_agent(active, sc["alert"], trace_box, result_box)
            st.rerun()

        # Show agent trace (tool calls)
        if st.session_state.agent_trace:
            with st.expander("agent trace — tool calls", expanded=False):
                st.markdown("".join(st.session_state.agent_trace), unsafe_allow_html=True)

        # Show resolution
        res_text = st.session_state.resolution_text or ""
        if res_text:
            st.markdown(
                f'<div class="res-wrap"><div style="font-size:13px;color:#8892a4;line-height:1.75">'
                f'{res_text.replace(chr(10), "<br>")}'
                f'</div></div>',
                unsafe_allow_html=True,
            )

# ── Multi-turn conversation ───────────────────────────────────────────────────
if active and st.session_state.resolution_text:
    st.divider()
    st.markdown("#### follow-up")
    st.caption("Ask Synapse anything about this incident")

    for msg in st.session_state.conversation:
        role_cls = "convo-user" if msg["role"] == "user" else "convo-asst"
        st.markdown(f'<div class="{role_cls}">{msg["content"]}</div>', unsafe_allow_html=True)

    user_input = st.text_input("", placeholder="e.g. what if the rollback fails? / how do I prevent this?",
                               key="followup", label_visibility="collapsed")

    if user_input and user_input.strip():
        st.session_state.conversation.append({"role": "user", "content": user_input})

        # Build context from incident + resolution + history
        history_msgs = [
            {
                "role": "system",
                "content": (
                    f"You are Synapse, an SRE expert. The current incident is:\n"
                    f"Alert: {sc['alert']}\n"
                    f"Resolution found:\n{st.session_state.resolution_text}\n\n"
                    "Answer follow-up questions concisely and precisely."
                ),
            }
        ] + [{"role": m["role"], "content": m["content"]} for m in st.session_state.conversation]

        with st.spinner("thinking…"):
            resp = requests.post(
                f"{OLLAMA_HOST}/api/chat",
                json={"model": OLLAMA_MODEL, "messages": history_msgs, "stream": False},
                timeout=90,
            )
            answer = resp.json()["message"]["content"].strip()

        st.session_state.conversation.append({"role": "assistant", "content": answer})
        st.rerun()
