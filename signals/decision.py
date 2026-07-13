"""
Score de DÉCISION unifié — le point unique où tous les signaux se combinent.

Avant, chaque source patchait le pipeline dans son coin (véto news ici, tilt secteur
là, nomination ailleurs) → la plupart du signal se dissipait. Ici, tout devient une
FEATURE pondérée, bidirectionnelle, explicite et backtestable. Fonction PURE (aucune
dépendance I/O) → utilisable à l'identique en live et en backtest, et loggée pour
l'attribution (mesurer empiriquement quel signal prédit le rendement).

decision = momentum
         + w_sector     · sector       (biais −2..+2)
         + w_news       · news         (−1..+1 ; bullish AIDE, bearish PÉNALISE)
         + w_conviction · conviction   (0/1 ; nommé par une newsletter)

Le momentum reste la base 0-100 ; les autres sont des ajustements en points, bornés.
Les poids vivent dans config.DECISION_WEIGHTS (tunables + backtestables).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Features:
    """Features d'un candidat. Chacune est source-agnostique et bornée."""
    momentum: float = 0.0     # score screener 0-100 (base)
    sector: float = 0.0       # biais sectoriel en unités −2..+2
    news: float = 0.0         # −1..+1 (bearish → bullish), 0 si aucune actu
    conviction: float = 0.0   # 0..1 (nommé par une newsletter US)

    def clamp(self) -> "Features":
        self.sector = max(-2.0, min(2.0, self.sector))
        self.news = max(-1.0, min(1.0, self.news))
        self.conviction = max(0.0, min(1.0, self.conviction))
        return self


def news_feature(direction: str, strength: float) -> float:
    """Convertit un signal news typé en feature bidirectionnelle −1..+1."""
    s = max(0.0, min(1.0, float(strength or 0)))
    if direction == "bullish":
        return +s
    if direction == "bearish":
        return -s
    return 0.0


def decision_score(f: Features, weights: dict) -> tuple[float, dict]:
    """
    Retourne (score_total, contributions par feature). Les contributions sont loggées
    pour l'attribution → on saura quel signal a réellement pesé, et s'il a payé.
    """
    f = f.clamp()
    contrib = {
        "momentum":   round(f.momentum, 3),
        "sector":     round(weights.get("sector", 0.0)     * f.sector, 3),
        "news":       round(weights.get("news", 0.0)       * f.news, 3),
        "conviction": round(weights.get("conviction", 0.0) * f.conviction, 3),
    }
    return round(sum(contrib.values()), 3), contrib
