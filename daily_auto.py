# -*- coding: utf-8 -*-
"""
Automatisation quotidienne du paper trading.
Lance chaque matin par le Planificateur de taches Windows.

Actions :
  1. Mise a jour des prix + declenchement SL/TP
  2. Scan des nouvelles opportunites
  3. Ouverture de positions si signaux + budget disponible
  4. Log horodate dans data/daily_log.txt
"""

import sys, os, io, json, traceback
from collections import Counter
from datetime import datetime, date
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from utils.near_miss import save_near_miss, purge_old_entries

BASE = os.path.dirname(__file__)
sys.path.insert(0, BASE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr  = io.TextIOWrapper(sys.stderr.buffer,  encoding='utf-8', errors='replace')

# ── ETFs sectoriels → secteur sous-jacent (pour le véto de concentration) ─────
_ETF_TO_UNDERLYING = {
    "SMH": "Semi",  "SOXX": "Semi",
    "XLK": "Tech",  "ARKK": "Tech", "ARKG": "Tech",
    "XLF": "Finance",
    "XLV": "Santé", "IBB": "Santé", "XBI": "Santé",
    "XLE": "Energie",
    "XLI": "Industrie",
    "XLY": "Conso",
    "XLP": "ConsoBase",
    "XLB": "Materiaux",
    "XLRE": "REIT",
}


def _near_earnings(ticker: str, days: int = 3) -> bool:
    """True si une publication de résultats tombe dans les `days` prochains/derniers jours."""
    try:
        import yfinance as yf
        from datetime import timedelta
        cal = yf.Ticker(ticker).calendar
        if not cal:
            return False
        today = date.today()
        # calendar peut être un dict {"Earnings Date": [...]} selon la version yfinance
        if isinstance(cal, dict):
            earn_dates = cal.get("Earnings Date", [])
            if not isinstance(earn_dates, (list, tuple)):
                earn_dates = [earn_dates]
        elif hasattr(cal, "index"):
            try:
                earn_dates = list(cal.loc["Earnings Date"])
            except Exception:
                return False
        else:
            return False
        for d in earn_dates:
            try:
                from datetime import datetime as _dt
                d_date = _dt.fromisoformat(str(d)[:10]).date()
                if abs((d_date - today).days) <= days:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False

_data_dir = os.environ.get("DATA_DIR", os.path.join(BASE, "data"))
os.makedirs(_data_dir, exist_ok=True)
LOG_FILE = os.path.join(_data_dir, "daily_log.txt")

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load_email_cfg() -> dict | None:
    cfg_path = os.path.join(_data_dir, "email_config.json")
    if not os.path.exists(cfg_path):
        return None
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def send_email(subject: str, html_body: str):
    """Envoie un email HTML via Gmail SMTP."""
    cfg = _load_email_cfg()
    if not cfg:
        log("[EMAIL] email_config.json introuvable - email non envoye")
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg["sender"]
        msg["To"]      = cfg["recipient"]
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["sender"], cfg["password"])
            server.sendmail(cfg["sender"], cfg["recipient"], msg.as_string())
        log(f"[EMAIL] Envoye a {cfg['recipient']}")
    except Exception as e:
        log(f"[EMAIL ERROR] {e}")


