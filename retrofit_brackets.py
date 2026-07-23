#!/usr/bin/env python
"""
Retrofit des brackets natifs sur les positions HISTORIQUES laissées nues (ou protégées par un
stop manuel isolé). Remplace ces protections partielles par de vrais brackets SL + ladder TP,
tenus côté serveur IBKR, et marque le ledger (`bracket_oca`) pour que le bot leur cède la
gestion (plus de double-check).

TOUT vient d'IBKR (source de vérité) : positions, coût moyen, prix courant, ordres ouverts.
Le ledger n'est qu'ÉCRIT (le flag bracket_oca), jamais lu pour décider.

Niveaux (depuis le coût moyen IBKR, sans ATR/ledger) :
    SL  = −8% (plancher de perte stratégie)   TP = +6% / +12% / +20% (0,75 / 1,5 / 2,5 R),
    vendus 25% / 35% / 40%. Les TP sous le prix courant sont ignorés (anti-vente immédiate).

Ordre SÛR (dans protect_position) : poser le nouveau bracket → confirmer les stops vivants →
PUIS annuler le stop manuel. Jamais de fenêtre sans protection.
    Lancement : IBKR_ENABLED=1 python retrofit_brackets.py   [--dry]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

SL_PCT = 0.08                                            # plancher (repli si ATR indispo)
R_LADDER = [(0.75, 0.25), (1.5, 0.35), (2.5, 0.40)]      # (R-multiple, fraction vendue) — repli
_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))
STATE_FILE = _data_dir / "portfolio_state.json"


def _levels(cost: float, atr: float) -> tuple[float, list[tuple[float, float]]]:
    """
    SL + ladder TP identiques aux ENTRÉES normales du bot : on réutilise `risk.sl_price` et
    `risk.tp_prices` (ATR-based, SL capé −8%, TP 1,5/3/5×ATR). Repli si ATR indispo : SL −8% +
    TP en R-multiples du stop (0,75/1,5/2,5 R) — même profil, exprimé sur le stop réel.
    """
    from portfolio.risk import sl_price, tp_prices
    if atr and atr > 0:
        sl = sl_price(cost, atr)
        tps = [(round(l["price"], 2), l["sell_pct"]) for l in tp_prices(cost, atr)]
        return round(sl, 2), tps
    sl = round(cost * (1 - SL_PCT), 2)
    R = cost - sl
    return sl, [(round(cost + m * R, 2), f) for m, f in R_LADDER]


def _atr_for(sym: str) -> float:
    """ATR courant du titre via le même pipeline que le bot (fetch_ohlcv → indicators)."""
    try:
        from data.fetcher import fetch_ohlcv
        from indicators import compute_all
        df = fetch_ohlcv(sym)
        if df is None or df.empty:
            return 0.0
        df = compute_all(df)
        return float(df["ATR"].iloc[-1]) if "ATR" in df else 0.0
    except Exception:
        return 0.0


def main(dry: bool = False) -> int:
    from config import IBKR_CONFIG
    if not IBKR_CONFIG.get("enabled"):
        print("IBKR désactivé — abort."); return 1

    from portfolio.ibkr_broker import IBKRBroker
    broker = IBKRBroker(IBKR_CONFIG)                      # clientId 17, readonly=False

    positions = broker.account_positions()               # {sym:{qty,avg_cost}} — IBKR
    orders = broker.open_orders_by_symbol()              # {sym:[{orderId,type,oca,...}]} — IBKR
    marks = {it.contract.symbol: it.marketPrice for it in broker.ib.portfolio(IBKR_CONFIG.get("account") or "")}

    done = {}                                            # {sym: oca} pour marquage ledger
    for sym, info in sorted(positions.items()):
        qty, cost = abs(info["qty"]), info["avg_cost"]
        if sym.endswith(".PA") or qty < 1 or cost <= 0:
            continue
        ords = orders.get(sym, [])
        if any(o["oca"] for o in ords):                  # déjà un vrai bracket (ordres en OCA)
            print(f"  {sym:6s} déjà bracketé → skip")
            continue

        manual_ids = [o["orderId"] for o in ords if o["type"] == "STP"]   # stop(s) manuel(s) à retirer
        mark = marks.get(sym, 0) or 0
        # Niveaux ATR-based (mêmes que les entrées normales) ; repli R-multiples si ATR indispo.
        sl, tps_all = _levels(cost, _atr_for(sym))
        tps = [(p, f) for p, f in tps_all if p > mark * 1.001]   # anti-vente immédiate (TP > prix)
        if not tps:                                      # position déjà au-dessus de tous les TP
            tps = [(round(cost * 1.20, 2), 1.0)]

        tp_str = "/".join(f"{p:.2f}" for p, _ in tps)
        print(f"  {sym:6s} qty={qty:.0f} coût={cost:.2f} mark={mark:.2f} → SL {sl:.2f} TP {tp_str}"
              + (f"  (annule stop manuel {manual_ids})" if manual_ids else ""))
        if dry:
            continue

        res = broker.protect_position(sym, qty, sl, tps, cancel_ids=manual_ids)
        if res["ok"]:
            done[sym] = res["oca"]
            print(f"         ✅ bracket posé ({res['oca']}), stops vivants")
        else:
            print(f"         ❌ stops NON confirmés → bracket annulé, stop manuel CONSERVÉ")

    broker.disconnect()

    # Marquage ledger : ÉCRITURE directe du flag bracket_oca (pas de 2e connexion IBKR).
    if done and not dry:
        try:
            d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            for sym, oca in done.items():
                if sym in d.get("positions", {}):
                    d["positions"][sym]["bracket_oca"] = oca
            STATE_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nLedger marqué bracket_oca pour : {', '.join(sorted(done))}")
        except Exception as e:
            print(f"\n⚠️ marquage ledger échoué : {e} — brackets POSÉS mais bot pourrait double-gérer")

    print(f"\n{len(done)} position(s) retrofit-bracketée(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry="--dry" in sys.argv))
