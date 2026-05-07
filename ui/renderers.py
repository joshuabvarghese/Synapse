"""
HTML rendering helpers.

All functions return raw HTML strings.  They have no Streamlit imports
and no side effects, making them independently testable.
"""
from __future__ import annotations

import re


# ── Log view ──────────────────────────────────────────────────────────────────

def render_log_wall(logs: list[dict]) -> str:
    """Render a list of log rows as a scrollable monospace wall."""
    if not logs:
        return '<div class="log-wrap"><span class="I">← trigger a scenario to populate logs</span></div>'

    rows = []
    for log in logs:
        ts      = log["ts"].strftime("%H:%M:%S") if hasattr(log["ts"], "strftime") else str(log["ts"])
        level   = log["level"]
        cls     = {"ERROR": "E", "WARN": "W"}.get(level, "I")
        rows.append(
            f'<div class="ll">'
            f'<span class="ts">{ts}</span>'
            f'<span class="{cls}">{level:<5}</span>'
            f'<span class="svc">{log["service"][:14]}</span>'
            f'<span class="msg-{cls}">{log["message"]}</span>'
            f'</div>'
        )
    return f'<div class="log-wrap">{"".join(rows)}</div>'


# ── Resolution ────────────────────────────────────────────────────────────────

_SECTIONS: dict[str, tuple[str, str]] = {
    "ROOT CAUSE":        ("#c94040", "🔍"),
    "REMEDIATION STEPS": ("#2d5fb0", "🔧"),
    "VERIFICATION":      ("#2a7a40", "✓"),
    "PREVENTION":        ("#b07a2d", "🛡"),
    "ESTIMATED MTTR":    ("#5a3070", "⏱"),
}


def render_resolution(text: str) -> str:
    """
    Parse structured agent output into colour-coded resolution sections.

    Falls back to plain prose if no section headers are found.
    """
    if not text:
        return ""

    html: list[str] = ['<div class="res-wrap">']
    found = False

    keys_re = "|".join(re.escape(k) for k in _SECTIONS)
    for header, (color, icon) in _SECTIONS.items():
        pattern = rf"\*\*{re.escape(header)}[:\*]*\*?\*?\s*(.*?)(?=\*\*(?:{keys_re})|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not match:
            continue
        content = match.group(1).strip()
        if not content:
            continue
        found = True
        content_html = re.sub(r"`([^`]+)`", r'<span class="cmd-inline">\1</span>', content)
        content_html = content_html.replace("\n", "<br>")
        html.append(
            f'<div class="res-section">'
            f'<div class="res-h" style="color:{color}">{icon} {header}</div>'
            f'<div class="res-body">{content_html}</div>'
            f'</div>'
        )

    if not found:
        prose = re.sub(r"`([^`]+)`", r'<span class="cmd-inline">\1</span>', text)
        html.append(f'<div class="res-body">{prose.replace(chr(10), "<br>")}</div>')

    html.append("</div>")
    return "\n".join(html)


# ── Timeline ──────────────────────────────────────────────────────────────────

def render_timeline(logs: list[dict]) -> str:
    """Render chronological event timeline with gap indicators."""
    if not logs:
        return (
            '<div style="color:#2a3040;font-size:13px;padding:40px 0;'
            'font-family:JetBrains Mono">← trigger a scenario to see the timeline</div>'
        )

    rows_html: list[str] = []
    prev_ts = None

    # logs arrives newest-first (DESC from DB); reverse to get chronological order
    chronological = list(reversed(logs[:60]))

    for log in chronological:
        ts    = log["ts"].strftime("%H:%M:%S") if hasattr(log["ts"], "strftime") else str(log["ts"])
        level = log["level"]
        dot   = {"ERROR": "tl-dot-E", "WARN": "tl-dot-W"}.get(level, "tl-dot-I")

        # Gap indicator — prev_ts is always earlier than log["ts"] now
        if prev_ts is not None:
            try:
                gap = (log["ts"] - prev_ts).total_seconds()
                if gap > 30:
                    rows_html.append(
                        f'<div style="text-align:center;color:#1a2030;font-family:JetBrains Mono;'
                        f'font-size:10px;padding:4px 0">··· {int(gap)}s gap ···</div>'
                    )
            except Exception:
                pass
        prev_ts = log["ts"]

        color = {"ERROR": "#c94040", "WARN": "#b07a2d"}.get(level, "#3d4557")
        rows_html.append(
            f'<div class="tl-row">'
            f'<span class="tl-time">{ts}</span>'
            f'<div class="tl-dot {dot}"></div>'
            f'<div>'
            f'<div class="tl-msg" style="color:{color}">{log["message"]}</div>'
            f'<div class="tl-svc">{level} · {log["service"]}</div>'
            f'</div></div>'
        )

    return f'<div class="timeline-wrap">{"".join(rows_html)}</div>'


# ── MTTR analytics ────────────────────────────────────────────────────────────

_SERVICE_COLORS: dict[str, str] = {
    "cassandra":  "#6a4aaa",
    "kafka":      "#4a7aaa",
    "opensearch": "#4aaa7a",
    "postgres":   "#aa4a4a",
    "redis":      "#aa7a4a",
    "nginx":      "#4a9aaa",
    "auth-svc":   "#7a4aaa",
    "checkout":   "#4a6aaa",
}


