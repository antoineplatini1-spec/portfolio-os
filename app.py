"""Point d'entrée principal — Dashboard Streamlit."""

import sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from portfolio.manager import PortfolioManager
from ui import (
    page_dashboard, page_positions, page_history,
    page_analysis, page_screener, page_backtest, page_report, page_lexique,
)
from ui.theme import inject

st.set_page_config(
    page_title="Zentry · Portfolio OS",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject()

# ── Authentification ───────────────────────────────────────────────────────────
def _check_auth() -> bool:
    try:
        pwd = st.secrets.get("auth", {}).get("password", "")
    except Exception:
        pwd = os.environ.get("APP_PASSWORD", "")
    if not pwd:
        return True
    if st.session_state.get("authenticated"):
        return True
    st.markdown("## 🔐 Zentry")
    entered = st.text_input("Mot de passe", type="password", key="pwd_input")
    if st.button("Connexion", type="primary"):
        if entered == pwd:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    return False

if not _check_auth():
    st.stop()

# ── Scheduler ─────────────────────────────────────────────────────────────────
if os.environ.get("RAILWAY_ENVIRONMENT") is not None:
    try:
        import scheduler as sched
        if not sched.is_running():
            sched.start()
    except ImportError:
        pass

# ── PortfolioManager ──────────────────────────────────────────────────────────
if "pm" not in st.session_state:
    st.session_state["pm"]       = PortfolioManager()
    st.session_state["pm_mtime"] = st.session_state["pm"].file_mtime

pm: PortfolioManager = st.session_state["pm"]

current_mtime = pm.file_mtime
if current_mtime != st.session_state.get("pm_mtime", 0):
    pm.reload()
    st.session_state["pm_mtime"] = current_mtime

# ── SIDEBAR — Métriques ────────────────────────────────────────────────────────
st.sidebar.markdown(
    """
    <div style="
        padding: 1.25rem 0.25rem 1.5rem;
        border-bottom: 1px solid #1e2d45;
        margin-bottom: 1rem;
    ">
        <div style="
            font: 700 0.58rem/1 'JetBrains Mono', monospace;
            color: #445470;
            letter-spacing: 0.2em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        ">Portfolio OS</div>
        <div style="
            font: 700 1.55rem/1 'Inter', sans-serif;
            color: #d6e0f0;
            letter-spacing: -0.04em;
        ">ZENTRY<span style="color:#2dd4bf;">.</span></div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.metric("Valeur totale",      f"{pm.total_value:,.2f} €")
st.sidebar.metric("Cash dispo",         f"{pm.operational_cash:,.2f} €")
st.sidebar.metric("Exposition",         f"{pm.exposure_pct * 100:.1f}%")
st.sidebar.metric("Positions ouvertes", len(pm.open_positions))
st.sidebar.caption(f"Réserve : {pm.reserve_cash:,.2f} €")

st.sidebar.markdown(
    "<div style='height:1px;background:#1e2d45;margin:0.6rem 0;'></div>",
    unsafe_allow_html=True,
)

if st.sidebar.button("🔄  Synchroniser", use_container_width=True,
                     help="Recharge l'état depuis le disque"):
    pm.reload()
    st.session_state["pm_mtime"] = pm.file_mtime
    st.rerun()

try:
    import scheduler as sched
    if sched.is_running():
        st.sidebar.caption(f"⏱ Prochain scan : {sched.next_run()}")
except Exception:
    pass

st.sidebar.markdown(
    "<div style='height:1px;background:#1e2d45;margin:0.6rem 0 0.5rem;'></div>",
    unsafe_allow_html=True,
)
st.sidebar.markdown(
    """
    <div style="padding:0 0.25rem;">
        <div style="font:600 0.62rem/1 'Inter',sans-serif; color:#445470;
                    letter-spacing:0.05em; margin-bottom:0.3rem;">🌐 Accès distant</div>
        <a href="https://dashboard.zentry.uk" target="_blank" style="
            display:block;font:500 0.78rem/1.6 'Inter',sans-serif;
            color:#2dd4bf; text-decoration:none;
        ">dashboard.zentry.uk</a>
        <a href="https://portfolio-os-wogyzautrgj4zbakdmehk5.streamlit.app" target="_blank" style="
            display:block;font:400 0.7rem/1.6 'Inter',sans-serif;
            color:#445470; text-decoration:none;
        ">streamlit backup</a>
    </div>
    """,
    unsafe_allow_html=True,
)
st.sidebar.caption("v0.1 · paper trading · yfinance")

# ── NAVIGATION HORIZONTALE (tabs) ─────────────────────────────────────────────
tab_dashboard, tab_positions, tab_history, \
tab_analysis, tab_screener, tab_backtest, tab_report, tab_lexique = st.tabs([
    "📊  Dashboard",
    "🎯  Positions",
    "📜  Historique",
    "🔍  Analyse",
    "📡  Screener",
    "⏱  Backtest",
    "📰  Rapport",
    "📖  Lexique",
])

with tab_dashboard:
    page_dashboard.render(pm)

with tab_positions:
    page_positions.render(pm)

with tab_history:
    page_history.render(pm)

with tab_analysis:
    page_analysis.render(pm)

with tab_screener:
    page_screener.render(pm)

with tab_backtest:
    page_backtest.render(pm)

with tab_report:
    page_report.render(pm)

with tab_lexique:
    page_lexique.render(pm)
