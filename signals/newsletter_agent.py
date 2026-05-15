"""
Agent Newsletter — lit la newsletter Momentum (Capital) depuis Gmail
et en extrait des signaux sectoriels pour le contexte macro.

Accès Gmail : IMAP via les credentials de email_config.json (section "reader")
Fallback : utilise la dernière newsletter mise en cache dans data/newsletter_cache.json
"""

from __future__ import annotations
import imaplib
import email
import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# ── Mapping valeur française → secteur US ─────────────────────────
TICKER_TO_SECTOR = {
    # Clés longues avant les courtes pour éviter les faux positifs
    "stmicroelectronics": "Semi",
    "dassault systèmes": "Tech", "dassault aviation": "Industrie",
    "capgemini": "Tech", "teleperformance": "Tech", "atos": "Tech",
    "ses": "Tech",
    "bnp": "Finance", "société générale": "Finance",
    "crédit agricole": "Finance", "axa": "Finance",
    "sanofi": "Santé", "eurofins": "Santé", "ipsen": "Santé",
    "medincell": "Santé", "biomérieux": "Santé",
    "totalenergies": "Energie", "total": "Energie", "engie": "Energie",
    "vallourec": "Energie",
    "schneider": "Industrie", "legrand": "Industrie",
    "eiffage": "Industrie", "vinci": "Industrie",
    "bouygues": "Industrie", "bureau veritas": "Industrie",
    "alstom": "Industrie", "airbus": "Industrie",
    "dassault aviation": "Industrie", "safran": "Industrie",
    "lvmh": "Conso", "kering": "Conso", "renault": "Conso",
    "stellantis": "Conso", "hermès": "Conso",
    "l'oréal": "ConsoBase", "danone": "ConsoBase",
    "orange": "Telecoms", "iliad": "Telecoms",
    "unibail": "REIT", "urw": "REIT",
    "aperam": "Materiaux", "saint-gobain": "Materiaux",
    "arcelormittal": "Materiaux",
    "netflix": "Media",
}

# Mots-clés de recommandation (cherchés après "Notre recommandation")
BUY_KEYWORDS    = ["achetez", "acheter", "action à privilégier", "opportunité d'achat", "privilégiez"]
SELL_KEYWORDS   = ["allégements s'imposent", "alléger", "réduisez", "vendez", "vendre"]
AVOID_KEYWORDS  = ["éviter", "évitez", "un non actionnaire devrait éviter"]
CAUTION_KEYWORDS= ["prudence reste de mise", "regain de prudence", "certaine prudence"]

# Signaux macro cherchés dans le texte
MACRO_PATTERNS = {
    "oil_bullish":    [r"pétrole.{0,30}(au-dessus|supérieur|dépasse).{0,20}100", r"prix.{0,20}pétrole.{0,10}(hausse|monte)"],
    "oil_bearish":    [r"pétrole.{0,30}(sous|inférieur|chute|baisse)"],
    "inflation_high": [r"inflation.{0,30}[3-9]\.\d+\s*%", r"inflation.{0,20}(élevée|forte|hausse)"],
    "tech_pressure":  [r"(tech|technolog).{0,30}(baisse|recul|pression|perd)"],
    "semis_warning":  [r"semi.{0,30}(surachat|prudence|correc|baisse|allég)", r"stmicroelectronics.{0,50}(prudence|allég|surachat)"],
    "energy_strong":  [r"énergie.{0,30}(hausse|fort|impuls|montée)", r"pétrole.{0,10}100"],
    "market_caution": [r"(prudence|incertitude|risque).{0,30}(marché|bourse|cac)", r"cac.{0,50}prudence"],
    "market_bullish": [r"cac.{0,50}(hausse|rebond|opportunité|achat)", r"indices.{0,30}(progressent|montent|rebondissent)"],
}


@dataclass
class StockSignal:
    name: str           # nom de la valeur (français)
    sector: str         # secteur US mappé
    sentiment: str      # "BUY" | "SELL" | "AVOID" | "CAUTION" | "HOLD"
    summary: str        # extrait de la recommandation


