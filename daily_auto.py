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

BASE = os.path.dirname(__file__)
sys.path.insert(0, BASE)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr  = io.TextIOWrapper(sys.stderr.buffer,  encoding='utf-8', errors='replace')

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

    # Variables recap email
    opened_positions_log: list[dict] = []
    closed_today: list[str] = []
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

        before_cash = pm.cash
        pm.update_prices(prices)

        # Rapport SL/TP declenches
        cash_delta = pm.cash - before_cash
        sltp_cash_delta = cash_delta
        if cash_delta != 0:
            log(f"  SL/TP declenches -> encaisse {cash_delta:+.2f} EUR")

        # Positions encore ouvertes apres update
        still_open = pm.open_positions
        closed_today = [t for t in open_pos if t not in still_open]
        for t in closed_today:  # noqa
            log(f"  Position FERMEE : {t}")

        # ── Time stop : fermer les positions qui stagnent ─────────
        # Si ouverte depuis > 25 jours ET prix < entry - 2% → on coupe
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

    # Seuil issu de l'agent macro (régime marché + VIX)
    min_score  = macro_ctx.min_net_score + 40   # min_net_score ~10-30 → min_score 50-70
    max_opens  = macro_ctx.max_trades_per_day
    market_ctx = macro_ctx.regime

    # Garde-fou : si le meilleur score du jour est trop bas, on ne trade pas
    if score_max < 45:
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
                continue

            # L'arbitre a tranché
            if not debate.buy:
                continue

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
                    "ticker":  ticker,
                    "score":   score,
                    "bull":    debate.bull.score,
                    "bear":    debate.bear.score,
                    "prix":    price,
                    "investi": inv,
                    "sl":      pos.sl,
                    "tp1":     pos.tp_levels[0].price,
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
        closed_today=closed_today if open_pos else [],
        sltp_cash=sltp_cash_delta,
        pm=pm,
        available=available,
    )


def _send_daily_email(
    today, market_ctx, score_max, score_med, n_candidates,
    opened_positions, closed_today, sltp_cash, pm, available,
):
    """Construit et envoie le recap journalier par email."""
    from portfolio.manager import PortfolioManager

    ctx_color = {"FORT": "#34d399", "MOYEN": "#fbbf24", "FAIBLE": "#fb7185"}.get(market_ctx, "#8097b5")

    # Bloc ordres ouverts
    if opened_positions:
        orders_html = "".join(
            f"<tr>"
            f"<td style='padding:6px 12px;font-weight:700;color:#d6e0f0'>{o['ticker']}</td>"
            f"<td style='padding:6px 12px;color:#34d399'>{o['score']}</td>"
            f"<td style='padding:6px 12px;color:#8097b5'>{o['prix']:.2f}</td>"
            f"<td style='padding:6px 12px;color:#8097b5'>{o['investi']:.0f} €</td>"
            f"<td style='padding:6px 12px;color:#fb7185'>{o['sl']:.2f}</td>"
            f"<td style='padding:6px 12px;color:#34d399'>{o['tp1']:.2f}</td>"
            f"<td style='padding:6px 12px;color:#8097b5'>{o['bull']}</td>"
            f"<td style='padding:6px 12px;color:#fb7185'>{o['bear']}</td>"
            f"</tr>"
            for o in opened_positions
        )
        orders_section = f"""
        <h3 style='color:#34d399;margin:24px 0 8px'>
            ✅ {len(opened_positions)} position(s) ouverte(s)
        </h3>
        <table style='width:100%;border-collapse:collapse;background:#0d1420;border-radius:8px;overflow:hidden'>
            <thead>
                <tr style='background:#192235'>
                    <th style='padding:8px 12px;text-align:left;color:#445470;font-size:11px'>TICKER</th>
                    <th style='padding:8px 12px;text-align:left;color:#445470;font-size:11px'>SCORE</th>
                    <th style='padding:8px 12px;text-align:left;color:#445470;font-size:11px'>PRIX</th>
                    <th style='padding:8px 12px;text-align:left;color:#445470;font-size:11px'>INVESTI</th>
                    <th style='padding:8px 12px;text-align:left;color:#445470;font-size:11px'>SL</th>
                    <th style='padding:8px 12px;text-align:left;color:#445470;font-size:11px'>TP1</th>
                    <th style='padding:8px 12px;text-align:left;color:#445470;font-size:11px'>BULL</th>
                    <th style='padding:8px 12px;text-align:left;color:#445470;font-size:11px'>BEAR</th>
                </tr>
            </thead>
            <tbody>{orders_html}</tbody>
        </table>"""
    else:
        raison = "Budget semaine epuise" if available < 100 else "Aucun signal suffisant (filtres score/bear)"
        orders_section = f"""
        <h3 style='color:#fbbf24;margin:24px 0 8px'>⚠️ Aucun ordre passe aujourd'hui</h3>
        <p style='color:#8097b5;margin:0'>{raison}</p>"""

    # Bloc fermetures
    closed_html = ""
    if closed_today:
        closed_html = "<h3 style='color:#fb7185;margin:24px 0 8px'>🔴 Positions fermees</h3>"
        closed_html += " &nbsp;".join(
            f"<span style='background:#1e1020;color:#fb7185;padding:3px 10px;"
            f"border-radius:4px;font-weight:700'>{t}</span>"
            for t in closed_today
        )

    # SL/TP encaisses
    sltp_html = ""
    if sltp_cash != 0:
        color = "#34d399" if sltp_cash > 0 else "#fb7185"
        sltp_html = (
            f"<p style='color:{color};margin:8px 0'>"
            f"💰 SL/TP encaisses : <strong>{sltp_cash:+.2f} €</strong></p>"
        )

    # Positions actuelles
    pos_rows = "".join(
        f"<tr>"
        f"<td style='padding:5px 12px;font-weight:700;color:#d6e0f0'>{t}</td>"
        f"<td style='padding:5px 12px;color:#8097b5'>{p.entry_price:.2f}</td>"
        f"<td style='padding:5px 12px;color:#8097b5'>{p.sl:.2f}</td>"
        f"<td style='padding:5px 12px;color:#8097b5'>{p.tp_levels[0].price:.2f}</td>"
        f"<td style='padding:5px 12px;color:#8097b5'>{p.qty_remaining:.4f}</td>"
        f"</tr>"
        for t, p in pm.open_positions.items()
    )

    subject_icon = "✅" if opened_positions else "⚠️"
    subject = f"{subject_icon} Portfolio {today} — {len(opened_positions)} ordre(s) | {len(pm.open_positions)} positions"

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
            {closed_html}
            {orders_section}

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
            {"<table style='width:100%;border-collapse:collapse;background:#0d1420;border-radius:8px;overflow:hidden'><thead><tr style='background:#192235'><th style='padding:7px 12px;text-align:left;color:#445470;font-size:11px'>TICKER</th><th style='padding:7px 12px;text-align:left;color:#445470;font-size:11px'>ENTREE</th><th style='padding:7px 12px;text-align:left;color:#445470;font-size:11px'>SL</th><th style='padding:7px 12px;text-align:left;color:#445470;font-size:11px'>TP1</th><th style='padding:7px 12px;text-align:left;color:#445470;font-size:11px'>QTE</th></tr></thead><tbody>" + pos_rows + "</tbody></table>" if pos_rows else "<p style='color:#445470'>Aucune position ouverte.</p>"}

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
