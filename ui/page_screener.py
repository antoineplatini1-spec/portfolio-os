"""Page Screener : scan multi-actifs, classement par score."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from config import DEFAULT_WATCHLIST, BUY_SIGNAL_MIN_SCORE
from portfolio.manager import PortfolioManager
from signals.screener import run_screener


def render(pm: PortfolioManager):
    st.title("Screener d'opportunités")

    # ── Paramètres ────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        period = st.selectbox("Période analyse", ["3mo", "6mo", "1y"], index=1)
    with col2:
        min_score = st.slider("Score minimum", 0, 100, 40, step=5)
    with col3:
        custom = st.text_input("Tickers custom (séparés par virgule)", "")

    tickers = DEFAULT_WATCHLIST.copy()
    if custom:
        extra = [t.strip().upper() for t in custom.split(",") if t.strip()]
        tickers = list(dict.fromkeys(extra + tickers))

    if st.button("Lancer le screener", key="btn_run_screener", type="primary"):
        with st.spinner(f"Analyse de {len(tickers)} actifs…"):
            df = run_screener(tickers, period=period, min_score=min_score)
        st.session_state["screener_result"] = df

    df = st.session_state.get("screener_result")
    if df is None or df.empty:
        st.info("Lance le screener pour voir les résultats.")
        return

    # ── Tableau résultats ─────────────────────────────────────────
    st.subheader(f"{len(df)} actif(s) — triés par score décroissant")

    display = df[["ticker", "score", "signal", "price", "sl", "tp1",
                  "r_ratio", "perf_pct", "atr"]].copy()
    display.columns = ["Ticker", "Score", "Signal", "Prix", "SL", "TP1", "R-Ratio", "Perf %", "ATR"]
    display["Signal"] = display["Signal"].map({True: "✅ Achat", False: "—"})

    def color_score(val):
        if val >= 70:
            return "background-color: #1b5e20; color: white"
        elif val >= 60:
            return "background-color: #2e7d32; color: white"
        elif val >= 40:
            return "background-color: #f57f17; color: black"
        return "background-color: #b71c1c; color: white"

    styled = display.style.applymap(color_score, subset=["Score"])
    st.dataframe(styled, width='stretch', hide_index=True)

    # ── Graphique des scores ───────────────────────────────────────
    colors = [
        "#66bb6a" if s >= BUY_SIGNAL_MIN_SCORE else "#ef5350"
        for s in df["score"]
    ]
    fig = go.Figure(go.Bar(
        x=df["ticker"], y=df["score"],
        marker_color=colors,
        text=df["score"], textposition="outside",
    ))
    fig.add_hline(y=BUY_SIGNAL_MIN_SCORE,
                  line=dict(color="#ffb300", dash="dash"),
                  annotation_text=f"Seuil signal ({BUY_SIGNAL_MIN_SCORE})")
    fig.update_layout(
        template="plotly_dark", height=380, title="Scores par actif",
        xaxis_title="Ticker", yaxis_title="Score",
        margin=dict(t=50, b=30),
    )
    st.plotly_chart(fig, width='stretch')

    # ── Achat rapide depuis le screener ───────────────────────────
    st.markdown("---")
    st.subheader("Achat rapide")
    buy_candidates = df[df["signal"] == True]["ticker"].tolist() if "signal" in df.columns else []
    # correction : la colonne signal peut être bool
    if "signal" in df.columns:
        buy_candidates = df[df["signal"]]["ticker"].tolist()

    if not buy_candidates:
        st.info("Aucun actif avec signal suffisant.")
        return

    sel = st.selectbox("Actif à acheter", buy_candidates)
    row = df[df["ticker"] == sel].iloc[0]

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Score", f"{row['score']}/100")
    col_b.metric("Prix", f"{row['price']:.4f}")
    col_c.metric("R-Ratio TP1", f"{row['r_ratio']:.1f}x")

    if sel in pm.open_positions:
        st.info(f"Position déjà ouverte sur {sel}.")
    else:
        deploy_cash = pm.available_deploy_cash(int(row["score"]))
        st.caption(f"Cash déployable : {deploy_cash:,.2f} €")
        if st.button(f"Acheter {sel}", key=f"buy_screener_{sel}", type="primary"):
            ok, msg, pos = pm.open_position(
                sel, float(row["price"]), float(row["atr"]), int(row["score"])
            )
            if ok:
                st.success(msg)
            else:
                st.error(msg)
