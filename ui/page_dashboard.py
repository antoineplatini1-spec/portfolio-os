"""Page Dashboard : vue globale du portefeuille."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

from config import INITIAL_CASH, MAX_TOTAL_EXPOSURE_PCT, RESERVE_CASH_PCT
from data.fetcher import fetch_ohlcv
from portfolio.manager import PortfolioManager
from utils.fees import net_pnl


def _get_live_price(ticker: str) -> float | None:
    try:
        df = fetch_ohlcv(ticker, period="5d", interval="1d")
        return float(df["Close"].iloc[-1]) if not df.empty else None
    except Exception:
        return None


def render(pm: PortfolioManager):
    st.title("Dashboard Portefeuille")

    # ── Rafraîchissement des prix ─────────────────────────────────
    if st.button("Rafraîchir les prix"):
        prices = {}
        for ticker in pm.open_positions:
            p = _get_live_price(ticker)
            if p:
                prices[ticker] = p
        pm.update_prices(prices)
        st.success(f"{len(prices)} position(s) mises à jour.")
        st.rerun()

    # ── KPI row ───────────────────────────────────────────────────
    total = pm.total_value
    invested = pm.total_invested
    cash_op = pm.operational_cash
    reserve = pm.reserve_cash

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Valeur totale", f"{total:,.2f} €")
    col2.metric("Cash opérationnel", f"{cash_op:,.2f} €")
    col3.metric("Poche réserve", f"{reserve:,.2f} €")
    col4.metric("Investi", f"{invested:,.2f} €", f"{pm.exposure_pct*100:.1f}%")
    pnl_total = total - pm.initial_cash
    col5.metric("PnL total", f"{pnl_total:+,.2f} €",
                f"{pnl_total/pm.initial_cash*100:+.2f}%",
                delta_color="normal")

    # ── Jauge d'exposition ────────────────────────────────────────
    st.markdown("---")
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=pm.exposure_pct * 100,
        title={"text": "Exposition (%)"},
        gauge={
            "axis": {"range": [0, 100]},
            "steps": [
                {"range": [0, 50], "color": "#263238"},
                {"range": [50, 80], "color": "#37474f"},
                {"range": [80, 100], "color": "#b71c1c"},
            ],
            "threshold": {
                "line": {"color": "#ef5350", "width": 3},
                "thickness": 0.8,
                "value": MAX_TOTAL_EXPOSURE_PCT * 100,
            },
            "bar": {"color": "#26a69a"},
        },
        number={"suffix": "%"},
    ))
    fig_gauge.update_layout(height=250, template="plotly_dark", margin=dict(t=40, b=0))
    st.plotly_chart(fig_gauge, width='stretch')

    # ── Positions ouvertes ────────────────────────────────────────
    st.subheader("Positions ouvertes")
    open_pos = pm.open_positions
    if not open_pos:
        st.info("Aucune position ouverte.")
    else:
        rows = []
        for ticker, pos in open_pos.items():
            live = _get_live_price(ticker) or pos.entry_price
            pnl = (live - pos.entry_price) * pos.qty_remaining
            pnl_pct = (live - pos.entry_price) / pos.entry_price * 100
            tp_hit = sum(1 for t in pos.tp_levels if t.hit)
            rows.append({
                "Ticker": ticker,
                "Entrée": f"{pos.entry_price:.4f}",
                "Prix live": f"{live:.4f}",
                "PnL €": f"{pnl:+.2f}",
                "PnL %": f"{pnl_pct:+.2f}%",
                "Qté restante": f"{pos.qty_remaining:.4f}",
                "SL": f"{pos.sl:.4f}",
                "TP atteints": f"{tp_hit}/{len(pos.tp_levels)}",
                "Statut": pos.status,
            })
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

        # Fermeture manuelle
        st.markdown("**Fermeture manuelle**")
        c1, c2, c3 = st.columns(3)
        with c1:
            sel = st.selectbox("Ticker", list(open_pos.keys()))
        with c2:
            manual_price = st.number_input("Prix de clôture", value=0.0, min_value=0.0)
        with c3:
            st.write("")
            st.write("")
            if st.button("Clôturer") and manual_price > 0:
                pm.manual_close(sel, manual_price)
                st.success(f"Position {sel} clôturée à {manual_price:.4f}")
                st.rerun()

    # ── Répartition du portefeuille ───────────────────────────────
    st.markdown("---")
    st.subheader("Répartition")
    labels = list(open_pos.keys()) + ["Cash opérationnel", "Réserve"]
    values = [p.qty_remaining * p.entry_price for p in open_pos.values()] + [cash_op, reserve]
    if sum(values) > 0:
        fig_pie = go.Figure(go.Pie(
            labels=labels, values=values,
            hole=0.4,
            marker=dict(colors=[
                f"hsl({i*37 % 360}, 70%, 50%)" for i in range(len(labels))
            ]),
        ))
        fig_pie.update_layout(
            template="plotly_dark", height=350, showlegend=True,
            margin=dict(t=20, b=20),
        )
        st.plotly_chart(fig_pie, width='stretch')

    # ── Allocation progressive ────────────────────────────────────
    st.markdown("---")
    st.subheader("Allocation progressive (mois 1)")
    if pm._is_ramp_up_phase():
        from config import WEEKLY_DEPLOY_PCT
        weekly_budget = pm.initial_cash * WEEKLY_DEPLOY_PCT
        remaining = max(0, weekly_budget - pm.weekly_deployed)
        pct_used = min(100, pm.weekly_deployed / weekly_budget * 100) if weekly_budget else 0
        st.progress(pct_used / 100, text=f"Budget semaine : {pm.weekly_deployed:.2f} / {weekly_budget:.2f} € déployés")
        st.caption(f"Restant cette semaine : {remaining:.2f} € | Semaine démarrée le {pm.week_start}")
    else:
        st.info("Phase d'arbitrage active — pas de limite hebdomadaire.")

    # ── Réinitialisation ──────────────────────────────────────────
    with st.expander("⚙ Paramètres avancés"):
        new_capital = st.number_input("Capital initial (€)", value=pm.initial_cash, min_value=100.0)
        if st.button("Réinitialiser le portefeuille (paper)"):
            pm.reset(new_capital)
            st.success("Portefeuille réinitialisé.")
            st.rerun()
