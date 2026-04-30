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
from datetime import datetime, date

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
    from data.fetcher import fetch_ohlcv
    from indicators import compute_all
    from signals.scoring import compute_score
    from config import DEFAULT_WATCHLIST, SECTOR_MAP

    pm = PortfolioManager()

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
        if cash_delta != 0:
            log(f"  SL/TP declenches -> encaisse {cash_delta:+.2f} EUR")

        # Positions encore ouvertes apres update
        still_open = pm.open_positions
        closed_today = [t for t in open_pos if t not in still_open]
        for t in closed_today:
            log(f"  Position FERMEE : {t}")
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

    # Seuil adaptatif :
    # - Marche fort (max>=60)  -> seuil 50
    # - Marche moyen (max>=45) -> seuil 38
    # - Marche faible (max<45) -> seuil 32, max 2 positions
    if score_max >= 60:
        min_score  = 50
        max_opens  = 5
        market_ctx = "FORT"
    elif score_max >= 45:
        min_score  = 38
        max_opens  = 3
        market_ctx = "MOYEN"
    else:
        min_score  = 32
        max_opens  = 2
        market_ctx = "FAIBLE/CORRECTION"

    log(f"Contexte marche : {market_ctx} -> seuil={min_score}, max_opens={max_opens}")

    candidates = df_screen[df_screen["score"] >= min_score].sort_values("score", ascending=False)
    log(f"{len(candidates)} candidats >= {min_score}")

    # ── 3. Ouverture de nouvelles positions ───────────────────────
    available = pm.available_deploy_cash()
    log(f"Cash deployable cette semaine : {available:.0f} EUR")

    if available < 100:
        log("Budget semaine epuise - pas de nouveaux achats.")
    elif candidates.empty:
        log("Aucun signal suffisant aujourd'hui.")
    else:
        opened = 0
        sectors_used = {
            SECTOR_MAP.get(t, "Other"): 1
            for t in pm.open_positions
        }

        for _, row in candidates.iterrows():
            if opened >= max_opens:
                break
            if available < 100:
                break

            ticker = row["ticker"]
            price  = float(row["price"])
            atr    = float(row.get("atr", 0))
            score  = int(row["score"])
            sector = SECTOR_MAP.get(ticker, "Other")

            if ticker in pm.open_positions:
                continue
            if atr <= 0:
                continue
            # Max 2 par secteur en cours
            if sectors_used.get(sector, 0) >= 2:
                continue

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
                log(f"  [ACHAT] {ticker} score={score} prix={price:.2f} "
                    f"investi={inv:.0f}EUR SL={pos.sl:.2f} TP1={pos.tp_levels[0].price:.2f}")
            else:
                log(f"  [SKIP] {ticker} : {msg}")

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


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log(f"ERREUR CRITIQUE : {traceback.format_exc()}")
        sys.exit(1)
