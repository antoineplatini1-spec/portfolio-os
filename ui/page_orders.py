"""Ordres ouverts — tableau cliquable, detail sur selection."""

from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from data.fetcher import fetch_ohlcv
from portfolio.manager import PortfolioManager
from ui.theme import COLORS as C

# ── Composant tableau cliquable (partagé avec page_positions) ─────────────────
_COMP_PATH = Path(__file__).parent / "components" / "clickable_table"
_clickable_table = components.declare_component(
    "clickable_table_orders", path=str(_COMP_PATH)
)


def clickable_table(headers, rows, selected=None, key="ct_orders"):
    return _clickable_table(
        headers=headers, rows=rows, selected=selected,
        key=key, default=selected,
    )


# ── Prix live ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def _live_price(ticker: str) -> float | None:
    try:
        df = fetch_ohlcv(ticker, period="5d", interval="1d")
        return float(df["Close"].iloc[-1]) if not df.empty else None
    except Exception:
        return None


def _pct(a, b):
    """% de a vers b."""
    if a == 0:
        return "—"
    return f"{(b - a) / a * 100:+.1f}%"


# ── Fiche détail ──────────────────────────────────────────────────────────────

def _detail_card(ticker: str, pos, live: float, pm: PortfolioManager):
    pnl     = (live - pos.entry_price) * pos.qty_remaining
    pnl_pct = (live / pos.entry_price - 1) * 100
    icon    = "🟢" if pnl >= 0 else "🔴"
    pnl_color = C["up"] if pnl >= 0 else C["down"]

    st.markdown(
        f"#### {icon} {ticker} &nbsp;·&nbsp; "
        f"<span style='color:{C['text2']};font-size:0.95rem'>"
        f"Live <b>{live:.4f}</b> &nbsp;·&nbsp; "
        f"PnL <span style='color:{pnl_color}'>"
        f"{pnl:+.2f} € ({pnl_pct:+.2f}%)</span></span>",
        unsafe_allow_html=True,
    )

    # ── Métriques ─────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prix entrée",    f"{pos.entry_price:.4f}")
    c2.metric("Prix live",      f"{live:.4f}", f"{pnl_pct:+.2f}%")
    c3.metric("Qté restante",   f"{pos.qty_remaining:.4f}",
              f"/ {pos.qty_total:.4f} total")
    c4.metric("Frais entrée",   f"{pos.fees_in:.2f} €")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Date entrée",    pos.entry_date)
    c6.metric("Valeur initiale",f"{pos.qty_total * pos.entry_price:.2f} €")
    c7.metric("Valeur actuelle",f"{pos.qty_remaining * live:.2f} €")
    c8.metric("Statut",         pos.status.upper())

    st.markdown(
        "<div style='height:1px;background:#1e2d45;margin:1rem 0;'></div>",
        unsafe_allow_html=True,
    )

    # ── Fills partiels ────────────────────────────────────────────────
    if pos.partial_fills:
        st.markdown("**Fills partiels réalisés**")
        fills_rows = []
        for f in pos.partial_fills:
            pnl_fill = (f.price - pos.entry_price) * f.qty
            fills_rows.append({
                "Date":        f.date,
                "Raison":      f.reason,
                "Qté vendue":  round(f.qty,   4),
                "Prix vente":  round(f.price, 4),
                "Produit €":   round(f.qty * f.price, 2),
                "PnL partiel": round(pnl_fill, 2),
            })

        def _style_fill(val):
            if isinstance(val, (int, float)):
                return ("color:#34d399;font-weight:600" if val >= 0
                        else "color:#fb7185;font-weight:600")
            return ""

        st.dataframe(
            pd.DataFrame(fills_rows).style.map(_style_fill, subset=["PnL partiel"]),
            width="stretch", hide_index=True,
        )
    else:
        st.caption("Aucun fill partiel réalisé.")

    st.markdown(
        "<div style='height:1px;background:#1e2d45;margin:1rem 0;'></div>",
        unsafe_allow_html=True,
    )

    # ── Clôture manuelle ──────────────────────────────────────────────
    st.markdown("**Clôture manuelle**")
    cc1, cc2 = st.columns([3, 1])
    with cc1:
        close_px = st.number_input(
            "Prix de clôture",
            value=float(round(live, 4)),
            min_value=0.0001,
            format="%.4f",
            key=f"close_px_{ticker}",
        )
    with cc2:
        st.write("")
        st.write("")
        if st.button(f"Clôturer {ticker}", key=f"close_btn_{ticker}",
                     type="primary", width="stretch"):
            pm.manual_close(ticker, close_px)
            st.session_state.pop("_orders_selected", None)
            st.success(f"✅ {ticker} clôturé à {close_px:.4f}")
            st.rerun()


