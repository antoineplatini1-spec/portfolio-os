"""
Rapport de validation sim-vs-réel : agrège data/ibkr_validation.jsonl.

    python tools/validation_report.py

Chaque ligne du log compare, pour un ordre réellement exécuté chez IBKR, le prix
et les frais RÉELS vs ce que notre PaperBroker simulé prédisait. Ce rapport dit si
le modèle (slippage 0.1% + frais) tient face aux conditions réelles — c'est le
feu vert (ou non) pour le go-live.
"""

import json
import sys
from pathlib import Path
from statistics import mean

# Sortie UTF-8 même sur console Windows cp1252 (les emojis ci-dessous)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_data_dir = Path(__file__).resolve().parent.parent / "data"
DEFAULT_LOG = _data_dir / "ibkr_validation.jsonl"


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    rows = load(path)
    if not rows:
        print(f"Aucune donnée de validation dans {path}")
        print("(Le log se remplit à chaque ordre exécuté avec IBKR_ENABLED=1 + IBKR_SHADOW=1)")
        return 0

    n = len(rows)
    price_diffs = [r["price_diff_pct"] for r in rows]
    fees_diffs = [r["fees_diff"] for r in rows]
    real_fees = sum(r["real_fees"] for r in rows)
    sim_fees = sum(r["sim_fees"] for r in rows)

    print(f"=== VALIDATION sim vs réel ({n} ordres) — {path.name} ===\n")
    print(f"Écart de prix (réel - sim, %) :")
    print(f"   moyen   : {mean(price_diffs):+.3f}%")
    print(f"   min/max : {min(price_diffs):+.3f}% / {max(price_diffs):+.3f}%")
    print(f"   |moyen| : {mean(abs(d) for d in price_diffs):.3f}%   (slippage réel moyen)")
    print()
    print(f"Frais :")
    print(f"   total réel IBKR : {real_fees:.2f}")
    print(f"   total simulé    : {sim_fees:.2f}")
    print(f"   écart moyen/ordre: {mean(fees_diffs):+.4f}")
    print()

    # Verdict simple
    avg_abs_slip = mean(abs(d) for d in price_diffs)
    fee_gap = abs(real_fees - sim_fees)
    print("=== VERDICT ===")
    if avg_abs_slip <= 0.20 and n >= 20:
        print(f"✅ Slippage réel ({avg_abs_slip:.3f}%) proche du modèle (0.1%). Modèle crédible.")
    elif n < 20:
        print(f"⏳ Échantillon trop petit ({n} ordres). Continuer à collecter (viser ≥ 20).")
    else:
        print(f"⚠️  Slippage réel ({avg_abs_slip:.3f}%) > modèle. Ajuster SLIPPAGE_PCT avant go-live.")
    if real_fees > 0 and fee_gap > real_fees * 0.5:
        print(f"⚠️  Frais réels très différents du modèle — mettre à jour BROKER_CONFIG.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
