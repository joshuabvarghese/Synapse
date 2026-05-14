"""
System-log service.

Provides helpers for injecting simulated scenario logs into Postgres
and querying recent entries for display in the UI.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from core.config import LOG_TAIL_LIMIT, LOG_TIMELINE_LIMIT
from core.db import execute, fetch
from data.scenarios import Scenario


def inject(scenario: Scenario) -> None:
    """
    Write all log lines from *scenario* into the ``system_logs`` table.

    Timestamps are spread backwards from now so the most recent log
    entry aligns with the current time.
    """
    import random

    now = datetime.utcnow()
    entries = scenario["logs"]
    for i, (level, service, message) in enumerate(entries):
        ts = now - timedelta(seconds=len(entries) - i)
        execute(
            "INSERT INTO system_logs "
            "(ts, level, service, host, message, status_code, latency_ms, trace_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                ts,
                level,
                service,
                f"prod-{random.randint(1, 3)}.internal",
                message,
                500 if level == "ERROR" else 200,
                random.randint(50, 9_000),
                uuid.uuid4().hex[:16],
            ),
        )


def recent(limit: int = LOG_TAIL_LIMIT) -> list[dict]:
    """Return the *limit* most recent log rows, newest first."""
    return fetch(
        "SELECT ts, level, service, message "
        "FROM   system_logs "
        "ORDER  BY ts DESC "
        "LIMIT  %s",
        (limit,),
    )


def timeline(limit: int = LOG_TIMELINE_LIMIT) -> list[dict]:
    """Return up to *limit* log rows for the timeline tab."""
    return recent(limit)
