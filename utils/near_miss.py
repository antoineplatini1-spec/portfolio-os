# -*- coding: utf-8 -*-
"""
Gestion du near-miss journal (14 jours roulants).

near_miss_history.json stocké dans data/ :
  liste de { date, ticker, net_score, reason, bull_score, bear_score, price, sector }

Raisons possibles :
  "veto_secteur" — débat ACHETER mais secteur saturé (>= 2 positions)
  "budget"       — débat ACHETER mais cash disponible < 100 €
  "score_limite" — décision PASSER avec net_score >= -5 (très proche du seuil)
  "score_bas"    — ticker screener avec score entre min_score-10 et min_score
"""

import json
import os
from datetime import date, timedelta

_FILENAME = "near_miss_history.json"
_RETENTION_DAYS = 14


def _json_path(data_dir: str) -> str:
    return os.path.join(data_dir, _FILENAME)


def _load_all(data_dir: str) -> list[dict]:
    path = _json_path(data_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_all(entries: list[dict], data_dir: str) -> None:
    path = _json_path(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def purge_old_entries(data_dir: str) -> None:
    """Supprime les entrées de plus de 14 jours."""
    cutoff = (date.today() - timedelta(days=_RETENTION_DAYS)).isoformat()
    entries = _load_all(data_dir)
    kept = [e for e in entries if e.get("date", "") >= cutoff]
    if len(kept) != len(entries):
        _save_all(kept, data_dir)


def save_near_miss(
    ticker: str,
    net_score: float,
    reason: str,
    bull_score: int,
    bear_score: int,
    price: float,
    sector: str,
    data_dir: str,
) -> None:
    """
    Enregistre un near-miss dans le journal.
    Déduplique : un seul enregistrement par (date, ticker, reason).
    """
    today_str = date.today().isoformat()
    entries = _load_all(data_dir)

    # Déduplication : pas deux fois le même ticker+raison le même jour
    for e in entries:
        if e["date"] == today_str and e["ticker"] == ticker and e["reason"] == reason:
            return

    entries.append({
        "date":       today_str,
        "ticker":     ticker,
        "net_score":  round(float(net_score), 1),
        "reason":     reason,
        "bull_score": int(bull_score),
        "bear_score": int(bear_score),
        "price":      round(float(price), 2),
        "sector":     sector,
    })
    _save_all(entries, data_dir)


def load_recent_near_misses(data_dir: str, days: int = _RETENTION_DAYS) -> list[dict]:
    """Retourne les near-misses des N derniers jours, triés par net_score desc puis date desc."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    entries = _load_all(data_dir)
    recent = [e for e in entries if e.get("date", "") >= cutoff]
    def _sort_key(e: dict):
        from datetime import date as _date
        try:
            d_ord = -_date.fromisoformat(e.get("date", "2000-01-01")).toordinal()
        except ValueError:
            d_ord = 0
        return (-e.get("net_score", 0), d_ord)

    return sorted(recent, key=_sort_key)
