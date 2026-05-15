"""
Thème Abyss Finance — dark navy · teal · soft contrasts.
Exporte : inject(), plotly_layout(), COLORS
"""

import streamlit as st

# ── Palette ────────────────────────────────────────────────────────────────
COLORS = {
    # Backgrounds
    "bg":       "#0d1117",
    "surf1":    "#13192a",
    "surf2":    "#192235",
    "surf3":    "#1e2a40",
    "surf4":    "#263652",
    # Borders
    "border":   "#1e2d45",
    "border2":  "#2a3d5c",
    # Text
    "text1":    "#d6e0f0",
    "text2":    "#8097b5",
    "text3":    "#445470",
    # Accent — teal
    "accent":   "#2dd4bf",
    "accent2":  "#14b8a6",
    # Finance colors
    "up":       "#34d399",
    "up_bg":    "rgba(52,211,153,0.10)",
    "down":     "#fb7185",
    "down_bg":  "rgba(251,113,133,0.10)",
    "amber":    "#fbbf24",
    "purple":   "#a78bfa",
    "blue":     "#60a5fa",
}

C = COLORS   # alias court


# ── Plotly layout helper ───────────────────────────────────────────────────
def plotly_layout(height: int = 300, title: str = "", **overrides) -> dict:
    """
    Retourne un dict de layout Plotly cohérent avec le thème.
    Usage : fig.update_layout(**plotly_layout(height=280, title="Mon graphe"))
    """
    base: dict = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=C["surf1"],
        font=dict(
            family="'Inter', 'DM Sans', system-ui, sans-serif",
            color=C["text2"],
            size=12,
        ),
        xaxis=dict(
            gridcolor=C["border"],
            zerolinecolor=C["border"],
            linecolor=C["border"],
            tickfont=dict(color=C["text3"], size=11),
            showspikes=True, spikecolor=C["border2"],
            spikethickness=1, spikedash="dot",
        ),
        yaxis=dict(
            gridcolor=C["border"],
            zerolinecolor=C["border"],
            linecolor=C["border"],
            tickfont=dict(color=C["text3"], size=11),
        ),
        hoverlabel=dict(
            bgcolor=C["surf3"],
            font_color=C["text1"],
            bordercolor=C["border2"],
            font_size=12,
            font_family="'Inter', 'DM Sans', sans-serif",
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(color=C["text2"], size=11),
            bordercolor=C["border"],
            borderwidth=1,
        ),
        margin=dict(t=50 if title else 20, b=30, l=10, r=10),
        height=height,
        template="plotly_dark",
    )
    if title:
        base["title"] = dict(
            text=title,
            font=dict(
                color=C["text1"], size=13,
                family="'Inter', 'DM Sans', sans-serif",
            ),
            x=0, xanchor="left", pad=dict(l=0),
        )
    # Deep merge overrides
    for k, v in overrides.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


