"""
Track record — mesure QUOTIDIENNE de l'edge sur les trades RÉELS.

Source = `data/trade_journal.jsonl` (fills IBKR réels : prix d'achat ET de vente). On apparie
les fills en round-trips FIFO et on calcule le PnL réel (prix vente − prix achat), FIABLE même
quand IBKR ne renvoie pas `realizedPNL` (cas paper). Se recoupe avec la variation de NLV — c'est
ce qui a permis de démasquer les chiffres pollués du ledger (44 trades à 0).

Pur et testable : `round_trip_stats(fills)` ne fait aucune I/O.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict, deque


def round_trip_stats(fills: list[dict]) -> dict:
    """
    Apparie les fills en round-trips FIFO (achats BOT ↔ ventes SLD, par titre) et renvoie les
    stats de trades RÉALISÉS. `fills` : liste de {symbol, side, qty, price, time}.
    Retourne {n_closed, wins, losses, win_rate, profit_factor, avg_win, avg_loss,
              realized_pnl, n_open}. profit_factor = None si aucune perte.
    """
    rows = sorted(
        [r for r in fills if (r.get("qty") or 0) > 0 and (r.get("price") or 0) > 0],
        key=lambda r: str(r.get("time", "")),
    )
    buys: dict[str, deque] = defaultdict(deque)
    open_qty: dict[str, float] = defaultdict(float)
    pnls: list[float] = []
    for r in rows:
        sym = r["symbol"]; q = float(r["qty"]); p = float(r["price"]); side = r.get("side")
        if side == "BOT":
            buys[sym].append([q, p]); open_qty[sym] += q
        elif side == "SLD":
            left = q
            while left > 1e-6 and buys[sym]:
                lot = buys[sym][0]
                m = min(left, lot[0])
                pnls.append((p - lot[1]) * m)          # PnL réel de la tranche appariée
                lot[0] -= m; left -= m; open_qty[sym] -= m
                if lot[0] <= 1e-6:
                    buys[sym].popleft()
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    gw = sum(wins); gl = abs(sum(losses))
    return {
        "n_closed": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(pnls), 4) if pnls else 0.0,
        "profit_factor": round(gw / gl, 2) if gl > 0 else None,
        "avg_win": round(gw / len(wins), 2) if wins else 0.0,
        "avg_loss": round(-gl / len(losses), 2) if losses else 0.0,
        "realized_pnl": round(gw - gl, 2),
        "n_open": sum(1 for _, q in open_qty.items() if q > 1e-6),
    }


def read_journal(journal_file: str) -> list[dict]:
    """Charge les fills du journal (jsonl). [] si absent."""
    if not os.path.exists(journal_file):
        return []
    out = []
    try:
        for line in open(journal_file, encoding="utf-8"):
            line = line.strip()
            if line:
                out.append(json.loads(line))
    except Exception:
        pass
    return out
