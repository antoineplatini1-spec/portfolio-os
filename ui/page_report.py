"""Rapport quotidien — historique des scans, arbitrages et analyses."""

from pathlib import Path
import streamlit as st

from portfolio.manager import PortfolioManager
from ui.theme import COLORS as C
from utils.log_parser import DayScan, last_trade_date, parse_log

LOG_PATH = Path(__file__).parent.parent / "data" / "daily_log.txt"

# ── Helpers visuels ───────────────────────────────────────────────────────────

def _badge(text: str, color: str, bg: str) -> str:
    return (
        f"<span style='display:inline-block;padding:1px 8px;border-radius:4px;"
        f"font:600 0.7rem/1.6 monospace;color:{color};background:{bg};"
        f"letter-spacing:0.04em'>{text}</span>"
    )


def _ctx_badge(ctx: str) -> str:
    if "FORT" in ctx:
        return _badge("FORT", "#34d399", "rgba(52,211,153,0.12)")
    if "MOYEN" in ctx:
        return _badge("MOYEN", "#fbbf24", "rgba(251,191,36,0.12)")
    if "FAIBLE" in ctx:
        return _badge("FAIBLE", "#fb7185", "rgba(251,113,133,0.12)")
    return _badge(ctx, C["text2"], C["surf3"])


def _pnl_color(v: float) -> str:
    return C["up"] if v >= 0 else C["down"]


def _section(title: str):
    st.markdown(
        f"<div style='font:600 0.7rem/1 monospace;color:{C['text3']};"
        f"letter-spacing:0.12em;text-transform:uppercase;"
        f"margin:1.2rem 0 0.5rem;padding-bottom:0.35rem;"
        f"border-bottom:1px solid {C['border']}'>{title}</div>",
        unsafe_allow_html=True,
    )


# ── Rendu d'un scan ───────────────────────────────────────────────────────────