def render_mttr_bars(analytics: list[dict]) -> str:
    """Horizontal bar chart of avg MTTR per service."""
    if not analytics:
        return ""

    max_mttr = max(float(r["avg_mttr"]) for r in analytics) or 1
    bars: list[str] = ['<div class="mttr-chart">']

    for row in sorted(analytics, key=lambda r: float(r["avg_mttr"]), reverse=True):
        mttr    = float(row["avg_mttr"])
        pct     = mttr / max_mttr * 100
        svc_c   = _SERVICE_COLORS.get(row["service"], "#3d7aed")
        sev_c   = "#c94040" if row["severity"] == "P1" else "#b07a2d"
        bars.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{row["service"]}</span>'
            f'<div class="bar-bg">'
            f'  <div class="bar-fill" style="width:{pct}%;background:{svc_c};opacity:0.75"></div>'
            f'</div>'
            f'<span class="bar-val">{mttr:.1f}m</span>'
            f'<span style="font-family:JetBrains Mono;font-size:10px;color:{sev_c};min-width:24px">'
            f'{row["severity"]}</span>'
            f'<span style="font-family:JetBrains Mono;font-size:10px;color:#2a3040">({row["count"]})</span>'
            f'</div>'
        )

    bars.append("</div>")
    return "".join(bars)


def render_sparkline(trend: list[dict]) -> str:
    """30-day incident volume sparkline."""
    if not trend:
        return ""

    max_count = max((r["count"] for r in trend), default=1) or 1
    bars: list[str] = [
        '<div class="mttr-chart">'
        '<div style="display:flex;align-items:flex-end;gap:3px;height:60px">'
    ]

    for r in trend[-28:]:
        height = max(4, int(r["count"] / max_count * 52))
        color  = "#c94040" if r["count"] >= 3 else "#2d5fb0" if r["count"] >= 1 else "#161c26"
        day    = r["day"].strftime("%m/%d") if hasattr(r["day"], "strftime") else ""
        bars.append(
            f'<div title="{day}: {r["count"]} incidents" '
            f'style="flex:1;height:{height}px;background:{color};border-radius:2px 2px 0 0;opacity:0.8">'
            f'</div>'
        )

    bars.append(
        '</div>'
        '<div style="font-family:JetBrains Mono;font-size:10px;color:#2a3040;'
        'margin-top:6px;display:flex;justify-content:space-between">'
        '<span>30d ago</span><span>today</span></div>'
        '</div>'
    )
    return "".join(bars)


def render_heatmap(analytics: list[dict]) -> str:
    """Service × severity MTTR heatmap."""
    if not analytics:
        return ""

    services   = sorted({r["service"] for r in analytics})
    severities = ["P1", "P2", "P3"]
    heat_data  = {(r["service"], r["severity"]): float(r["avg_mttr"]) for r in analytics}
    heat_max   = max(heat_data.values()) if heat_data else 1

    cells: list[str] = ['<div class="mttr-chart">']
    # Header row
    cells.append(
        '<div style="display:grid;grid-template-columns:100px repeat(3,80px);gap:4px;margin-bottom:4px">'
        '<span></span>'
        + "".join(
            f'<span style="font-family:JetBrains Mono;font-size:10px;color:#3d4557;text-align:center">'
            f'{s}</span>'
            for s in severities
        )
        + "</div>"
    )

    for svc in services:
        cells.append(
            '<div style="display:grid;grid-template-columns:100px repeat(3,80px);gap:4px;margin-bottom:4px">'
            f'<span style="font-family:JetBrains Mono;font-size:11px;color:#5a6478;padding-top:6px">{svc}</span>'
        )
        for sev in severities:
            val = heat_data.get((svc, sev))
            if val is not None:
                intensity = val / heat_max
                red = int(40 + 150 * intensity)
                cells.append(
                    f'<div style="background:rgb({red},20,20);border-radius:3px;padding:5px 4px;'
                    f'text-align:center;font-family:JetBrains Mono;font-size:10px;color:#c9d1e0">'
                    f'{val:.0f}m</div>'
                )
            else:
                cells.append(
                    '<div style="background:#0f1318;border:1px solid #161c26;border-radius:3px;'
                    'padding:5px 4px;text-align:center;font-family:JetBrains Mono;'
                    'font-size:10px;color:#1a2030">—</div>'
                )
        cells.append("</div>")

    cells.append("</div>")
    return "".join(cells)


# ── KB cards ──────────────────────────────────────────────────────────────────

def render_kb_card(entry: dict) -> str:
    """Single KB card with metadata and a truncated resolution preview."""
    sev_color = {"P1": "#8a1a1a", "P2": "#8a5a1a"}.get(entry.get("severity", "P2"), "#1a4a8a")
    tags_html = "".join(f'<span class="tag">{t}</span>' for t in (entry.get("tags") or []))
    score_html = (
        f' · score={float(entry.get("similarity", 0)):.3f}'
        if "similarity" in entry
        else ""
    )
    preview = (entry.get("resolution") or "")[:120].replace("\n", " ")
    return (
        f'<div class="kb-card">'
        f'<div class="kb-card-id">{entry["inc_id"]}</div>'
        f'<div class="kb-card-title">{entry["title"]}</div>'
        f'<div class="kb-card-meta">'
        f'<span style="color:{sev_color}">{entry.get("severity", "")}</span>'
        f' · {entry.get("service", "")}{score_html}{tags_html}'
        f'</div>'
        f'<div class="kb-card-body">{preview}…</div>'
        f'</div>'
    )
