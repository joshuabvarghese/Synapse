"""
Synapse v4 — SRE Incident Co-Pilot
===================================
Streamlit entrypoint.  This file owns:
  - Page config
  - Session-state initialisation
  - Sidebar rendering
  - Tab routing

All business logic lives in ``core/``.
All HTML rendering lives in ``ui/``.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime

import streamlit as st

import core.knowledge_base as kb
import core.log_service as log_service
import ui.renderers as render
from core.agent import run as run_agent
from core.analytics import get_analytics, get_trend
from core.config import AUTO_REFRESH_INTERVAL, LOG_TAIL_LIMIT, LOG_TIMELINE_LIMIT, OLLAMA_MODEL
from core.db import fetch
from core.ollama_client import is_healthy, models_ready
from data.scenarios import SCENARIOS
from ui.export import build_report
from ui.styles import STYLES

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Synapse",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(STYLES, unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────

_DEFAULTS: dict = {
    "initialized":     False,
    "scenario":        None,
    "resolution_text": None,
    "agent_trace":     [],
    "conversation":    [],
    "db_ok":           False,
    "db_err":          "",
    "auto_refresh":    False,
    "last_refresh":    time.time(),
}

for key, default in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default

if not st.session_state.initialized:
    try:
        kb.seed()
        threading.Thread(target=kb.watch, daemon=True).start()
        st.session_state.db_ok       = True
        st.session_state.initialized = True
    except Exception as exc:
        st.session_state.db_err = str(exc)


# ── Auto-refresh ──────────────────────────────────────────────────────────────

if st.session_state.auto_refresh:
    if time.time() - st.session_state.last_refresh > AUTO_REFRESH_INTERVAL:
        st.session_state.last_refresh = time.time()
        st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _render_sidebar() -> None:
    db_ok = st.session_state.db_ok
    ol_ok = is_healthy()
    ready = models_ready() if ol_ok else {"inference": False, "embed": False}
    kb_count = kb.count() if db_ok else 0

    st.markdown("## ⬡ Synapse")
    st.caption("SRE incident co-pilot · v4 · agentic · offline")
    st.divider()

    st.markdown("### stack")
    _badge("postgres+pgvector+pool", db_ok)
    _badge(OLLAMA_MODEL,             ready["inference"])
    _badge("nomic-embed-text",       ready["embed"])
    st.markdown(
        f'<span class="status-info">● {kb_count} incidents · hybrid RRF search</span>',
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown("### simulate incident")
    st.caption("k8s · postgres · cassandra · kafka · opensearch · redis")

    for key, sc in SCENARIOS.items():
        if st.button(f"{sc['icon']}  {sc['label']}", key=f"sc_{key}"):
            if not db_ok:
                st.error("Postgres not connected")
            elif not (ready["inference"] and ready["embed"]):
                st.warning("Models still pulling — wait and retry")
            else:
                with st.spinner("injecting logs…"):
                    log_service.inject(sc)
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
    st.markdown("### live settings")
    auto = st.toggle("Auto-refresh logs (5s)", value=st.session_state.auto_refresh)
    if auto != st.session_state.auto_refresh:
        st.session_state.auto_refresh = auto

    st.divider()
    st.markdown("### knowledge base")
    st.caption(f"`kb/` — {kb_count} incidents. Drop `.md` to auto-embed.")


def _badge(label: str, ok: bool) -> None:
    css = "status-ok" if ok else "status-warn"
    icon = "●" if ok else "◌"
    st.markdown(f'<span class="{css}">{icon} {label}</span>', unsafe_allow_html=True)


with st.sidebar:
    _render_sidebar()


# ── Header ────────────────────────────────────────────────────────────────────

active = st.session_state.scenario
sc     = SCENARIOS.get(active) if active else None
db_ok  = st.session_state.db_ok

h1, h2 = st.columns([3, 1])
with h1:
    st.markdown("## ⬡ Synapse")
with h2:
    st.markdown("<br>", unsafe_allow_html=True)
    if active and sc:
        st.markdown(f'<span class="status-err">● INCIDENT · {sc["severity"]}</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-ok">● nominal</span>', unsafe_allow_html=True)
    if st.session_state.auto_refresh:
        st.markdown('<span class="refresh-badge">↻ live</span>', unsafe_allow_html=True)

if active and sc:
    st.markdown(f'<div class="alert-bar">⚠ {sc["alert"]}</div>', unsafe_allow_html=True)

m_cpu, m_err, m_lat, m_kb = st.columns(4)
cpu = sc["metrics"]["cpu"]         if sc else "21%"
err = sc["metrics"]["error_rate"]  if sc else "0.08%"
lat = sc["metrics"]["p99_latency"] if sc else "134ms"
with m_cpu: st.metric("CPU — prod cluster", cpu)
with m_err: st.metric("error rate (5m)", err)
with m_lat: st.metric("p99 latency", lat)
with m_kb:
    count = db_ok and fetch("SELECT COUNT(*) AS c FROM incident_kb")[0]["c"] or "—"
    st.metric("KB incidents", str(count))

st.divider()


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_incident, tab_timeline, tab_analytics, tab_kb = st.tabs([
    "⬡  Incident", "◎  Timeline", "▲  MTTR Analytics", "◈  KB Manager",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — INCIDENT
# ═══════════════════════════════════════════════════════════════════════════════

with tab_incident:
    left, right = st.columns([1.1, 0.9], gap="large")

    with left:
        c1, c2 = st.columns([4, 1])
        with c1:
            st.markdown("#### system\\_logs")
            st.caption("postgres · ordered by ts desc")
        with c2:
            if st.button("↻", key="manual_refresh"):
                st.rerun()

        logs = log_service.recent(LOG_TAIL_LIMIT) if db_ok else []
        st.markdown(render.render_log_wall(logs), unsafe_allow_html=True)

    with right:
        st.markdown("#### incident co-pilot")

        if not active:
            st.markdown(
                '<div style="color:#2a3040;font-size:13px;text-align:center;padding:80px 0;'
                'font-family:JetBrains Mono">← trigger a scenario</div>',
                unsafe_allow_html=True,
            )
        else:
            assert sc is not None

            if st.session_state.resolution_text is None:
                trace_placeholder = st.empty()
                with st.spinner(f"⬡ Synapse investigating with {OLLAMA_MODEL}…"):
                    result = run_agent(
                        scenario_key=active,
                        alert_text=sc["alert"],
                        on_tool_call=lambda trace: trace_placeholder.markdown(
                            "".join(trace), unsafe_allow_html=True
                        ),
                    )
                st.session_state.resolution_text = result.resolution
                st.session_state.agent_trace     = result.trace
                st.rerun()

            if st.session_state.agent_trace:
                with st.expander("agent trace — tool calls", expanded=False):
                    st.markdown("".join(st.session_state.agent_trace), unsafe_allow_html=True)

            res_text = st.session_state.resolution_text or ""
            if res_text:
                st.markdown(render.render_resolution(res_text), unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)

                report_md = build_report(
                    scenario_key = active,
                    label        = sc["label"],
                    severity     = sc["severity"],
                    service      = sc["service"],
                    stack        = sc.get("stack", "unknown"),
                    alert        = sc["alert"],
                    metrics      = sc["metrics"],
                    logs         = log_service.recent(20),
                    resolution   = res_text,
                )
                st.download_button(
                    label     = "↓ export incident report (.md)",
                    data      = report_md,
                    file_name = f"synapse_{active}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.md",
                    mime      = "text/markdown",
                    key       = "export_btn",
                )

    # Multi-turn follow-up
    if active and sc and st.session_state.resolution_text:
        st.divider()
        st.markdown("#### follow-up")
        st.caption("Ask Synapse anything about this incident")

        for msg in st.session_state.conversation:
            role_cls = "convo-user" if msg["role"] == "user" else "convo-asst"
            st.markdown(
                f'<div class="{role_cls}">{msg["content"].replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )

        user_input = st.text_input(
            "",
            placeholder="e.g. what if the rollback fails? / how do I prevent this?",
            key="followup",
            label_visibility="collapsed",
        )
        if user_input and user_input.strip():
            st.session_state.conversation.append({"role": "user", "content": user_input})
            history = [
                {
                    "role":    "system",
                    "content": (
                        f"You are Synapse, an SRE expert specialising in distributed systems "
                        f"(Cassandra, Kafka, OpenSearch, PostgreSQL, Redis, Kubernetes).\n"
                        f"Current incident: {sc['alert']}\n"
                        f"Resolution: {st.session_state.resolution_text}\n"
                        "Answer follow-up questions concisely."
                    ),
                },
                *[{"role": m["role"], "content": m["content"]} for m in st.session_state.conversation],
            ]
            from core.ollama_client import chat
            with st.spinner("thinking…"):
                answer = chat(history).get("content", "").strip()
            st.session_state.conversation.append({"role": "assistant", "content": answer})
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — TIMELINE
# ═══════════════════════════════════════════════════════════════════════════════

with tab_timeline:
    st.markdown("#### incident timeline")
    st.caption("Chronological view of events ordered by timestamp")

    if active and sc:
        st.markdown(
            f'<div style="font-family:JetBrains Mono;font-size:11px;color:#2a4a70;'
            f'background:#0c1520;padding:8px 12px;border-radius:4px;margin-bottom:12px">'
            f'● INCIDENT ACTIVE · {sc["service"].upper()} · {sc["severity"]} · '
            f'{sc.get("stack", "kubernetes").upper()}</div>',
            unsafe_allow_html=True,
        )

    all_logs = log_service.timeline(LOG_TIMELINE_LIMIT) if db_ok else []
    st.markdown(render.render_timeline(all_logs), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — MTTR ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_analytics:
    st.markdown("#### MTTR analytics")
    st.caption("Mean time to resolution · Cassandra · Kafka · OpenSearch · Postgres · Redis")

    analytics = get_analytics()
    trend     = get_trend()

    if analytics:
        all_mttrs = [float(r["avg_mttr"]) for r in analytics]
        p1_rows   = [r for r in analytics if r["severity"] == "P1"]
        avg_all   = sum(all_mttrs) / len(all_mttrs)
        p1_avg    = sum(float(r["avg_mttr"]) for r in p1_rows) / len(p1_rows) if p1_rows else 0
        best      = min(analytics, key=lambda r: float(r["avg_mttr"]))
        total     = sum(int(r["count"]) for r in analytics)

        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("overall avg MTTR", f"{avg_all:.1f}m")
        with c2: st.metric("P1 avg MTTR",      f"{p1_avg:.1f}m")
        with c3: st.metric("total incidents",   str(total))
        with c4: st.metric("fastest service",   best["service"])

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("##### avg MTTR by service (minutes)")
    st.markdown(render.render_mttr_bars(analytics), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("##### incident volume · 30 days")
    st.markdown(render.render_sparkline(trend), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("##### MTTR heatmap — service × severity")
    st.markdown(render.render_heatmap(analytics), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — KB MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

with tab_kb:
    st.markdown("#### knowledge base manager")
    st.caption("Browse, search, add, and delete runbooks · All entries are pgvector-indexed via hybrid RRF search")

    kb_left, kb_right = st.columns([1.3, 0.7])

    with kb_left:
        st.markdown("##### indexed runbooks")
        search_query = st.text_input(
            "",
            placeholder="search KB (hybrid vector + FTS)…",
            key="kb_search",
            label_visibility="collapsed",
        )

        if search_query:
            try:
                entries = kb.hybrid_search(search_query, top_k=10)
            except Exception:
                entries = [
                    e for e in kb.get_all()
                    if search_query.lower() in (e.get("title") or "").lower()
                ]
        else:
            entries = kb.get_all()

        if not entries:
            st.markdown(
                '<div style="color:#2a3040;font-family:JetBrains Mono;font-size:12px;padding:20px">'
                "No KB entries found</div>",
                unsafe_allow_html=True,
            )
        else:
            for entry in entries:
                st.markdown(render.render_kb_card(entry), unsafe_allow_html=True)
                if st.button(f"🗑 delete {entry['inc_id']}", key=f"del_{entry['inc_id']}"):
                    kb.delete(entry["inc_id"])
                    st.rerun()

    with kb_right:
        st.markdown("##### add / update runbook")
        with st.form("add_kb_form"):
            new_id       = st.text_input("Incident ID",       placeholder="INC-2024-9999")
            new_title    = st.text_input("Title",             placeholder="Brief incident description")
            new_service  = st.text_input("Service",           placeholder="cassandra / kafka / postgres…")
            new_severity = st.selectbox("Severity",           ["P1", "P2", "P3"])
            new_tags     = st.text_input("Tags (comma-sep)",  placeholder="compaction, oom, replication")
            new_res      = st.text_area("Resolution / Runbook", height=200,
                                        placeholder="Root cause + step-by-step remediation…")
            if st.form_submit_button("embed & save"):
                if not new_id or not new_title or not new_res:
                    st.error("ID, Title and Resolution are required")
                else:
                    try:
                        with st.spinner("embedding…"):
                            kb.upsert(new_id, new_title, new_service, new_severity, new_tags, new_res)
                        st.success(f"✓ {new_id} saved and indexed")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Error: {exc}")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("##### kb stats")
        try:
            stats = fetch(
                "SELECT service, COUNT(*) AS cnt, array_agg(DISTINCT severity) AS severities "
                "FROM   incident_kb "
                "GROUP  BY service "
                "ORDER  BY cnt DESC "
                "LIMIT  8"
            )
            if stats:
                rows_html = [
                    '<div style="background:#080b0f;border:1px solid #161c26;border-radius:6px;padding:12px">'
                ]
                for s in stats:
                    svs = ", ".join(sorted(s["severities"] or []))
                    rows_html.append(
                        f'<div style="display:flex;justify-content:space-between;'
                        f'padding:4px 0;border-bottom:1px solid #0f1318">'
                        f'<span style="font-family:JetBrains Mono;font-size:11px;color:#5a6478">'
                        f'{s["service"]}</span>'
                        f'<span style="font-family:JetBrains Mono;font-size:11px;color:#2a4a70">'
                        f'{s["cnt"]} · {svs}</span>'
                        f'</div>'
                    )
                rows_html.append("</div>")
                st.markdown("".join(rows_html), unsafe_allow_html=True)
        except Exception:
            pass
