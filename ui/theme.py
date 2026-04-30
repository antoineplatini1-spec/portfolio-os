"""
Thème clair — fond blanc chaud, couleurs reposantes, contraste élevé.
Palette : blanc ivoire · ardoise · sauge profond · bleu doux
"""

CYBERPUNK_CSS = """
<style>
/* ── Google Fonts ─────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&family=DM+Mono:wght@400;500&family=DM+Serif+Display:ital@0;1&display=swap');

/* ── Variables ────────────────────────────────────────────────── */
:root {
    --bg-base:      #faf9f6;
    --bg-surface:   #f2f0eb;
    --bg-raised:    #ffffff;
    --border:       #dedad2;
    --border-dark:  #c8c3b8;

    --sage:         #3d7a65;
    --sage-light:   #3d7a6512;
    --sage-mid:     #3d7a6525;
    --blue:         #3d5fa0;
    --blue-light:   #3d5fa010;

    --red:          #b84040;
    --red-light:    #b8404010;
    --green:        #2e7a52;
    --green-light:  #2e7a5210;
    --amber:        #8a6420;

    --text:         #1e1c18;
    --text-mid:     #4a4740;
    --text-muted:   #8a8780;
}

/* ── Base ─────────────────────────────────────────────────────── */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stApp"],
[data-testid="stMain"] > div,
[data-testid="block-container"] {
    background-color: var(--bg-base) !important;
    font-family: 'DM Sans', sans-serif !important;
    color: var(--text) !important;
}

/* ── Sidebar ──────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: var(--bg-surface) !important;
    border-right: 1px solid var(--border) !important;
}

[data-testid="stSidebar"] * {
    font-family: 'DM Sans', sans-serif !important;
}

/* ── Titres ───────────────────────────────────────────────────── */
h1 {
    font-family: 'DM Serif Display', serif !important;
    font-weight: 400 !important;
    font-size: 1.9rem !important;
    color: var(--text) !important;
    border-bottom: 1px solid var(--border) !important;
    padding-bottom: 0.6rem !important;
    margin-bottom: 1.5rem !important;
    letter-spacing: -0.01em !important;
}

h2 {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.1em !important;
    color: var(--text-muted) !important;
    text-transform: uppercase !important;
    margin-bottom: 0.8rem !important;
}

h3 {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.95rem !important;
    color: var(--sage) !important;
}

p, li, span, div {
    color: var(--text) !important;
}

/* ── Métriques ────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background-color: var(--bg-raised) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    padding: 1rem 1.2rem !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
}

[data-testid="stMetricLabel"] > div {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.68rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: var(--text-muted) !important;
}

[data-testid="stMetricValue"] {
    font-family: 'DM Mono', monospace !important;
    font-size: 1.35rem !important;
    font-weight: 500 !important;
    color: var(--text) !important;
}

[data-testid="stMetricDelta"] svg { display: none !important; }

[data-testid="stMetricDelta"] > div {
    font-family: 'DM Mono', monospace !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
}

/* ── Boutons ──────────────────────────────────────────────────── */
[data-testid="stButton"] > button {
    background-color: var(--bg-raised) !important;
    border: 1px solid var(--border-dark) !important;
    color: var(--text-mid) !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    border-radius: 6px !important;
    padding: 0.45rem 1.1rem !important;
    transition: all 0.15s ease !important;
    font-size: 0.87rem !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.06) !important;
}

[data-testid="stButton"] > button:hover {
    border-color: var(--sage) !important;
    color: var(--sage) !important;
    background-color: var(--sage-light) !important;
    box-shadow: 0 1px 4px rgba(61,122,101,0.15) !important;
}

[data-testid="stButton"] > button[kind="primary"] {
    background-color: var(--sage) !important;
    border-color: var(--sage) !important;
    color: #ffffff !important;
    box-shadow: 0 2px 6px rgba(61,122,101,0.25) !important;
}

[data-testid="stButton"] > button[kind="primary"]:hover {
    background-color: #2e6352 !important;
    box-shadow: 0 3px 10px rgba(61,122,101,0.3) !important;
}

/* ── Inputs ───────────────────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input {
    background-color: var(--bg-raised) !important;
    border: 1px solid var(--border-dark) !important;
    color: var(--text) !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.87rem !important;
    border-radius: 6px !important;
}

[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus {
    border-color: var(--sage) !important;
    box-shadow: 0 0 0 2px var(--sage-mid) !important;
    outline: none !important;
}

[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label,
[data-testid="stDateInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stMultiSelect"] label,
[data-testid="stSlider"] label {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    color: var(--text-muted) !important;
}

/* Select */
[data-baseweb="select"] > div {
    background-color: var(--bg-raised) !important;
    border-color: var(--border-dark) !important;
    border-radius: 6px !important;
    color: var(--text) !important;
    font-family: 'DM Sans', sans-serif !important;
}

/* Slider track */
[data-baseweb="slider"] [data-testid="stSlider"] div[role="slider"] {
    background-color: var(--sage) !important;
}

/* ── Dataframes ───────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    overflow: hidden !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
}

/* ── Alertes ──────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 6px !important;
    border-left-width: 3px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.88rem !important;
    font-weight: 400 !important;
}

/* info */
[data-testid="stAlert"][data-baseweb="notification"][kind="info"] {
    background-color: var(--blue-light) !important;
    border-left-color: var(--blue) !important;
}

/* success */
[data-testid="stAlert"][data-baseweb="notification"][kind="success"] {
    background-color: var(--green-light) !important;
    border-left-color: var(--green) !important;
}

/* warning */
[data-testid="stAlert"][data-baseweb="notification"][kind="warning"] {
    background-color: #8a642010 !important;
    border-left-color: var(--amber) !important;
}

/* error */
[data-testid="stAlert"][data-baseweb="notification"][kind="error"] {
    background-color: var(--red-light) !important;
    border-left-color: var(--red) !important;
}

/* ── Expanders ────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background-color: var(--bg-raised) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
}

[data-testid="stExpander"] summary {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: var(--text-muted) !important;
}

/* ── Progress bars ────────────────────────────────────────────── */
[data-testid="stProgress"] > div > div {
    background-color: var(--border) !important;
    border-radius: 3px !important;
}

[data-testid="stProgress"] > div > div > div {
    background-color: var(--sage) !important;
    border-radius: 3px !important;
}

/* ── Radio ────────────────────────────────────────────────────── */
[data-testid="stRadio"] label {
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    color: var(--text-mid) !important;
}

[data-testid="stRadio"] label:has(input:checked) {
    color: var(--sage) !important;
    font-weight: 600 !important;
}

/* ── Checkbox ────────────────────────────────────────────────── */
[data-testid="stCheckbox"] label {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.87rem !important;
    color: var(--text-mid) !important;
}

/* ── Séparateurs ─────────────────────────────────────────────── */
hr {
    border: none !important;
    border-top: 1px solid var(--border) !important;
    margin: 1.5rem 0 !important;
}

/* ── Caption ─────────────────────────────────────────────────── */
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
    font-family: 'DM Mono', monospace !important;
    font-size: 0.72rem !important;
    color: var(--text-muted) !important;
}

/* ── Multiselect tags ────────────────────────────────────────── */
[data-baseweb="tag"] {
    background-color: var(--sage-light) !important;
    border: 1px solid var(--sage) !important;
    border-radius: 4px !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 0.74rem !important;
    color: var(--sage) !important;
}

/* ── Markdown texte ──────────────────────────────────────────── */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.9rem !important;
    line-height: 1.65 !important;
    color: var(--text-mid) !important;
}

/* ── Scrollbar ───────────────────────────────────────────────── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: var(--bg-surface); }
::-webkit-scrollbar-thumb { background: var(--border-dark); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: var(--sage); }

/* ── Header ──────────────────────────────────────────────────── */
[data-testid="stHeader"] {
    background-color: var(--bg-base) !important;
    border-bottom: 1px solid var(--border) !important;
}

/* ── Sidebar métriques ───────────────────────────────────────── */
[data-testid="stSidebar"] [data-testid="stMetric"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid var(--border) !important;
    border-radius: 0 !important;
    padding: 0.65rem 0 !important;
    box-shadow: none !important;
}

[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: var(--text) !important;
}
</style>
"""


def inject() -> None:
    import streamlit as st
    st.markdown(CYBERPUNK_CSS, unsafe_allow_html=True)
