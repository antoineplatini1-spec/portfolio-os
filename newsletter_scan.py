#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scan newsletter 13h — lit la newsletter Momentum et met à jour le contexte macro.
Planifié chaque jour ouvré à 13h (heure Paris).

Lance aussi un screener léger si des signaux forts sont détectés.
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
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run():
    today = date.today()
    if today.weekday() >= 5:
        log("Week-end — pas de scan newsletter.")
        return

    log("=" * 55)
    log(f"SCAN NEWSLETTER 13H — {today}")
    log("=" * 55)

    from signals.newsletter_agent import NewsletterAgent
    from signals.macro_agent import MacroAgent

    # 1. Lire la newsletter
    try:
        nl = NewsletterAgent().fetch_and_parse()
        for line in nl.format_log():
            log(line)
    except Exception as e:
        log(f"[NEWSLETTER] Erreur : {e}")
        return

    if nl.source == "none":
        log("Newsletter indisponible — scan annulé.")
        return

    # 2. Recalculer le contexte macro avec les signaux newsletter
    macro = MacroAgent().analyze(newsletter_signal=nl)

    # 3. Log du résumé d'action
    log(f"Regime macro: {macro.regime} | secteurs autorisés: {macro.allowed_sectors or 'TOUS'}")

    # 4. Si signaux forts (AVOID sur Semi/Tech en bear) → envoyer une alerte
    strong_avoids = [s for s in nl.stock_signals if s.sentiment in ("AVOID", "SELL")]
    if strong_avoids:
        from daily_auto import send_email
        sectors_warned = list({s.sector for s in strong_avoids})
        html = f"""
        <div style='background:#0a0f1a;color:#d6e0f0;font-family:Inter,Arial,sans-serif;padding:20px'>
            <h2 style='color:#fb7185'>⚠️ Alerte Newsletter Momentum — {today}</h2>
            <p>La newsletter signale des <strong>signaux baissiers</strong> sur :</p>
            <ul>
                {''.join(f"<li><strong>{s.name}</strong> ({s.sector}) → {s.sentiment} : {s.summary[:100]}</li>" for s in strong_avoids)}
            </ul>
            <p>Secteurs concernés : <strong>{', '.join(sectors_warned)}</strong></p>
            <p>Régime macro : <strong>{macro.regime}</strong> |
               Secteurs autorisés : <strong>{', '.join(macro.allowed_sectors) if macro.allowed_sectors else 'TOUS'}</strong></p>
            <p style='color:#445470;font-size:11px'>Newsletter Momentum — {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        </div>"""
        send_email(f"⚠️ Alerte Newsletter {today} — {', '.join(sectors_warned)}", html)
        log(f"[ALERTE] Email envoyé pour : {', '.join(s.name for s in strong_avoids)}")

    log("Scan newsletter terminé.")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        log(f"ERREUR : {traceback.format_exc()}")
