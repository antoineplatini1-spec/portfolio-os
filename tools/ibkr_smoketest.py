"""
Smoke test IBKR — à lancer sur le VPS une fois le Gateway démarré.

    IBKR_ENABLED=1 python tools/ibkr_smoketest.py

Vérifie, sans passer d'ordre :
  1. la connexion au Gateway
  2. la qualification d'un contrat (AAPL)
  3. la lecture du compte (cash + positions)

Si tout passe, on peut activer le routage des ordres.
"""

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import IBKR_CONFIG


def main():
    print(f"Config IBKR : host={IBKR_CONFIG['host']} port={IBKR_CONFIG['port']} "
          f"client_id={IBKR_CONFIG['client_id']} order_type={IBKR_CONFIG['order_type']}")
    if not IBKR_CONFIG["enabled"]:
        print("⚠️  IBKR_ENABLED != 1 — active-le pour ce test : IBKR_ENABLED=1 python tools/ibkr_smoketest.py")
        return 1

    from portfolio.ibkr_broker import IBKRBroker, IBKRConnectionError

    try:
        broker = IBKRBroker(IBKR_CONFIG)
        print("✅ Connexion Gateway OK")
    except IBKRConnectionError as e:
        print(f"❌ Connexion échouée : {e}")
        return 1

    try:
        c = broker._stock_contract("AAPL")
        print(f"✅ Contrat qualifié : {c.symbol} @ {c.exchange}/{c.currency} (conId={c.conId})")
    except Exception as e:
        print(f"❌ Qualification contrat échouée : {e}")
        broker.disconnect()
        return 1

    try:
        cash = broker.account_cash()
        pos = broker.account_positions()
        print(f"✅ Compte : cash={cash:.2f}  positions={len(pos)}")
        for t, p in pos.items():
            print(f"     {t:8s} qty={p['qty']:.0f} avg={p['avg_cost']:.2f}")
    except Exception as e:
        print(f"⚠️  Lecture compte partielle : {e}")

    broker.disconnect()
    print("\n🎉 Smoke test terminé — Gateway prêt pour le routage d'ordres.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
