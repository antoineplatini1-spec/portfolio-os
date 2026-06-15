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
    total       = pm.total_value          # marché (last_prices ou entry si pas de prix)
    invested    = pm.total_market_value   # positions au prix de marché
    invested_cost = pm.total_invested     # positions au coût d'entrée
    cash_op     = pm.operational_cash
    reserve     = pm.reserve_cash
    pnl_real    = pm.pnl_realized         # réalisé : trades fermés + fills partiels TP
    pnl_lat     = pm.pnl_unrealized       # latent : positions ouvertes au marché
    pnl_total   = pnl_real + pnl_lat
    pnl_pct     = (total / pm.initial_cash - 1) * 100
    expo_pct    = pm.exposure_pct * 100
    has_prices  = bool(pm.last_prices)

    closed_count = len(pm.history)
    wins         = sum(1 for h in pm.history if h["pnl"] > 0)
    win_rate     = wins / closed_count * 100 if closed_count else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    price_note = "" if has_prices else " ⚠"
    c1.metric(
        f"Valeur totale{price_note}",
        f"{total:,.0f} €",
        f"{pnl_pct:+.2f}%",
        help="Valorisation au dernier prix de marché connu. ⚠ = prix non disponibles (valeur au coût)." if not has_prices
             else "Valorisation au dernier prix de marché connu (mis à jour chaque jour à 13h).",
    )
    c2.metric(
        "PnL total",
        f"{pnl_total:+,.0f} €",
        f"réalisé {pnl_real:+,.0f} € / latent {pnl_lat:+,.0f} €",
        delta_color="normal",
        help="PnL réalisé = trades fermés + fills partiels TP déjà encaissés. PnL latent = positions ouvertes au prix de marché.",
    )
    c3.metric("Cash dispo",      f"{cash_op:,.0f} €",  help="Cash opérationnel hors réserve.")
    c4.metric("Investi (marché)",f"{invested:,.0f} €",  f"{expo_pct:.1f}% expo.",
              help="Valeur des positions ouvertes au dernier prix de marché.")
    c5.metric("Win rate",        f"{win_rate:.0f}%" if closed_count else "—",
              f"{closed_count} trades fermés")
    c6.metric("Positions",       len(pm.open_positions), f"depuis {pm.start_date}")

    if not has_prices:
        st.caption("⚠️ Aucun prix de marché disponible — valeurs affichées au coût d'entrée. "
                   "Les prix se mettent à jour à 13h via GitHub Actions.")

    # ── Barres d'état ────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:0.5rem'></div>", unsafe_allow_html=True)

    expo_norm = min(1.0, pm.exposure_pct / MAX_TOTAL_EXPOSURE_PCT)
    expo_color = "#34d399" if expo_pct < 70 else ("#fbbf24" if expo_pct < 88 else "#fb7185")
    st.markdown(
        f"<div style='font:500 0.75rem/1 monospace;color:#8097b5;margin-bottom:4px'>"
        f"Exposition &nbsp;<b style='color:{expo_color}'>{expo_pct:.1f}%</b>"
        f" <span style='color:#445470'>/ {MAX_TOTAL_EXPOSURE_PCT*100:.0f}% max</span></div>",
        unsafe_allow_html=True,
    )
    st.progress(expo_norm)

    if pm._is_ramp_up_phase():
        weekly_budget = pm.initial_cash * WEEKLY_DEPLOY_PCT
        pct_used      = min(1.0, pm.weekly_deployed / weekly_budget) if weekly_budget else 0
        remaining     = max(0.0, weekly_budget - pm.weekly_deployed)
        st.markdown(
            f"<div style='font:500 0.75rem/1 monospace;color:#8097b5;"
            f"margin:8px 0 4px'>Budget semaine &nbsp;"
            f"<b style='color:#d6e0f0'>{pm.weekly_deployed:.0f} / {weekly_budget:.0f} €</b>"
            f" <span style='color:#445470'>— reste {remaining:.0f} €</span></div>",
            unsafe_allow_html=True,
        )
        st.progress(pct_used)
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

    # ── Courbe de capital (base 100) ──────────────────────────────────────
    if pm.history:
        st.markdown("---")
        df = pd.DataFrame(pm.history).sort_values("close_date").copy()
        df["cum_pnl"] = df["pnl"].cumsum()
        df["capital"] = pm.initial_cash + df["cum_pnl"]
        df["idx"] = df["capital"] / pm.initial_cash * 100

        spy_s = _spy_series(pm.start_date, pm.initial_cash)
        spy_idx = (spy_s / pm.initial_cash * 100) if spy_s is not None and not spy_s.empty else None

        if spy_idx is not None:
            spy_pct    = float(spy_idx.iloc[-1]) - 100
            port_pct   = float(df["idx"].iloc[-1]) - 100
            alpha      = port_pct - spy_pct
            ca, cb, _  = st.columns([1, 1, 4])
            ca.metric("Portfolio", f"{port_pct:+.2f}%")
            cb.metric("Alpha vs SPY", f"{alpha:+.2f}%", delta_color="normal" if alpha >= 0 else "inverse")

        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=df["close_date"], y=[100.0] * len(df),
            mode="lines", line=dict(color=C["border2"], width=0),
            showlegend=False, hoverinfo="skip",
        ))
        fig_eq.add_trace(go.Scatter(
            x=df["close_date"], y=df["idx"],
            mode="lines", fill="tonexty", fillcolor=C["up_bg"],
            line=dict(color=C["up"], width=0),
            showlegend=False, hoverinfo="skip",
        ))
        if spy_idx is not None:
            fig_eq.add_trace(go.Scatter(
                x=spy_idx.index.astype(str), y=spy_idx.values,
                mode="lines", name="SPY",
                line=dict(color=C["text3"], width=1.5, dash="dot"),
                hovertemplate="<b>SPY</b> %{x}<br>%{y:.1f}<extra></extra>",
            ))
        fig_eq.add_trace(go.Scatter(
            x=df["close_date"], y=df["idx"],
            mode="lines+markers", name="Portfolio",
            line=dict(color=C["accent"], width=2),
            marker=dict(size=5, color=C["accent"], line=dict(color=C["bg"], width=2)),
            hovertemplate="<b>Portfolio</b> %{x}<br>%{y:.1f}<extra></extra>",
        ))
        fig_eq.add_hline(
            y=100,
            line=dict(color=C["text3"], dash="dash", width=1),
            annotation_text="Base 100",
            annotation_font_color=C["text3"],
            annotation_font_size=10,
            annotation_position="bottom right",
        )
        fig_eq.update_layout(
            **plotly_layout(height=240, title="Portfolio vs SPY (base 100)"),
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
