#!/usr/bin/env python
"""
Healthcheck du IB Gateway : exit 0 si l'API RÉPOND (session vivante), exit 1 sinon.

⚠️ Un simple test de port (nc) ne suffit PAS : le port 4002 reste ouvert (docker-proxy) même
quand la session est LOGGED-OUT → il faut un vrai handshake API. C'est exactement le mode de
panne qui a tué 2 runs d'affilée (Gateway « Up » mais API en timeout). Utilisé par run_daily.sh
en pré-vol : si exit 1 → on redémarre le Gateway avant de lancer le run.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    host = os.environ.get("IBKR_HOST", "127.0.0.1")
    port = int(os.environ.get("IBKR_PORT", "4002"))
    cid = int(os.environ.get("IBKR_HEALTH_CLIENT_ID", "9"))
    try:
        from ib_async import IB
        ib = IB()
        ib.connect(host, port, clientId=cid, timeout=15, readonly=True)
        ok = ib.isConnected()
        ib.disconnect()
        print("gateway OK" if ok else "gateway KO (connecté mais pas prêt)")
        return 0 if ok else 1
    except Exception as e:
        print(f"gateway KO : {type(e).__name__}: {str(e)[:100]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
