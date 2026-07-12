"""
SEC EDGAR — détection déterministe des dépôts 8-K (événements corporate officiels).

API publique et gratuite de la SEC. AUCUN LLM ici : on récupère les faits (type
d'événement via les codes d'items du 8-K, date, lien). Ces faits sont ensuite
loggés (provenance "algo / SEC", visibles même si le LLM est éteint) PUIS injectés
dans l'appel news du LLM pour l'interprétation direction/matérialité — sans appel
supplémentaire.

Deux endpoints :
  - https://www.sec.gov/files/company_tickers.json  (ticker → CIK, mis en cache)
  - https://data.sec.gov/submissions/CIK##########.json  (dépôts récents d'un émetteur)

La SEC exige un User-Agent déclaratif (sinon 403). Réglable via EDGAR_USER_AGENT ;
défaut fonctionnel. Aucune clé requise.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Libellés des items 8-K (les matériels d'abord). Un 8-K peut porter plusieurs items.
ITEM_LABELS: dict[str, str] = {
    "1.01": "Accord matériel signé",
    "1.02": "Résiliation d'accord matériel",
    "1.03": "Faillite / mise sous séquestre",
    "2.01": "Acquisition / cession d'actifs",
    "2.02": "Résultats financiers",
    "2.03": "Nouvelle obligation financière",
    "2.04": "Exigibilité anticipée de dette",
    "2.05": "Coûts de restructuration",
    "2.06": "Dépréciation d'actifs",
    "3.01": "Radiation / non-conformité de cotation",
    "3.02": "Émission non enregistrée de titres",
    "3.03": "Modification des droits des porteurs",
    "4.01": "Changement d'auditeur",
    "4.02": "États financiers jugés non fiables (restatement)",
    "5.01": "Changement de contrôle",
    "5.02": "Départ / nomination d'un dirigeant",
    "5.03": "Modification des statuts",
    "5.07": "Résultats de vote des actionnaires",
    "7.01": "Divulgation Regulation FD",
    "8.01": "Autre événement matériel",
    "9.01": "États financiers & annexes",
}

# Items à fort signal (déclencheurs d'attention : earnings, dirigeants, M&A, red flags).
MATERIAL_ITEMS = {"1.01", "1.03", "2.01", "2.02", "2.06",
                  "3.01", "4.01", "4.02", "5.01", "5.02"}

_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
CIK_CACHE = _data_dir / "edgar_ciks.json"
_UA = os.environ.get("EDGAR_USER_AGENT", "portfolio-os research bot (contact: set EDGAR_USER_AGENT)")


def _get(url: str, timeout: int = 15):
    """GET JSON avec le User-Agent exigé par la SEC. Lève sur erreur (pas de silence)."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _load_cik_map() -> dict[str, str]:
    """Charge ticker→CIK (10 chiffres) depuis le cache (< 7 j) ou la SEC."""
    if CIK_CACHE.exists():
        age = datetime.now().timestamp() - CIK_CACHE.stat().st_mtime
        if age < 7 * 86400:
            try:
                with open(CIK_CACHE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    data = _get("https://www.sec.gov/files/company_tickers.json")
    m: dict[str, str] = {}
    for row in data.values():
        t = str(row.get("ticker", "")).upper()
        cik = str(row.get("cik_str", "")).zfill(10)
        if t:
            m[t] = cik
    _data_dir.mkdir(exist_ok=True)
    with open(CIK_CACHE, "w", encoding="utf-8") as f:
        json.dump(m, f)
    return m


def recent_8k(tickers: list[str], days: int = 7) -> dict[str, list[dict]]:
    """
    Retourne {ticker: [{date, items:[codes], labels:[str], material:bool, url}]} pour les
    tickers ayant déposé un 8-K dans les `days` derniers jours. Déterministe. Lève si la
    connexion SEC échoue (l'appelant logge → jamais de fallback silencieux).
    """
    cikmap = _load_cik_map()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    out: dict[str, list[dict]] = {}

    for t in tickers:
        cik = cikmap.get(t.upper())
        if not cik:                       # ticker inconnu de la SEC (ex. .PA) → ignoré
            continue
        sub = _get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        rec = sub.get("filings", {}).get("recent", {})
        forms = rec.get("form", [])
        dates = rec.get("filingDate", [])
        items = rec.get("items", [])
        accs  = rec.get("accessionNumber", [])
        docs  = rec.get("primaryDocument", [])

        events: list[dict] = []
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            try:
                fdate = datetime.strptime(dates[i], "%Y-%m-%d").date()
            except Exception:
                continue
            if fdate < cutoff:
                continue
            codes = [c.strip() for c in (items[i] if i < len(items) else "").split(",") if c.strip()]
            labels = [ITEM_LABELS.get(c, f"Item {c}") for c in codes]
            material = any(c in MATERIAL_ITEMS for c in codes)
            acc = accs[i].replace("-", "") if i < len(accs) else ""
            doc = docs[i] if i < len(docs) else ""
            url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
                   if acc and doc else "")
            events.append({"date": dates[i], "items": codes, "labels": labels,
                           "material": material, "url": url})
        if events:
            out[t.upper()] = events
    return out
