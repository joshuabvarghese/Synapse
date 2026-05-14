"""
Database helpers.

Provides a lazily-initialised ThreadedConnectionPool plus two thin
query wrappers — ``fetch`` (SELECT) and ``execute`` (DML/DDL) — that
borrow and return connections automatically.

Usage
-----
from core.db import fetch, execute

rows = fetch("SELECT * FROM incident_kb WHERE service = %s", ("kafka",))
execute("DELETE FROM incident_kb WHERE inc_id = %s", ("INC-001",))
"""
from __future__ import annotations

import logging
import threading
from typing import Any

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from core.config import PG_DSN, PG_POOL_MAX, PG_POOL_MIN

logger = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


# ── Pool management ───────────────────────────────────────────────────────────

def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return the singleton connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                logger.info("Initialising Postgres connection pool (min=%d max=%d)", PG_POOL_MIN, PG_POOL_MAX)
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=PG_POOL_MIN,
                    maxconn=PG_POOL_MAX,
                    **PG_DSN,
                )
    return _pool


def _borrow() -> psycopg2.extensions.connection:
    """Borrow a connection from the pool, falling back to a direct connect."""
    try:
        return _get_pool().getconn()
    except Exception:
        logger.warning("Pool exhausted or unavailable — opening direct connection")
        return psycopg2.connect(**PG_DSN)


def _return(conn: psycopg2.extensions.connection) -> None:
    """Return a connection to the pool, closing it if the pool rejects it."""
    try:
        _get_pool().putconn(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


# ── Public helpers ────────────────────────────────────────────────────────────

def fetch(sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    """Execute *sql* and return all rows as a list of plain dicts."""
    conn = _borrow()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params or [])
            return [dict(row) for row in cur.fetchall()]
    finally:
        _return(conn)


def execute(sql: str, params: tuple | list | None = None) -> None:
    """Execute *sql* in autocommit mode (INSERT / UPDATE / DELETE / DDL)."""
    conn = _borrow()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
    finally:
        _return(conn)
