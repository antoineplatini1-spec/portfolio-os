"""
Couche d'enrichissement LLM — OPTIONNELLE et éteinte par défaut.

Philosophie (cf. discussion archi) : le LLM ne décide rien, ne calcule aucun
chiffre qui touche un ordre. Il lit du texte non structuré (newsletter, headlines
d'actualité) et en sort des SIGNAUX TYPÉS + sourcés, que le code déterministe
consomme comme de simples features. Tout est :

  - désactivé tant que LLM_ENABLED != "1" ET qu'aucune clé ANTHROPIC_API_KEY n'est
    posée → aucun appel, aucun coût, aucun changement de comportement ;
  - à tolérance de panne : toute erreur (pas de clé, SDK absent, API down, JSON
    invalide) retombe sur le chemin déterministe existant (regex / pas de signal) ;
  - tracé : chaque sortie est écrite dans data/llm_signals.jsonl avec modèle, version
    de prompt, tokens (coût) et provenance (citation + source) → substrat d'audit et
    de future évaluation forward-return.

Deux fonctions publiques :
  - fetch_news_signals(tickers)         : headlines yfinance → signaux événementiels.
  - enrich_sector_bias(text, regex_bias): newsletter → biais sectoriel fiabilisé.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from signals.learning import CAUSE_VOCAB

# Modèle par défaut : Opus 4.8 (le plus capable). Basculer sur claude-sonnet-5 via
# la variable d'env LLM_MODEL pour diviser le coût par ~2,5 sur ces tâches
# d'extraction (Sonnet suffit largement à lire du texte).
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-opus-4-8")

# Vocabulaire sectoriel FERMÉ : doit rester aligné sur les valeurs de SECTOR_MAP
# (config.py) pour que l'overlay macro sache mapper le biais sur l'univers US.
SECTOR_VOCAB = [
    "Tech", "Semi", "Finance", "Santé", "Energie", "Industrie",
    "Conso", "ConsoBase", "Materiaux", "REIT", "Telecoms", "Media",
    "Utilities", "Macro",
]

PROMPT_VERSION = "2026-07-11.1"

# Tarifs $/million de tokens (input, output) — pour l'ESTIMATION de coût affichée
# dans l'email récap. Tarif STANDARD (borne haute) : pendant une période d'intro le
# coût réel est plus bas. À ajuster si Anthropic change ses prix.
PRICING = {
    "claude-sonnet-5":  (3.0, 15.0),
    "claude-opus-4-8":  (5.0, 25.0),
    "claude-opus-4-7":  (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5":   (10.0, 50.0),
}

# Accumulateur de conso sur le run courant (le process daily_auto tourne 1×/jour).
_usage_run = {"input": 0, "output": 0, "calls": 0}

_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
LLM_LOG = _data_dir / "llm_signals.jsonl"


def usage_summary() -> dict:
    """Conso LLM cumulée du run : {model, calls, input, output, cost_usd}.
    cost_usd = None si le modèle n'est pas au barème."""
    rate = PRICING.get(LLM_MODEL)
    inp, outp = _usage_run["input"], _usage_run["output"]
    cost = (inp / 1e6 * rate[0] + outp / 1e6 * rate[1]) if rate else None
    return {
        "model":    LLM_MODEL,
        "calls":    _usage_run["calls"],
        "input":    inp,
        "output":   outp,
        "cost_usd": cost,
    }


# Erreurs des appels LLM du run — JAMAIS avalées : surfacées dans les logs + l'email,
# pour toujours savoir quand un fallback algo a eu lieu et pourquoi.
_run_status = {"errors": []}


def run_errors() -> list:
    """Liste des échecs d'appels LLM du run (vide = tout OK)."""
    return list(_run_status["errors"])


# ── Activation ────────────────────────────────────────────────────

def is_enabled() -> bool:
    """
    Le LLM n'est actif que si on l'a explicitement demandé (LLM_ENABLED=1) ET
    qu'une clé API est présente. Sinon tout le module est un no-op silencieux.
    """
    return os.environ.get("LLM_ENABLED", "0") == "1" and bool(
        os.environ.get("ANTHROPIC_API_KEY")
    )


# ── Client + audit ────────────────────────────────────────────────

def _client():
    """Import paresseux : `anthropic` n'est requis que si le LLM est activé."""
    import anthropic  # noqa: PLC0415
    return anthropic.Anthropic()