@dataclass
class NewsletterSignal:
    date: str
    source: str                          # "imap" | "gdrive" | "cache" | "none"
    cac40_sentiment: str                 # "BULLISH" | "BEARISH" | "NEUTRAL"
    stock_signals: list[StockSignal]     # signaux par valeur
    sector_bias: dict[str, int]          # {sector: score} -2 fort négatif à +2 fort positif
    macro_flags: list[str]               # ["oil_bullish", "semis_warning", ...]
    raw_subject: str                     # sujet de l'email
    is_fresh: bool                       # newsletter d'aujourd'hui ou d'hier

    def format_log(self) -> list[str]:
        lines = [
            "── NEWSLETTER MOMENTUM ────────────────────────────────",
            f"  Date     : {self.date}  [{self.source}]{'  ⚠ ANCIENNE' if not self.is_fresh else ''}",
            f"  CAC 40   : {self.cac40_sentiment}",
        ]
        if self.stock_signals:
            lines.append("  Valeurs  :")
            for s in self.stock_signals:
                icon = {"BUY": "✅", "SELL": "🔴", "AVOID": "🚫", "CAUTION": "⚠️", "HOLD": "⏸️"}.get(s.sentiment, "•")
                lines.append(f"    {icon} {s.name} ({s.sector}) → {s.sentiment}")
        if self.macro_flags:
            lines.append(f"  Macro    : {', '.join(self.macro_flags)}")
        if self.sector_bias:
            biases = [f"{s}:{'+' if v>0 else ''}{v}" for s, v in sorted(self.sector_bias.items(), key=lambda x: -abs(x[1]))]
            lines.append(f"  Secteurs : {', '.join(biases[:6])}")
        lines.append("─" * 55)
        return lines


_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
CACHE_FILE = _data_dir / "newsletter_cache.json"


