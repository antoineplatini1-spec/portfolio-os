"""
Boucle d'apprentissage DÉTERMINISTE sur les trades clôturés.

Le LLM (llm_enrich.postmortem) attribue à chaque clôture une CAUSE typée + une leçon.
Ici, aucun LLM : on agrège ces causes dans le temps et on en tire des SUGGESTIONS
concrètes et chiffrées, affichées dans l'email récap. C'est ce qui transforme le
post-mortem en boucle utile (close → cause → agrégat → suggestion) plutôt qu'en
journal mort. Le code compte, l'humain (ou plus tard un paramètre) ajuste.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Vocabulaire FERMÉ des causes de clôture (partagé avec le prompt du post-mortem).
# Toute cause hors de cette liste est rejetée (anti-hallucination).
CAUSE_VOCAB: dict[str, str] = {
    "tp_gagnant":         "Objectif atteint (gagnant).",
    "sl_franc":           "SL touché nettement, thèse invalidée.",
    "stop_premature":     "SL touché sur un repli court — stop peut-être trop serré.",
    "momentum_essouffle": "Sortie lente / time-stop, momentum retombé.",
    "gap_defavorable":    "Mouvement adverse brutal (gap / choc).",
    "surachat_entree":    "Entrée en zone de surachat, retournement rapide.",
    "bruit":              "Bruit / malchance, faible amplitude.",
}

# Règles de suggestion : cause dominante → recommandation d'ajustement paramétrique.
# Déclenché quand la cause pèse une part significative des clôtures perdantes.
_SUGGESTION_RULES: dict[str, str] = {
    "stop_premature":     "SL prématurés fréquents → envisager d'élargir ATR_SL_MULTIPLIER "
                          "ou le plafond MAX_LOSS_PCT (stops trop serrés).",
    "momentum_essouffle": "Beaucoup de sorties sur essoufflement → resserrer le time-stop "
                          "(TIME_STOP_DAYS/LOSS) ou relever le seuil d'entrée du screener.",
    "gap_defavorable":    "Pertes sur gaps → renforcer le filtre earnings/news avant entrée "
                          "(élargir la fenêtre earnings, abaisser le seuil de véto news).",
    "surachat_entree":    "Entrées en surachat → durcir le filtre RSI/score du screener.",
    "sl_franc":           "SL francs récurrents → revoir la qualité de sélection (le screener "
                          "sur-note peut-être ce profil).",
}

# Une cause déclenche sa suggestion si elle représente ≥ ce seuil des clôtures PERDANTES
# de la fenêtre, avec un minimum d'occurrences pour éviter le bruit statistique.
_SHARE_THRESHOLD = 0.33
_MIN_OCCURRENCES = 3

_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
POSTMORTEM_LOG = _data_dir / "postmortems.jsonl"


def record_postmortem(record: dict) -> None:
    """Ajoute un post-mortem au journal (append-only)."""
    try:
        _data_dir.mkdir(exist_ok=True)
        row = {"ts": datetime.now(timezone.utc).isoformat(), **record}
        with open(POSTMORTEM_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _load(window_days: int) -> list[dict]:
    if not POSTMORTEM_LOG.exists():
        return []
    cutoff = datetime.now(timezone.utc).timestamp() - window_days * 86400
    out = []
    with open(POSTMORTEM_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                ts = datetime.fromisoformat(r["ts"]).timestamp()
                if ts >= cutoff:
                    out.append(r)
            except Exception:
                continue
    return out


def digest(window_days: int = 90) -> dict | None:
    """
    Agrège les post-mortems de la fenêtre et en tire des suggestions.
    Retourne None si trop peu de données pour conclure.

    {
      "n": int,                       # clôtures analysées
      "n_losers": int,
      "causes": {tag: count},         # toutes causes
      "suggestions": [str],           # actions concrètes déclenchées
      "recent_lessons": [{ticker, cause, lesson, pnl_pct}],
    }
    """
    rows = _load(window_days)
    if len(rows) < _MIN_OCCURRENCES:
        return None

    causes: dict[str, int] = {}
    losers: dict[str, int] = {}
    n_losers = 0
    for r in rows:
        c = r.get("cause", "")
        if c not in CAUSE_VOCAB:
            continue
        causes[c] = causes.get(c, 0) + 1
        if (r.get("pnl_pct") or 0) < 0:
            n_losers += 1
            losers[c] = losers.get(c, 0) + 1

    # Suggestions : causes PERDANTES qui pèsent assez pour agir.
    suggestions: list[str] = []
    for cause, count in sorted(losers.items(), key=lambda x: -x[1]):
        if cause not in _SUGGESTION_RULES:
            continue
        share = count / n_losers if n_losers else 0
        if count >= _MIN_OCCURRENCES and share >= _SHARE_THRESHOLD:
            suggestions.append(
                f"{_SUGGESTION_RULES[cause]} ({count}/{n_losers} pertes)"
            )

    recent = [
        {
            "ticker":  r.get("ticker", "?"),
            "cause":   r.get("cause", ""),
            "lesson":  r.get("lesson", ""),
            "pnl_pct": r.get("pnl_pct"),
        }
        for r in rows[-5:]
    ]

    return {
        "n":              len(rows),
        "n_losers":       n_losers,
        "causes":         causes,
        "suggestions":    suggestions,
        "recent_lessons": recent,
    }
