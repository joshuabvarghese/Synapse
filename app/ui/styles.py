"""
CSS styles injected into the Streamlit page.

Keeping all style rules here means changes to the visual design never
require touching application logic.
"""

STYLES = """
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

.stTextInput input, .stTextArea textarea {
    background:#0f1318!important; border:1px solid #161c26!important;
    color:#c9d1e0!important; font-family:'JetBrains Mono'!important; font-size:12px!important;
    border-radius:4px!important }
.stTextInput input:focus, .stTextArea textarea:focus { border-color:#3d7aed!important }
.stSelectbox > div > div { background:#0f1318!important; border:1px solid #161c26!important; color:#c9d1e0!important; border-radius:4px!important }

.log-wrap {
    background:#080b0f; border:1px solid #161c26; border-radius:8px;
    padding:14px 16px; max-height:380px; overflow-y:auto;
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

.res-wrap    { background:#080b0f; border:1px solid #161c26; border-radius:8px; padding:16px }
.res-section { margin-bottom:14px }
.res-h       { font-size:10px; text-transform:uppercase; letter-spacing:1.2px;
               font-family:'JetBrains Mono'; margin-bottom:6px }
.res-body    { font-size:12.5px; color:#8892a4; line-height:1.75 }
.cmd-inline  { background:#060810; border:1px solid #161c26; border-radius:3px; padding:1px 5px;
               font-family:'JetBrains Mono'; font-size:11px; color:#2d5fb0 }

.alert-bar   { background:#140a0a; border:1px solid #5a1a1a; border-radius:6px;
               padding:10px 16px; margin-bottom:14px; font-size:13px; color:#c94040;
               font-family:'JetBrains Mono' }
.status-ok   { background:#0c1a10; color:#2a7a40; font-size:11px; padding:2px 8px; border-radius:3px; font-family:'JetBrains Mono' }
.status-err  { background:#1a0c0c; color:#c94040; font-size:11px; padding:2px 8px; border-radius:3px; font-family:'JetBrains Mono' }
.status-warn { background:#1a150c; color:#b07a2d; font-size:11px; padding:2px 8px; border-radius:3px; font-family:'JetBrains Mono' }
.status-info { background:#0c1520; color:#2a5090; font-size:11px; padding:2px 8px; border-radius:3px; font-family:'JetBrains Mono' }

.timeline-wrap { background:#080b0f; border:1px solid #161c26; border-radius:8px; padding:14px 16px }
.tl-row        { display:flex; gap:14px; padding:6px 0; border-bottom:1px solid #0f1318; align-items:flex-start }
.tl-time       { font-family:'JetBrains Mono'; font-size:11px; color:#2a3040; min-width:70px; padding-top:2px }
.tl-dot        { width:8px; height:8px; border-radius:50%; margin-top:5px; flex-shrink:0 }
.tl-dot-E      { background:#c94040 } .tl-dot-W { background:#b07a2d } .tl-dot-I { background:#2a4a70 }
.tl-msg        { font-size:12px; line-height:1.6 }
.tl-svc        { font-family:'JetBrains Mono'; font-size:10px; color:#2a3040; margin-top:2px }

.mttr-chart    { background:#080b0f; border:1px solid #161c26; border-radius:8px; padding:16px }
.bar-row       { display:flex; align-items:center; gap:10px; margin-bottom:10px }
.bar-label     { font-family:'JetBrains Mono'; font-size:11px; color:#3d4557; min-width:120px; text-align:right }
.bar-bg        { flex:1; background:#0f1318; border-radius:2px; height:14px }
.bar-fill      { height:100%; border-radius:2px }
.bar-val       { font-family:'JetBrains Mono'; font-size:10px; color:#2a4a70; min-width:40px }

.kb-card       { background:#0f1318; border:1px solid #161c26; border-radius:6px; padding:12px 14px; margin-bottom:8px }
.kb-card-id    { font-family:'JetBrains Mono'; font-size:10px; color:#2a4a70; margin-bottom:4px }
.kb-card-title { font-size:13px; color:#8892a4; margin-bottom:6px }
.kb-card-meta  { font-size:11px; color:#2a3040; font-family:'JetBrains Mono' }
.kb-card-body  { font-size:11.5px; color:#3d4557; margin-top:8px; line-height:1.7; max-height:80px; overflow:hidden }

.tag           { background:#0c1520; color:#2a4a70; font-size:10px; padding:1px 5px; border-radius:3px; margin-left:4px }
.convo-user    { background:#0f1318; border:1px solid #161c26; border-radius:6px 6px 0 6px; padding:8px 12px; margin:6px 0; font-size:12px; color:#8892a4; font-family:'JetBrains Mono' }
.convo-asst    { background:#080b0f; border:1px solid #161c26; border-left:2px solid #2d5fb0; border-radius:0 6px 6px 6px; padding:8px 12px; margin:6px 0; font-size:12px; color:#7a8499; line-height:1.7 }
.refresh-badge { font-family:'JetBrains Mono'; font-size:10px; color:#2a3040; background:#0f1318; border:1px solid #161c26; padding:2px 8px; border-radius:3px; margin-left:8px }

div[data-testid="stExpander"] { background:#0f1318!important; border:1px solid #161c26!important; border-radius:6px!important }
hr { border-color:#161c26!important }
</style>
"""