def run():
    today = date.today()
    # Pas de trading le week-end
    if today.weekday() >= 5:
        log(f"Week-end ({today.strftime('%A')}) - pas de trading.")
        return

    log("=" * 60)
    log(f"SCAN JOURNALIER - {today}")
    log("=" * 60)

    from portfolio.manager import PortfolioManager
    from signals.screener import run_screener
    from signals.agent_debate import run_debate
    from data.fetcher import fetch_ohlcv
    from indicators import compute_all
    from signals.scoring import compute_score
    from config import DEFAULT_WATCHLIST, SECTOR_MAP, MIN_R_RATIO
    from signals.macro_agent import MacroAgent
    from config import MAX_TRADES_PER_DAY

    pm = PortfolioManager()

    # ── 0. Contexte macro + Newsletter ──────────────────────────────
    from signals.newsletter_agent import NewsletterAgent
    nl_signal = None
    try:
        nl_signal = NewsletterAgent().fetch_and_parse()
        for line in nl_signal.format_log():
            log(line)
    except Exception as e:
        log(f"[NEWSLETTER] Erreur lecture : {e}")

    macro_ctx = MacroAgent().analyze(newsletter_signal=nl_signal)
    for line in macro_ctx.format_log():
        log(line)

    # Purger les near-misses anciens en début de session
    purge_old_entries(_data_dir)

    # Variables recap email
    opened_positions_log: list[dict] = []
    sales_log: list[dict] = []        # achats partiels TP + clôtures SL/time stop
    sltp_cash_delta: float = 0.0

    # ── 1. Mise a jour des prix des positions ouvertes ────────────
    open_pos = pm.open_positions
    if open_pos:
        log(f"{len(open_pos)} position(s) ouverte(s) - mise a jour des prix...")
        prices = {}
        for ticker in open_pos:
            try:
                df = fetch_ohlcv(ticker, period="5d", interval="1d", force_refresh=True)
                if not df.empty:
                    prices[ticker] = float(df["Close"].iloc[-1])
                    log(f"  {ticker}: {prices[ticker]:.2f}")
            except Exception as e:
                log(f"  {ticker}: erreur prix - {e}")

        # Snapshot fills avant update (pour détecter les nouveaux TP partiels)
        fills_snap = {t: len(pos.partial_fills) for t, pos in open_pos.items()}

        before_cash = pm.cash
        pm.update_prices(prices)

        cash_delta = pm.cash - before_cash
        sltp_cash_delta = cash_delta
        if cash_delta != 0:
            log(f"  SL/TP declenches -> encaisse {cash_delta:+.2f} EUR")

        # ── Clôtures complètes (SL ou TP3 final) ─────────────────
        closed_tickers = [t for t in open_pos if t not in pm.open_positions]
        for t in closed_tickers:
            log(f"  Position FERMEE : {t}")
            h = next((x for x in reversed(pm.history) if x["ticker"] == t), None)
            if h:
                ep  = h["entry_price"]
                cp  = h["close_price"]
                pct = (cp - ep) / ep * 100
                sales_log.append({
                    "ticker": t, "reason": h.get("close_reason", "?"),
                    "price": cp, "pnl": h["pnl"], "pnl_pct": round(pct, 2),
                    "partial": False,
                })

        # ── Ventes partielles nouvelles (TP1/TP2 hits) ───────────
        for ticker, pos in open_pos.items():
            if ticker not in pm.open_positions:
                continue  # déjà capturé ci-dessus
            old_n = fills_snap.get(ticker, 0)
            for fill in pos.partial_fills[old_n:]:
                pnl  = (fill.price - pos.entry_price) * fill.qty
                pct  = (fill.price / pos.entry_price - 1) * 100
                log(f"  {fill.reason} {ticker} : {fill.price:.2f} ({pct:+.1f}%)")
                sales_log.append({
                    "ticker": ticker, "reason": fill.reason,
                    "price": fill.price, "pnl": round(pnl, 2),
                    "pnl_pct": round(pct, 2), "partial": True,
                })

        # ── Time stop : fermer les positions qui stagnent ─────────
        TIME_STOP_DAYS = 25
        TIME_STOP_LOSS_PCT = 0.02
        for ticker, pos in list(pm.open_positions.items()):
            price = prices.get(ticker)
            if price is None or not pos.entry_date:
                continue
            try:
                entry_dt = datetime.strptime(pos.entry_date, "%Y-%m-%d")
                age_days = (datetime.now() - entry_dt).days
                loss_pct = (price - pos.entry_price) / pos.entry_price
                if age_days >= TIME_STOP_DAYS and loss_pct < -TIME_STOP_LOSS_PCT:
                    log(f"  [TIME STOP] {ticker} : {age_days}j ouverte, "
                        f"PnL={loss_pct*100:.1f}% -> fermeture")
                    pm.manual_close(ticker, price)
                    pnl_eu = (price - pos.entry_price) * pos.qty_remaining
                    sales_log.append({
                        "ticker": ticker, "reason": "Time Stop",
                        "price": price, "pnl": round(pnl_eu, 2),
                        "pnl_pct": round(loss_pct * 100, 2), "partial": False,
                    })
            except Exception as e:
                log(f"  [TIME STOP ERROR] {ticker} : {e}")
    else:
        log("Aucune position ouverte.")

    # ── 2. Screener ───────────────────────────────────────────────
    log("Screener en cours...")
    try:
        df_screen = run_screener(tickers=DEFAULT_WATCHLIST, period="6mo", min_score=0)
    except Exception as e:
        log(f"Erreur screener : {e}")
        return

    if df_screen.empty:
        log("Screener vide - pas de donnees.")
        return

    score_max = int(df_screen["score"].max())
    score_med = int(df_screen["score"].median())
    log(f"Scores : max={score_max}  mediane={score_med}  ({len(df_screen)} tickers)")

    # Seuil pré-filtre screener (le débat multi-agents est le vrai filtre)
    # BULL: min_net=10 → min_score=40 | NEUTRAL: 20→50 | BEAR: 30→60
    min_score  = macro_ctx.min_net_score + 30
    max_opens  = macro_ctx.max_trades_per_day
    market_ctx = macro_ctx.regime

    # Garde-fou : si le meilleur score du jour est vraiment trop bas, on ne trade pas
    if score_max < 35:
        log(f"Qualite signaux insuffisante (max={score_max}) - pas de nouveaux achats.")
        min_score = 999
        max_opens = 0

    log(f"Contexte marche : {market_ctx} | seuil={min_score} | max_trades={max_opens} | score_max={score_max}")

    # Pré-filtre large : on laisse le débat gérer les cas limites
    candidates = df_screen[
        (df_screen["score"] >= min_score) &
        (df_screen["r_ratio"] >= MIN_R_RATIO * 0.8)
    ].sort_values("score", ascending=False)

    # Filtre sectoriel macro
    if macro_ctx.allowed_sectors:
        before = len(candidates)
        candidates = candidates[
            candidates["ticker"].apply(
                lambda t: SECTOR_MAP.get(t, "Other") in macro_ctx.allowed_sectors
            )
        ]
        log(f"Filtre sectoriel macro : {before} → {len(candidates)} candidats "
            f"(secteurs auth. : {', '.join(macro_ctx.allowed_sectors)})")

    log(f"{len(candidates)} candidats pre-filtres (score>={min_score}, R>={MIN_R_RATIO*0.8:.1f})")

    # Near-miss screener : tickers qui frôlent le seuil pré-filtre (score_bas)
    if min_score < 999:
        near_screen = df_screen[
            (df_screen["score"] >= min_score - 10) &
            (df_screen["score"] < min_score)
        ]
        for _, ns_row in near_screen.iterrows():
            ns_ticker = ns_row["ticker"]
            if ns_ticker not in pm.open_positions:
                save_near_miss(
                    ticker     = ns_ticker,
                    net_score  = float(ns_row["score"]) - min_score,
                    reason     = "score_bas",
                    bull_score = int(ns_row.get("bull_score", ns_row["score"])),
                    bear_score = int(ns_row.get("bear_score", 0)),
                    price      = float(ns_row["price"]),
                    sector     = SECTOR_MAP.get(ns_ticker, "Other"),
                    data_dir   = _data_dir,
                )

    # ── 3. Débat multi-agents + ouverture de positions ────────────
    available = pm.available_deploy_cash()
    opened = 0
    max_opens = min(max_opens, macro_ctx.max_trades_per_day, MAX_TRADES_PER_DAY)
    log(f"Cash deployable cette semaine : {available:.0f} EUR  (max trades/j : {max_opens})")

    if available < 100:
        log("Budget semaine epuise - pas de nouveaux achats.")
    elif candidates.empty:
        log("Aucun signal suffisant aujourd'hui.")
    else:
        sectors_used = Counter(SECTOR_MAP.get(t, "Other") for t in pm.open_positions)
        # Les ETFs sectoriels comptent aussi pour leur secteur sous-jacent
        for t in pm.open_positions:
            underlying = _ETF_TO_UNDERLYING.get(t.upper())
            if underlying and underlying != SECTOR_MAP.get(t, "Other"):
                sectors_used[underlying] = sectors_used.get(underlying, 0) + 1
        debates_run  = 0

        for _, cand_row in candidates.iterrows():
            if opened >= max_opens:
                break
            if available < 100:
                break

            ticker = cand_row["ticker"]
            price  = float(cand_row["price"])
            atr    = float(cand_row.get("atr", 0))
            score  = int(cand_row["score"])
            sector = SECTOR_MAP.get(ticker, "Other")

            if ticker in pm.open_positions:
                continue
            if atr <= 0:
                continue

            # ── Filtre earnings ───────────────────────────────────
            if _near_earnings(ticker, days=3):
                log(f"  [SKIP earnings] {ticker} : publication de résultats dans ±3j")
                continue

            # ── Débat Bull / Bear / Arbitre ───────────────────────
            debates_run += 1
            cand_dict = cand_row.to_dict()
            cand_dict["min_net_score"]  = macro_ctx.min_net_score
            cand_dict["market_regime"]  = "bear" if macro_ctx.regime == "BEAR" else (
                                          "bull" if macro_ctx.regime == "BULL" else "neutral")
            debate = run_debate(ticker, cand_dict, pm)

            # Log du débat complet
            for line in debate.format_log():
                log(line)

            # Véto sectoriel (hors débat — règle portefeuille hard)
            if sectors_used.get(sector, 0) >= 2:
                log(f"  [VETO secteur] {ticker} : {sector} deja a {sectors_used[sector]} positions")
                if debate.buy:
                    save_near_miss(
                        ticker     = ticker,
                        net_score  = debate.net_score,
                        reason     = "veto_secteur",
                        bull_score = debate.bull.score,
                        bear_score = debate.bear.score,
                        price      = price,
                        sector     = sector,
                        data_dir   = _data_dir,
                    )
                continue

            # L'arbitre a tranché
            if not debate.buy:
                # Near-miss score_limite : PASSER mais tout proche du seuil
                if debate.net_score >= -5:
                    save_near_miss(
                        ticker     = ticker,
                        net_score  = debate.net_score,
                        reason     = "score_limite",
                        bull_score = debate.bull.score,
                        bear_score = debate.bear.score,
                        price      = price,
                        sector     = sector,
                        data_dir   = _data_dir,
                    )
                continue

            # Budget épuisé après vérification (available peut avoir baissé en cours de boucle)
            if available < 100:
                save_near_miss(
                    ticker     = ticker,
                    net_score  = debate.net_score,
                    reason     = "budget",
                    bull_score = debate.bull.score,
                    bear_score = debate.bear.score,
                    price      = price,
                    sector     = sector,
                    data_dir   = _data_dir,
                )
                break

            # ── Exécution ─────────────────────────────────────────
            ok, msg, pos = pm.open_position(
                ticker=ticker,
                current_price=price,
                atr=atr,
                score=score,
            )

            if ok:
                opened += 1
                inv = pos.qty_remaining * pos.entry_price
                sectors_used[sector] = sectors_used.get(sector, 0) + 1
                available -= inv
                log(f"  [ACHAT] {ticker} score={score} "
                    f"bull={debate.bull.score} bear={debate.bear.score} "
                    f"prix={price:.2f} investi={inv:.0f}EUR "
                    f"SL={pos.sl:.2f} TP1={pos.tp_levels[0].price:.2f}")
                opened_positions_log.append({
                    "ticker":    ticker,
                    "score":     score,
                    "bull":      debate.bull.score,
                    "bear":      debate.bear.score,
                    "net_score": debate.net_score,
                    "bull_args": debate.bull.top_args(3),
                    "prix":      price,
                    "investi":   inv,
                    "sl":        pos.sl,
                    "tp1":       pos.tp_levels[0].price,
                })
            else:
                log(f"  [SKIP portefeuille] {ticker} : {msg}")

        log(f"{debates_run} debat(s) mene(s) → {opened} achat(s) effectue(s).")
        if opened == 0:
            log("Aucune nouvelle position ouverte.")

    # ── 4. Resume du portefeuille ─────────────────────────────────
    log("-" * 40)
    log(f"RESUME : valeur={pm.total_value:.2f} EUR  "
        f"investi={pm.total_invested:.2f} EUR  "
        f"cash={pm.cash:.2f} EUR  "
        f"expo={pm.exposure_pct*100:.1f}%  "
        f"positions={len(pm.open_positions)}")
    log("-" * 40)

    # ── 5. Email recap ────────────────────────────────────────────
    _send_daily_email(
        today=today,
        market_ctx=market_ctx,
        score_max=score_max,
        score_med=score_med,
        n_candidates=len(candidates),
        opened_positions=opened_positions_log,
        sales_log=sales_log,
        sltp_cash=sltp_cash_delta,
        pm=pm,
        available=available,
        live_prices=prices if open_pos else {},
    )


