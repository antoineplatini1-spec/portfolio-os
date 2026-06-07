"""Parse daily_log.txt en structures de données exploitables par le dashboard."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

# ── Patterns ──────────────────────────────────────────────────────────────────
_LINE    = re.compile(r'^\[(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}\] (.*)$')
_SCORE   = re.compile(r'Scores : max=(\d+)\s+mediane=(\d+)\s+\((\d+) tickers\)')
_CTX     = re.compile(r'Contexte marche : (\S+) -> seuil=(\d+), max_opens=(\d+)')
_CTX_WK  = re.compile(r'Contexte marche (\w+) \(max=(\d+)\)')
_CAND    = re.compile(r'(\d+) candidats')
_CASH    = re.compile(r'Cash deployable cette semaine : ([\d.]+) EUR')
_ACHAT   = re.compile(
    r'\[ACHAT\] (\w+) score=(\d+)'
    r'(?:\s+bull=(\d+)\s+bear=(\d+))?'
    r'\s+prix=([\d.]+)\s+investi=([\d.]+)EUR\s+SL=([\d.]+)\s+TP1=([\d.]+)'
    r'(.*)?'
)
_SKIP    = re.compile(r'\[SKIP\] (\w+) : (.+)')
_TSTOP   = re.compile(r'\[TIME STOP\] (\w+) : (.+)')
_SLTP    = re.compile(r'SL/TP declenches -> encaisse ([+\-][\d.]+) EUR')
_CLOSED  = re.compile(r'Position FERMEE : (\w+)')
_RESUME  = re.compile(
    r'RESUME : valeur=([\d.]+) EUR\s+investi=([\d.]+) EUR\s+'
    r'cash=([\d.]+) EUR\s+expo=([\d.]+)%\s+positions=(\d+)'
)
_PRIX    = re.compile(r'^\s{2}(\w+): ([\d.]+)$')
_WEEKEND = re.compile(r'Week-end')
_ERROR   = re.compile(r'ERREUR CRITIQUE')


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class BuyRecord:
    ticker:   str
    score:    int
    bull:     int | None
    bear:     int | None
    price:    float
    invested: float
    sl:       float
    tp1:      float
    bear_flags: list[str] = field(default_factory=list)


@dataclass
class DayScan:
    date:          str              # "YYYY-MM-DD"
    time:          str              # "HH:MM"
    weekend:       bool = False
    error:         str  = ""
    # Marché
    score_max:     int  = 0
    score_median:  int  = 0
    n_tickers:     int  = 0
    market_ctx:    str  = ""
    min_score:     int  = 0
    max_opens:     int  = 0
    n_candidates:  int  = 0
    # Budget
    deploy_cash:   float = 0.0
    budget_msg:    str   = ""
    # Prix mis à jour
    prices_updated: dict[str, float] = field(default_factory=dict)
    # SL/TP
    sltp_cash:     float = 0.0
    closed:        list[str] = field(default_factory=list)
    time_stops:    list[str] = field(default_factory=list)
    # Achats / skips
    buys:          list[BuyRecord] = field(default_factory=list)
    skips:         list[tuple[str, str]] = field(default_factory=list)
    # Résumé final
    total_value:   float = 0.0
    total_invested: float = 0.0
    total_cash:    float = 0.0
    exposure_pct:  float = 0.0
    n_positions:   int   = 0


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse_block(day_date: str, day_time: str, lines: list[str]) -> DayScan:
    scan = DayScan(date=day_date, time=day_time)

    for raw in lines:
        m = _LINE.match(raw)
        msg = m.group(2) if m else raw

        if _WEEKEND.search(msg):
            scan.weekend = True

        elif _ERROR.search(msg):
            scan.error = msg.replace("ERREUR CRITIQUE : ", "").strip()[:200]

        elif m2 := _SCORE.search(msg):
            scan.score_max    = int(m2.group(1))
            scan.score_median = int(m2.group(2))
            scan.n_tickers    = int(m2.group(3))

        elif m2 := _CTX.search(msg):
            scan.market_ctx = m2.group(1)
            scan.min_score  = int(m2.group(2))
            scan.max_opens  = int(m2.group(3))

        elif m2 := _CTX_WK.search(msg):
            scan.market_ctx = m2.group(1)
            scan.score_max  = int(m2.group(2))

        elif m2 := _CAND.search(msg):
            scan.n_candidates = int(m2.group(1))

        elif m2 := _CASH.search(msg):
            scan.deploy_cash = float(m2.group(1))

        elif "Budget semaine epuise" in msg:
            scan.budget_msg = "Budget épuisé"

        elif "Aucun signal suffisant" in msg:
            scan.budget_msg = "Aucun signal"

        elif "pas de nouveaux achats" in msg and "FAIBLE" in msg:
            scan.budget_msg = "Marché faible — pas de trades"

        elif m2 := _SLTP.search(msg):
            scan.sltp_cash = float(m2.group(1))

        elif m2 := _CLOSED.search(msg):
            scan.closed.append(m2.group(1))

        elif m2 := _TSTOP.search(msg):
            scan.time_stops.append(m2.group(1))

        elif m2 := _ACHAT.search(msg):
            flags_raw = m2.group(9) or ""
            flags = [f.strip().lstrip("⚠").strip()
                     for f in flags_raw.split(",") if f.strip()]
            scan.buys.append(BuyRecord(
                ticker   = m2.group(1),
                score    = int(m2.group(2)),
                bull     = int(m2.group(3)) if m2.group(3) else None,
                bear     = int(m2.group(4)) if m2.group(4) else None,
                price    = float(m2.group(5)),
                invested = float(m2.group(6)),
                sl       = float(m2.group(7)),
                tp1      = float(m2.group(8)),
                bear_flags = [f for f in flags if f],
            ))

        elif m2 := _SKIP.search(msg):
            scan.skips.append((m2.group(1), m2.group(2)))

        elif m2 := _PRIX.search(msg):
            scan.prices_updated[m2.group(1)] = float(m2.group(2))

        elif m2 := _RESUME.search(msg):
            scan.total_value    = float(m2.group(1))
            scan.total_invested = float(m2.group(2))
            scan.total_cash     = float(m2.group(3))
            scan.exposure_pct   = float(m2.group(4))
            scan.n_positions    = int(m2.group(5))

    return scan


def parse_log(log_path: Path) -> list[DayScan]:
    """
    Parse le fichier log et retourne la liste des scans,
    un par bloc (plusieurs blocs possibles le même jour).
    Trie par date décroissante.
    """
    if not log_path.exists():
        return []

    raw_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()

    # Découper en blocs : chaque bloc commence par une ligne "==="
    blocks: list[tuple[str, str, list[str]]] = []  # (date, time, lines)
    current_date = ""
    current_time = ""
    current_lines: list[str] = []
    in_block = False

    for line in raw_lines:
        m = _LINE.match(line)
        if not m:
            if in_block:
                current_lines.append(line)
            continue

        day = m.group(1)
        time_str = line[12:17]  # "HH:MM"
        msg = m.group(2)

        if "SCAN JOURNALIER" in msg or "Week-end" in msg:
            if in_block and current_lines:
                blocks.append((current_date, current_time, current_lines))
            current_date  = day
            current_time  = time_str
            current_lines = [line]
            in_block      = True
        elif in_block:
            current_lines.append(line)

    if in_block and current_lines:
        blocks.append((current_date, current_time, current_lines))

    scans = [_parse_block(d, t, ls) for d, t, ls in blocks]
    # Trier du plus récent au plus ancien, conserver le dernier bloc de chaque jour
    seen: dict[str, DayScan] = {}
    for s in scans:
        seen[s.date] = s   # écrase → garde le dernier run du jour
    result = sorted(seen.values(), key=lambda s: s.date, reverse=True)
    return result


def last_trade_date(scans: list[DayScan]) -> str | None:
    """Retourne la date du dernier achat réel."""
    for s in scans:
        if s.buys:
            return s.date
    return None
