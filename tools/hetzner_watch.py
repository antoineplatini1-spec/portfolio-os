"""
Veille de disponibilité d'un type de serveur Hetzner (ex: CX23, en rupture).

Interroge l'API Hetzner Cloud et dit si le type visé est dispo dans les DC européens
(Falkenstein fsn1, Nuremberg nbg1, Helsinki hel1). Dès qu'il revient en stock, on
peut créer le serveur.

Prérequis — un token API Hetzner (lecture seule suffit) :
  Console Hetzner → projet → Security → API Tokens → Generate → permission "Read"
  Puis, dans PowerShell :  $env:HCLOUD_TOKEN = "le_token"
  (le token reste chez toi ; ne le colle pas dans le chat)

Usage :
  # Vérif ponctuelle
  $env:HCLOUD_TOKEN="..."; python tools/hetzner_watch.py

  # Veille en boucle toutes les 10 min, alerte email quand dispo
  $env:HCLOUD_TOKEN="..."; python tools/hetzner_watch.py --loop 10 --email

  # Cibler un autre type
  python tools/hetzner_watch.py --type cx23
"""

import argparse
import json
import os
import smtplib
import sys
import time
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API = "https://api.hetzner.cloud/v1"
EU_DATACENTERS = {"fsn1": "Falkenstein", "nbg1": "Nuremberg", "hel1": "Helsinki"}
_data_dir = Path(__file__).resolve().parent.parent / "data"


def _get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def check_availability(token: str, type_name: str) -> dict[str, bool]:
    """Retourne {dc_name: dispo?} pour le type visé dans les DC européens."""
    types = _get("/server_types?per_page=100", token)["server_types"]
    match = next((t for t in types if t["name"].lower() == type_name.lower()), None)
    if not match:
        names = ", ".join(sorted(t["name"] for t in types if t["name"].startswith("cx")))
        raise SystemExit(f"Type '{type_name}' introuvable. Types CX connus : {names}")
    type_id = match["id"]

    dcs = _get("/datacenters", token)["datacenters"]
    out = {}
    for dc in dcs:
        if dc["name"] in EU_DATACENTERS:
            available_ids = dc["server_types"]["available"]
            out[EU_DATACENTERS[dc["name"]]] = type_id in available_ids
    return out


def _send_email(type_name: str, dispo: dict[str, bool]):
    cfg_path = _data_dir / "email_config.json"
    if not cfg_path.exists():
        print("  [email] email_config.json introuvable — pas d'alerte email")
        return
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    where = ", ".join(dc for dc, ok in dispo.items() if ok)
    body = (f"<h2>✅ {type_name.upper()} de nouveau disponible</h2>"
            f"<p>Datacenters : <b>{where}</b></p>"
            f"<p>Fonce créer le serveur : https://console.hetzner.cloud</p>")
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = f"🟢 Hetzner {type_name.upper()} dispo — crée le VPS"
    msg["From"] = cfg["sender"]
    msg["To"] = cfg["recipient"]
    try:
        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as s:
            s.ehlo(); s.starttls(); s.login(cfg["sender"], cfg["password"])
            s.sendmail(cfg["sender"], cfg["recipient"], msg.as_string())
        print(f"  [email] alerte envoyée à {cfg['recipient']}")
    except Exception as e:
        print(f"  [email] échec envoi : {e}")


def _print_status(type_name: str, dispo: dict[str, bool]) -> bool:
    ts = datetime.now().strftime("%H:%M:%S")
    any_ok = any(dispo.values())
    line = "  ".join(f"{dc}:{'✅' if ok else '❌'}" for dc, ok in dispo.items())
    print(f"[{ts}] {type_name.upper()}  {line}")
    return any_ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", default="cx23", help="Type Hetzner à surveiller (défaut cx23)")
    ap.add_argument("--loop", type=float, default=0, help="Intervalle en minutes (0 = une seule vérif)")
    ap.add_argument("--email", action="store_true", help="Alerte email via data/email_config.json quand dispo")
    args = ap.parse_args()

    token = os.environ.get("HCLOUD_TOKEN")
    if not token:
        raise SystemExit("HCLOUD_TOKEN manquant. Crée un token lecture seule et : "
                         '$env:HCLOUD_TOKEN="..."')

    if args.loop <= 0:
        dispo = check_availability(token, args.type)
        ok = _print_status(args.type, dispo)
        if ok and args.email:
            _send_email(args.type, dispo)
        return 0 if ok else 2

    print(f"Veille {args.type.upper()} toutes les {args.loop} min (Ctrl+C pour arrêter)…")
    while True:
        try:
            dispo = check_availability(token, args.type)
            if _print_status(args.type, dispo):
                print(f"\n🟢 {args.type.upper()} DISPONIBLE — va créer le serveur !")
                if args.email:
                    _send_email(args.type, dispo)
                return 0
        except Exception as e:
            print(f"  [warn] {e}")
        time.sleep(args.loop * 60)


if __name__ == "__main__":
    sys.exit(main())