# ── Page ──────────────────────────────────────────────────────────────────────

def render(pm: PortfolioManager):
    st.title("Ordres ouverts")

    open_pos = pm.open_positions
    if not open_pos:
        st.info("Aucun ordre ouvert pour le moment.")
        return

    # ── Barre d'outils ────────────────────────────────────────────────
    col_btn, col_pnl, col_nb = st.columns([1, 2, 2])
    with col_btn:
        if st.button("🔄 Rafraîchir", key="btn_refresh_orders", width="stretch"):
            _live_price.clear()
            prices_upd = {t: p for t in open_pos if (p := _live_price(t))}
            if prices_upd:
                pm.update_prices(prices_upd)
            st.rerun()

    prices: dict[str, float] = {
        t: (_live_price(t) or pos.entry_price)
        for t, pos in open_pos.items()
    }

    total_pnl = sum(
        (prices[t] - pos.entry_price) * pos.qty_remaining
        for t, pos in open_pos.items()
    )
    col_pnl.metric("PnL latent total", f"{total_pnl:+,.2f} €")
    col_nb.metric("Ordres ouverts", len(open_pos))

    # ── Tableau ───────────────────────────────────────────────────────
    headers = ["Ticker", "Date", "Entrée", "Live", "PnL %", "PnL €",
               "Qté rest.", "Valeur €", "Statut", "TP atteints"]

    rows = []
    for ticker, pos in open_pos.items():
        live    = prices[ticker]
        pnl     = (live - pos.entry_price) * pos.qty_remaining
        pnl_pct = (live - pos.entry_price) / pos.entry_price * 100
        tp_hit  = sum(1 for t in pos.tp_levels if t.hit)
        rows.append([
            ticker,
            pos.entry_date,
            f"{pos.entry_price:.4f}",
            f"{live:.4f}",
            f"{pnl_pct:+.2f}%",
            f"{pnl:+.2f}",
            f"{pos.qty_remaining:.4f}",
            f"{pos.qty_remaining * live:.2f}",
            pos.status.upper(),
            f"{tp_hit}/{len(pos.tp_levels)}",
        ])

    sel_ticker = st.session_state.get("_orders_selected")

    clicked = clickable_table(
        headers=headers, rows=rows,
        selected=sel_ticker, key="orders_table",
    )

    if clicked and clicked != sel_ticker:
        st.session_state["_orders_selected"] = clicked
        st.rerun()

    sel_ticker = st.session_state.get("_orders_selected")

    # ── Séparateur ────────────────────────────────────────────────────
    st.markdown(
        "<div style='height:1px;background:#1e2d45;margin:1.5rem 0 1rem;'></div>",
        unsafe_allow_html=True,
    )

    # ── Zone détail ───────────────────────────────────────────────────
    if not sel_ticker or sel_ticker not in open_pos:
        st.markdown(
            f"""
            <div style="
                display:flex; flex-direction:column; align-items:center;
                justify-content:center; gap:0.6rem;
                padding: 3.5rem 0;
                color:{C['text3']};
            ">
                <div style="font-size:2rem; opacity:0.35">📋</div>
                <div style="font:500 0.85rem/1 'Inter',sans-serif;
                            letter-spacing:0.03em;">
                    Cliquez sur une ligne pour afficher les détails
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        _detail_card(sel_ticker, open_pos[sel_ticker], prices[sel_ticker], pm)