class NewsletterAgent:
    """Lit et parse la newsletter Momentum depuis Gmail."""

    def parse_from_text(self, text: str, subject: str = "", date_str: str = "") -> NewsletterSignal:
        """
        Parse une newsletter depuis un texte brut fourni directement
        (ex : contenu lu via Gmail MCP par Claude).
        Sauvegarde automatiquement en cache pour les runs automatisés suivants.
        """
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        signal = self._parse(text, subject, date_str, source="mcp")
        self._save_cache(text, subject, date_str)
        return signal

    def fetch_and_parse(self) -> NewsletterSignal:
        """
        Tente de lire la dernière newsletter dans l'ordre de priorité :
        1. IMAP Gmail (si app password configuré)
        2. Google Drive JSON cloud (si gdrive_cache_url configuré)
        3. Cache local JSON
        """
        cfg = self._load_imap_cfg()
        text, subject, date_str, source = None, "", "", "none"

        # 1 — IMAP
        if cfg:
            try:
                text, subject, date_str = self._fetch_imap(cfg)
                source = "imap"
            except Exception:
                pass

        # 2 — Google Drive cloud cache
        if text is None:
            gdrive_url = self._load_gdrive_url()
            if gdrive_url:
                try:
                    text, subject, date_str = self._fetch_gdrive(gdrive_url)
                    source = "gdrive"
                except Exception:
                    pass

        # 3 — Cache local
        if text is None:
            cached = self._load_cache()
            if cached:
                text     = cached.get("text", "")
                subject  = cached.get("subject", "")
                date_str = cached.get("date", "")
                source   = "cache"

        if not text:
            return self._empty_signal()

        signal = self._parse(text, subject, date_str, source)

        if source == "imap":
            self._save_cache(text, subject, date_str)

        return signal

    # ── Google Drive ───────────────────────────────────────────────────

    def _load_gdrive_url(self) -> Optional[str]:
        """Lit gdrive_cache_url dans email_config.json, retourne None si absent."""
        cfg_path = _data_dir / "email_config.json"
        if not cfg_path.exists():
            return None
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        url = cfg.get("gdrive_cache_url", "").strip()
        return url if url and "GDRIVE_FILE_ID" not in url else None

    def _fetch_gdrive(self, url: str) -> tuple[str, str, str]:
        """
        Télécharge le JSON de cache depuis Google Drive et retourne
        (text, subject, date_str).
        URL attendue : https://drive.google.com/uc?export=download&id=FILE_ID
        """
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        return data.get("text", ""), data.get("subject", ""), data.get("date", "")

    # ── IMAP ──────────────────────────────────────────────────────────

    def _load_imap_cfg(self) -> Optional[dict]:
        cfg_path = _data_dir / "email_config.json"
        if not cfg_path.exists():
            return None
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        reader = cfg.get("reader")
        if not reader or not reader.get("password") or reader.get("password") == "APP_PASSWORD_READER":
            return None
        return reader

    def _fetch_imap(self, cfg: dict) -> tuple[str, str, str]:
        """Récupère le dernier email de momentum@prismamedia.com via IMAP."""
        mail = imaplib.IMAP4_SSL(cfg.get("imap_server", "imap.gmail.com"), 993)
        mail.login(cfg["email"], cfg["password"])
        mail.select("inbox")

        # Chercher les emails des 3 derniers jours de ce sender
        since = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(FROM "momentum@prismamedia.com" SINCE "{since}")')
        mail.logout()

        ids = data[0].split()
        if not ids:
            raise ValueError("Aucun email Momentum trouvé")

        # Prendre le plus récent
        latest_id = ids[-1]
        mail2 = imaplib.IMAP4_SSL(cfg.get("imap_server", "imap.gmail.com"), 993)
        mail2.login(cfg["email"], cfg["password"])
        mail2.select("inbox")
        _, msg_data = mail2.fetch(latest_id, "(RFC822)")
        mail2.logout()

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        subject = str(msg["Subject"] or "")
        date_str = str(msg["Date"] or "")

        # Extraire le texte
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")

        return body, subject, date_str

    # ── Cache ──────────────────────────────────────────────────────────

    def _load_cache(self) -> Optional[dict]:
        if not CACHE_FILE.exists():
            return None
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_cache(self, text: str, subject: str, date_str: str):
        _data_dir.mkdir(exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"text": text, "subject": subject, "date": date_str,
                       "saved_at": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)

    # ── Parser ─────────────────────────────────────────────────────────

    def _parse(self, text: str, subject: str, date_str: str, source: str) -> NewsletterSignal:
        text_lower = text.lower()

        # Fraîcheur : date dans le sujet ou le texte
        today = datetime.now().strftime("%Y-%m-%d")
        is_fresh = (
            datetime.now().strftime("%d %B %Y").lower() in text_lower or
            datetime.now().strftime("%Y").lower() in date_str
        )

        # ── CAC 40 sentiment ──────────────────────────────────────────
        cac40_section = self._extract_section(text, "CAC 40")
        cac40_rec     = self._extract_recommendation(cac40_section)
        cac40_sentiment = self._rec_to_cac_sentiment(cac40_rec, cac40_section)

        # ── Signaux par valeur ─────────────────────────────────────────
        stock_signals: list[StockSignal] = []
        sector_bias: dict[str, int] = {}
        seen_names: set[str] = set()   # déduplication : évite doublon stm/stmicroelectronics

        for name_lower, sector in TICKER_TO_SECTOR.items():
            if name_lower not in text_lower:
                continue
            # Dédupliquer : si un alias plus court est un sous-ensemble d'un nom déjà vu, ignorer
            if any(name_lower in seen or seen in name_lower for seen in seen_names):
                continue
            # Trouver la section correspondante
            section = self._extract_section_for(text, name_lower)
            if not section:
                continue
            rec = self._extract_recommendation(section)
            if not rec:
                continue
            sentiment = self._classify_recommendation(rec, section)
            if sentiment == "UNKNOWN":
                continue

            seen_names.add(name_lower)
            display_name = name_lower.title()
            stock_signals.append(StockSignal(
                name=display_name, sector=sector,
                sentiment=sentiment, summary=rec[:120] if rec else ""
            ))

            # Biais sectoriel
            bias = {"BUY": +1, "SELL": -1, "AVOID": -2, "CAUTION": -1, "HOLD": 0}.get(sentiment, 0)
            sector_bias[sector] = sector_bias.get(sector, 0) + bias

        # ── Signaux macro ──────────────────────────────────────────────
        macro_flags: list[str] = []
        for flag, patterns in MACRO_PATTERNS.items():
            if any(re.search(p, text_lower) for p in patterns):
                macro_flags.append(flag)

        # Ajustements sectoriels depuis les macros
        if "oil_bullish" in macro_flags:
            sector_bias["Energie"] = sector_bias.get("Energie", 0) + 2
        if "inflation_high" in macro_flags or "tech_pressure" in macro_flags:
            sector_bias["Tech"]    = sector_bias.get("Tech", 0) - 1
        if "semis_warning" in macro_flags:
            sector_bias["Semi"]    = sector_bias.get("Semi", 0) - 2
        if "energy_strong" in macro_flags:
            sector_bias["Energie"] = sector_bias.get("Energie", 0) + 1

        return NewsletterSignal(
            date           = today,
            source         = source,
            cac40_sentiment= cac40_sentiment,
            stock_signals  = stock_signals,
            sector_bias    = sector_bias,
            macro_flags    = macro_flags,
            raw_subject    = subject,
            is_fresh       = is_fresh,
        )

    def _extract_section(self, text: str, keyword: str) -> str:
        """Extrait la section qui commence par `keyword`, jusqu'à la prochaine 'Notre recommandation'."""
        idx = text.lower().find(keyword.lower())
        if idx == -1:
            return ""
        # Chercher la fin de la recommandation propre à cette section
        rec_idx = text.lower().find("notre recommandation", idx)
        if rec_idx == -1:
            return text[idx:idx + 1500]
        # Fin = prochain double saut de ligne après la recommandation
        end = text.find("\n\n", rec_idx + 20)
        if end == -1:
            end = rec_idx + 800
        return text[idx:end]

    def _extract_section_for(self, text: str, name_lower: str) -> str:
        """
        Extrait la section d'une valeur : de son nom jusqu'à la fin de
        SA recommandation (la prochaine après le nom).
        Évite de déborder sur la section suivante.
        """
        idx = text.lower().find(name_lower)
        if idx == -1:
            return ""
        start = text.rfind("\n", 0, idx)
        start = start + 1 if start != -1 else idx

        # La recommandation propre à cette valeur = première occurrence après son nom
        rec_idx = text.lower().find("notre recommandation", idx)
        if rec_idx == -1:
            return text[start:start + 1000]
        # Fin = prochain \n\n après la recommandation (= fin du paragraphe)
        end = text.find("\n\n", rec_idx + 20)
        if end == -1:
            end = rec_idx + 600
        return text[start:end]

    def _extract_recommendation(self, section: str) -> str:
        """Extrait le texte après 'Notre recommandation :'."""
        if not section:
            return ""
        pat = re.search(
            r"Notre recommandation\s*:?\*?\*?\s*(.{20,600}?)(?:\n\n|\Z)",
            section, re.DOTALL | re.IGNORECASE
        )
        if pat:
            return pat.group(1).strip().replace("\n", " ")
        return ""

    def _classify_recommendation(self, rec: str, section: str) -> str:
        """
        Classifie uniquement sur le texte de la recommandation (rec).
        N'utilise pas section[-200:] pour éviter la contamination inter-sections.
        """
        text = rec.lower()
        if any(kw in text for kw in AVOID_KEYWORDS):
            return "AVOID"
        if any(kw in text for kw in SELL_KEYWORDS):
            return "SELL"
        if any(kw in text for kw in BUY_KEYWORDS):
            return "BUY"
        if any(kw in text for kw in CAUTION_KEYWORDS):
            return "CAUTION"
        if "conserver" in text or "conservez" in text:
            return "HOLD"
        return "UNKNOWN"

    def _rec_to_cac_sentiment(self, rec: str, section: str) -> str:
        # Utiliser la recommandation + début de section uniquement (pas la fin)
        text = (rec + " " + section[:400]).lower()
        if any(kw in text for kw in BUY_KEYWORDS):
            return "BULLISH"
        if any(kw in text for kw in AVOID_KEYWORDS + SELL_KEYWORDS):
            return "BEARISH"
        if any(kw in text for kw in CAUTION_KEYWORDS):
            return "BEARISH"
        return "NEUTRAL"

    def _empty_signal(self) -> NewsletterSignal:
        return NewsletterSignal(
            date="", source="none", cac40_sentiment="NEUTRAL",
            stock_signals=[], sector_bias={}, macro_flags=[],
            raw_subject="", is_fresh=False,
        )
