"""Page Analyse : graphique interactif + score + achat paper."""

import streamlit as st
import pandas as pd

from config import DEFAULT_WATCHLIST
from data.fetcher import fetch_ohlcv
from indicators import compute_all
from portfolio.manager import PortfolioManager
from portfolio.risk import r_ratio, sl_price, tp_prices
from signals.screener import get_market_regime
from signals.scoring import compute_score
from ui.charts import build_price_chart
from utils.fees import break_even_price, compute_fees


def render(pm: PortfolioManager):
    st.title("Analyse technique")

    # ── Sélection actif ───────────────────────────────────────────
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        ticker = st.text_input("Ticker", value="AAPL").upper().strip()
    with col2:
        period = st.selectbox("Période", ["1mo", "3mo", "6mo", "1y", "2y"], index=2)
    with col3:
        interval = st.selectbox("Intervalle", ["1d", "1wk"], index=0)

    ov1, ov2, ov3, ov4, _ = st.columns([1, 1, 1, 1, 4])
    show_ema  = ov1.checkbox("EMA", value=True)
    show_bb   = ov2.checkbox("Bollinger", value=True)
    show_vwap = ov3.checkbox("VWAP", value=True)
    show_fib  = ov4.checkbox("Fibonacci", value=False)

    if not ticker:
        return

    with st.spinner(f"Chargement {ticker}…"):
        df = fetch_ohlcv(ticker, period=period, interval=interval)

    if df.empty:
        st.error(f"Impossible de charger les données pour {ticker}")
        return

    df = compute_all(df)
    regime = get_market_regime()
    result = compute_score(df, ticker=ticker, market_regime=regime)
    position = pm.positions.get(ticker)

    # ── Graphique ─────────────────────────────────────────────────
    fig = build_price_chart(
        df, ticker, position,
        show_ema=show_ema, show_bb=show_bb, show_vwap=show_vwap, show_fib=show_fib
    )
    st.plotly_chart(fig, width='stretch')

    # ── Score ─────────────────────────────────────────────────────
    score = result["score"]
    col_s, col_sig = st.columns(2)
    with col_s:
        color = "#66bb6a" if score >= 60 else ("#ffb300" if score >= 40 else "#ef5350")
        st.markdown(f"### Score signal : <span style='color:{color}'>{score}/100</span>",
                    unsafe_allow_html=True)
    with col_sig:
        if result["signal"]:
            st.success("Signal d'achat actif")
        else:
            st.warning("Pas de signal suffisant")

    # Détail des contributions
    with st.expander("Détail des indicateurs"):
        detail_rows = [
            {"Indicateur": k, "Valeur": str(v["value"]), "Points": f"{v['pts']:+d}"}
            for k, v in result["details"].items()
        ]
        if detail_rows:
            st.dataframe(pd.DataFrame(detail_rows), hide_index=True, width='stretch')

    st.markdown("---")

    # ── Calcul TP/SL ─────────────────────────────────────────────
    price = result.get("last_close") or float(df["Close"].iloc[-1])
    atr = result.get("atr") or 0.0

    st.subheader("Niveaux calculés")
    if atr > 0:
        sl = sl_price(price, atr)
        tps = tp_prices(price, atr)
        be = break_even_price(price, 1)

        col1, col2, col3 = st.columns(3)
        col1.metric("Stop-Loss", f"{sl:.4f}", f"{(sl-price)/price*100:.2f}%",
                    delta_color="inverse")
        col2.metric("Break-even", f"{be:.4f}")
        col3.metric("ATR (14)", f"{atr:.4f}")

        for i, tp in enumerate(tps):
            r = r_ratio(price, tp["price"], sl)
            st.metric(
                f"TP{i+1} ({tp['atr_mult']}×ATR) — vendre {int(tp['sell_pct']*100)}%",
                f"{tp['price']:.4f}",
                f"R={r:.1f}x | +{(tp['price']-price)/price*100:.2f}%",
            )
    else:
        st.warning("ATR non calculé — données insuffisantes pour les niveaux.")

    # ── Achat paper ───────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Passer un ordre (paper)")

    if ticker in pm.open_positions:
        st.info(f"Position déjà ouverte sur {ticker}.")
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            manual_price = st.number_input("Prix d'entrée", value=round(price, 4), min_value=0.0001)
        with col_b:
            deploy_cash = pm.available_deploy_cash(score)
            st.metric("Cash déployable", f"{deploy_cash:,.2f} €")

        if st.button(f"Acheter {ticker}", key=f"buy_analysis_{ticker}", type="primary"):
            if atr <= 0:
                st.error("ATR invalide — impossible de calculer le SL.")
            else:
                ok, msg, pos = pm.open_position(ticker, manual_price, atr, score)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
