"""Point d'entrée principal — Dashboard Streamlit."""

import sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from portfolio.manager import PortfolioManager
from ui import page_dashboard, page_analysis, page_screener, page_history, page_backtest
from ui.theme import inject

st.set_page_config(
    page_title="Portfolio OS",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject()

# ── Authentification ──────────────────────────────────────────────
def _check_auth() -> bool:
    """Retourne True si l'utilisateur est authentifié (ou si pas de mot de passe configuré)."""
    try:
        pwd = st.secrets.get("auth", {}).get("password", "")
    except Exception:
        pwd = os.environ.get("APP_PASSWORD", "")

    if not pwd:
        return True  # pas de mot de passe configuré → accès libre

    if st.session_state.get("authenticated"):
        return True

    st.markdown("## 🔐 Portfolio OS")
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

# ── Scheduler in-process (cloud) ──────────────────────────────────
# Sur Railway, le cron job railway.toml prend le dessus.
# En local ou si pas de cron Railway, APScheduler prend le relais.
if os.environ.get("RAILWAY_ENVIRONMENT") is None:
    # Local ou autre cloud sans cron natif
    try:
        import scheduler as sched
        if not sched.is_running():
            sched.start()
    except ImportError:
        pass

# ── PortfolioManager : rechargement auto si le fichier a changé ───
if "pm" not in st.session_state:
    st.session_state["pm"] = PortfolioManager()
    st.session_state["pm_mtime"] = st.session_state["pm"].file_mtime

pm: PortfolioManager = st.session_state["pm"]

current_mtime = pm.file_mtime
if current_mtime != st.session_state.get("pm_mtime", 0):
    pm.reload()
    st.session_state["pm_mtime"] = current_mtime

# ── Navigation ────────────────────────────────────────────────────
st.sidebar.markdown("# PORTFOLIO OS")
st.sidebar.markdown("---")

pages = {
    "Dashboard":  page_dashboard,
    "Analyse":    page_analysis,
    "Screener":   page_screener,
    "Historique": page_history,
    "Backtest":   page_backtest,
}

page_name = st.sidebar.radio("Navigation", list(pages.keys()))

# ── Métriques rapides sidebar ─────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.metric("Valeur totale",      f"{pm.total_value:,.2f} €")
st.sidebar.metric("Cash dispo",         f"{pm.operational_cash:,.2f} €")
st.sidebar.metric("Exposition",         f"{pm.exposure_pct*100:.1f}%")
st.sidebar.metric("Positions ouvertes", len(pm.open_positions))
st.sidebar.caption(f"Réserve : {pm.reserve_cash:,.2f} €")

if st.sidebar.button("🔄 Synchroniser", help="Recharge l'état depuis le disque"):
    pm.reload()
    st.session_state["pm_mtime"] = pm.file_mtime
    st.rerun()

# Prochain scan auto
try:
    import scheduler as sched
    if sched.is_running():
        st.sidebar.caption(f"⏱ Prochain scan : {sched.next_run()}")
except Exception:
    pass

st.sidebar.markdown("---")
st.sidebar.caption("v0.1 · paper trading · yfinance")

# ── Rendu de la page sélectionnée ────────────────────────────────
pages[page_name].render(pm)
