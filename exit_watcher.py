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
JOURNAL_FILE = _data_dir / "trade_journal.jsonl"


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


def _journal_fills(fills) -> int:
    """
    Écrit dans le JOURNAL DURABLE (`trade_journal.jsonl`) chaque exécution IBKR nouvelle
    (achats BOT ET ventes SLD), dédupliquée par execId. C'est le registre AUTORITAIRE des
    fills — sourcé d'IBKR (prix + realizedPNL réels), jamais reconstruit. Idempotent : un
    execId déjà présent n'est pas ré-écrit. Retourne le nombre de lignes ajoutées.
    """
    seen: set[str] = set()
    if JOURNAL_FILE.exists():
        try:
            for line in JOURNAL_FILE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    eid = json.loads(line).get("execId")
                    if eid:
                        seen.add(eid)
        except Exception:
            pass

    rows = []
    for f in fills or []:
        try:
            e = f.execution
            if e.execId in seen:
                continue
            seen.add(e.execId)                          # anti-doublon intra-run aussi
            comm = rpnl = None
            cr = getattr(f, "commissionReport", None)
            if cr:
                if cr.commission is not None:
                    comm = abs(float(cr.commission))
                rp = getattr(cr, "realizedPNL", None)
                if rp is not None and abs(float(rp)) < 1e12:   # 1e18 = sentinel "non renseigné"
                    rpnl = float(rp)
            rows.append({
                "execId": e.execId,
                "time": str(e.time)[:19],
                "symbol": f.contract.symbol,
                "side": e.side,                         # BOT = achat, SLD = vente
                "qty": float(e.shares),
                "price": float(e.avgPrice or e.price or 0),
                "commission": comm,
                "realized_pnl": rpnl,
            })
        except Exception:
            continue

    if rows:
        try:
            with open(JOURNAL_FILE, "a", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        except Exception as ex:
            print(f"[EXIT-WATCH] écriture journal impossible : {ex}")
            return 0
    return len(rows)


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

    # JOURNAL DURABLE : on enregistre TOUS les fills (achats + ventes), à chaque tick, quel que
    # soit l'état email/baseline. C'est le registre autoritaire sourcé IBKR. Idempotent (execId).
    n_journal = _journal_fills(fills)

    # Premier lancement (pas d'état) : on établit une BASELINE silencieuse — toutes les ventes
    # déjà présentes sont marquées "vues" SANS email. On n'alerte que sur les sorties POSTÉRIEURES.
    # Évite de blaster l'historique (et les éventuels fills fantômes du paper) à chaque déploiement.
    first_run = not SEEN_FILE.exists()
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

    if first_run:
        _save_seen(window_sell_ids)
        ib.disconnect()
        print(f"[EXIT-WATCH] baseline initialisée ({len(window_sell_ids)} vente(s) marquée(s) vue(s), "
              f"aucun email). Journal : +{n_journal} fill(s). Les prochaines sorties seront notifiées.")
        return 0

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
    print(f"[EXIT-WATCH] {notified} sortie(s) notifiée(s), {len(window_sell_ids)} vente(s) en fenêtre, "
          f"journal +{n_journal} fill(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(test="--test" in sys.argv))
