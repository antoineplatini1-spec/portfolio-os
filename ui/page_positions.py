"""Positions ouvertes — niveaux SL / TP visuels."""

from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
import pandas as pd

from data.fetcher import fetch_ohlcv
from portfolio.manager import PortfolioManager
from portfolio.position import Position
from ui.theme import plotly_layout, COLORS as C

# ── Composant tableau cliquable ───────────────────────────────────────────────
_COMP_PATH = Path(__file__).parent / "components" / "clickable_table"
_clickable_table = components.declare_component(
    "clickable_table", path=str(_COMP_PATH)
)


def clickable_table(headers: list, rows: list, selected: str | None = None,
                    key: str = "ct") -> str | None:
    """Tableau HTML cliquable — retourne le ticker sélectionné ou None."""
    return _clickable_table(
        headers=headers, rows=rows, selected=selected,
        key=key, default=selected
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def _live_price(ticker: str) -> float | None:
    try:
        df = fetch_ohlcv(ticker, period="5d", interval="1d")
        return float(df["Close"].iloc[-1]) if not df.empty else None
    except Exception:
        return None


def _pct_to(live: float, target: float) -> str:
    if live == 0:
        return "—"
    return f"{(target - live) / live * 100:+.1f}%"


# ── Graphique price-ladder ────────────────────────────────────────────────────

def _ladder_chart(ticker: str, pos: Position, live: float) -> go.Figure:
    entry = pos.entry_price
    sl    = pos.sl
    tps   = pos.tp_levels
    if not tps:
        return go.Figure()

    all_prices = [sl, entry, live] + [t.price for t in tps]
    if pos.trailing_stop:
        all_prices.append(pos.trailing_stop_price)

    p_min = min(all_prices) * 0.9965
    p_max = max(all_prices) * 1.0035

    fig = go.Figure()
    fig.add_shape(type="rect", x0=sl, x1=entry, y0=0, y1=1,
                  fillcolor="rgba(251,113,133,0.07)", line_width=0, layer="below")
    gain_alphas = [0.06, 0.11, 0.17]
    prev = entry
    for i, tp in enumerate(tps):
        a = gain_alphas[min(i, len(gain_alphas) - 1)]
        fig.add_shape(type="rect", x0=prev, x1=tp.price, y0=0, y1=1,
                      fillcolor=f"rgba(52,211,153,{a})", line_width=0, layer="below")
        prev = tp.price

    fig.add_shape(type="line", x0=p_min, x1=p_max, y0=0.5, y1=0.5,
                  line=dict(color=C["border2"], width=1))

    def add_mkr(x, symbol, color, label, y_lbl=0.85, size=12):
        fig.add_trace(go.Scatter(
            x=[x], y=[0.5], mode="markers",
            marker=dict(symbol=symbol, size=size, color=color,
                        line=dict(color=C["bg"], width=1.5)),
            showlegend=False,
            hovertemplate=f"<b>{label}</b><br>{x:.4f}<extra></extra>",
        ))
        fig.add_annotation(
            x=x, y=y_lbl, text=label, showarrow=True, arrowhead=2,
            arrowcolor=color, arrowwidth=1,
            font=dict(size=9, color=color, family="'JetBrains Mono', monospace"),
            bgcolor=C["surf3"], bordercolor=color, borderpad=2, borderwidth=1,
            ay=-16,
        )

    add_mkr(sl, "triangle-left-open", C["down"], f"SL\n{sl:.4f}", y_lbl=0.14)
    if pos.trailing_stop and abs(pos.trailing_stop_price - sl) > 0.0001:
        add_mkr(pos.trailing_stop_price, "triangle-left", C["amber"],
                f"Trail\n{pos.trailing_stop_price:.4f}", y_lbl=0.25)
    add_mkr(entry, "square", C["blue"], f"Entrée\n{entry:.4f}", y_lbl=0.86)
    add_mkr(live, "circle", C["amber"], f"Live\n{live:.4f}", y_lbl=0.65, size=15)

    tp_colors = [C["up"], "#10b981", "#059669"]
    tp_y_lbls = [0.14, 0.28, 0.42]
    for i, tp in enumerate(tps):
        color = C["text3"] if tp.hit else tp_colors[min(i, len(tp_colors) - 1)]
        label = f"✓TP{i+1}\n{tp.price:.4f}" if tp.hit else f"TP{i+1}\n{tp.price:.4f}"
        add_mkr(tp.price, "triangle-right", color, label,
                y_lbl=tp_y_lbls[min(i, len(tp_y_lbls) - 1)])

    fig.update_layout(
        **plotly_layout(
            height=200,
            margin=dict(t=10, b=28, l=10, r=10),
            showlegend=False,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor=C["surf2"],
            xaxis=dict(range=[p_min, p_max], showgrid=True, gridcolor=C["border"],
                       tickformat=".4f",
                       tickfont=dict(color=C["text3"], size=9,
                                     family="'JetBrains Mono', monospace"),
                       title=None, linecolor=C["border"], showline=True),
            yaxis=dict(visible=False, range=[0, 1]),
        ),
    )
    return fig


# ── Fiche détaillée ───────────────────────────────────────────────────────────

def _detail_card(ticker: str, pos: Position, live: float):
    pnl     = (live - pos.entry_price) * pos.qty_remaining
    pnl_pct = (live / pos.entry_price - 1) * 100
    eff_sl  = pos.trailing_stop_price if pos.trailing_stop else pos.sl
    risk_eu = abs((live - eff_sl) * pos.qty_remaining)
    icon    = "🟢" if pnl >= 0 else "🔴"

    st.markdown(
        f"#### {icon} {ticker} &nbsp;·&nbsp; "
        f"<span style='color:{C['text2']};font-size:0.95rem'>"
        f"Live {live:.4f} &nbsp;·&nbsp; "
        f"PnL <span style='color:{C['up'] if pnl >= 0 else C['down']}'>"
        f"{pnl:+.2f} € ({pnl_pct:+.2f}%)</span></span>",
        unsafe_allow_html=True,
    )

    n_tp = len(pos.tp_levels)
    cols = st.columns(1 + n_tp + 1)
    sl_label = "SL (trailing)" if pos.trailing_stop else "SL"
    cols[0].metric(sl_label, f"{eff_sl:.4f}", _pct_to(live, eff_sl),
                   delta_color="inverse")
    for i, tp in enumerate(pos.tp_levels):
        delta = "✅ atteint" if tp.hit else _pct_to(live, tp.price)
        cols[i + 1].metric(f"TP{i+1} · {tp.sell_pct * 100:.0f}%",
                           f"{tp.price:.4f}", delta,
                           delta_color="off" if tp.hit else "normal")
    cols[-1].metric("Risque SL", f"{risk_eu:.2f} €",
                    _pct_to(live, eff_sl), delta_color="inverse")

    st.plotly_chart(_ladder_chart(ticker, pos, live), width="stretch")

    if pos.trailing_stop:
        st.info(f"🔁 **Trailing stop actif** · SL dynamique : "
                f"{pos.trailing_stop_price:.4f} (entrée : {pos.entry_price:.4f})")

    pct_rem = (pos.qty_remaining / pos.qty_total * 100 if pos.qty_total > 0 else 0)
    st.caption(f"Qté : {pos.qty_remaining:.4f} / {pos.qty_total:.4f} "
               f"({pct_rem:.0f}% restant) · Entrée le {pos.entry_date}")

    if pos.partial_fills:
        fills = [{"Date": f.date, "Raison": f.reason,
                  "Qté": round(f.qty, 4), "Prix": round(f.price, 4),
                  "PnL €": round((f.price - pos.entry_price) * f.qty, 2)}
                 for f in pos.partial_fills]

        def _fp(val):
            if isinstance(val, (int, float)):
                return (f"color:{C['up']};font-weight:600" if val >= 0
                        else f"color:{C['down']};font-weight:600")
            return ""

        st.dataframe(pd.DataFrame(fills).style.map(_fp, subset=["PnL €"]),
                     width="stretch", hide_index=True)


# ── Page ──────────────────────────────────────────────────────────────────────

def render(pm: PortfolioManager):
    st.title("Positions ouvertes — SL / TP")

    open_pos = pm.open_positions
    if not open_pos:
        st.info("Aucune position ouverte.")
        return

    col_btn, _ = st.columns([1, 6])
    with col_btn:
        if st.button("🔄 Rafraîchir", key="btn_refresh_positions", width="stretch"):
            _live_price.clear()
            prices_upd = {t: p for t in open_pos if (p := _live_price(t))}
            if prices_upd:
                pm.update_prices(prices_upd)
            st.rerun()

    prices: dict[str, float] = {
        t: (_live_price(t) or pos.entry_price)
        for t, pos in open_pos.items()
    }

    # ── Données tableau ───────────────────────────────────────────────────
    headers = ["Ticker", "Entrée", "Live", "PnL %", "SL", "% → SL",
               "Trail.", "TP1", "% → TP1", "TP2", "% → TP2",
               "TP3", "% → TP3", "Qté rest.", "Valeur €"]

    rows = []
    for ticker, pos in open_pos.items():
        live   = prices[ticker]
        eff_sl = pos.trailing_stop_price if pos.trailing_stop else pos.sl
        row = [
            ticker,
            f"{pos.entry_price:.4f}",
            f"{live:.4f}",
            f"{(live / pos.entry_price - 1) * 100:+.2f}%",
            f"{eff_sl:.4f}",
            _pct_to(live, eff_sl),
            "✓" if pos.trailing_stop else "—",
        ]
        for i in range(3):
            if i < len(pos.tp_levels):
                tp = pos.tp_levels[i]
                row += [f"{tp.price:.4f}",
                        "✓" if tp.hit else _pct_to(live, tp.price)]
            else:
                row += ["—", "—"]
        row += [f"{pos.qty_remaining:.4f}", f"{pos.qty_remaining * live:.2f}"]
        rows.append(row)

    # ── Tableau cliquable (composant natif) ───────────────────────────────
    sel_ticker = st.session_state.get("_pos_selected")

    clicked = clickable_table(
        headers=headers,
        rows=rows,
        selected=sel_ticker,
        key="pos_table",
    )

    # Met à jour la sélection si l'utilisateur a cliqué
    if clicked and clicked != sel_ticker:
        st.session_state["_pos_selected"] = clicked
        st.rerun()
    elif not clicked and sel_ticker:
        # Le composant renvoie None au démarrage — ne pas réinitialiser
        pass

    sel_ticker = st.session_state.get("_pos_selected")

    # ── Séparateur ────────────────────────────────────────────────────────
    st.markdown(
        "<div style='height:1px;background:#1e2d45;margin:1.5rem 0 1rem;'></div>",
        unsafe_allow_html=True,
    )

    # ── Zone détail ───────────────────────────────────────────────────────
    if not sel_ticker or sel_ticker not in open_pos:
        st.markdown(
            f"""
            <div style="
                display:flex; flex-direction:column; align-items:center;
                justify-content:center; gap:0.6rem;
                padding: 3.5rem 0;
                color:{C['text3']};
            ">
                <div style="font-size:2rem; opacity:0.35">📊</div>
                <div style="font:500 0.85rem/1 'Inter',sans-serif;
                            letter-spacing:0.03em;">
                    Cliquez sur une ligne pour afficher les détails
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        _detail_card(sel_ticker, open_pos[sel_ticker], prices[sel_ticker])
