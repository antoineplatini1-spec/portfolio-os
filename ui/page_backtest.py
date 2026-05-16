"""Page Backtest : rejoue la stratégie jour par jour depuis une date."""

import random
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date

from config import DEFAULT_WATCHLIST, INITIAL_CASH, SECTOR_MAP


def render(_pm=None):
    st.title("Backtest — Stratégie jour par jour")

    # ── Paramètres ────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        start = st.date_input("Début", value=date(2025, 1, 1))
    with col2:
        end = st.date_input("Fin", value=date.today())
    with col3:
        capital = st.number_input("Capital initial (€)", value=float(INITIAL_CASH), min_value=1000.0)
    with col4:
        min_score = st.slider("Score minimum signal", 20, 80, 45)

    # ── Positions préexistantes ───────────────────────────────────
    with st.expander("Portefeuille de départ (optionnel)", expanded=False):
        st.caption(
            "Simule un portefeuille déjà en place au jour 1. "
            "Ces positions sont achetées au prix d'ouverture du premier jour "
            "et conservées sans TP/SL. La stratégie tourne sur le cash restant."
        )

        rc1, rc2, rc3 = st.columns([1, 1, 3])
        with rc1:
            target_pct = st.slider("% du capital à investir", 10, 90, 80, step=5,
                                   help="Part du capital mobilisée par le portefeuille initial")
        with rc2:
            n_random = st.number_input("Nb positions", min_value=2, max_value=20, value=8, step=1)
        with rc3:
            st.write("")
            st.write("")
            if st.button("Générer aléatoirement", key="btn_backtest_random"):
                rng = random.Random()
                # Exclure ETF macro/volatilité, prendre actions diversifiées
                universe = [t for t in DEFAULT_WATCHLIST
                            if SECTOR_MAP.get(t, "") not in ("Macro", "ETF")]
                n = min(int(n_random), len(universe))
                picks = rng.sample(universe, n)
                # Répartition aléatoire : poids Dirichlet-like
                weights = [rng.uniform(0.5, 2.0) for _ in picks]
                total_w = sum(weights)
                budget = capital * target_pct / 100
                amounts = [round(budget * w / total_w / 100) * 100 for w in weights]
                # Ajuster le dernier pour coller exactement au budget
                amounts[-1] = max(100, budget - sum(amounts[:-1]))
                st.session_state["rand_positions"] = [
                    {"ticker": t, "amount": a} for t, a in zip(picks, amounts)
                ]
                st.rerun()

        # Positions (manuel ou générées)
        rand = st.session_state.get("rand_positions", [])
        n_init = st.number_input("Nombre de positions manuelles", min_value=0, max_value=20,
                                  value=len(rand) if rand else 0, step=1,
                                  help="Modifie ce chiffre pour ajouter/supprimer des lignes manuelles")

        alloc_configs = []
        n_rows = max(int(n_init), len(rand))
        if n_rows > 0:
            header = st.columns([2, 1])
            header[0].markdown("**Ticker**")
            header[1].markdown("**Montant (€)**")
        for i in range(n_rows):
            default_t = rand[i]["ticker"] if i < len(rand) else "SPY"
            default_a = float(rand[i]["amount"]) if i < len(rand) else round(capital * 0.05, 0)
            c1, c2 = st.columns([2, 1])
            with c1:
                t = st.text_input("", value=default_t, key=f"it_{i}",
                                  label_visibility="collapsed").upper().strip()
            with c2:
                amt = st.number_input("", min_value=100.0, value=default_a,
                                      key=f"ia_{i}", label_visibility="collapsed")
            if t:
                alloc_configs.append({"ticker": t, "amount": amt})

    total_alloc = sum(a["amount"] for a in alloc_configs)
    strategy_capital = capital - total_alloc
    if total_alloc > 0:
        pct_alloc = total_alloc / capital * 100
        pct_strat = strategy_capital / capital * 100
        st.info(
            f"Portefeuille initial : **{total_alloc:,.0f} €** ({pct_alloc:.0f}%) · "
            f"Cash stratégie : **{strategy_capital:,.0f} €** ({pct_strat:.0f}%)"
        )
    if strategy_capital < 0:
        st.error(f"Le portefeuille initial ({total_alloc:,.0f} €) dépasse le capital ({capital:,.0f} €).")
        return

    # ── Sélection des tickers stratégie ──────────────────────────
    with st.expander(f"Tickers stratégie ({len(DEFAULT_WATCHLIST)} disponibles)"):
        selected = st.multiselect(
            "Sélection",
            DEFAULT_WATCHLIST,
            default=DEFAULT_WATCHLIST[:40],
        )

    if st.button("Lancer le backtest", key="btn_run_backtest", type="primary"):
        if not selected:
            st.error("Sélectionne au moins un ticker.")
            return
        if start >= end:
            st.error("La date de début doit être antérieure à la date de fin.")
            return

        from backtest.engine import BacktestEngine, FixedAllocation

        # Positions préexistantes = achat lump au jour 1
        fixed = [
            FixedAllocation(
                ticker=a["ticker"],
                amount=a["amount"],
                alloc_start=start,
                alloc_end=start,
                mode="lump",
            )
            for a in alloc_configs
            if a["ticker"]
        ]

        engine = BacktestEngine(
            tickers=selected,
            start=start,
            end=end,
            initial_cash=capital,
            min_score=min_score,
            fixed_allocations=fixed,
        )

        # ── Chargement des données ────────────────────────────────
        st.markdown("**Étape 1/3 — Chargement des données**")
        bar = st.progress(0)
        status = st.empty()

        def load_cb(i, total, ticker):
            bar.progress((i + 1) / total)
            status.caption(f"Chargement {ticker} ({i+1}/{total})")

        errors = engine.load_data(progress_cb=load_cb)
        bar.empty()
        loaded = len(engine._data)
        status.caption(f"{loaded} actifs chargés, {len(errors)} erreurs.")
        if errors:
            with st.expander("Tickers en erreur"):
                st.json(errors)

        if not engine._trading_days:
            st.error("Aucun jour de trading trouvé sur la période.")
            return

        # ── Simulation ────────────────────────────────────────────
        st.markdown(f"**Étape 2/3 — Simulation ({len(engine._trading_days)} jours de trading)**")
        bar2 = st.progress(0)
        status2 = st.empty()

        def run_cb(i, total, day):
            bar2.progress((i + 1) / total)
            status2.caption(f"Jour {i+1}/{total} — {day}")

        engine.run(progress_cb=run_cb)
        engine.close_all_at_end()
        bar2.empty()
        status2.empty()

        # ── Résultats ─────────────────────────────────────────────
        st.markdown("**Étape 3/3 — Résultats**")
        stats = engine.stats()
        st.session_state["bt_engine"] = engine
        st.session_state["bt_stats"] = stats

    # ── Affichage des résultats ───────────────────────────────────
    engine = st.session_state.get("bt_engine")
    stats  = st.session_state.get("bt_stats")
    if engine is None:
        return

    st.markdown("---")

    # Diagnostic : signaux et trades
    total_signals = sum(getattr(engine, "signals_per_day", {}).values())
    st.info(
        f"**{len(engine.trades)} trades** réalisés · "
        f"{total_signals} signaux détectés sur {len(engine._trading_days)} jours · "
        f"Score minimum utilisé : {engine.min_score}"
    )

    if not engine.trades:
        st.warning(
            "Aucun trade exécuté. Causes possibles :\n"
            "- Score minimum trop élevé — essaie 30–40\n"
            "- Tickers sans signal sur la période\n"
            "- Budget ramp-up épuisé (phase 1 = 25%/semaine)"
        )
        # Scores max observés pour aider à calibrer le seuil
        with st.expander("Diagnostic — scores observés"):
            scores_debug = []
            for ticker in engine._data:
                df = engine._data[ticker]
                hist = df[df.index.date < engine.end]
                if len(hist) < 50:
                    continue
                from indicators import compute_all
                from signals.scoring import compute_score
                try:
                    r = compute_score(compute_all(hist), ticker=ticker)
                    scores_debug.append({"Ticker": ticker, "Score": r["score"]})
                except Exception:
                    pass
            if scores_debug:
                sd = pd.DataFrame(scores_debug).sort_values("Score", ascending=False)
                st.dataframe(sd, hide_index=True, width='stretch')
        return

    if not stats:
        return

    # ── KPI ───────────────────────────────────────────────────────
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Capital initial", f"{engine.initial_cash:,.2f} €")
    col2.metric("Capital final", f"{stats['final_value']:,.2f} €")
    col3.metric("PnL net", f"{stats['total_pnl']:+,.2f} €",
                f"{stats['total_pnl_pct']:+.2f}%",
                delta_color="normal" if stats["total_pnl"] >= 0 else "inverse")
    col4.metric("Max drawdown", f"{stats['max_drawdown_pct']:.1f}%", delta_color="inverse")
    col5.metric("Sharpe", f"{stats['sharpe']:.2f}")
    col6.metric("Win rate", f"{stats['win_rate']:.1f}%")

    col7, col8, col9, col10 = st.columns(4)
    col7.metric("Trades", stats["total_trades"])
    col8.metric("Profit factor", f"{stats['profit_factor']:.2f}")
    col9.metric("Gain moyen", f"{stats['avg_win']:+.2f} €")
    col10.metric("Frais totaux", f"{stats['total_fees']:.2f} €")

    col_ann, col_vol, col_calmar, col_hold = st.columns(4)
    col_ann.metric("Rend. annualisé", f"{stats.get('annualized_return', 0):+.1f}%")
    col_vol.metric("Volatilité", f"{stats.get('volatility', 0):.1f}%")
    col_calmar.metric("Calmar", f"{stats.get('calmar', 0):.2f}")
    col_hold.metric("Durée moy.", f"{stats.get('avg_holding_days', 0):.0f}j")

    # ── Courbe de capital ─────────────────────────────────────────
    eq_df = pd.DataFrame([s.__dict__ for s in engine.equity_curve])
    eq_df["day"] = pd.to_datetime(eq_df["day"])

    # Benchmark SPY (si disponible dans les données)
    spy_df = engine._data.get("SPY")

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.55, 0.25, 0.20],
                        vertical_spacing=0.04,
                        subplot_titles=("Capital & Benchmark", "Positions ouvertes", "PnL journalier"))

    # Capital total
    fig.add_trace(go.Scatter(
        x=eq_df["day"], y=eq_df["portfolio_value"],
        name="Portefeuille total", line=dict(color="#26a69a", width=2),
        fill="tozeroy", fillcolor="rgba(38,166,154,0.08)",
    ), row=1, col=1)

    # Poche stratégie seule
    if "strategy_value" in eq_df.columns and eq_df["strategy_value"].sum() > 0:
        fig.add_trace(go.Scatter(
            x=eq_df["day"], y=eq_df["cash"] + eq_df["strategy_value"],
            name="Stratégie seule", line=dict(color="#29b6f6", width=1.5, dash="dot"),
        ), row=1, col=1)

    # Poche allocation fixe seule
    if "alloc_value" in eq_df.columns and eq_df["alloc_value"].sum() > 0:
        fig.add_trace(go.Scatter(
            x=eq_df["day"], y=eq_df["alloc_value"],
            name="Allocation fixe", line=dict(color="#ffb300", width=1.5, dash="dash"),
        ), row=1, col=1)

    # Capital initial (ligne de référence)
    fig.add_hline(y=engine.initial_cash, row=1, col=1,
                  line=dict(color="#546e7a", dash="dash"),
                  annotation_text="Capital initial")

    # Benchmark SPY normalisé
    if spy_df is not None and not spy_df.empty:
        spy_period = spy_df[spy_df.index.date >= engine.start]
        if not spy_period.empty:
            spy_norm = spy_period["Close"] / spy_period["Close"].iloc[0] * engine.initial_cash
            fig.add_trace(go.Scatter(
                x=spy_period.index, y=spy_norm,
                name="SPY (benchmark)", line=dict(color="#ff7043", width=1.5, dash="dot"),
            ), row=1, col=1)

    # Nb positions
    fig.add_trace(go.Scatter(
        x=eq_df["day"], y=eq_df["n_positions"],
        name="Positions", line=dict(color="#ffb300", width=1.5),
        fill="tozeroy", fillcolor="rgba(255,179,0,0.1)",
    ), row=2, col=1)

    # PnL journalier
    colors = ["#26a69a" if v >= 0 else "#ef5350" for v in eq_df["daily_pnl"]]
    fig.add_trace(go.Bar(
        x=eq_df["day"], y=eq_df["daily_pnl"],
        name="PnL jour", marker_color=colors, opacity=0.7,
    ), row=3, col=1)

    fig.update_layout(
        template="plotly_dark", height=700,
        legend=dict(orientation="h", y=1.02),
        margin=dict(t=60, b=30),
        title="<b>Résultats du backtest</b>",
    )
    st.plotly_chart(fig, width='stretch')

    # ── Drawdown ──────────────────────────────────────────────────
    eq = eq_df["portfolio_value"]
    roll_max = eq.cummax()
    dd_pct = (eq - roll_max) / roll_max * 100

    fig_dd = go.Figure(go.Scatter(
        x=eq_df["day"], y=dd_pct,
        fill="tozeroy", fillcolor="rgba(239,83,80,0.2)",
        line=dict(color="#ef5350", width=1),
        name="Drawdown %",
    ))
    fig_dd.update_layout(
        template="plotly_dark", height=200, title="Drawdown (%)",
        margin=dict(t=40, b=20),
        yaxis=dict(ticksuffix="%"),
    )
    st.plotly_chart(fig_dd, width='stretch')

    # ── Rendements mensuels ───────────────────────────────────────
    monthly = stats.get("monthly_returns", {})
    if monthly:
        st.subheader("Rendements mensuels (%)")
        monthly_df = pd.DataFrame(
            list(monthly.items()), columns=["Mois", "Rendement (%)"]
        ).set_index("Mois")

        fig_m = go.Figure(go.Bar(
            x=list(monthly.keys()),
            y=list(monthly.values()),
            marker_color=["#26a69a" if v >= 0 else "#ef5350" for v in monthly.values()],
            text=[f"{v:+.1f}%" for v in monthly.values()],
            textposition="outside",
        ))
        fig_m.update_layout(
            template="plotly_dark", height=280,
            margin=dict(t=20, b=40),
            yaxis=dict(ticksuffix="%"),
        )
        st.plotly_chart(fig_m, width="stretch")

    # ── Tableau des trades ────────────────────────────────────────
    st.subheader(f"Trades ({stats['total_trades']})")
    trades_df = pd.DataFrame([t.__dict__ for t in engine.trades])
    if not trades_df.empty:
        trades_df["pnl"] = trades_df["pnl"].apply(lambda x: f"{x:+.2f} €")
        trades_df["entry_price"] = trades_df["entry_price"].apply(lambda x: f"{x:.2f}")
        trades_df["exit_price"]  = trades_df["exit_price"].apply(lambda x: f"{x:.2f}")
        trades_df = trades_df.rename(columns={
            "ticker": "Ticker", "entry_date": "Entrée", "exit_date": "Sortie",
            "entry_price": "Prix entrée", "exit_price": "Prix sortie",
            "qty": "Qté", "pnl": "PnL", "fees": "Frais", "reason": "Raison",
        })
        st.dataframe(trades_df[["Ticker","Entrée","Sortie","Prix entrée","Prix sortie","Qté","PnL","Frais","Raison"]],
                     width='stretch', hide_index=True)

    # ── Best / Worst ──────────────────────────────────────────────
    if stats.get("best_trade") and stats.get("worst_trade"):
        col_b, col_w = st.columns(2)
        b = stats["best_trade"]
        w = stats["worst_trade"]
        col_b.success(f"Meilleur trade : **{b.get('ticker','')}** "
                      f"({b.get('entry_date','')} → {b.get('exit_date','')}) "
                      f"**+{b.get('pnl',0):.2f} €** [{b.get('reason','')}]")
        col_w.error(f"Pire trade : **{w.get('ticker','')}** "
                    f"({w.get('entry_date','')} → {w.get('exit_date','')}) "
                    f"**{w.get('pnl',0):.2f} €** [{w.get('reason','')}]")

    # ── Log d'activité ────────────────────────────────────────────
    with st.expander("Log d'activité détaillé"):
        st.text("\n".join(engine.log[-200:]))