def _send_daily_email(
    today, market_ctx, score_max, score_med, n_candidates,
    opened_positions, sales_log, sltp_cash, pm, available,
    live_prices: dict | None = None,
):
    """Construit et envoie le recap journalier par email."""
    from portfolio.manager import PortfolioManager

    ctx_color = {"FORT": "#34d399", "MOYEN": "#fbbf24", "FAIBLE": "#fb7185"}.get(market_ctx, "#8097b5")
    # ── Section A — Nouvelles positions ouvertes (enrichi bull/bear) ─────────
    if opened_positions:
        def _pos_card(o: dict) -> str:
            bull_args = o.get("bull_args", [])
            bull_args_html = "".join(
                f"<li style='margin:2px 0;color:#6ee7b7;font-size:11px'>• {a}</li>"
                for a in bull_args[:3]
            ) if bull_args else ""
            bull_list = f"<ul style='margin:6px 0 0;padding:0;list-style:none'>{bull_args_html}</ul>" if bull_args_html else ""
            net = o.get("net_score", o["bull"] - o["bear"] * 0.6)
            net_color = "#34d399" if net >= 0 else "#fb7185"
            return (
                f"<div style='background:#0d1420;border-radius:8px;padding:14px 16px;"
                f"margin-bottom:10px;border-left:3px solid #34d399'>"
                f"<div style='display:flex;align-items:center;gap:12px;flex-wrap:wrap'>"
                f"<span style='font-weight:700;font-size:15px;color:#d6e0f0'>{o['ticker']}</span>"
                f"<span style='color:#8097b5;font-size:12px'>{o['prix']:.2f} €</span>"
                f"<span style='color:#8097b5;font-size:12px'>investi {o['investi']:.0f} €</span>"
                f"<span style='background:#0a2218;color:#34d399;padding:1px 7px;"
                f"border-radius:4px;font-size:11px'>SL {o['sl']:.2f}</span>"
                f"<span style='background:#0a1a0a;color:#34d399;padding:1px 7px;"
                f"border-radius:4px;font-size:11px'>TP1 {o['tp1']:.2f}</span>"
                f"</div>"
                f"<div style='display:flex;gap:16px;margin-top:8px;font-size:12px'>"
                f"<span>BULL <strong style='color:#34d399'>{o['bull']}</strong></span>"
                f"<span>BEAR <strong style='color:#fb7185'>{o['bear']}</strong></span>"
                f"<span>NET <strong style='color:{net_color}'>{net:+.0f}</strong></span>"
                f"<span style='color:#445470'>score screener {o['score']}</span>"
                f"</div>"
                f"{bull_list}"
                f"</div>"
            )

        orders_section = (
            f"<h3 style='color:#34d399;margin:24px 0 8px'>"
            f"&#x2705; {len(opened_positions)} position(s) ouverte(s) aujourd'hui</h3>"
            + "".join(_pos_card(o) for o in opened_positions)
        )
    else:
        raison = "Budget semaine epuise" if available < 100 else "Aucun signal suffisant (filtres score/bear)"
        orders_section = (
            f"<h3 style='color:#fbbf24;margin:24px 0 8px'>&#x26A0;&#xFE0F; Aucun ordre passe aujourd'hui</h3>"
            f"<p style='color:#8097b5;margin:0'>{raison}</p>"
        )

    watchlist_section = ""

    # ── Section ventes ────────────────────────────────────────────────────────
    def _sale_card(s: dict) -> str:
        pnl    = s["pnl"]
        pct    = s["pnl_pct"]
        reason = s["reason"]
        clr    = "#34d399" if pnl >= 0 else "#fb7185"
        border = clr
        icon   = "🟢" if pnl >= 0 else "🔴"
        # label raison
        reason_labels = {
            "SL": "🛑 Stop Loss", "TP1": "✅ TP1 (25%)", "TP2": "✅ TP2 (35%)",
            "TP3": "✅ TP3 (40%)", "Time Stop": "⏱ Time Stop", "manual": "✋ Manuel",
        }
        reason_txt = reason_labels.get(reason, reason)
        partial_tag = (
            "<span style='font-size:10px;color:#8097b5;margin-left:8px'>vente partielle</span>"
            if s.get("partial") else ""
        )
        return (
            f"<div style='background:#0d1420;border-radius:8px;padding:12px 16px;"
            f"margin-bottom:8px;border-left:3px solid {border};"
            f"display:flex;align-items:center;gap:16px;flex-wrap:wrap'>"
            f"<span style='font-weight:700;font-size:15px;color:#d6e0f0'>{icon} {s['ticker']}</span>"
            f"<span style='color:#8097b5;font-size:12px'>{s['price']:.2f} €</span>"
            f"<span style='color:#8097b5;font-size:12px'>{reason_txt}</span>"
            f"{partial_tag}"
            f"<span style='margin-left:auto;font-weight:700;color:{clr}'>"
            f"{pct:+.1f}% &nbsp; {pnl:+.0f} €</span>"
            f"</div>"
        )

    if sales_log:
        total_pnl_sales = sum(s["pnl"] for s in sales_log)
        clr_total = "#34d399" if total_pnl_sales >= 0 else "#fb7185"
        sales_html = (
            f"<h3 style='color:#8097b5;margin:24px 0 8px'>"
            f"📤 Ventes du jour "
            f"<span style='font-size:13px;color:{clr_total}'>"
            f"({total_pnl_sales:+.0f} € net)</span></h3>"
            + "".join(_sale_card(s) for s in sales_log)
        )
    else:
        sales_html = ""

    # SL/TP encaisses (résumé cash)
    sltp_html = ""
    if sltp_cash != 0:
        color = "#34d399" if sltp_cash > 0 else "#fb7185"
        sltp_html = (
            f"<p style='color:{color};margin:8px 0'>"
            f"💰 Cash encaisse aujourd'hui : <strong>{sltp_cash:+.2f} €</strong></p>"
        )

    # Positions actuelles avec PnL latent
    _lp = live_prices or {}
    def _pos_row(t, p):
        live  = _lp.get(t, p.entry_price)
        pnl   = (live - p.entry_price) * p.qty_remaining
        ppct  = (live / p.entry_price - 1) * 100
        clr   = "#34d399" if pnl >= 0 else "#fb7185"
        return (
            f"<tr>"
            f"<td style='padding:5px 12px;font-weight:700;color:#d6e0f0'>{t}</td>"
            f"<td style='padding:5px 12px;color:#8097b5'>{p.entry_price:.2f}</td>"
            f"<td style='padding:5px 12px;color:#8097b5'>{live:.2f}</td>"
            f"<td style='padding:5px 12px;font-weight:600;color:{clr}'>"
            f"{ppct:+.1f}% / {pnl:+.0f}€</td>"
            f"<td style='padding:5px 12px;color:#8097b5'>{p.sl:.2f}</td>"
            f"<td style='padding:5px 12px;color:#8097b5'>{p.tp_levels[0].price:.2f}</td>"
            f"</tr>"
        )
    pos_rows = "".join(_pos_row(t, p) for t, p in pm.open_positions.items())

    subject_icon = "✅" if opened_positions else ("📤" if sales_log else "⚠️")
    n_sales = len(sales_log)
    subject = (
        f"{subject_icon} Portfolio {today} — "
        f"{len(opened_positions)} achat(s) · {n_sales} vente(s) | "
        f"{len(pm.open_positions)} positions"
    )

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style='background:#0a0f1a;color:#d6e0f0;font-family:Inter,Arial,sans-serif;
                 margin:0;padding:24px'>
        <div style='max-width:640px;margin:0 auto'>

            <!-- Header -->
            <div style='background:#192235;border-radius:10px;padding:20px 24px;
                        border-left:4px solid {ctx_color};margin-bottom:20px'>
                <h2 style='margin:0 0 4px;color:#d6e0f0'>
                    Rapport journalier — {today}
                </h2>
                <span style='background:{ctx_color}22;color:{ctx_color};
                             padding:2px 10px;border-radius:4px;font-size:12px;font-weight:700'>
                    Marche {market_ctx}
                </span>
            </div>

            <!-- Marché -->
            <div style='display:flex;gap:12px;margin-bottom:20px'>
                <div style='flex:1;background:#192235;border-radius:8px;padding:14px 18px;text-align:center'>
                    <div style='color:#445470;font-size:11px;margin-bottom:4px'>SCORE MAX</div>
                    <div style='font-size:22px;font-weight:700;color:{ctx_color}'>{score_max}</div>
                </div>
                <div style='flex:1;background:#192235;border-radius:8px;padding:14px 18px;text-align:center'>
                    <div style='color:#445470;font-size:11px;margin-bottom:4px'>MEDIANE</div>
                    <div style='font-size:22px;font-weight:700;color:#8097b5'>{score_med}</div>
                </div>
                <div style='flex:1;background:#192235;border-radius:8px;padding:14px 18px;text-align:center'>
                    <div style='color:#445470;font-size:11px;margin-bottom:4px'>CANDIDATS</div>
                    <div style='font-size:22px;font-weight:700;color:#8097b5'>{n_candidates}</div>
                </div>
                <div style='flex:1;background:#192235;border-radius:8px;padding:14px 18px;text-align:center'>
                    <div style='color:#445470;font-size:11px;margin-bottom:4px'>POSITIONS</div>
                    <div style='font-size:22px;font-weight:700;color:#8097b5'>{len(pm.open_positions)}</div>
                </div>
            </div>

            {sltp_html}
            {sales_html}
            {orders_section}
            {watchlist_section}

            <!-- Portefeuille -->
            <h3 style='color:#8097b5;margin:24px 0 8px'>📊 Portefeuille</h3>
            <div style='display:flex;gap:12px;margin-bottom:16px'>
                <div style='flex:1;background:#192235;border-radius:8px;padding:12px 16px'>
                    <div style='color:#445470;font-size:11px'>VALEUR TOTALE</div>
                    <div style='font-size:18px;font-weight:700;color:#d6e0f0'>
                        {pm.total_value:,.2f} €
                    </div>
                </div>
                <div style='flex:1;background:#192235;border-radius:8px;padding:12px 16px'>
                    <div style='color:#445470;font-size:11px'>CASH LIBRE</div>
                    <div style='font-size:18px;font-weight:700;color:#d6e0f0'>
                        {pm.cash:,.2f} €
                    </div>
                </div>
                <div style='flex:1;background:#192235;border-radius:8px;padding:12px 16px'>
                    <div style='color:#445470;font-size:11px'>EXPOSITION</div>
                    <div style='font-size:18px;font-weight:700;color:#d6e0f0'>
                        {pm.exposure_pct*100:.1f}%
                    </div>
                </div>
            </div>

            <!-- Positions ouvertes -->
            {"<table style='width:100%;border-collapse:collapse;background:#0d1420;border-radius:8px;overflow:hidden'><thead><tr style='background:#192235'><th style='padding:7px 12px;text-align:left;color:#445470;font-size:11px'>TICKER</th><th style='padding:7px 12px;text-align:left;color:#445470;font-size:11px'>ENTRÉE</th><th style='padding:7px 12px;text-align:left;color:#445470;font-size:11px'>LIVE</th><th style='padding:7px 12px;text-align:left;color:#445470;font-size:11px'>PNL% / €</th><th style='padding:7px 12px;text-align:left;color:#445470;font-size:11px'>SL</th><th style='padding:7px 12px;text-align:left;color:#445470;font-size:11px'>TP1</th></tr></thead><tbody>" + pos_rows + "</tbody></table>" if pos_rows else "<p style='color:#445470'>Aucune position ouverte.</p>"}

            <p style='color:#2a3d5c;font-size:11px;margin-top:24px;text-align:center'>
                Portfolio Manager — {datetime.now().strftime("%Y-%m-%d %H:%M")}
            </p>
        </div>
    </body>
    </html>
    """
    send_email(subject, html)


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log(f"ERREUR CRITIQUE : {traceback.format_exc()}")
        send_email(
            subject=f"🚨 Portfolio — ERREUR CRITIQUE ({date.today()})",
            html_body="<p style='color:red;font-family:monospace'>"
                      + traceback.format_exc().replace("\n", "<br>") + "</p>",
        )
        sys.exit(1)
