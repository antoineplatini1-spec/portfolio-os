"""
Réconciliation état local ↔ compte IBKR réel.

    IBKR_ENABLED=1 python tools/reconcile.py

Compare, position par position, ce que le bot croit détenir (portfolio_state.json)
avec ce que le compte IBKR paper détient réellement. Signale les écarts de quantité
et les positions fantômes (présentes d'un côté seulement). En lecture seule : ne
corrige rien automatiquement, affiche juste le diff pour décision.
"""

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import IBKR_CONFIG

_data_dir = Path(__file__).resolve().parent.parent / "data"
STATE_FILE = _data_dir / "portfolio_state.json"
TOL = 1e-4


def load_local() -> dict[str, float]:
    with open(STATE_FILE, encoding="utf-8") as f:
        d = json.load(f)
    return {
        t: p.get("qty_remaining", 0)
        for t, p in d.get("positions", {}).items()
        if p.get("status") != "closed" and p.get("qty_remaining", 0) > TOL
    }


def main():
    if not IBKR_CONFIG["enabled"]:
        print("⚠️  IBKR_ENABLED != 1 — active-le pour la réconciliation.")
        return 1

    from portfolio.ibkr_broker import IBKRBroker

    broker = IBKRBroker(IBKR_CONFIG)
    local = load_local()
    remote = {t: p["qty"] for t, p in broker.account_positions().items()}
    broker.disconnect()

    all_tickers = sorted(set(local) | set(remote))
    print(f"{'TICKER':10s} {'LOCAL':>12s} {'IBKR':>12s} {'ÉCART':>12s}")
    print("-" * 48)
    n_diff = 0
    for t in all_tickers:
        lq = local.get(t, 0)
        rq = remote.get(t, 0)
        diff = rq - lq
        flag = ""
        if abs(diff) > TOL:
            n_diff += 1
            if lq == 0:
                flag = "  ← seulement IBKR"
            elif rq == 0:
                flag = "  ← seulement local"
            else:
                flag = "  ← écart qty"
        print(f"{t:10s} {lq:12.4f} {rq:12.4f} {diff:12.4f}{flag}")

    print("-" * 48)
    if n_diff == 0:
        print("✅ Réconcilié : local et IBKR sont alignés.")
    else:
        print(f"⚠️  {n_diff} écart(s) — à investiguer avant go-live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
