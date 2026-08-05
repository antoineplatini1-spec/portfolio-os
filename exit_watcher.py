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
STATE_FILE = _data_dir / "portfolio_state.json"


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


def _avg_entry(symbol: str) -> float | None:
    """
    Prix d'entrée du symbole pour étiqueter TP/SL et calculer le PnL € (essentiel quand IBKR
    renvoie realizedPNL=0 en paper). Sources par fiabilité décroissante :
    1) LEDGER (portfolio_state.json) : entry_price de la position ouverte, sinon dernier trade
       fermé de l'historique — vrai prix de fill enregistré par le bot, fiable même pour les
       positions achetées AVANT l'existence du journal (ex. MA/SPG) ;
    2) JOURNAL des fills IBKR : moyenne pondérée des ACHATS (repli).
    """
    try:
        d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        p = d.get("positions", {}).get(symbol)
        if p and p.get("entry_price"):
            return float(p["entry_price"])
        for h in reversed(d.get("history", [])):          # dernier trade fermé de ce symbole
            if h.get("ticker") == symbol and h.get("entry_price"):
                return float(h["entry_price"])
    except Exception:
        pass
    if JOURNAL_FILE.exists():
        tot_q = tot_v = 0.0
        try:
            for line in JOURNAL_FILE.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("symbol") == symbol and r.get("side") == "BOT":
                    q = float(r.get("qty", 0) or 0); p = float(r.get("price", 0) or 0)
                    if q > 0 and p > 0:
                        tot_q += q; tot_v += q * p
        except Exception:
            return None
        if tot_q > 0:
            return tot_v / tot_q
    return None


def _ledger_levels(symbol: str):
    """(sl, [tp_prices]) de la position depuis le ledger, ou (None, [])."""
    try:
        d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        p = d.get("positions", {}).get(symbol)
        if p:
            tps = [t.get("price") for t in p.get("tp_levels", []) if t.get("price")]
            return p.get("sl"), tps
    except Exception:
        pass
    return None, []


