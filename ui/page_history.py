"""Historique des ordres — trades fermés + journal complet BUY/SELL."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from portfolio.manager import PortfolioManager
from ui.theme import plotly_layout, COLORS as C


# ─── Journal d'ordres ───────────────────────────────────────────────────────

def _build_order_log(pm: PortfolioManager) -> pd.DataFrame:
    events = []
    seen_close: set[tuple] = set()

    for h in pm.history:
        events.append({
            "Date":    h["entry_date"],
            "Ticker":  h["ticker"],
            "Type":    "BUY",
            "Qté":     round(h["qty"], 4),
            "Prix":    round(h["entry_price"], 4),
            "Montant": round(h["qty"] * h["entry_price"], 2),
            "PnL €":   None,
            "Raison":  "entrée",
        })
        events.append({
            "Date":    h["close_date"],
            "Ticker":  h["ticker"],
            "Type":    "SELL",
            "Qté":     round(h["qty"], 4),
            "Prix":    round(h["close_price"], 4),
            "Montant": round(h["qty"] * h["close_price"], 2),
            "PnL €":   round(h["pnl"], 2),
            "Raison":  h["close_reason"],
        })
        seen_close.add((h["ticker"], h["close_date"]))

    for ticker, pos in pm.positions.items():
        events.append({
            "Date":    pos.entry_date,
            "Ticker":  ticker,
            "Type":    "BUY",
            "Qté":     round(pos.qty_total, 4),
            "Prix":    round(pos.entry_price, 4),
            "Montant": round(pos.qty_total * pos.entry_price, 2),
            "PnL €":   None,
            "Raison":  "entrée",
        })
        for f in pos.partial_fills:
            pnl_fill = (f.price - pos.entry_price) * f.qty
            events.append({
                "Date":    f.date,
                "Ticker":  ticker,
                "Type":    "SELL partiel",
                "Qté":     round(f.qty, 4),
                "Prix":    round(f.price, 4),
                "Montant": round(f.qty * f.price, 2),
                "PnL €":   round(pnl_fill, 2),
                "Raison":  f.reason,
            })
        if (pos.is_closed and pos.close_price and pos.close_date
                and (ticker, pos.close_date) not in seen_close):
            pnl_pos = (pos.close_price - pos.entry_price) * pos.qty_total
            events.append({
                "Date":    pos.close_date,
                "Ticker":  ticker,
                "Type":    "SELL",
                "Qté":     round(pos.qty_remaining or pos.qty_total, 4),
                "Prix":    round(pos.close_price, 4),
                "Montant": round((pos.qty_remaining or pos.qty_total) * pos.close_price, 2),
                "PnL €":   round(pnl_pos, 2),
                "Raison":  "close",
            })

    df = pd.DataFrame(events)
    if df.empty:
        return df
    return df.sort_values("Date", ascending=False).reset_index(drop=True)


# ─── Page ───────────────────────────────────────────────────────────────────

def render(pm: PortfolioManager):
    st.title("Historique des ordres")

    tab1, tab2 = st.tabs(["📈 Performances trades", "📋 Journal des ordres"])

    # ══════════════════════════════════════════════════════════════════
    with tab1:
        history = pm.history
        if not history:
            st.info("Aucun trade fermé pour l'instant.")
        else:
            df = pd.DataFrame(history)
            total_trades = len(df)
            wins         = df[df["pnl"] > 0]
            losses       = df[df["pnl"] <= 0]
            win_rate     = len(wins) / total_trades * 100 if total_trades else 0
            avg_win      = float(wins["pnl"].mean())   if len(wins)   else 0.0
            avg_loss     = float(losses["pnl"].mean()) if len(losses) else 0.0
            total_fees   = float(df["fees_total"].sum())
            total_pnl    = float(df["pnl"].sum())
            pf = abs(avg_win / avg_loss) if avg_loss != 0 else None

            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Trades",        total_trades)
            c2.metric("Win rate",      f"{win_rate:.1f}%")
            c3.metric("PnL net",       f"{total_pnl:+.2f} €",
                      delta_color="normal")
            c4.metric("Gain moyen",    f"{avg_win:+.2f} €")
            c5.metric("Perte moyenne", f"{avg_loss:+.2f} €",
                      delta_color="inverse")
            c6.metric("Profit factor", f"{pf:.2f}" if pf is not None else "∞")

            st.caption(f"Frais totaux : {total_fees:.2f} €")
            st.markdown("---")

            # ── Courbe de capital ─────────────────────────────────────
            df_s = df.sort_values("close_date").copy()
            df_s["cum_pnl"] = df_s["pnl"].cumsum()
            df_s["capital"] = pm.initial_cash + df_s["cum_pnl"]

            fig_eq = go.Figure()
            # Fill above/below baseline
            fig_eq.add_trace(go.Scatter(
                x=df_s["close_date"],
                y=[pm.initial_cash] * len(df_s),
                mode="lines", line=dict(width=0),
                showlegend=False, hoverinfo="skip",
            ))
            fig_eq.add_trace(go.Scatter(
                x=df_s["close_date"], y=df_s["capital"],
                mode="lines",
                fill="tonexty",
                fillcolor=C["up_bg"] if total_pnl >= 0 else C["down_bg"],
                line=dict(color=C["accent"], width=0),
                showlegend=False, hoverinfo="skip",
            ))
            fig_eq.add_trace(go.Scatter(
                x=df_s["close_date"], y=df_s["capital"],
                mode="lines+markers",
                line=dict(color=C["accent"], width=2),
                marker=dict(size=6, color=C["accent"],
                            line=dict(color=C["bg"], width=2)),
                name="Capital",
                hovertemplate="<b>%{x}</b><br>%{y:,.2f} €<extra></extra>",
            ))
            fig_eq.add_hline(
                y=pm.initial_cash,
                line=dict(color=C["text3"], dash="dash", width=1),
                annotation_text=f"Capital initial {pm.initial_cash:,.0f} €",
                annotation_font_color=C["text3"],
                annotation_font_size=10,
                annotation_position="bottom right",
            )
            fig_eq.update_layout(
                **plotly_layout(height=260, title="Courbe de capital"),
                showlegend=False,
            )
            st.plotly_chart(fig_eq, width="stretch")

            # ── PnL par trade ─────────────────────────────────────────
            bar_colors = [
                C["up"] if p > 0 else C["down"]
                for p in df_s["pnl"]
            ]
            fig_bar = go.Figure(go.Bar(
                x=df_s["ticker"] + " · " + df_s["close_date"].str[:10],
                y=df_s["pnl"],
                marker=dict(
                    color=bar_colors,
                    line=dict(color=C["bg"], width=1),
                    opacity=0.85,
                ),
                text=df_s["pnl"].apply(lambda x: f"{x:+.2f}"),
                textposition="outside",
                textfont=dict(
                    color=[C["up"] if p > 0 else C["down"] for p in df_s["pnl"]],
                    size=10, family="'JetBrains Mono', monospace",
                ),
                hovertemplate="<b>%{x}</b><br>PnL : %{y:+.2f} €<extra></extra>",
            ))
            fig_bar.update_layout(
                **plotly_layout(height=300, title="PnL par trade (€)"),
                bargap=0.35,
            )
            st.plotly_chart(fig_bar, width="stretch")

            # ── Pie raisons de clôture ────────────────────────────────
            reason_counts = df["close_reason"].value_counts()
            reason_palette = [
                C["down"], C["up"], C["accent"], C["amber"],
                C["purple"], C["blue"],
            ]
            fig_rea = go.Figure(go.Pie(
                labels=reason_counts.index.tolist(),
                values=reason_counts.values.tolist(),
                hole=0.45,
                marker=dict(
                    colors=reason_palette[:len(reason_counts)],
                    line=dict(color=C["bg"], width=2),
                ),
                textinfo="label+percent",
                textfont=dict(color=C["text1"], size=11),
                hovertemplate="<b>%{label}</b><br>%{value} trades<br>%{percent}<extra></extra>",
            ))
            fig_rea.update_layout(
                **plotly_layout(height=240, title="Raisons de clôture",
                                margin=dict(t=40, b=10, l=10, r=10),
                                showlegend=False),
            )
            st.plotly_chart(fig_rea, width="stretch")

            # ── Tableau détaillé ──────────────────────────────────────
            st.subheader("Détail des trades fermés")
            display = df[[
                "ticker", "entry_date", "close_date",
                "entry_price", "close_price", "qty",
                "pnl", "fees_total", "close_reason",
            ]].copy()
            display.columns = [
                "Ticker", "Entrée", "Clôture",
                "Prix entrée", "Prix clôture", "Qté",
                "PnL €", "Frais €", "Raison",
            ]
            display["PnL €"] = display["PnL €"].apply(lambda x: f"{x:+.2f}")

            def _style_pnl(val):
                if isinstance(val, str) and val.startswith("+"):
                    return f"color:{C['up']};font-weight:600"
                if isinstance(val, str) and val.startswith("-"):
                    return f"color:{C['down']};font-weight:600"
                return ""

            st.dataframe(
                display.style.map(_style_pnl, subset=["PnL €"]),
                width="stretch", hide_index=True,
            )

    # ══════════════════════════════════════════════════════════════════
    with tab2:
        st.subheader("Journal des ordres")
        df_log = _build_order_log(pm)

        if df_log.empty:
            st.info("Aucun ordre enregistré.")
            return

        # Filtres
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            all_tickers = sorted(df_log["Ticker"].unique().tolist())
            sel_tickers = st.multiselect("Ticker(s)", all_tickers, default=[])
        with col_f2:
            all_types = sorted(df_log["Type"].unique().tolist())
            sel_types = st.multiselect("Type d'ordre", all_types, default=[])
        with col_f3:
            all_raisons = sorted(df_log["Raison"].unique().tolist())
            sel_raisons = st.multiselect("Raison", all_raisons, default=[])

        df_f = df_log.copy()
        if sel_tickers:
            df_f = df_f[df_f["Ticker"].isin(sel_tickers)]
        if sel_types:
            df_f = df_f[df_f["Type"].isin(sel_types)]
        if sel_raisons:
            df_f = df_f[df_f["Raison"].isin(sel_raisons)]

        st.caption(f"{len(df_f)} ordre(s) affiché(s) sur {len(df_log)} total")

        buys        = df_f[df_f["Type"] == "BUY"]["Montant"].sum()
        sells       = df_f[df_f["Type"].str.startswith("SELL")]["Montant"].sum()
        pnl_visible = df_f[df_f["PnL €"].notna()]["PnL €"].sum()

        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Volume BUY",  f"{buys:,.2f} €")
        cc2.metric("Volume SELL", f"{sells:,.2f} €")
        cc3.metric("PnL affiché", f"{pnl_visible:+.2f} €", delta_color="normal")

        df_display = df_f.copy()
        df_display["PnL €"] = df_display["PnL €"].apply(
            lambda v: "—" if v is None or (isinstance(v, float) and pd.isna(v))
            else f"{v:+.2f}"
        )

        def _style_type(val):
            if val == "BUY":
                return f"color:{C['blue']};font-weight:600"
            if "SELL" in str(val):
                return f"color:{C['down']};font-weight:600"
            return ""

        def _style_pnl2(val):
            if isinstance(val, str) and val.startswith("+"):
                return f"color:{C['up']};font-weight:600"
            if isinstance(val, str) and val.startswith("-"):
                return f"color:{C['down']};font-weight:600"
            return ""

        st.dataframe(
            df_display.style
            .map(_style_type,  subset=["Type"])
            .map(_style_pnl2, subset=["PnL €"]),
            width="stretch", hide_index=True,
        )
