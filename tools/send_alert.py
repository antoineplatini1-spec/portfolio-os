#!/usr/bin/env python
"""
Envoie un email d'ALERTE via le même Gmail que le recap (data/email_config.json). Sujet en
argv[1], corps lu sur stdin (texte). Sert au run quotidien : sur échec (rc != 0), alerter
IMMÉDIATEMENT — sans dépendance externe (pas besoin de healthchecks.io). Comble le trou du
"run échoué en silence" (2 jours perdus les 27-28/07 sans alerte).
    tail -30 log | python tools/send_alert.py "🚨 Run échoué"
"""
import json
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

_data = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))


def main() -> int:
    subject = sys.argv[1] if len(sys.argv) > 1 else "🚨 Alerte portfolio-os"
    body = sys.stdin.read() if not sys.stdin.isatty() else "(pas de détail)"
    cfg_path = os.path.join(_data, "email_config.json")
    if not os.path.exists(cfg_path):
        print("[ALERT] email_config.json introuvable — pas d'alerte")
        return 1
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    html = f"<h2 style='color:#c0392b'>{subject}</h2><pre style='font-size:12px;white-space:pre-wrap'>{body[-4000:]}</pre>"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = cfg["recipient"]
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as s:
            s.ehlo(); s.starttls(); s.login(cfg["sender"], cfg["password"])
            s.sendmail(cfg["sender"], cfg["recipient"], msg.as_string())
        print(f"[ALERT] email envoyé à {cfg['recipient']}")
        return 0
    except Exception as e:
        print(f"[ALERT] envoi échoué : {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