def _render_scan(s: DayScan):
    # ── En-tête ───────────────────────────────────────────────────────
    if s.weekend:
        st.markdown(
            f"<div style='color:{C['text3']};font-size:0.85rem'>Week-end — pas de trading.</div>",
            unsafe_allow_html=True,
        )
        return

    if s.error:
        st.error(f"**Erreur critique lors du scan** — {s.error[:300]}")
        return

    # ── Marché ────────────────────────────────────────────────────────
    if s.score_max or s.market_ctx:
        _section("Analyse de marché")
        cols = st.columns(4)
        cols[0].metric("Score max", s.score_max)
        cols[1].metric("Score médiane", s.score_median)
        cols[2].metric("Tickers scannés", s.n_tickers)
        cols[3].metric("Candidats retenus", s.n_candidates)

        if s.market_ctx:
            st.markdown(
                f"Contexte : {_ctx_badge(s.market_ctx)} &nbsp;·&nbsp; "
                f"Seuil score ≥ **{s.min_score}** &nbsp;·&nbsp; "
                f"Max **{s.max_opens}** positions",
                unsafe_allow_html=True,
            )

    # ── Mises à jour prix ─────────────────────────────────────────────
    if s.prices_updated or s.sltp_cash != 0 or s.closed or s.time_stops:
        _section("Mise à jour des positions")

        if s.prices_updated:
            pills = "  ".join(
                f"<span style='font:500 0.78rem/1 monospace;color:{C['text2']}'>"
                f"{t} <span style='color:{C['text3']}'>→</span> "
                f"<b>{p:.2f}</b></span>"
                for t, p in s.prices_updated.items()
            )
            st.markdown(pills, unsafe_allow_html=True)

        if s.sltp_cash != 0:
            color = _pnl_color(s.sltp_cash)
            st.markdown(
                f"💰 Cash flow du jour "
                f"<span style='color:{color};font-weight:700'>{s.sltp_cash:+.2f} €</span>"
                f"<span style='color:{C['text3']};font-size:0.8em'>"
                f" — cash reçu après SL/TP déclenchés</span>",
                unsafe_allow_html=True,
            )

        for t in s.closed:
            st.markdown(
                f"🔴 Position **{t}** fermée (SL ou TP total)",
                unsafe_allow_html=True,
            )

        for t in s.time_stops:
            st.markdown(
                f"⏱ **Time stop** déclenché sur **{t}** (position stagnante)",
                unsafe_allow_html=True,
            )

    # ── Achats ────────────────────────────────────────────────────────
    if s.buys:
        _section(f"Positions ouvertes ({len(s.buys)})")
        for b in s.buys:
            bull_str = (
                f"bull <span style='color:{C['up']}'>{b.bull}</span> · "
                f"bear <span style='color:{C['down']}'>{b.bear}</span> · "
                if b.bull is not None else ""
            )
            r_ratio = (b.tp1 - b.price) / (b.price - b.sl) if b.price > b.sl else 0
            st.markdown(
                f"<div style='background:{C['surf2']};border:1px solid {C['border']};"
                f"border-left:3px solid {C['up']};border-radius:6px;"
                f"padding:0.55rem 0.9rem;margin-bottom:0.4rem'>"
                f"<span style='color:{C['up']};font-weight:700;font-size:1rem'>{b.ticker}</span>"
                f"&nbsp; score <b>{b.score}</b> &nbsp;·&nbsp; {bull_str}"
                f"R = <b>{r_ratio:.2f}</b>"
                f"<br>"
                f"<span style='color:{C['text3']};font-size:0.8rem'>"
                f"Entrée {b.price:.4f} · Investi {b.invested:.0f} € · "
                f"SL {b.sl:.4f} · TP1 {b.tp1:.4f}"
                + (f" · ⚠ {' / '.join(b.bear_flags)}" if b.bear_flags else "")
                + "</span></div>",
                unsafe_allow_html=True,
            )

    # ── Skips ─────────────────────────────────────────────────────────
    if s.skips:
        with st.expander(f"Signaux écartés ({len(s.skips)})", expanded=False):
            for ticker, reason in s.skips:
                st.markdown(
                    f"<span style='color:{C['text2']};font-weight:600'>{ticker}</span>"
                    f"<span style='color:{C['text3']};font-size:0.82rem'> — {reason}</span>",
                    unsafe_allow_html=True,
                )

    # ── Pas de trade ──────────────────────────────────────────────────
    if not s.buys and s.budget_msg:
        st.markdown(
            f"<div style='color:{C['text3']};font-size:0.85rem;font-style:italic'>"
            f"Aucun achat — {s.budget_msg}</div>",
            unsafe_allow_html=True,
        )

    # ── Résumé portefeuille ───────────────────────────────────────────
    if s.total_value:
        _section("Résumé portefeuille")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Valeur totale",  f"{s.total_value:,.2f} €")
        c2.metric("Investi",        f"{s.total_invested:,.2f} €")
        c3.metric("Cash",           f"{s.total_cash:,.2f} €")
        c4.metric("Exposition",     f"{s.exposure_pct:.1f}%")
        c5.metric("Positions",      s.n_positions)

    # ── Budget hebdo ──────────────────────────────────────────────────
    if s.deploy_cash > 0:
        st.caption(f"Budget déployable semaine : {s.deploy_cash:,.0f} €")


# ── Page principale ───────────────────────────────────────────────────────────

def render(pm: PortfolioManager):
    st.title("Rapport quotidien")

    scans = parse_log(LOG_PATH)

    if not scans:
        st.info("Aucun log disponible.")
        return

    # ── Bandeau synthèse ──────────────────────────────────────────────
    last_buy = last_trade_date(scans)
    total_buys  = sum(len(s.buys) for s in scans)
    total_closes = sum(len(s.closed) for s in scans)
    total_sltp  = sum(s.sltp_cash for s in scans)

    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Dernier achat",      last_buy or "—")
    b2.metric("Total achats",       total_buys)
    b3.metric("Total fermetures",   total_closes)
    b4.metric("Cash flow (SL/TP)",  f"{total_sltp:+.2f} €",
              delta_color="normal")

    st.markdown(
        "<div style='height:1px;background:#1e2d45;margin:1rem 0 1.5rem;'></div>",
        unsafe_allow_html=True,
    )

    # ── Sélecteur de date ─────────────────────────────────────────────
    dates = [s.date for s in scans]
    sel_date = st.selectbox(
        "Date du rapport",
        options=dates,
        index=0,
        format_func=lambda d: f"📅 {d}",
        key="report_date",
    )

    scan = next(s for s in scans if s.date == sel_date)

    st.markdown(
        f"<h3 style='margin:1.2rem 0 0.2rem;font-size:1.1rem'>"
        f"Scan du {sel_date} "
        f"<span style='color:{C['text3']};font-size:0.78rem;font-weight:400'>"
        f"— {scan.time}</span></h3>",
        unsafe_allow_html=True,
    )

    _render_scan(scan)
