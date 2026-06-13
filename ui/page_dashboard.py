"""Dashboard — Vue synthétique du portefeuille."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf

from config import INITIAL_CASH, MAX_TOTAL_EXPOSURE_PCT, WEEKLY_DEPLOY_PCT
from portfolio.manager import PortfolioManager
from ui.theme import plotly_layout, COLORS as C


@st.cache_data(ttl=3600)
def _spy_series(start_date: str, initial_cash: float) -> pd.Series | None:
    try:
        df = yf.download("SPY", start=start_date, progress=False,
                         auto_adjust=True, multi_level_index=False)
        if df.empty:
            return None
        close = df["Close"].dropna()
        return (close / float(close.iloc[0]) * initial_cash).round(2)
    except Exception:
        return None


def render(pm: PortfolioManager):
    st.title("Dashboard")

    # ── KPIs ──────────────────────────────────────────────────────────────
    total    = pm.total_value
    invested = pm.total_invested
    cash_op  = pm.operational_cash
    reserve  = pm.reserve_cash
    pnl_real = sum(h["pnl"] for h in pm.history)
    pnl_pct  = (total / pm.initial_cash - 1) * 100
    expo_pct = pm.exposure_pct * 100

    closed_count = len(pm.history)
    wins         = sum(1 for h in pm.history if h["pnl"] > 0)
    win_rate     = wins / closed_count * 100 if closed_count else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Valeur totale",   f"{total:,.0f} €",   f"{pnl_pct:+.2f}%")
    c2.metric("Investi",         f"{invested:,.0f} €", f"{expo_pct:.1f}% expo.")
    c3.metric("Cash dispo",      f"{cash_op:,.0f} €")
    c4.metric("PnL réalisé",     f"{pnl_real:+,.0f} €", delta_color="normal")
    c5.metric("Win rate",        f"{win_rate:.0f}%" if closed_count else "—",
              f"{closed_count} trades")
    c6.metric("Positions",       len(pm.open_positions), f"depuis {pm.start_date}")

    # ── Barre d'exposition ────────────────────────────────────────────────
    expo_norm = min(1.0, pm.exposure_pct / MAX_TOTAL_EXPOSURE_PCT)
    st.progress(expo_norm,
                text=f"Exposition : **{expo_pct:.1f}%** / {MAX_TOTAL_EXPOSURE_PCT*100:.0f}% max")

    if pm._is_ramp_up_phase():
        weekly_budget = pm.initial_cash * WEEKLY_DEPLOY_PCT
        pct_used      = min(1.0, pm.weekly_deployed / weekly_budget) if weekly_budget else 0
        remaining     = max(0.0, weekly_budget - pm.weekly_deployed)
        st.progress(pct_used,
                    text=f"Budget semaine : **{pm.weekly_deployed:.0f} / {weekly_budget:.0f} €** "
                         f"— reste {remaining:.0f} €")
    else:
        st.caption("⚡ Phase arbitrage — pas de limite hebdomadaire")

    st.markdown("---")

    # ── Pie chart + positions côte à côte ────────────────────────────────
    open_pos = pm.open_positions
    if open_pos:
        col_pie, col_pos = st.columns([1, 2])
    else:
        col_pie = st.container()
        col_pos = st.container()

    with col_pie:
        labels = list(open_pos.keys()) + ["Cash", "Réserve"]
        values = [p.qty_remaining * p.entry_price
                  for p in open_pos.values()] + [cash_op, reserve]

        if sum(values) > 0:
            n_pos   = len(open_pos)
            palette = ["#2dd4bf", "#60a5fa", "#a78bfa", "#fb7185", "#fbbf24",
                       "#34d399", "#f472b6", "#38bdf8", "#818cf8", "#4ade80"]
            colors  = [palette[i % len(palette)] for i in range(n_pos)] + [C["text3"], C["surf4"]]

            fig_pie = go.Figure(go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker=dict(colors=colors, line=dict(color=C["bg"], width=2)),
                textinfo="percent",
                textfont=dict(color=C["text1"], size=9, family="'Inter', sans-serif"),
                hovertemplate="<b>%{label}</b><br>%{value:,.0f} €  %{percent}<extra></extra>",
                showlegend=False,
            ))
            fig_pie.update_layout(
                **plotly_layout(height=220, margin=dict(t=10, b=10, l=10, r=10)),
                annotations=[dict(
                    text=f"<b>{n_pos}</b><br><span style='font-size:9px'>pos.</span>",
                    x=0.5, y=0.5,
                    font=dict(color=C["text1"], size=18,
                              family="'JetBrains Mono', monospace"),
                    showarrow=False,
                )],
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    with col_pos:
        if open_pos:
            rows = []
            for t, p in open_pos.items():
                live_px = p.entry_price  # prix d'entrée par défaut (pas de fetch ici)
                pnl_lat = (live_px - p.entry_price) * p.qty_remaining
                pnl_pct = (live_px / p.entry_price - 1) * 100 if p.entry_price else 0
                tp1 = f"{p.tp_levels[0].price:.2f}" if p.tp_levels else "—"
                rows.append({
                    "Ticker":   t,
                    "Entrée":   f"{p.entry_price:.2f}",
                    "SL":       f"{p.sl:.2f}",
                    "TP1":      tp1,
                    "PnL %":   f"{pnl_pct:+.1f}%",
                    "Statut":   p.status.upper(),
                    "Depuis":   p.entry_date or "—",
                })
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
                height=220,
            )
        else:
            st.caption("Aucune position ouverte.")

    # ── Courbe de capital ─────────────────────────────────────────────────
    if pm.history:
        st.markdown("---")
        df = pd.DataFrame(pm.history).sort_values("close_date").copy()
        df["cum_pnl"] = df["pnl"].cumsum()
        df["capital"] = pm.initial_cash + df["cum_pnl"]

        spy_s = _spy_series(pm.start_date, pm.initial_cash)

        if spy_s is not None and not spy_s.empty:
            spy_final  = float(spy_s.iloc[-1])
            port_final = float(df["capital"].iloc[-1])
            spy_pct    = (spy_final  / pm.initial_cash - 1) * 100
            port_pct   = (port_final / pm.initial_cash - 1) * 100
            alpha      = port_pct - spy_pct
            ca, cb, _  = st.columns([1, 1, 4])
            ca.metric("Portfolio", f"{port_pct:+.2f}%")
            cb.metric("Alpha vs SPY", f"{alpha:+.2f}%", delta_color="normal" if alpha >= 0 else "inverse")

        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=df["close_date"], y=[pm.initial_cash] * len(df),
            mode="lines", line=dict(color=C["border2"], width=0),
            showlegend=False, hoverinfo="skip",
        ))
        fig_eq.add_trace(go.Scatter(
            x=df["close_date"], y=df["capital"],
            mode="lines", fill="tonexty", fillcolor=C["up_bg"],
            line=dict(color=C["up"], width=0),
            showlegend=False, hoverinfo="skip",
        ))
        if spy_s is not None and not spy_s.empty:
            fig_eq.add_trace(go.Scatter(
                x=spy_s.index.astype(str), y=spy_s.values,
                mode="lines", name="SPY",
                line=dict(color=C["text3"], width=1.5, dash="dot"),
                hovertemplate="<b>SPY</b> %{x}<br>%{y:,.0f} €<extra></extra>",
            ))
        fig_eq.add_trace(go.Scatter(
            x=df["close_date"], y=df["capital"],
            mode="lines+markers", name="Portfolio",
            line=dict(color=C["accent"], width=2),
            marker=dict(size=5, color=C["accent"], line=dict(color=C["bg"], width=2)),
            hovertemplate="<b>Portfolio</b> %{x}<br>%{y:,.0f} €<extra></extra>",
        ))
        fig_eq.add_hline(
            y=pm.initial_cash,
            line=dict(color=C["text3"], dash="dash", width=1),
            annotation_text=f"{pm.initial_cash:,.0f} €",
            annotation_font_color=C["text3"],
            annotation_font_size=10,
            annotation_position="bottom right",
        )
        fig_eq.update_layout(
            **plotly_layout(height=240, title="Portfolio vs SPY"),
            showlegend=True,
        )
        st.plotly_chart(fig_eq, use_container_width=True)

    # ── Paramètres ────────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("⚙ Paramètres"):
        new_capital = st.number_input("Capital initial (€)", value=pm.initial_cash, min_value=100.0)
        if st.button("Réinitialiser le portefeuille", key="btn_reset_portfolio", type="primary"):
            pm.reset(new_capital)
            st.success("Portefeuille réinitialisé.")
            st.rerun()
