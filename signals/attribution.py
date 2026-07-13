"""
Boucle d'ATTRIBUTION — mesure empirique de quel signal prédit réellement le rendement.

C'est la brique qui dissout le goulot d'étranglement : au lieu de supposer que les
signaux collectés (news, secteur, conviction…) sont utiles, on le MESURE.

- record_decision(...) : à chaque ouverture, logge les features + contributions du score.
- digest() : joint ces décisions aux post-mortems (PnL réalisé à la clôture) et calcule
  la corrélation de chaque feature avec le PnL. Résultat surfacé dans l'email → tu vois
  noir sur blanc quels signaux paient, et lesquels sont du bruit à dépondérer/couper.

Déterministe, aucune dépendance LLM. Le forward-test des signaux LLM (news, newsletter)
passe UNIQUEMENT par ici — le backtest, lui, ne peut valider que le cœur déterministe.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
DECISIONS_LOG = _data_dir / "decisions_log.jsonl"
POSTMORTEM_LOG = _data_dir / "postmortems.jsonl"

_FEATURES = ("momentum", "sector", "news", "conviction")


def record_decision(ticker: str, features: dict, contrib: dict, total: float) -> None:
    """Logge la décision d'ouverture (features + contributions) pour attribution."""
    try:
        _data_dir.mkdir(exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            "features": {k: features.get(k) for k in _FEATURES},
            "contrib": contrib,
            "total": total,
        }
        with open(DECISIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    return out


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / (vx ** 0.5 * vy ** 0.5)


def digest(min_n: int = 10) -> dict | None:
    """
    Joint décisions (features à l'ouverture) ↔ post-mortems (PnL à la clôture) par ticker,
    et calcule la corrélation de chaque feature avec le PnL réalisé.
    Retourne None tant qu'il y a trop peu de trades appariés (< min_n).

    {
      "n": int,
      "corr": {feature: corr | None},   # corrélation feature ↔ PnL%
      "avg_pnl": float,
    }
    """
    decisions = _load_jsonl(DECISIONS_LOG)
    postmortems = [p for p in _load_jsonl(POSTMORTEM_LOG) if p.get("pnl_pct") is not None]
    if not decisions or not postmortems:
        return None

    # Index des décisions par ticker (triées par ts) pour apparier chaque clôture à la
    # décision d'ouverture la plus récente AVANT la clôture.
    by_ticker: dict[str, list[dict]] = {}
    for d in decisions:
        by_ticker.setdefault(d["ticker"], []).append(d)
    for lst in by_ticker.values():
        lst.sort(key=lambda r: r.get("ts", ""))

    pairs: list[tuple[dict, float]] = []
    for pm in postmortems:
        tk = pm.get("ticker")
        cands = by_ticker.get(tk)
        if not cands:
            continue
        pm_ts = pm.get("ts", "")
        prior = [d for d in cands if d.get("ts", "") <= pm_ts] or cands
        pairs.append((prior[-1]["features"], float(pm["pnl_pct"])))

    if len(pairs) < min_n:
        return None

    pnls = [p for _, p in pairs]
    corr = {}
    for feat in _FEATURES:
        xs = [float((f.get(feat) or 0)) for f, _ in pairs]
        c = _pearson(xs, pnls)
        corr[feat] = round(c, 3) if c is not None else None

    return {
        "n": len(pairs),
        "corr": corr,
        "avg_pnl": round(sum(pnls) / len(pnls), 2),
    }
