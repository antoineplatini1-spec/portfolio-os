"""Momentum PTF — poche pilotée par la newsletter Capital Momentum.

Vue dédiée : métriques de la poche, positions, historique, et surtout le
JOURNAL D'INTERPRÉTATION — pour chaque newsletter, ce que le bot a lu et décidé.
"""

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from data.fetcher import fetch_ohlcv
from portfolio.momentum_portfolio import MomentumPortfolio
from ui.theme import COLORS as C

_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
_SIGNALS_FILE = _data_dir / "momentum_signals.jsonl"


@st.cache_data(ttl=60)
def _live_price(ticker: str) -> float | None:
    try:
        df = fetch_ohlcv(ticker, period="5d", interval="1d")
        return float(df["Close"].iloc[-1]) if not df.empty else None
    except Exception:
        return None


def _load_signals() -> list[dict]:
    if not _SIGNALS_FILE.exists():
        return []
    out = []
    with open(_SIGNALS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    # plus récent en premier
    return sorted(out, key=lambda r: r.get("date", ""), reverse=True)


_ACTION_COLOR = {"BUY": C["up"], "SELL": C["down"], "AVOID": C["down"],
                 "HOLD": C["text3"], "CAUTION": C["amber"]}


def render():
    st.title("📰 Momentum PTF — Capital Momentum")
    st.caption("Poche pilotée exclusivement par la newsletter de midi. "
               "Achats/ventes selon les recommandations parsées.")

    mpm = MomentumPortfolio()

    # ── Métriques de la poche ─────────────────────────────────────────────
    total = mpm.total_value
    pnl = mpm.pnl_realized + mpm.pnl_unrealized
    perf_pct = (total - mpm.initial_cash) / mpm.initial_cash * 100 if mpm.initial_cash else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valeur poche", f"{total:,.0f} €", f"{perf_pct:+.2f}%")
    c2.metric("Cash dispo", f"{mpm.cash:,.0f} €")
    c3.metric("PnL total", f"{pnl:+,.0f} €")
    c4.metric("Positions", len(mpm.open_positions))

    signals = _load_signals()
    if not signals and not mpm.open_positions and not mpm.history:
        st.info("Poche en attente : aucune newsletter encore traitée. "
                "Elle se remplira dès le prochain scan avec une newsletter exploitable.")

    # ── Positions ouvertes ────────────────────────────────────────────────
    st.markdown("### Positions ouvertes")
    if mpm.open_positions:
        rows = []
        for t, p in mpm.open_positions.items():
            live = _live_price(t) or p.entry_price
            pnl_e = (live - p.entry_price) * p.qty_remaining
            pnl_p = (live / p.entry_price - 1) * 100 if p.entry_price else 0
            eff_sl = p.trailing_stop_price if p.trailing_stop else p.sl
            tps = " / ".join(f"{tp.price:.2f}{'✓' if tp.hit else ''}" for tp in p.tp_levels)
            rows.append({
                "Ticker": t, "Entrée": round(p.entry_price, 2), "Live": round(live, 2),
                "PnL %": round(pnl_p, 1), "PnL €": round(pnl_e, 0),
                "SL": round(eff_sl, 2), "TPs": tps,
                "Entrée le": p.entry_date or "—",
            })
        df = pd.DataFrame(rows)

        def _clr(v):
            if isinstance(v, (int, float)):
                return f"color:{C['up']}" if v >= 0 else f"color:{C['down']}"
            return ""
        st.dataframe(df.style.map(_clr, subset=["PnL %", "PnL €"]),
                     width="stretch", hide_index=True)
    else:
        st.caption("Aucune position ouverte.")

    # ── Journal d'interprétation des newsletters ──────────────────────────
    st.markdown("### 🧠 Comment le bot a lu chaque newsletter")
    if not signals:
        st.caption("Aucune newsletter interprétée pour l'instant.")
    else:
        for rec in signals:
            date = rec.get("date", "?")
            subject = rec.get("subject", "")
            source = rec.get("source", "")
            trades = rec.get("trades", [])
            n_buy = sum(1 for t in trades if t.get("action") == "BUY")
            header = f"📅 {date} — {len(trades)} société(s) lue(s), {n_buy} achat(s)"
            with st.expander(header, expanded=(rec is signals[0])):
                if subject:
                    st.caption(f"Sujet : {subject[:120]}  ·  source : {source}")
                for t in trades:
                    action = t.get("action", "?")
                    clr = _ACTION_COLOR.get(action, C["text3"])
                    tps = t.get("tp", [])
                    tps_str = " / ".join(f"{x:.2f}" for x in tps) if tps else "—"
                    sl = t.get("sl", 0)
                    sl_str = f"{sl:.2f}" if sl else "défaut -7%"
                    st.markdown(
                        f"<div style='margin:6px 0;padding:8px 12px;background:{C['surf2']};"
                        f"border-left:3px solid {clr};border-radius:6px'>"
                        f"<b style='color:{C['text2']}'>{t.get('company','?')}</b> "
                        f"<span style='color:{C['text3']};font-size:0.8rem'>({t.get('ticker','?')})</span> "
                        f"&nbsp;<b style='color:{clr}'>{action}</b><br>"
                        f"<span style='color:{C['text3']};font-size:0.82rem'>"
                        f"Objectifs : {tps_str} &nbsp;·&nbsp; SL : {sl_str}</span><br>"
                        f"<span style='color:{C['text2']};font-size:0.85rem'>"
                        f"→ {t.get('decision','')}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    raw = t.get("raw_rec", "")
                    if raw:
                        st.caption(f"« {raw.strip()[:300]} »")

    # ── Historique des trades clôturés ────────────────────────────────────
    st.markdown("### Historique des trades clôturés")
    if mpm.history:
        hrows = []
        for h in sorted(mpm.history, key=lambda x: x.get("close_date", ""), reverse=True):
            hrows.append({
                "Ticker": h.get("ticker"), "Entrée": round(h.get("entry_price", 0), 2),
                "Sortie": round(h.get("close_price", 0), 2),
                "PnL €": round(h.get("pnl", 0), 0), "Raison": h.get("close_reason", ""),
                "Clôturé le": h.get("close_date", ""),
            })
        hdf = pd.DataFrame(hrows)

        def _clr2(v):
            if isinstance(v, (int, float)):
                return f"color:{C['up']}" if v >= 0 else f"color:{C['down']}"
            return ""
        st.dataframe(hdf.style.map(_clr2, subset=["PnL €"]),
                     width="stretch", hide_index=True)
    else:
        st.caption("Aucun trade clôturé pour l'instant.")
