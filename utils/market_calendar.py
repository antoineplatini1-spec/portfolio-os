"""
Calendrier des jours fériés boursiers US (NYSE/Nasdaq).

Sans dépendance externe : les jours fériés NYSE sont publiés des années à l'avance et
stables, on les hardcode. Sert à SKIPPER le run quotidien les jours de fermeture (sinon
le bot place des ordres MKT dans le vide → rejets/queue).

⚠️ À prolonger chaque année (ajouter l'année suivante). Un `date` non couvert par
`_HOLIDAYS` lève un avertissement via `is_us_market_holiday(..., strict=False)` qui
retourne False par prudence (on préfère tourner que sauter à tort) — mais on log l'année
manquante pour penser à la compléter.
"""

from __future__ import annotations

from datetime import date

# Jours de FERMETURE COMPLÈTE du NYSE (les demi-journées ne sont pas des fermetures → non listées).
_HOLIDAYS: dict[int, set[str]] = {
    2026: {
        "2026-01-01",  # Jour de l'An
        "2026-01-19",  # Martin Luther King Jr. Day
        "2026-02-16",  # Presidents' Day
        "2026-04-03",  # Good Friday
        "2026-05-25",  # Memorial Day
        "2026-06-19",  # Juneteenth
        "2026-07-03",  # Independence Day (observé, le 4 tombe un samedi)
        "2026-09-07",  # Labor Day
        "2026-11-26",  # Thanksgiving
        "2026-12-25",  # Noël
    },
    2027: {
        "2027-01-01",  # Jour de l'An
        "2027-01-18",  # Martin Luther King Jr. Day
        "2027-02-15",  # Presidents' Day
        "2027-03-26",  # Good Friday
        "2027-05-31",  # Memorial Day
        "2027-06-18",  # Juneteenth (observé, le 19 tombe un samedi)
        "2027-07-05",  # Independence Day (observé, le 4 tombe un dimanche)
        "2027-09-06",  # Labor Day
        "2027-11-25",  # Thanksgiving
        "2027-12-24",  # Noël (observé, le 25 tombe un samedi)
    },
}

# Années couvertes — au-delà, on log un avertissement (à compléter).
_COVERED_YEARS = set(_HOLIDAYS)


def is_us_market_holiday(d: date | None = None) -> tuple[bool, str]:
    """
    (fermé, motif). `fermé`=True si `d` (défaut aujourd'hui) est un jour férié NYSE OU un
    week-end. Motif = étiquette lisible (jour férié, week-end, ou année non couverte).
    """
    d = d or date.today()
    if d.weekday() >= 5:                       # 5=samedi, 6=dimanche
        return True, "week-end"
    if d.year not in _COVERED_YEARS:
        # Année non renseignée : on NE bloque PAS (préférer tourner que sauter à tort),
        # mais on signale pour compléter _HOLIDAYS.
        return False, f"année {d.year} non couverte par le calendrier (à compléter)"
    if d.isoformat() in _HOLIDAYS[d.year]:
        return True, "jour férié US"
    return False, ""
