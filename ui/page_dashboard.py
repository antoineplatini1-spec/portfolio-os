"""Dashboard — Vue synthétique du portefeuille."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from config import INITIAL_CASH, MAX_TOTAL_EXPOSURE_PCT, WEEKLY_DEPLOY_PCT
from portfolio.manager import PortfolioManager
from ui.theme import plotly_layout, COLORS as C


def render(pm: PortfolioManager):
    st.title("Dashboard")

    # ── KPIs ──────────────────────────────────────────────────────────────
    total    = pm.total_value
    invested = pm.total_invested
    cash_op  = pm.operational_cash
    reserve  = pm.reserve_cash
    pnl_real = sum(h["pnl"] for h in pm.history)
    pnl_pct  = (total / pm.initial_cash - 1) * 100

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Valeur totale",   f"{total:,.2f} €",
              f"{pnl_pct:+.2f}%")
    c2.metric("Cash disponible", f"{cash_op:,.2f} €")
    c3.metric("Réserve",         f"{reserve:,.2f} €")
    c4.metric("Investi",         f"{invested:,.2f} €",
              f"{pm.exposure_pct * 100:.1f}% expo.")
    c5.metric("PnL réalisé",     f"{pnl_real:+,.2f} €",
              delta_color="normal")

    st.markdown("---")

    col_l, col_r = st.columns(2)

    # ── Jauge d'exposition ────────────────────────────────────────────────
    with col_l:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=pm.exposure_pct * 100,
            title={"text": "Exposition", "font": {"color": C["text2"], "size": 13}},
            gauge={
                "axis": {
                    "range": [0, 100],
                    "tickcolor": C["text3"],
                    "tickfont": {"color": C["text3"], "size": 10},
                },
                "steps": [
                    {"range": [0,  50], "color": C["surf2"]},
                    {"range": [50, 80], "color": C["surf3"]},
                    {"range": [80, 100], "color": "rgba(251,113,133,0.18)"},
                ],
                "threshold": {
                    "line": {"color": C["down"], "width": 3},
                    "thickness": 0.8,
                    "value": MAX_TOTAL_EXPOSURE_PCT * 100,
                },
                "bar": {"color": C["accent"], "thickness": 0.22},
                "bgcolor": C["surf1"],
                "borderwidth": 0,
            },
            number={
                "suffix": "%",
                "font": {"color": C["text1"], "size": 28,
                         "family": "'JetBrains Mono', monospace"},
            },
        ))
        fig_gauge.update_layout(
            **plotly_layout(height=240, margin=dict(t=30, b=10, l=30, r=30)),
        )
        st.plotly_chart(fig_gauge, width="stretch")

        # Phase ramp-up
        if pm._is_ramp_up_phase():
            weekly_budget = pm.initial_cash * WEEKLY_DEPLOY_PCT
            pct_used      = min(1.0, pm.weekly_deployed / weekly_budget) if weekly_budget else 0
            remaining     = max(0.0, weekly_budget - pm.weekly_deployed)
            st.progress(pct_used,
                        text=f"Budget sem. : {pm.weekly_deployed:.0f} / {weekly_budget:.0f} €")
            st.caption(f"Restant cette semaine : {remaining:.2f} € · depuis {pm.week_start}")
        else:
            st.caption("⚡ Phase arbitrage — pas de limite hebdomadaire")

    # ── Allocation pie ────────────────────────────────────────────────────
    with col_r:
        open_pos = pm.open_positions
        labels = list(open_pos.keys()) + ["Cash", "Réserve"]
        values = [p.qty_remaining * p.entry_price
                  for p in open_pos.values()] + [cash_op, reserve]

        if sum(values) > 0:
            n_pos = len(open_pos)
            palette = [
                "#2dd4bf", "#60a5fa", "#a78bfa", "#fb7185", "#fbbf24",
                "#34d399", "#f472b6", "#38bdf8", "#818cf8", "#4ade80",
            ]
            colors = (
                [palette[i % len(palette)] for i in range(n_pos)]
                + [C["text3"], C["surf4"]]
            )
            # Avec beaucoup de positions : légende plutôt que labels
            use_legend = n_pos >= 5
            fig_pie = go.Figure(go.Pie(
                labels=labels,
                values=values,
                hole=0.52,
                marker=dict(
                    colors=colors,
                    line=dict(color=C["bg"], width=2),
                ),
                textinfo="percent" if use_legend else "label+percent",
                textfont=dict(
                    color=C["text1"], size=10,
                    family="'Inter', sans-serif",
                ),
                hovertemplate="<b>%{label}</b><br>%{value:,.2f} €<br>%{percent}<extra></extra>",
                insidetextorientation="radial",
                showlegend=use_legend,
            ))
            legend_cfg = dict(
                bgcolor="rgba(0,0,0,0)",
                font=dict(color=C["text2"], size=10, family="'Inter',sans-serif"),
                orientation="v",
                x=1.02, y=0.5,
                xanchor="left", yanchor="middle",
            ) if use_legend else dict(bgcolor="rgba(0,0,0,0)")
            fig_pie.update_layout(
                **plotly_layout(height=300, title="Répartition",
                                margin=dict(t=40, b=10, l=10, r=120 if use_legend else 10),
                                showlegend=use_legend,
                                legend=legend_cfg),
                annotations=[dict(
                    text=f"<b>{len(open_pos)}</b><br><span style='font-size:10px'>positions</span>",
                    x=0.38 if use_legend else 0.5, y=0.5,
                    font=dict(color=C["text1"], size=16,
                              family="'JetBrains Mono', monospace"),
                    showarrow=False,
                )],
            )
            st.plotly_chart(fig_pie, width="stretch")

    # ── Courbe de capital ─────────────────────────────────────────────────
    if pm.history:
        st.markdown("---")
        df = pd.DataFrame(pm.history).sort_values("close_date").copy()
        df["cum_pnl"] = df["pnl"].cumsum()
        df["capital"] = pm.initial_cash + df["cum_pnl"]
        above = df["capital"] >= pm.initial_cash

        fig_eq = go.Figure()

        # Zone above baseline
        fig_eq.add_trace(go.Scatter(
            x=df["close_date"], y=df["capital"],
            mode="lines",
            line=dict(color=C["up"], width=0),
            fill="tonexty",
            fillcolor=C["up_bg"],
            showlegend=False,
            hoverinfo="skip",
        ))
        # Baseline
        fig_eq.add_trace(go.Scatter(
            x=df["close_date"],
            y=[pm.initial_cash] * len(df),
            mode="lines",
            line=dict(color=C["border2"], width=0),
            showlegend=False,
            hoverinfo="skip",
        ))
        # Main line
        fig_eq.add_trace(go.Scatter(
            x=df["close_date"], y=df["capital"],
            mode="lines+markers",
            name="Capital",
            line=dict(color=C["accent"], width=2),
            marker=dict(
                size=6, color=C["accent"],
                line=dict(color=C["bg"], width=2),
            ),
            hovertemplate="<b>%{x}</b><br>%{y:,.2f} €<extra></extra>",
        ))
        fig_eq.add_hline(
            y=pm.initial_cash,
            line=dict(color=C["text3"], dash="dash", width=1),
            annotation_text=f"Capital initial {pm.initial_cash:,.0f} €",
            annotation_font_color=C["text3"],
            annotation_font_size=11,
            annotation_position="bottom right",
        )
        fig_eq.update_layout(
            **plotly_layout(height=260, title="Courbe de capital"),
            showlegend=False,
        )
        st.plotly_chart(fig_eq, width="stretch")

    # ── Résumé bas de page ────────────────────────────────────────────────
    st.markdown("---")
    open_count    = len(pm.open_positions)
    partial_count = sum(1 for p in pm.open_positions.values() if p.status == "partial")
    closed_count  = len(pm.history)
    wins          = sum(1 for h in pm.history if h["pnl"] > 0)
    win_rate      = wins / closed_count * 100 if closed_count else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Positions ouvertes", open_count)
    c2.metric("Dont partielles",    partial_count)
    c3.metric("Trades fermés",      closed_count)
    c4.metric("Win rate",           f"{win_rate:.0f}%" if closed_count else "—")
    c5.metric("Depuis",             pm.start_date)

    # ── Paramètres avancés ────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("⚙ Paramètres avancés"):
        new_capital = st.number_input(
            "Capital initial (€)", value=pm.initial_cash, min_value=100.0
        )
        if st.button("Réinitialiser le portefeuille", key="btn_reset_portfolio", type="primary"):
            pm.reset(new_capital)
            st.success("Portefeuille réinitialisé.")
            st.rerun()
