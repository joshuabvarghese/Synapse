"""
Agentic investigation loop.

``run(scenario_key, alert_text, on_tool_call)`` drives the Ollama
tool-use loop.  It is a plain function — no Streamlit imports, no
global state — making it independently testable.

The caller supplies an ``on_tool_call`` callback that receives rendered
HTML for each tool invocation so the UI can stream progress live.
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from core.analytics import record_mttr
from core.config import AGENT_MAX_STEPS
from core.db import fetch
from core.knowledge_base import hybrid_search
from core.ollama_client import chat
from data.diagnostics import simulate
from data.scenarios import SCENARIOS

logger = logging.getLogger(__name__)

# ── Tool schema ───────────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name":        "query_logs",
            "description": "Query recent system logs from PostgreSQL. Filter by service or log level.",
            "parameters": {
                "type":       "object",
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
            "name":        "search_kb",
            "description": "Search the incident knowledge base using hybrid vector + full-text search.",
            "parameters": {
                "type":       "object",
                "required":   ["query"],
                "properties": {
                    "query": {"type": "string",  "description": "Describe the issue to search for"},
                    "top_k": {"type": "integer", "description": "Number of results (default 3)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_diagnostic",
            "description": (
                "Run a diagnostic command. Supports: kubectl, nodetool (Cassandra), "
                "kafka-topics/consumer-groups, curl (OpenSearch/_cluster), "
                "redis-cli, aws rds, psql."
            ),
            "parameters": {
                "type":       "object",
                "required":   ["command", "reason"],
                "properties": {
                    "command": {"type": "string", "description": "Full command to run"},
                    "reason":  {"type": "string", "description": "Why you are running this"},
                },
            },
        },
    },
]

# ── Tool executor ─────────────────────────────────────────────────────────────

def _execute_tool(name: str, args: dict, scenario_key: str) -> str:
    if name == "query_logs":
        return _tool_query_logs(
            service=args.get("service"),
            level=args.get("level"),
            limit=args.get("limit", 15),
        )
    if name == "search_kb":
        return _tool_search_kb(
            query=args.get("query", ""),
            top_k=args.get("top_k", 3),
        )
    if name == "run_diagnostic":
        return simulate(args.get("command", ""), scenario_key)
    return f"Unknown tool: {name}"


def _tool_query_logs(
    service: str | None,
    level: str | None,
    limit: int,
) -> str:
    sql    = "SELECT ts, level, service, message FROM system_logs WHERE 1=1"
    params: list = []

    if service:
        sql += " AND service ILIKE %s"
        params.append(f"%{service}%")
    if level:
        sql += " AND level = %s"
        params.append(level.upper())

    sql += " ORDER BY ts DESC LIMIT %s"
    params.append(limit)

    rows = fetch(sql, params)
    if not rows:
        return "No log entries found matching those filters."

    return "\n".join(
        f"[{r['ts'].strftime('%H:%M:%S')}] {r['level']:<5} {r['service']:<15} {r['message']}"
        for r in rows
    )


def _tool_search_kb(query: str, top_k: int) -> str:
    hits = hybrid_search(query, top_k=top_k)
    if not hits:
        return "No matching incidents found in knowledge base."

    return "\n\n".join(
        f"[{h['inc_id']}] {h['title']} (score={float(h['similarity']):.3f})\n"
        f"  Severity: {h['severity']} | Service: {h['service']}\n"
        f"  Resolution: {h['resolution'][:400]}..."
        for h in hits
    )


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are Synapse, an expert SRE incident co-pilot specialising in distributed systems: "
    "Cassandra, Kafka, OpenSearch, PostgreSQL, Redis, Kubernetes.\n"
    "Work methodically:\n"
    "1. query_logs — see what's happening right now\n"
    "2. search_kb  — find similar past incidents and resolutions\n"
    "3. run_diagnostic — gather evidence and confirm root cause\n"
    "4. run_diagnostic — apply the fix and verify recovery\n\n"
    "Final answer MUST use these exact headers:\n"
    "**ROOT CAUSE:** (cite specific log lines/output)\n"
    "**REMEDIATION STEPS:** (exact numbered commands)\n"
    "**VERIFICATION:** (commands to confirm resolution)\n"
    "**PREVENTION:** (specific config/policy change)\n"
    "**ESTIMATED MTTR:** (X minutes)\n"
    "Commands must be exact and runnable. Be concise."
)


# ── Public interface ──────────────────────────────────────────────────────────

class AgentResult:
    """Carries the outcome of a completed agent run."""

    def __init__(self, resolution: str, trace: list[str]):
        self.resolution = resolution
        self.trace      = trace   # list of rendered HTML strings, one per tool call


def run(
    scenario_key: str,
    alert_text:   str,
    on_tool_call: Callable[[list[str]], None] | None = None,
) -> AgentResult:
    """
    Drive the Ollama tool-use loop for up to ``AGENT_MAX_STEPS`` steps.

    Parameters
    ----------
    scenario_key:
        Slug of the active scenario.
    alert_text:
        The alert string shown to the agent.
    on_tool_call:
        Optional callback invoked after each tool execution with the
        current list of HTML trace strings so the UI can refresh.

    Returns
    -------
    AgentResult
        Contains the final resolution text and the full tool-call trace.
    """
    sc = SCENARIOS[scenario_key]
    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role":    "user",
            "content": (
                f"ALERT: {alert_text}\n"
                f"Service: {sc['service']} | Severity: {sc['severity']}\n\n"
                "Investigate this incident. Use your tools to diagnose and resolve it."
            ),
        },
    ]

    trace: list[str] = []

    for step in range(AGENT_MAX_STEPS):
        logger.debug("Agent step %d/%d", step + 1, AGENT_MAX_STEPS)
        message = chat(messages, tools=TOOLS)
        messages.append(message)

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            # Model produced a final text answer
            resolution = message.get("content", "").strip()
            record_mttr(scenario_key, sc["service"], sc["severity"])
            return AgentResult(resolution=resolution, trace=trace)

        for tc in tool_calls:
            fn     = tc["function"]
            name   = fn["name"]
            raw    = fn.get("arguments", {})
            args   = raw if isinstance(raw, dict) else json.loads(raw)
            result = _execute_tool(name, args, scenario_key)

            messages.append({
                "role":         "tool",
                "content":      result,
                "tool_call_id": tc.get("id", name),
            })

            args_display = ", ".join(f"{k}={json.dumps(v)}" for k, v in args.items())
            preview      = result[:300] + ("…" if len(result) > 300 else "")
            trace.append(
                f'<div class="tool-call">'
                f'<span class="tool-name">⟶ {name}</span>'
                f'<span class="tool-args"> ({args_display})</span>'
                f'<div class="tool-result">{preview}</div>'
                f'</div>'
            )

            if on_tool_call:
                on_tool_call(trace)

    return AgentResult(
        resolution="Agent reached max steps. Review trace above.",
        trace=trace,
    )