def _position_exits(symbol: str) -> list[tuple[str, float, float]]:
    """
    Ventes (time, price, qty) du ROUND-TRIP courant depuis le journal : les SLD postérieurs au
    dernier achat (BOT) du symbole. Sert au gain CUMULÉ sur la ligne et au n° de palier.
    """
    if not JOURNAL_FILE.exists():
        return []
    try:
        recs = [json.loads(l) for l in JOURNAL_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return []
    recs = [r for r in recs if r.get("symbol") == symbol]
    last_bot = ""
    for r in recs:
        if r.get("side") == "BOT":
            last_bot = max(last_bot, str(r.get("time", "")))
    out = []
    for r in recs:
        if r.get("side") == "SLD" and str(r.get("time", "")) >= last_bot:
            out.append((str(r.get("time", "")), float(r.get("price", 0) or 0), float(r.get("qty", 0) or 0)))
    return out


def _tp_rung(symbol: str, px: float, exits: list) -> tuple[int, int] | None:
    """
    (n° de palier, nb total de paliers) pour ce prix de sortie. PRIMAIRE = rang du prix parmi
    les prix de sortie DISTINCTS du round-trip (le plus bas = TP1) — robuste MÊME quand la
    position est fermée (le ledger a alors perdu ses tp_levels). C'était le bug « toujours TP1 ».
    Le nb total de paliers vient du ladder ledger si dispo, sinon du nb de prix vus.
    """
    raw = sorted(p for _, p, q in exits if p > 0)
    if not raw:
        return None
    # Clusterise les prix proches (< 0,5%) → un même palier TP peut être rempli en plusieurs
    # fills à un cent près (58,40 / 58,41) : ils ne doivent PAS compter comme 2 paliers.
    levels = []
    for p in raw:
        if not levels or (p - levels[-1]) / levels[-1] > 0.005:
            levels.append(p)
    rank = min(range(len(levels)), key=lambda i: abs(levels[i] - px)) + 1
    _, tps = _ledger_levels(symbol)
    total = len(tps) if tps else max(len(levels), rank)
    return rank, total


def _wrap(head: str, rows: str, note: str) -> str:
    return (f"<div style='font-family:system-ui,Arial;max-width:520px'>"
            f"<h2 style='margin:0 0 8px'>{head}</h2>"
            f"<table style='border-collapse:collapse;font-size:14px'>{rows}</table>"
            f"<p style='color:#889;font-size:12px;margin-top:12px'>{note}</p></div>")


def _row(label: str, value: str, color: str = "#111") -> str:
    return (f"<tr><td style='padding:4px 14px 4px 0;color:#667;white-space:nowrap'>{label}</td>"
            f"<td style='color:{color};font-weight:600'>{value}</td></tr>")


def _txn_email(side: str, sym: str, qty: float, px: float,
               realized: float | None, when: str) -> tuple[str, str]:
    """
    (sujet, html) d'une transaction, complète : montant €, niveaux, résultat.
    BOT = ENTRÉE (achat) ; SLD = SORTIE étiquetée 🎯 TP (gain) / 🛑 SL (perte) — sans ambiguïté,
    même en paper (PnL reconstruit depuis l'entrée du ledger si realizedPNL absent).
    """
    montant = qty * px
    if side == "BOT":
        sl, tps = _ledger_levels(sym)
        rows = (_row("Quantité", f"{qty:.0f} actions")
                + _row("Prix d'achat", f"{px:.2f} $")
                + _row("Montant", f"{montant:,.0f} $")
                + (_row("Stop-loss", f"{sl:.2f} $", "#fb7185") if sl else "")
                + (_row("Objectifs TP", " / ".join(f"{t:.2f}" for t in tps), "#34d399") if tps else "")
                + _row("Heure", when))
        return (f"🟢 Entrée {sym} — {montant:,.0f} $",
                _wrap(f"🟢 Entrée — {sym}", rows, "Nouvel achat. Bracket SL/TP posé sur IBKR."))

    entry = _avg_entry(sym)
    # PnL € : le realizedPNL IBKR fait autorité UNIQUEMENT s'il est réellement non nul (compte
    # réel). En paper il revient à 0.0 (un vrai 0, pas None) → on RECONSTRUIT depuis l'entrée,
    # sinon le gain € s'affichait à +0 $ alors que le % était bon.
    if realized is not None and abs(realized) > 0.005:
        pnl_eur = realized
    elif entry:
        pnl_eur = (px - entry) * qty
    else:
        pnl_eur = None
    gain = (px >= entry) if entry else (pnl_eur is None or pnl_eur >= 0)
    emoji = "🎯" if gain else "🛑"
    color = "#34d399" if gain else "#fb7185"
    pct = f"{(px/entry-1)*100:+.1f}%" if entry else "n/c"
    pl = f"{pnl_eur:+,.0f} $" if pnl_eur is not None else "n/c"

    # Palier déclenché (TP1/2/3) + gain CUMULÉ sur la ligne (toutes les tranches vendues).
    exits = _position_exits(sym)
    rung = _tp_rung(sym, px, exits) if gain else None
    if rung:
        type_txt = f"{emoji} TP{rung[0]}/{rung[1]} — prise de profit"
    else:
        type_txt = f"{emoji} {'TP — prise de profit' if gain else 'SL — perte coupée'}"
    n_exits = len(exits)
    cumul = sum((p - entry) * q for _, p, q in exits) if entry and exits else None

    rows = (_row("Palier" if rung else "Type", type_txt, color)
            + _row("Quantité", f"{qty:.0f} actions")
            + _row("Entrée &rarr; Sortie", f"{('%.2f'%entry) if entry else '?'} &rarr; {px:.2f} $")
            + _row("Montant reçu", f"{montant:,.0f} $")
            + _row("Gain (cette tranche)", f"{pct}  ({pl})", color))
    if n_exits > 1 and cumul is not None:                 # 2e/3e palier → gain cumulé sur la ligne
        rows += _row("Gain cumulé (ligne)", f"{cumul:+,.0f} $  sur {n_exits} tranche(s)", color)
    rows += _row("Heure", when)

    note = ("Sortie déclenchée par le bracket IBKR (côté serveur). "
            + ("PnL réalisé IBKR." if realized is not None and abs(realized) > 0.005
               else "PnL calculé depuis l'entrée (paper : realizedPNL non fourni par IBKR)."))
    tp_tag = f"TP{rung[0]}" if rung else ("TP" if gain else "SL")
    return (f"{emoji} {tp_tag} {sym} {pct} ({pl})",
            _wrap(f"{emoji} Sortie — {sym}", rows, note))


def _aggregate(fills, skip_ids: set | None = None, day_filter: str | None = None) -> list[dict]:
    """
    Regroupe les fills en NOTIFICATIONS (1 mail par groupe, plus 1 mail par fill) :
    - ACHATS (BOT) groupés par TITRE → un ordre rempli en N exécutions = UNE entrée.
    - VENTES (SLD) groupées par (TITRE, prix arrondi) → chaque palier TP a son mail, mais les
      fills d'un MÊME palier fusionnent.
    Ignore les execId de skip_ids. Prix = moyenne pondérée du groupe. Retourne des dicts
    {execIds, side, sym, qty, price, realized, when}.
    """
    groups: dict = {}
    for f in fills:
        try:
            e = f.execution
            if e.side not in ("BOT", "SLD"):
                continue
            if day_filter and str(e.time)[:10] != day_filter:
                continue
            if skip_ids is not None and e.execId in skip_ids:
                continue
            sym = f.contract.symbol
            price = float(e.avgPrice or e.price or 0)
            qty = float(e.shares)
            realized = None
            try:
                r = f.commissionReport.realizedPNL
                if r is not None and abs(r) < 1e12:
                    realized = float(r)
            except Exception:
                pass
            key = (e.side, sym)                        # 1 mail par titre & par sens (par run)
            g = groups.setdefault(key, {"execIds": set(), "side": e.side, "sym": sym,
                                        "qty": 0.0, "val": 0.0, "realized": 0.0,
                                        "has_real": False, "when": ""})
            g["execIds"].add(e.execId)
            g["qty"] += qty
            g["val"] += price * qty
            if realized is not None:
                g["realized"] += realized
                g["has_real"] = True
            g["when"] = max(g["when"], str(e.time)[:19])
        except Exception:
            continue
    out = []
    for g in groups.values():
        avg = g["val"] / g["qty"] if g["qty"] else 0.0
        out.append({"execIds": g["execIds"], "side": g["side"], "sym": g["sym"], "qty": g["qty"],
                    "price": avg, "realized": (g["realized"] if g["has_real"] else None),
                    "when": g["when"]})
    return out


def main(test: bool = False, resend_today: bool = False) -> int:
    if test:
        subj, html = _txn_email("SLD", "TEST", 10, 130.00, None, datetime.now().strftime("%Y-%m-%d %H:%M"))
        return 0 if _send_email("[TEST] " + subj, html) else 1

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

    # RESEND : renvoie les transactions du JOUR au format corrigé (entrées + TP/SL), en
    # ignorant la dédup. Sert à re-notifier après un changement de format d'email.
    if resend_today:
        today = datetime.now().strftime("%Y-%m-%d")
        _journal_fills(fills)                          # journal à jour (pour _avg_entry / paliers)
        sent = 0
        for g in _aggregate(fills, day_filter=today):
            subj, html = _txn_email(g["side"], g["sym"], g["qty"], g["price"], g["realized"], g["when"])
            try:
                _send_email("[RENVOI] " + subj, html); sent += 1
            except Exception as ex:
                print(f"[EXIT-WATCH] renvoi échoué {g['sym']}: {ex}")
        ib.disconnect()
        print(f"[EXIT-WATCH] {sent} transaction(s) du jour renvoyée(s) (agrégées).")
        return 0

    # JOURNAL DURABLE : on enregistre TOUS les fills (achats + ventes), à chaque tick, quel que
    # soit l'état email/baseline. C'est le registre autoritaire sourcé IBKR. Idempotent (execId).
    n_journal = _journal_fills(fills)

    # Premier lancement (pas d'état) : on établit une BASELINE silencieuse — toutes les ventes
    # déjà présentes sont marquées "vues" SANS email. On n'alerte que sur les sorties POSTÉRIEURES.
    # Évite de blaster l'historique (et les éventuels fills fantômes du paper) à chaque déploiement.
    first_run = not SEEN_FILE.exists()
    seen = _load_seen()
    window_ids = {f.execution.execId for f in fills
                  if getattr(f.execution, "side", "") in ("BOT", "SLD")}

    if first_run:
        _save_seen(window_ids)
        ib.disconnect()
        print(f"[EXIT-WATCH] baseline initialisée ({len(window_ids)} transaction(s) marquée(s) vue(s), "
              f"aucun email). Journal : +{n_journal} fill(s). Les prochaines seront notifiées.")
        return 0

    # AGRÉGATION : 1 mail par ENTRÉE (titre) et 1 mail par PALIER de sortie (titre+prix), même si
    # l'ordre s'est rempli en plusieurs exécutions → fini les mails en rafale pour une ouverture.
    groups = _aggregate(fills, skip_ids=seen)
    notified = 0
    failed_ids: set[str] = set()
    for g in groups:
        try:
            subj, html = _txn_email(g["side"], g["sym"], g["qty"], g["price"], g["realized"], g["when"])
            _send_email(subj, html)
            notified += 1
        except Exception as ex:
            print(f"[EXIT-WATCH] envoi échoué pour {g['sym']} : {ex}")
            failed_ids |= g["execIds"]                 # groupe raté → pas marqué vu → réessai

    # Marque vu tout ce qui est en fenêtre SAUF les groupes dont l'email a échoué (retry au tick suivant).
    _save_seen(window_ids - failed_ids)
    ib.disconnect()
    print(f"[EXIT-WATCH] {notified} notification(s) (agrégées), {len(window_ids)} fill(s) en fenêtre, "
          f"journal +{n_journal} fill(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(test="--test" in sys.argv, resend_today="--resend-today" in sys.argv))
