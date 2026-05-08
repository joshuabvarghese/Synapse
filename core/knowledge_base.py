"""
Knowledge-base service.

Handles KB ingestion (from .md files), hybrid pgvector + FTS search
via Reciprocal Rank Fusion, and CRUD operations for the KB Manager UI.
"""
from __future__ import annotations

import logging
import re

from core.config import HYBRID_TOP_K, KB_DIR, KB_FALLBACK_DIR, RRF_K
from core.db import execute, fetch
from core.ollama_client import embed

logger = logging.getLogger(__name__)


# ── Parsing ───────────────────────────────────────────────────────────────────

def _parse_kb_file(text: str) -> list[dict]:
    """
    Parse a markdown KB file into a list of incident dicts.

    Expected format per incident block::

        ## INC-001 · P1 · service · tag1, tag2
        **Title:** Short description
        Resolution body…
    """
    incidents = []
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

        title = inc_id
        for line in lines[1:]:
            m = re.match(r"\*\*Title:\*\*\s*(.+)", line)
            if m:
                title = m.group(1).strip()
                break

        incidents.append(
            dict(
                inc_id     = inc_id,
                title      = title,
                service    = service,
                severity   = severity,
                tags       = tags,
                resolution = "\n".join(lines[1:]).strip(),
            )
        )
    return incidents


# ── Ingestion ─────────────────────────────────────────────────────────────────

def seed() -> None:
    """
    Scan KB directories for .md files and upsert any new incidents.
    Already-indexed incidents (matched by inc_id) are skipped.
    """
    kb_files = list(KB_DIR.glob("*.md")) if KB_DIR.exists() else []
    if not kb_files:
        kb_files = list(KB_FALLBACK_DIR.glob("*.md"))

    for path in kb_files:
        for inc in _parse_kb_file(path.read_text()):
            if fetch("SELECT 1 FROM incident_kb WHERE inc_id = %s", (inc["inc_id"],)):
                continue
            vector = embed(f"{inc['title']}. {inc['resolution']}")
            execute(
                "INSERT INTO incident_kb "
                "(inc_id, title, service, severity, tags, resolution, source_file, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (inc_id) DO NOTHING",
                (
                    inc["inc_id"], inc["title"], inc["service"], inc["severity"],
                    inc["tags"],  inc["resolution"], str(path), vector,
                ),
            )


def watch() -> None:
    """
    Start a background watchdog thread that re-runs ``seed()`` whenever
    a .md file in KB_DIR is created or modified.
    """
    if not KB_DIR.exists():
        logger.warning("KB_DIR %s does not exist — file watcher not started", KB_DIR)
        return

    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.src_path.endswith(".md"):
                seed()

        on_created = on_modified  # type: ignore[assignment]

    observer = Observer()
    observer.schedule(_Handler(), str(KB_DIR), recursive=False)
    observer.start()
    logger.info("KB watcher started on %s", KB_DIR)


# ── Search ────────────────────────────────────────────────────────────────────

def hybrid_search(query: str, top_k: int = HYBRID_TOP_K) -> list[dict]:
    """
    Hybrid vector + full-text search using Reciprocal Rank Fusion (RRF).

    Returns up to *top_k* incident dicts ordered by fused relevance score.
    """
    vector = embed(query)
    return fetch(
        f"""
        WITH vec AS (
            SELECT inc_id,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> %s::vector) AS vec_rank
            FROM   incident_kb
            LIMIT  20
        ),
        fts AS (
            SELECT inc_id,
                   ROW_NUMBER() OVER (
                       ORDER BY ts_rank(fts_vector, plainto_tsquery('english', %s)) DESC
                   ) AS fts_rank
            FROM   incident_kb
            WHERE  fts_vector @@ plainto_tsquery('english', %s)
            LIMIT  20
        ),
        rrf AS (
            SELECT v.inc_id,
                   (1.0 / ({RRF_K} + v.vec_rank)
                    + 1.0 / ({RRF_K} + COALESCE(f.fts_rank, 100))) AS score
            FROM   vec v
            LEFT JOIN fts f USING (inc_id)
        )
        SELECT k.inc_id, k.title, k.service, k.severity, k.tags,
               k.resolution, r.score AS similarity
        FROM   rrf r
        JOIN   incident_kb k USING (inc_id)
        ORDER  BY r.score DESC
        LIMIT  %s
        """,
        (vector, query, query, top_k),
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

def get_all() -> list[dict]:
    """Return all KB entries ordered by inc_id."""
    try:
        return fetch(
            "SELECT inc_id, title, service, severity, tags, resolution "
            "FROM   incident_kb "
            "ORDER  BY inc_id"
        )
    except Exception:
        return []


def upsert(
    inc_id:   str,
    title:    str,
    service:  str,
    severity: str,
    tags_csv: str,
    resolution: str,
) -> None:
    """Insert or update a KB entry, re-embedding the resolution text."""
    tags   = [t.strip() for t in tags_csv.split(",") if t.strip()]
    vector = embed(f"{title}. {resolution}")
    execute(
        "INSERT INTO incident_kb "
        "(inc_id, title, service, severity, tags, resolution, source_file, embedding) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (inc_id) DO UPDATE SET "
        "  title = %s, service = %s, severity = %s, "
        "  tags = %s, resolution = %s, embedding = %s",
        (
            inc_id, title, service, severity, tags, resolution, "manual", vector,
            title, service, severity, tags, resolution, vector,
        ),
    )


def delete(inc_id: str) -> None:
    """Permanently remove an incident from the knowledge base."""
    execute("DELETE FROM incident_kb WHERE inc_id = %s", (inc_id,))


def count() -> int:
    """Return the total number of indexed incidents."""
    try:
        return fetch("SELECT COUNT(*) AS c FROM incident_kb")[0]["c"]
    except Exception:
        return 0