# ── CSS ────────────────────────────────────────────────────────────────────
_CSS = """
<style>

/* ══════════════════════════════════════════════════════
   FONTS
══════════════════════════════════════════════════════ */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ══════════════════════════════════════════════════════
   ROOT VARIABLES
══════════════════════════════════════════════════════ */
:root {
    --bg:       #0d1117;
    --surf1:    #13192a;
    --surf2:    #192235;
    --surf3:    #1e2a40;
    --surf4:    #263652;
    --border:   #1e2d45;
    --border2:  #2a3d5c;

    --text1:    #d6e0f0;
    --text2:    #8097b5;
    --text3:    #445470;

    --accent:   #2dd4bf;
    --accent2:  #14b8a6;

    --up:       #34d399;
    --up-bg:    rgba(52,211,153,0.10);
    --down:     #fb7185;
    --down-bg:  rgba(251,113,133,0.10);
    --amber:    #fbbf24;

    --radius:    12px;
    --radius-sm: 8px;
    --radius-xs: 5px;
    --font:     'Inter', 'DM Sans', system-ui, sans-serif;
    --mono:     'JetBrains Mono', 'DM Mono', monospace;

    --shadow:   0 4px 24px rgba(0,0,0,0.35);
    --shadow-sm:0 2px 8px  rgba(0,0,0,0.25);
}

/* ══════════════════════════════════════════════════════
   GLOBAL BASE
══════════════════════════════════════════════════════ */
html, body {
    background: var(--bg) !important;
    font-family: var(--font) !important;
    color: var(--text1) !important;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}

[data-testid="stAppViewContainer"],
[data-testid="stApp"],
[data-testid="stMain"],
[data-testid="stMain"] > div {
    background: var(--bg) !important;
}

.block-container,
[data-testid="block-container"] {
    background: var(--bg) !important;
    padding-top: 2rem !important;
    padding-left: 2.5rem !important;
    padding-right: 2.5rem !important;
    max-width: 1480px !important;
}

/* ══════════════════════════════════════════════════════
   SIDEBAR
══════════════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background: var(--surf1) !important;
    border-right: 1px solid var(--border) !important;
}

[data-testid="stSidebar"] * {
    font-family: var(--font) !important;
}

/* Nav section label */
[data-testid="stSidebar"] .stMarkdown p {
    color: var(--text3) !important;
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
}

/* Radio nav items */
[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    gap: 2px !important;
    display: flex !important;
    flex-direction: column !important;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label {
    border-radius: var(--radius-sm) !important;
    padding: 0.55rem 0.85rem !important;
    transition: all 0.15s ease !important;
    color: var(--text2) !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    border: 1px solid transparent !important;
    margin: 0 !important;
    display: flex !important;
    align-items: center !important;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: var(--surf3) !important;
    color: var(--text1) !important;
    border-color: var(--border) !important;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: rgba(45,212,191,0.12) !important;
    color: var(--accent) !important;
    border-color: rgba(45,212,191,0.25) !important;
    font-weight: 600 !important;
}

/* Hide radio input circles */
[data-testid="stSidebar"] [data-testid="stRadio"] input[type="radio"] {
    display: none !important;
}

/* Sidebar metrics */
[data-testid="stSidebar"] [data-testid="stMetric"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid var(--border) !important;
    border-radius: 0 !important;
    padding: 0.6rem 0 !important;
    box-shadow: none !important;
}

[data-testid="stSidebar"] [data-testid="stMetricLabel"] > div {
    color: var(--text3) !important;
    font-size: 0.65rem !important;
}

[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: var(--text1) !important;
    font-size: 1rem !important;
    font-family: var(--mono) !important;
}

/* Sidebar button */
[data-testid="stSidebar"] .stButton > button {
    width: 100% !important;
    background: var(--surf2) !important;
    border-color: var(--border) !important;
    color: var(--text2) !important;
    font-size: 0.8rem !important;
}

[data-testid="stSidebar"] .stButton > button:hover {
    background: var(--surf3) !important;
    border-color: var(--accent) !important;
    color: var(--accent) !important;
}

[data-testid="stSidebar"] hr {
    border-color: var(--border) !important;
    margin: 0.75rem 0 !important;
}

[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
    color: var(--text3) !important;
    font-size: 0.7rem !important;
    font-family: var(--mono) !important;
}

/* ══════════════════════════════════════════════════════
   TYPOGRAPHY
══════════════════════════════════════════════════════ */
h1 {
    font-family: var(--font) !important;
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.03em !important;
    color: var(--text1) !important;
    padding-bottom: 0.75rem !important;
    border-bottom: 1px solid var(--border) !important;
    margin-bottom: 1.75rem !important;
}

h2 {
    font-family: var(--font) !important;
    font-size: 0.65rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    color: var(--text3) !important;
    margin-bottom: 0.75rem !important;
}

h3 {
    font-family: var(--font) !important;
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    color: var(--text1) !important;
    letter-spacing: -0.01em !important;
}

p, li {
    color: var(--text2) !important;
    font-size: 0.9rem !important;
    line-height: 1.6 !important;
}

strong, b {
    color: var(--text1) !important;
    font-weight: 600 !important;
}

hr {
    border: none !important;
    border-top: 1px solid var(--border) !important;
    margin: 1.5rem 0 !important;
}

/* ══════════════════════════════════════════════════════
   METRIC CARDS
══════════════════════════════════════════════════════ */
[data-testid="stMetric"] {
    background: var(--surf1) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1rem 1.25rem !important;
    box-shadow: var(--shadow-sm) !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
    position: relative !important;
    overflow: hidden !important;
}

[data-testid="stMetric"]::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--accent), transparent);
    opacity: 0;
    transition: opacity 0.2s;
}

[data-testid="stMetric"]:hover {
    border-color: var(--border2) !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4) !important;
}

[data-testid="stMetric"]:hover::before {
    opacity: 1;
}

[data-testid="stMetricLabel"] > div {
    font-size: 0.65rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.12em !important;
    text-transform: uppercase !important;
    color: var(--text3) !important;
    font-family: var(--font) !important;
}

[data-testid="stMetricValue"] {
    font-size: 1.45rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.025em !important;
    color: var(--text1) !important;
    font-family: var(--mono) !important;
    line-height: 1.2 !important;
}

[data-testid="stMetricDelta"] svg { display: none !important; }

[data-testid="stMetricDelta"] > div {
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    font-family: var(--mono) !important;
}

/* ══════════════════════════════════════════════════════
   BUTTONS
══════════════════════════════════════════════════════ */
.stButton > button {
    background: var(--surf2) !important;
    color: var(--text2) !important;
    border: 1px solid var(--border2) !important;
    border-radius: var(--radius-sm) !important;
    font-family: var(--font) !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    padding: 0.45rem 1rem !important;
    letter-spacing: 0.01em !important;
    transition: all 0.15s ease !important;
    box-shadow: none !important;
    cursor: pointer !important;
}

.stButton > button:hover {
    background: var(--surf3) !important;
    border-color: var(--accent) !important;
    color: var(--accent) !important;
    box-shadow: 0 0 0 1px rgba(45,212,191,0.15) !important;
}

.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--accent), var(--accent2)) !important;
    color: var(--bg) !important;
    border-color: transparent !important;
    font-weight: 700 !important;
    box-shadow: 0 2px 12px rgba(45,212,191,0.3) !important;
}

.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 20px rgba(45,212,191,0.4) !important;
    transform: translateY(-1px) !important;
}

/* ══════════════════════════════════════════════════════
   TABS
══════════════════════════════════════════════════════ */
.stTabs [data-baseweb="tab-list"] {
    background: var(--surf1) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 4px !important;
    gap: 3px !important;
    margin-bottom: 1.5rem !important;
}

.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: var(--radius-xs) !important;
    color: var(--text3) !important;
    font-family: var(--font) !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    padding: 0.4rem 1.1rem !important;
    border: 1px solid transparent !important;
    transition: all 0.15s ease !important;
    letter-spacing: 0.01em !important;
}

.stTabs [data-baseweb="tab"]:hover {
    color: var(--text2) !important;
    background: var(--surf2) !important;
}

.stTabs [aria-selected="true"] {
    background: var(--surf3) !important;
    color: var(--text1) !important;
    border-color: var(--border2) !important;
    font-weight: 600 !important;
}

.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {
    display: none !important;
}

/* ══════════════════════════════════════════════════════
   EXPANDERS
══════════════════════════════════════════════════════ */
[data-testid="stExpander"] {
    background: var(--surf1) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    margin-bottom: 0.5rem !important;
    box-shadow: var(--shadow-sm) !important;
    overflow: hidden !important;
    transition: border-color 0.2s !important;
}

[data-testid="stExpander"]:hover {
    border-color: var(--border2) !important;
}

[data-testid="stExpander"] summary {
    color: var(--text1) !important;
    font-family: var(--font) !important;
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    padding: 0.85rem 1.1rem !important;
    transition: background 0.15s !important;
    border-radius: var(--radius) !important;
}

[data-testid="stExpander"] summary:hover {
    background: var(--surf2) !important;
}

[data-testid="stExpander"] summary svg {
    color: var(--text3) !important;
}

[data-testid="stExpander"] > div > div {
    background: var(--surf1) !important;
    padding: 0.5rem 1rem 1rem !important;
    border-top: 1px solid var(--border) !important;
}

/* ══════════════════════════════════════════════════════
   DATAFRAMES
══════════════════════════════════════════════════════ */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-sm) !important;
}

/* iframe inside dataframe */
[data-testid="stDataFrame"] iframe {
    border-radius: var(--radius) !important;
}

/* ══════════════════════════════════════════════════════
   INPUTS
══════════════════════════════════════════════════════ */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input {
    background: var(--surf2) !important;
    border: 1px solid var(--border2) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text1) !important;
    font-family: var(--mono) !important;
    font-size: 0.88rem !important;
    padding: 0.45rem 0.75rem !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}

[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px rgba(45,212,191,0.15) !important;
    outline: none !important;
    background: var(--surf3) !important;
}

[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label,
[data-testid="stDateInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stMultiSelect"] label,
[data-testid="stSlider"] label {
    font-family: var(--font) !important;
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: var(--text3) !important;
}

/* Selectbox / Multiselect */
[data-baseweb="select"] > div {
    background: var(--surf2) !important;
    border-color: var(--border2) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text1) !important;
    font-family: var(--font) !important;
    transition: border-color 0.15s !important;
}

[data-baseweb="select"] > div:focus-within {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px rgba(45,212,191,0.15) !important;
}

/* Dropdown menu */
[data-baseweb="popover"] {
    background: var(--surf3) !important;
    border: 1px solid var(--border2) !important;
    border-radius: var(--radius-sm) !important;
    box-shadow: var(--shadow) !important;
}

[data-baseweb="menu"] {
    background: var(--surf3) !important;
}

[role="option"]:hover {
    background: var(--surf4) !important;
}

/* Tag (multiselect badge) */
[data-baseweb="tag"] {
    background: rgba(45,212,191,0.12) !important;
    border: 1px solid rgba(45,212,191,0.25) !important;
    border-radius: 4px !important;
    font-family: var(--mono) !important;
    font-size: 0.75rem !important;
    color: var(--accent) !important;
}

/* ══════════════════════════════════════════════════════
   PROGRESS BAR
══════════════════════════════════════════════════════ */
[data-testid="stProgress"] {
    margin: 0.5rem 0 !important;
}

[data-testid="stProgress"] > div {
    background: var(--surf3) !important;
    border-radius: 999px !important;
    height: 6px !important;
    border: 1px solid var(--border) !important;
    overflow: hidden !important;
}

[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, var(--accent2), var(--accent)) !important;
    border-radius: 999px !important;
    height: 100% !important;
    box-shadow: 0 0 8px rgba(45,212,191,0.4) !important;
}

/* ══════════════════════════════════════════════════════
   ALERTS
══════════════════════════════════════════════════════ */
[data-testid="stAlert"] {
    border-radius: var(--radius-sm) !important;
    border: none !important;
    font-family: var(--font) !important;
    font-size: 0.875rem !important;
    padding: 0.75rem 1rem !important;
}

/* Success */
.stSuccess, [data-baseweb="notification"][kind="positive"] {
    background: var(--up-bg) !important;
    border: 1px solid rgba(52,211,153,0.2) !important;
    color: var(--up) !important;
}

/* Error */
.stError, [data-baseweb="notification"][kind="negative"] {
    background: var(--down-bg) !important;
    border: 1px solid rgba(251,113,133,0.2) !important;
    color: var(--down) !important;
}

/* Info */
.stInfo, [data-baseweb="notification"][kind="info"] {
    background: rgba(45,212,191,0.07) !important;
    border: 1px solid rgba(45,212,191,0.18) !important;
    color: var(--text2) !important;
}

/* Warning */
.stWarning, [data-baseweb="notification"][kind="warning"] {
    background: rgba(251,191,36,0.07) !important;
    border: 1px solid rgba(251,191,36,0.2) !important;
    color: var(--amber) !important;
}

/* ══════════════════════════════════════════════════════
   PLOTLY CHART CONTAINER
══════════════════════════════════════════════════════ */
[data-testid="stPlotlyChart"] {
    border-radius: var(--radius) !important;
    overflow: hidden !important;
    border: 1px solid var(--border) !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ══════════════════════════════════════════════════════
   CAPTION / SMALL TEXT
══════════════════════════════════════════════════════ */
[data-testid="stCaptionContainer"] p,
.stCaption p {
    font-family: var(--mono) !important;
    font-size: 0.72rem !important;
    color: var(--text3) !important;
    line-height: 1.5 !important;
}

/* ══════════════════════════════════════════════════════
   MARKDOWN
══════════════════════════════════════════════════════ */
[data-testid="stMarkdownContainer"] p {
    font-family: var(--font) !important;
    color: var(--text2) !important;
    font-size: 0.9rem !important;
}

[data-testid="stMarkdownContainer"] a {
    color: var(--accent) !important;
    text-decoration: none !important;
    border-bottom: 1px solid rgba(45,212,191,0.3) !important;
    transition: border-color 0.15s !important;
}

[data-testid="stMarkdownContainer"] a:hover {
    border-color: var(--accent) !important;
}

/* Code inline */
code {
    background: var(--surf3) !important;
    color: var(--accent) !important;
    border-radius: 3px !important;
    padding: 0.1em 0.35em !important;
    font-family: var(--mono) !important;
    font-size: 0.82em !important;
    border: 1px solid var(--border2) !important;
}

/* ══════════════════════════════════════════════════════
   RADIO (global)
══════════════════════════════════════════════════════ */
[data-testid="stRadio"] label {
    font-family: var(--font) !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: var(--text2) !important;
    cursor: pointer !important;
}

/* ══════════════════════════════════════════════════════
   CHECKBOX
══════════════════════════════════════════════════════ */
[data-testid="stCheckbox"] label {
    font-family: var(--font) !important;
    font-size: 0.875rem !important;
    color: var(--text2) !important;
}

/* ══════════════════════════════════════════════════════
   NUMBER INPUT ARROWS
══════════════════════════════════════════════════════ */
[data-testid="stNumberInput"] button {
    background: var(--surf3) !important;
    border-color: var(--border2) !important;
    color: var(--text2) !important;
}

[data-testid="stNumberInput"] button:hover {
    background: var(--surf4) !important;
    color: var(--accent) !important;
}

/* ══════════════════════════════════════════════════════
   SCROLLBAR
══════════════════════════════════════════════════════ */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--surf4); border-radius: 999px; }
::-webkit-scrollbar-thumb:hover { background: var(--text3); }

/* ══════════════════════════════════════════════════════
   HEADER / FOOTER (hide Streamlit chrome)
══════════════════════════════════════════════════════ */
[data-testid="stHeader"]  { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
footer                    { display: none !important; }
#MainMenu                 { display: none !important; }

/* Remove top padding now that header is gone */
.block-container { padding-top: 1rem !important; }

/* ══════════════════════════════════════════════════════
   TOOLTIP
══════════════════════════════════════════════════════ */
[data-baseweb="tooltip"] {
    background: var(--surf3) !important;
    border: 1px solid var(--border2) !important;
    border-radius: var(--radius-xs) !important;
    font-family: var(--font) !important;
    font-size: 0.8rem !important;
    color: var(--text1) !important;
}

/* ══════════════════════════════════════════════════════
   SPINNER
══════════════════════════════════════════════════════ */
[data-testid="stSpinner"] {
    color: var(--accent) !important;
}

</style>
"""


def inject() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
