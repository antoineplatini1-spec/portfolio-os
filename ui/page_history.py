"""Page Historique : trades fermés + statistiques de performance."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from portfolio.manager import PortfolioManager


def render(pm: PortfolioManager):
    st.title("Historique des trades")

    history = pm.history
    if not history:
        st.info("Aucun trade fermé pour l'instant.")
        return

    df = pd.DataFrame(history)

    # ── Statistiques globales ─────────────────────────────────────
    total_trades = len(df)
    wins = df[df["pnl"] > 0]
    losses = df[df["pnl"] <= 0]
    win_rate = len(wins) / total_trades * 100 if total_trades else 0
    avg_win = wins["pnl"].mean() if len(wins) else 0
    avg_loss = losses["pnl"].mean() if len(losses) else 0
    total_fees = df["fees_total"].sum()
    total_pnl = df["pnl"].sum()

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Trades", total_trades)
    col2.metric("Win rate", f"{win_rate:.1f}%")
    col3.metric("PnL total net", f"{total_pnl:+.2f} €",
                delta_color="normal")
    col4.metric("Gain moyen", f"{avg_win:+.2f} €")
    col5.metric("Frais totaux", f"{total_fees:.2f} €")

    if avg_loss != 0 and avg_win != 0:
        profit_factor = abs(avg_win / avg_loss)
        st.caption(f"Profit factor : {profit_factor:.2f} | Perte moy. : {avg_loss:+.2f} €")

    # ── Courbe de capital ─────────────────────────────────────────
    df_sorted = df.sort_values("close_date").copy()
    df_sorted["cum_pnl"] = df_sorted["pnl"].cumsum()
    df_sorted["capital"] = pm.initial_cash + df_sorted["cum_pnl"]

    fig_equity = go.Figure()
    fig_equity.add_trace(go.Scatter(
        x=df_sorted["close_date"], y=df_sorted["capital"],
        mode="lines+markers",
        line=dict(color="#26a69a", width=2),
        fill="tozeroy",
        fillcolor="rgba(38,166,154,0.1)",
        name="Capital",
    ))
    fig_equity.add_hline(y=pm.initial_cash,
                         line=dict(color="#546e7a", dash="dash"),
                         annotation_text="Capital initial")
    fig_equity.update_layout(
        template="plotly_dark", height=300, title="Courbe de capital",
        xaxis_title="Date", yaxis_title="Capital (€)",
        margin=dict(t=50, b=30),
    )
    st.plotly_chart(fig_equity, width='stretch')

    # ── PnL par trade ─────────────────────────────────────────────
    colors = ["#26a69a" if p > 0 else "#ef5350" for p in df_sorted["pnl"]]
    fig_pnl = go.Figure(go.Bar(
        x=df_sorted["ticker"] + " " + df_sorted["close_date"].str[:10],
        y=df_sorted["pnl"],
        marker_color=colors,
        text=df_sorted["pnl"].apply(lambda x: f"{x:+.2f}"),
        textposition="outside",
    ))
    fig_pnl.update_layout(
        template="plotly_dark", height=320, title="PnL par trade",
        xaxis_title="Trade", yaxis_title="PnL net (€)",
        margin=dict(t=50, b=50),
    )
    st.plotly_chart(fig_pnl, width='stretch')

    # ── Tableau détaillé ──────────────────────────────────────────
    st.subheader("Détail des trades")
    display = df[["ticker", "entry_date", "close_date", "entry_price",
                  "close_price", "qty", "pnl", "fees_total", "close_reason"]].copy()
    display.columns = ["Ticker", "Entrée", "Clôture", "Prix entrée",
                       "Prix clôture", "Qté", "PnL €", "Frais €", "Raison"]
    display["PnL €"] = display["PnL €"].apply(lambda x: f"{x:+.2f}")
    st.dataframe(display, width='stretch', hide_index=True)
