"""
Prudence ÉVÉNEMENTIELLE : nombre de jours avant les prochains résultats (earnings) d'un titre.

Objectif : ne PAS ouvrir une position juste avant des résultats — le risque de gap (un titre
peut sauter de ±10% sur un chiffre) n'est pas maîtrisable par un stop intraday. C'est une mesure
de prudence standard. Source : yfinance `.calendar` (pas de dépendance lxml, pas d'abonnement
IBKR). Cache par run (une position ne rouvre pas 15× dans la même journée).
"""

from __future__ import annotations

from datetime import date

_cache: dict[str, int | None] = {}


def days_to_earnings(ticker: str) -> int | None:
    """Jours calendaires avant les PROCHAINS résultats (>= 0), ou None si inconnu/passé."""
    if ticker in _cache:
        return _cache[ticker]
    d: int | None = None
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
        ed = cal.get("Earnings Date") if isinstance(cal, dict) else None
        nxt = None
        if isinstance(ed, (list, tuple)) and ed:
            nxt = ed[0]
        elif ed is not None:
            nxt = ed
        if nxt is not None and hasattr(nxt, "toordinal"):
            delta = (nxt - date.today()).days
            if delta >= 0:
                d = delta
    except Exception:
        d = None
    _cache[ticker] = d
    return d


def has_imminent_earnings(ticker: str, within_days: int) -> bool:
    """True si des résultats tombent dans <= within_days (0 → prudence désactivée)."""
    if within_days <= 0:
        return False
    d = days_to_earnings(ticker)
    return d is not None and 0 <= d <= within_days
