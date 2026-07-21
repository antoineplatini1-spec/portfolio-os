#!/usr/bin/env python
"""
Watcher de SORTIES IBKR — email quasi temps réel quand un STOP ou un TP est touché.

Les brackets se déclenchent EN SÉANCE sur les serveurs IBKR ; le bot ne les réconcilie
qu'au run quotidien (le lendemain). Ce watcher comble le trou : lancé toutes les ~15 min en
séance (cron dédié), il lit les EXÉCUTIONS IBKR (source de vérité, lecture seule), repère les
VENTES nouvelles (stop/TP) et envoie un mail par sortie, avec le PnL réalisé calculé par IBKR.

Dédup : `data/notified_execs.json` (execId déjà notifiés), auto-borné à la fenêtre lue.
ClientId 18 (distinct du bot=17) pour cohabiter avec le run quotidien.
    Lancement : `IBKR_ENABLED=1 python exit_watcher.py`   (ou `--test` pour un mail d'essai)
"""

from __future__ import annotations

import json
import os
import smtplib
import sys
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))
SEEN_FILE = _data_dir / "notified_execs.json"


def _send_email(subject: str, html_body: str) -> bool:
    """Envoi Gmail SMTP — même schéma que daily_auto.send_email (ehlo→starttls→login)."""
    cfg_path = _data_dir / "email_config.json"
    if not cfg_path.exists():
        print("[EXIT-WATCH] email_config.json introuvable — pas d'email")
        return False
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = cfg["recipient"]
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as s:
        s.ehlo()
        s.starttls()
        s.login(cfg["sender"], cfg["password"])
        s.sendmail(cfg["sender"], cfg["recipient"], msg.as_string())
    print(f"[EXIT-WATCH] email envoyé à {cfg['recipient']} — {subject}")
    return True


def _load_seen() -> set[str]:
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_seen(ids: set[str]) -> None:
    try:
        SEEN_FILE.write_text(json.dumps(sorted(ids)), encoding="utf-8")
    except Exception as e:
        print(f"[EXIT-WATCH] sauvegarde état impossible : {e}")


def _exit_html(sym: str, qty: float, px: float, pnl: float | None, when: str) -> str:
    up = pnl is None or pnl >= 0
    emoji = "🟢" if up else "🔴"
    color = "#34d399" if up else "#fb7185"
    pl = f"{pnl:+.0f} $" if pnl is not None else "n/c"
    return (
        f"<div style='font-family:system-ui,Arial;max-width:480px'>"
        f"<h2 style='margin:0 0 8px'>{emoji} Sortie exécutée — {sym}</h2>"
        f"<table style='border-collapse:collapse;font-size:14px'>"
        f"<tr><td style='padding:3px 12px 3px 0;color:#667'>Quantité</td><td><b>{qty:.0f}</b> actions</td></tr>"
        f"<tr><td style='padding:3px 12px 3px 0;color:#667'>Prix de fill</td><td><b>{px:.2f}</b></td></tr>"
        f"<tr><td style='padding:3px 12px 3px 0;color:#667'>PnL réalisé (IBKR)</td>"
        f"<td style='color:{color};font-weight:700'>{pl}</td></tr>"
        f"<tr><td style='padding:3px 12px 3px 0;color:#667'>Heure</td><td>{when}</td></tr>"
        f"</table>"
        f"<p style='color:#889;font-size:12px;margin-top:12px'>Déclenché par un ordre "
        f"stop/TP posé sur IBKR (sortie serveur, hors run du bot).</p></div>"
    )


def main(test: bool = False) -> int:
    if test:
        ok = _send_email("🟢 [TEST] Watcher de sorties actif",
                         _exit_html("TEST", 10, 123.45, 42.0, datetime.now().strftime("%Y-%m-%d %H:%M")))
        return 0 if ok else 1

    from config import IBKR_CONFIG
    if not IBKR_CONFIG.get("enabled"):
        print("[EXIT-WATCH] IBKR désactivé — no-op")
        return 0

    from ib_async import IB, ExecutionFilter
    ib = IB()
    try:
        ib.connect(IBKR_CONFIG["host"], IBKR_CONFIG["port"], clientId=18,
                   timeout=20, readonly=True)
    except Exception as e:
        print(f"[EXIT-WATCH] connexion IBKR impossible : {e}")
        return 0                                       # silencieux : le prochain tick réessaiera

    try:
        since = (datetime.now() - timedelta(days=2)).strftime("%Y%m%d-%H:%M:%S")
        fills = ib.reqExecutions(ExecutionFilter(time=since)) or []
    except Exception as e:
        print(f"[EXIT-WATCH] lecture exécutions impossible : {e}")
        ib.disconnect()
        return 0

    seen = _load_seen()
    window_sell_ids: set[str] = set()
    to_notify = []
    for f in fills:
        try:
            e = f.execution
            if e.side != "SLD":                        # SLD = vente (stop/TP), BOT = achat
                continue
            window_sell_ids.add(e.execId)
            if e.execId in seen:
                continue
            pnl = None
            try:
                r = f.commissionReport.realizedPNL
                if r is not None and abs(r) < 1e12:    # 1e18 = sentinel "non renseigné"
                    pnl = float(r)
            except Exception:
                pnl = None
            to_notify.append((e.execId, f.contract.symbol, float(e.shares),
                              float(e.avgPrice or 0), pnl, str(e.time)[:19]))
        except Exception:
            continue

    notified = 0
    for exec_id, sym, qty, px, pnl, when in to_notify:
        emoji = "🟢" if (pnl is None or pnl >= 0) else "🔴"
        pl = f"{pnl:+.0f}$" if pnl is not None else ""
        try:
            _send_email(f"{emoji} Sortie {sym} {pl}".strip(), _exit_html(sym, qty, px, pnl, when))
            notified += 1
        except Exception as ex:
            print(f"[EXIT-WATCH] envoi échoué pour {sym} : {ex}")
            window_sell_ids.discard(exec_id)           # email raté → pas marqué vu → réessai au prochain tick

    # État borné à la fenêtre : les execId hors fenêtre disparaîtront (ils ne reviendront pas).
    _save_seen(window_sell_ids)
    ib.disconnect()
    print(f"[EXIT-WATCH] {notified} sortie(s) notifiée(s), {len(window_sell_ids)} vente(s) en fenêtre.")
    return 0


if __name__ == "__main__":
    sys.exit(main(test="--test" in sys.argv))
