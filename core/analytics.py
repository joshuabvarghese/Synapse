"""
MTTR analytics service.

Fetches real data from ``incident_history`` when available, otherwise
returns static fallback data so the dashboard is always populated.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from core.db import execute, fetch


# ── MTTR recording ────────────────────────────────────────────────────────────

_MTTR_RANGES: dict[str, tuple[int, int]] = {
    "P1": (3, 12),
    "P2": (8, 25),
    "P3": (15, 45),
}
_MTTR_DEFAULT_RANGE = (8, 20)


def record_mttr(scenario_key: str, service: str, severity: str) -> None:
    """
    Append a simulated MTTR entry to ``incident_history``.

    Uses a realistic random duration within the severity band.
    Silently swallows DB errors so a failed write never crashes the agent.
    """
    import uuid

    lo, hi = _MTTR_RANGES.get(severity, _MTTR_DEFAULT_RANGE)
    try:
        execute(
            "INSERT INTO incident_history "
            "(scenario_key, service, severity, mttr_minutes, resolved_at) "
            "VALUES (%s, %s, %s, %s, NOW())",
            (
                f"{scenario_key}_{uuid.uuid4().hex[:6]}",
                service,
                severity,
                random.randint(lo, hi),
            ),
        )
    except Exception:
        pass


# ── Queries ───────────────────────────────────────────────────────────────────

_FALLBACK_ANALYTICS = [
    {"service": "cassandra",  "severity": "P1", "avg_mttr": 18.4, "count": 7,  "min_mttr": 8,  "max_mttr": 32},
    {"service": "postgres",   "severity": "P1", "avg_mttr": 6.2,  "count": 12, "min_mttr": 3,  "max_mttr": 14},
    {"service": "kafka",      "severity": "P2", "avg_mttr": 22.1, "count": 5,  "min_mttr": 11, "max_mttr": 38},
    {"service": "opensearch", "severity": "P1", "avg_mttr": 14.8, "count": 4,  "min_mttr": 7,  "max_mttr": 28},
    {"service": "redis",      "severity": "P2", "avg_mttr": 9.3,  "count": 9,  "min_mttr": 4,  "max_mttr": 18},
    {"service": "nginx",      "severity": "P1", "avg_mttr": 5.8,  "count": 6,  "min_mttr": 3,  "max_mttr": 11},
    {"service": "auth-svc",   "severity": "P2", "avg_mttr": 11.4, "count": 8,  "min_mttr": 6,  "max_mttr": 24},
    {"service": "checkout",   "severity": "P2", "avg_mttr": 7.9,  "count": 11, "min_mttr": 4,  "max_mttr": 16},
]


def get_analytics() -> list[dict]:
    """Return per-service MTTR aggregates, with static fallback."""
    try:
        rows = fetch(
            "SELECT service, severity, "
            "       AVG(mttr_minutes) AS avg_mttr, COUNT(*) AS count, "
            "       MIN(mttr_minutes) AS min_mttr, MAX(mttr_minutes) AS max_mttr "
            "FROM   incident_history "
            "GROUP  BY service, severity "
            "ORDER  BY avg_mttr DESC"
        )
        if rows:
            return rows
    except Exception:
        pass
    return _FALLBACK_ANALYTICS


def get_trend(days: int = 30) -> list[dict]:
    """Return daily incident counts and avg MTTR for the past *days* days."""
    try:
        rows = fetch(
            "SELECT DATE_TRUNC('day', resolved_at) AS day, "
            "       COUNT(*) AS count, "
            "       AVG(mttr_minutes) AS avg_mttr "
            "FROM   incident_history "
            "WHERE  resolved_at > NOW() - (%s * INTERVAL '1 day') "
            "GROUP  BY day "
            "ORDER  BY day",
            (days,),
        )
        if rows:
            return rows
    except Exception:
        pass

    base = datetime.utcnow() - timedelta(days=days)
    return [
        {
            "day":      base + timedelta(days=i),
            "count":    random.randint(0, 4),
            "avg_mttr": round(random.uniform(5, 25), 1),
        }
        for i in range(days)
    ]