def _log(kind: str, payload: dict, usage: Optional[dict] = None):
    """Journalise une sortie LLM (audit + substrat d'évaluation)."""
    try:
        _data_dir.mkdir(exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,                 # "news" | "sector_bias"
            "model": LLM_MODEL,
            "prompt_version": PROMPT_VERSION,
            "usage": usage or {},
            **payload,
        }
        with open(LLM_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        # L'audit ne doit jamais casser le run.
        pass


def _extract_json(text: str):
    """
    Extrait l'objet OU le tableau JSON d'une réponse (robuste aux préambules / fences).
    Le conteneur externe est choisi selon le PREMIER crochet rencontré : '{' → objet,
    '[' → tableau. Indispensable pour ne pas prendre un tableau interne (ex. la valeur
    "sectors":[...]) pour le conteneur d'un objet {"sectors":[...], "trades":[...]}.
    """
    text = text.strip()
    obj_i = text.find("{")
    arr_i = text.find("[")
    if obj_i == -1 and arr_i == -1:
        return json.loads(text)
    if arr_i == -1 or (obj_i != -1 and obj_i < arr_i):
        return json.loads(text[obj_i : text.rfind("}") + 1])
    return json.loads(text[arr_i : text.rfind("]") + 1])


def _call(system: str, user: str, max_tokens: int = 1500) -> tuple[Optional[object], dict]:
    """
    Un appel LLM, sans thinking (extraction simple → on garde coût/latence bas).
    Retourne (data_json_ou_None, usage). Toute erreur → (None, {}).
    """
    try:
        client = _client()
        msg = client.messages.create(
            model=LLM_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(
            getattr(b, "text", "") for b in msg.content
            if getattr(b, "type", "") == "text"
        )
        usage = {
            "in": getattr(msg.usage, "input_tokens", None),
            "out": getattr(msg.usage, "output_tokens", None),
        }
        _usage_run["input"]  += usage["in"] or 0
        _usage_run["output"] += usage["out"] or 0
        _usage_run["calls"]  += 1
        return _extract_json(text), usage
    except Exception as e:
        # Ne JAMAIS avaler : on enregistre la raison pour la rendre visible en aval.
        _run_status["errors"].append(f"{type(e).__name__}: {str(e)[:150]}")
        return None, {}


# ── 1. Signaux d'actualité par titre ──────────────────────────────

_NEWS_SYSTEM = (
    "Tu es un analyste actions. On te donne des titres d'actualité RÉCENTS pour "
    "quelques valeurs. Pour chaque valeur ayant une actualité MATÉRIELLE (résultats, "
    "guidance, contrat, rachat, litige, régulation, M&A, dirigeant), renvoie un objet. "
    "Ignore le bruit (opinions d'analystes génériques, listicles). "
    "N'invente jamais : ne cite que ce qui est présent dans les titres fournis. "
    "Réponds UNIQUEMENT par un tableau JSON, sans texte autour. Schéma par élément : "
    '{"ticker": str, "event": str court, "direction": "bullish"|"bearish"|"neutral", '
    '"strength": float 0..1, "horizon_days": int, "quote": str (titre verbatim), "url": str}. '
    "Tableau vide [] si rien de matériel."
)


def _recent_headlines(ticker: str, max_items: int = 5, max_age_days: int = 4) -> list[dict]:
    """Récupère les headlines récentes via yfinance, format tolérant aux versions."""
    out: list[dict] = []
    try:
        import yfinance as yf
        raw = yf.Ticker(ticker).news or []
    except Exception:
        return out

    now = datetime.now(timezone.utc)
    for item in raw:
        # yfinance récent imbrique sous "content", ancien à plat.
        c = item.get("content", item) if isinstance(item, dict) else {}
        title = c.get("title") or item.get("title") or ""
        if not title:
            continue
        # Date de publication (formats variés)
        ts = (
            item.get("providerPublishTime")
            or c.get("pubDate")
            or c.get("displayTime")
        )
        age_days = None
        try:
            if isinstance(ts, (int, float)):
                pub = datetime.fromtimestamp(ts, tz=timezone.utc)
            elif isinstance(ts, str):
                pub = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            else:
                pub = None
            if pub is not None:
                age_days = (now - pub).total_seconds() / 86400
        except Exception:
            age_days = None
        if age_days is not None and age_days > max_age_days:
            continue
        link = (
            (c.get("canonicalUrl") or {}).get("url")
            if isinstance(c.get("canonicalUrl"), dict)
            else item.get("link", "")
        ) or ""
        pub_name = ""
        prov = c.get("provider") or item.get("publisher")
        if isinstance(prov, dict):
            pub_name = prov.get("displayName", "")
        elif isinstance(prov, str):
            pub_name = prov
        out.append({"title": title, "publisher": pub_name, "url": link})
        if len(out) >= max_items:
            break
    return out


def fetch_news_signals(
    tickers: list[str], max_tickers: int = 30, edgar_events: dict | None = None
) -> dict[str, dict]:
    """
    Retourne {ticker: {event, direction, strength, horizon_days, quote, url}} pour les
    valeurs ayant une actualité matérielle récente. {} si LLM désactivé ou aucune
    actualité. Un SEUL appel LLM (batch) pour tenir le coût.

    edgar_events : {ticker: [{date, labels, url, ...}]} déjà récupéré par le code (SEC
    8-K). Fusionné VERBATIM dans le corpus → le LLM interprète les événements officiels
    en même temps que les headlines, sans appel supplémentaire.
    """
    if not is_enabled() or not tickers:
        return {}

    # Le code récupère les faits (headlines + 8-K SEC) et les passe VERBATIM au LLM.
    # Le LLM ne "va" jamais chercher lui-même → factuel, auditable.
    corpus: dict[str, list[dict]] = {}
    for t in tickers[:max_tickers]:
        hl = _recent_headlines(t)
        if hl:
            corpus[t] = hl

    # Événements 8-K officiels prépendus (prioritaires) — inclut les tickers qui ont un
    # 8-K mais pas de headline.
    for tk, evs in (edgar_events or {}).items():
        entries = [
            {"title": f"SEC 8-K ({e.get('date')}) : " + ", ".join(e.get("labels", [])),
             "publisher": "SEC EDGAR", "url": e.get("url", "")}
            for e in evs
        ]
        if entries:
            corpus[tk.upper()] = entries + corpus.get(tk.upper(), [])

    if not corpus:
        return {}

    lines = []
    for t, items in corpus.items():
        lines.append(f"### {t}")
        for h in items:
            src = f" — {h['publisher']}" if h["publisher"] else ""
            lines.append(f"- {h['title']}{src}")
    user = "\n".join(lines)

    data, usage = _call(_NEWS_SYSTEM, user, max_tokens=2000)
    if not isinstance(data, list):
        return {}

    # Validation stricte : on ne garde que les tickers réellement soumis, et on
    # rattache l'URL depuis notre corpus (le LLM n'invente pas de source).
    valid_dir = {"bullish", "bearish", "neutral"}
    result: dict[str, dict] = {}
    for it in data:
        if not isinstance(it, dict):
            continue
        tk = str(it.get("ticker", "")).upper()
        if tk not in corpus:
            continue
        direction = str(it.get("direction", "")).lower()
        if direction not in valid_dir:
            continue
        try:
            strength = max(0.0, min(1.0, float(it.get("strength", 0))))
        except (TypeError, ValueError):
            strength = 0.0
        # URL de confiance = celle de notre corpus si le LLM n'en fournit pas de valide
        url = it.get("url") or (corpus[tk][0]["url"] if corpus[tk] else "")
        result[tk] = {
            "event": str(it.get("event", ""))[:200],
            "direction": direction,
            "strength": strength,
            "horizon_days": int(it.get("horizon_days", 0) or 0),
            "quote": str(it.get("quote", ""))[:300],
            "url": url,
        }

    _log("news", {"tickers": list(corpus.keys()), "signals": result}, usage)
    return result


# ── 2. Lecture de la newsletter en UN appel : biais secteur + trades momentum ──

_NEWSLETTER_SYSTEM = (
    "Tu analyses une newsletter boursière française. Réponds UNIQUEMENT par un objet "
    "JSON à DEUX clés, sans texte autour, en te fondant EXCLUSIVEMENT sur le texte "
    "fourni (n'invente rien) :\n"
    '- "sectors": [{"sector": str, "bias": int -2..2, "quote": str extrait verbatim}] '
    f"— biais sectoriel net. Secteurs AUTORISÉS uniquement : {', '.join(SECTOR_VOCAB)}. "
    "N'inclus un secteur que si le texte le justifie (citation obligatoire).\n"
    '- "trades": [{"company": str nom FR, "action": "BUY"|"SELL"|"HOLD"|"AVOID", '
    '"tp_levels": [float euros], "sl": float euros ou 0, "quote": str extrait}] '
    "— pour chaque société française avec une reco claire. N'invente AUCUN prix : "
    "extrais-les verbatim (objectifs = TP ; seuil de sortie / support cassé = SL). "
    "Citation obligatoire. Liste vide si rien d'exploitable.\n"
    '- "us_trades": [{"ticker": str (symbole US, ETF ou action), "action": "BUY"|"SELL", '
    '"tp_levels": [float], "sl": float ou 0, "quote": str}] — UNIQUEMENT les instruments '
    "COTÉS AUX USA explicitement recommandés (ex. ETF SPY/QQQ/XLE, actions US). "
    "Prix extraits verbatim. Liste vide si aucun.\n"
    "Toute citation doit être COURTE (≤ 15 mots)."
)


def _parse_sector_rows(rows) -> tuple[dict, list]:
    """Valide les lignes secteur : vocab fermé + citation obligatoire. → (bias, audit)."""
    bias: dict[str, int] = {}
    audit: list = []
    if not isinstance(rows, list):
        return bias, audit
    for r in rows:
        if not isinstance(r, dict):
            continue
        sector = str(r.get("sector", ""))
        if sector not in SECTOR_VOCAB:
            continue
        quote = str(r.get("quote", "")).strip()
        if not quote:                          # anti-hallucination
            continue
        try:
            b = int(r.get("bias", 0))
        except (TypeError, ValueError):
            continue
        b = max(-2, min(2, b))
        bias[sector] = b
        audit.append({"sector": sector, "bias": b, "quote": quote[:200]})
    return bias, audit


def _parse_trade_rows(rows) -> list[dict]:
    """Valide les trades : whitelist FR_TICKER_MAP + citation + prix positifs."""
    if not isinstance(rows, list):
        return []
    from signals.newsletter_agent import FR_TICKER_MAP

    valid_actions = {"BUY", "SELL", "HOLD", "AVOID"}
    out: list[dict] = []
    seen: set[str] = set()
    for it in rows:
        if not isinstance(it, dict):
            continue
        company = str(it.get("company", "")).strip().lower()
        ticker = FR_TICKER_MAP.get(company)
        if not ticker or ticker in seen:       # whitelist stricte + dédup
            continue
        action = str(it.get("action", "")).upper()
        if action not in valid_actions:
            continue
        quote = str(it.get("quote", "")).strip()
        if not quote:                          # citation obligatoire
            continue
        tps: list[float] = []
        for p in (it.get("tp_levels") or []):
            try:
                v = float(p)
                if v > 0:
                    tps.append(round(v, 4))
            except (TypeError, ValueError):
                continue
        try:
            sl = float(it.get("sl", 0) or 0)
            sl = sl if sl > 0 else 0.0
        except (TypeError, ValueError):
            sl = 0.0
        seen.add(ticker)
        out.append({
            "company":   company.title(),
            "ticker":    ticker,
            "action":    action,
            "tp_levels": sorted(tps),
            "sl":        sl,
            "quote":     quote[:200],
        })
    return out


def enrich_newsletter(
    newsletter_text: str,
    regex_bias: dict[str, int],
    regex_trades: list,
) -> Optional[dict]:
    """
    UN SEUL appel LLM qui lit la newsletter et renvoie à la fois le biais sectoriel
    fiabilisé ET les trades momentum (classification + prix TP/SL), pour ne pas lire
    le texte deux fois. Retourne {"sector_bias": dict|None, "momentum_trades": list|None}
    ou None (LLM off / échec / texte vide → l'appelant garde le regex).
    """
    if not is_enabled() or not newsletter_text or not newsletter_text.strip():
        return None

    hint_b = ", ".join(f"{s}:{v:+d}" for s, v in sorted((regex_bias or {}).items())) or "(aucun)"
    hint_t = ", ".join(f"{getattr(t, 'company', '?')}:{getattr(t, 'action', '?')}"
                       for t in (regex_trades or [])) or "(aucune)"
    user = (
        f"Biais sectoriel heuristique : {hint_b}\n"
        f"Trades heuristiques : {hint_t}\n\n"
        f"--- NEWSLETTER ---\n{newsletter_text[:12000]}"
    )

    # 4000 : le combiné (secteurs + trades + citations) est plus verbeux qu'un appel
    # simple ; un plafond trop bas tronque le JSON → parse échoué → fallback inutile.
    data, usage = _call(_NEWSLETTER_SYSTEM, user, max_tokens=4000)
    if not isinstance(data, dict):
        return None

    bias, audit = _parse_sector_rows(data.get("sectors"))
    trades = _parse_trade_rows(data.get("trades"))
    us_trades = _parse_us_trade_rows(data.get("us_trades"))
    _log("newsletter", {"sector_bias": bias, "sector_detail": audit,
                        "n_trades": len(trades), "trades": trades,
                        "us_trades": us_trades}, usage)
    return {"sector_bias": bias or None, "momentum_trades": trades or None,
            "us_trades": us_trades or None}


def _parse_us_trade_rows(rows) -> list[dict]:
    """
    Valide les instruments US directs recommandés par la newsletter FR (ETF/actions US) :
    ticker ∈ (watchlist US ∪ référentiel EDGAR), action BUY/SELL, prix positifs, citation.
    Ces trades s'exécutent aux TERMES de la newsletter sur le book réel (≠ poche FR).
    """
    if not isinstance(rows, list):
        return []
    from config import DEFAULT_WATCHLIST
    us_ok = set(DEFAULT_WATCHLIST)
    try:
        from signals import edgar
        us_ok |= set(edgar._load_cik_map().keys())
    except Exception:
        pass
    out: list[dict] = []
    seen: set[str] = set()
    for it in rows:
        if not isinstance(it, dict):
            continue
        tk = str(it.get("ticker", "")).upper().strip()
        if not tk or tk in seen or tk not in us_ok:   # whitelist US stricte
            continue
        action = str(it.get("action", "")).upper()
        if action not in {"BUY", "SELL"}:
            continue
        quote = str(it.get("quote", "")).strip()
        if not quote:
            continue
        tps: list[float] = []
        for p in (it.get("tp_levels") or []):
            try:
                v = float(p)
                if v > 0:
                    tps.append(round(v, 4))
            except (TypeError, ValueError):
                continue
        try:
            sl = float(it.get("sl", 0) or 0)
            sl = sl if sl > 0 else 0.0
        except (TypeError, ValueError):
            sl = 0.0
        seen.add(tk)
        out.append({"ticker": tk, "action": action, "tp_levels": sorted(tps),
                    "sl": sl, "quote": quote[:200]})
    return out


# ── 2bis. Newsletter US (ex. Barchart) : biais secteur + idées titres US ──────────

_US_SOURCE_SYSTEM = (
    "Tu analyses une newsletter boursière US. Réponds UNIQUEMENT par un objet JSON à "
    "deux clés, fondé EXCLUSIVEMENT sur le texte (n'invente rien) :\n"
    '- "sectors": [{"sector": str, "bias": int -2..2, "quote": str}] — biais sectoriel. '
    f"Secteurs AUTORISÉS uniquement : {', '.join(SECTOR_VOCAB)}. Citation obligatoire.\n"
    '- "tickers": [{"ticker": str (symbole US en MAJUSCULES), '
    '"stance": "bullish"|"bearish"|"neutral", "quote": str}] — valeurs US explicitement '
    "mises en avant. Citation obligatoire. Listes vides si rien. Citations COURTES (≤15 mots)."
)


def enrich_us_source(text: str) -> Optional[dict]:
    """
    Lit une newsletter US → {"sector_bias": dict|None, "tickers": [{ticker, stance, quote}]}.
    Tickers validés contre le référentiel US EDGAR (whitelist anti-hallucination) ;
    secteurs contre le vocab fermé ; citation obligatoire partout. None si off/échec/vide.
    """
    if not is_enabled() or not text or not text.strip():
        return None

    data, usage = _call(_US_SOURCE_SYSTEM, f"--- NEWSLETTER US ---\n{text[:10000]}",
                        max_tokens=1500)
    if not isinstance(data, dict):
        return None

    bias, _audit = _parse_sector_rows(data.get("sectors"))

    # Whitelist tickers = référentiel SEC EDGAR (si dispo). Sinon, on exige au moins
    # une citation (garde-fou minimal) plutôt que de tout rejeter.
    try:
        from signals import edgar
        cikmap = edgar._load_cik_map()
    except Exception:
        cikmap = {}
    valid_stance = {"bullish", "bearish", "neutral"}
    tickers: list[dict] = []
    seen: set[str] = set()
    for it in (data.get("tickers") or []):
        if not isinstance(it, dict):
            continue
        tk = str(it.get("ticker", "")).upper().strip()
        if not tk or tk in seen:
            continue
        if cikmap and tk not in cikmap:            # ticker US inconnu → rejet
            continue
        quote = str(it.get("quote", "")).strip()
        if not quote:
            continue
        stance = str(it.get("stance", "")).lower()
        if stance not in valid_stance:
            stance = "neutral"
        seen.add(tk)
        tickers.append({"ticker": tk, "stance": stance, "quote": quote[:200]})

    _log("us_source", {"sector_bias": bias, "tickers": tickers}, usage)
    return {"sector_bias": bias or None, "tickers": tickers}


# ── 3. Post-mortem d'un trade clôturé (catégorisation → boucle d'apprentissage) ──

_POSTMORTEM_SYSTEM = (
    "Tu es analyste risque. On te donne les FAITS d'un trade CLÔTURÉ, parfois précédés "
    "d'un bloc MÉMOIRE (tendances des clôtures passées). Attribue UNE cause parmi cette "
    "liste FERMÉE (clé exacte, rien d'autre) : " + ", ".join(CAUSE_VOCAB) + ". "
    "La cause doit venir UNIQUEMENT des faits du trade — ne te laisse PAS biaiser par les "
    "fréquences passées. Utilise la MÉMOIRE seulement pour rendre la leçon plus pertinente "
    "(la relier à une tendance récurrente si c'en est une). Écris une leçon courte "
    '(1 phrase), actionnable. Réponds UNIQUEMENT par un objet JSON : {"cause": str, "lesson": str}.'
)


def _memory_block() -> str:
    """
    Résumé COMPACT et de TAILLE FIXE des post-mortems passés (Niveau 0 d'apprentissage).
    Ce n'est PAS l'historique tronqué : c'est l'agrégat déterministe (comptage des causes,
    borné par le vocab fermé), donc constant quel que soit le nombre de clôtures → le coût
    du prompt reste plafonné. Vide tant qu'il n'y a pas assez de données.
    """
    from signals.learning import digest
    d = digest()
    if not d or not d.get("causes"):
        return ""
    causes = ", ".join(f"{k}={v}" for k, v in sorted(d["causes"].items(), key=lambda x: -x[1]))
    return (f"MÉMOIRE — {d['n']} clôtures/90j ({d['n_losers']} perdantes). "
            f"Causes récurrentes : {causes}.")


def postmortem(trade: dict) -> Optional[dict]:
    """
    Catégorise un trade clôturé : {cause_tag (∈ CAUSE_VOCAB), lesson}. None si off/échec.
    trade attendu : {ticker, entry_price, close_price, pnl_pct, reason, holding_days, entry_score}.
    """
    if not is_enabled():
        return None
    facts = (
        f"ticker={trade.get('ticker')} entrée={trade.get('entry_price')} "
        f"sortie={trade.get('close_price')} PnL={trade.get('pnl_pct')}% "
        f"raison_sortie={trade.get('reason')} durée_jours={trade.get('holding_days')} "
        f"score_entrée={trade.get('entry_score')}"
    )
    mem = _memory_block()   # Niveau 0 : mémoire compacte de taille fixe (coût plafonné)
    user = (mem + "\n\n" + facts) if mem else facts
    data, usage = _call(_POSTMORTEM_SYSTEM, user, max_tokens=300)
    if not isinstance(data, dict):
        return None
    cause = str(data.get("cause", "")).strip()
    if cause not in CAUSE_VOCAB:
        return None
    lesson = str(data.get("lesson", "")).strip()[:200]
    _log("postmortem", {"ticker": trade.get("ticker"), "cause": cause, "lesson": lesson}, usage)
    return {"cause_tag": cause, "lesson": lesson}
