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
    """Extrait le premier objet/tableau JSON d'une réponse (robuste aux préambules)."""
    text = text.strip()
    for opener, closer in (("[", "]"), ("{", "}")):
        i = text.find(opener)
        j = text.rfind(closer)
        if i != -1 and j != -1 and j > i:
            return json.loads(text[i : j + 1])
    return json.loads(text)


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
    except Exception:
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


def fetch_news_signals(tickers: list[str], max_tickers: int = 30) -> dict[str, dict]:
    """
    Retourne {ticker: {event, direction, strength, horizon_days, quote, url}} pour les
    valeurs ayant une actualité matérielle récente. {} si LLM désactivé ou aucune
    actualité. Un SEUL appel LLM (batch) pour tenir le coût.
    """
    if not is_enabled() or not tickers:
        return {}

    # Le code récupère les faits (headlines) et les passe VERBATIM au LLM.
    # Le LLM ne "va" jamais chercher lui-même → factuel, auditable.
    corpus: dict[str, list[dict]] = {}
    for t in tickers[:max_tickers]:
        hl = _recent_headlines(t)
        if hl:
            corpus[t] = hl
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


# ── 2. Fiabilisation du biais sectoriel de la newsletter ──────────

_SECTOR_SYSTEM = (
    "Tu es un analyste macro. On te donne le texte d'une newsletter boursière "
    "(valeurs surtout françaises) et un biais sectoriel calculé par heuristique. "
    "Ta tâche : produire un biais sectoriel NET par secteur, en te fondant "
    "UNIQUEMENT sur le texte fourni (n'invente rien). Utilise EXCLUSIVEMENT ces "
    f"secteurs : {', '.join(SECTOR_VOCAB)}. "
    "Réponds UNIQUEMENT par un objet JSON, sans texte autour. Schéma : "
    '{"sectors": [{"sector": str∈vocab, "bias": int -2..2, "quote": str (extrait '
    'verbatim justifiant), "rationale": str court}]}. '
    "N'inclus un secteur QUE si le texte le justifie explicitement (avec citation)."
)


def enrich_sector_bias(
    newsletter_text: str, regex_bias: dict[str, int]
) -> Optional[dict[str, int]]:
    """
    Renvoie un dict {sector: bias int} fiabilisé par le LLM, ou None pour signaler
    à l'appelant de conserver le biais regex existant (LLM désactivé / échec / texte
    vide). N'émet que des secteurs du vocabulaire fermé, chacun justifié par citation.
    """
    if not is_enabled() or not newsletter_text or not newsletter_text.strip():
        return None

    hint = ", ".join(f"{s}:{v:+d}" for s, v in sorted(regex_bias.items())) or "(aucun)"
    # On borne le texte (coût) : l'essentiel du signal sectoriel tient au début.
    user = (
        f"Biais heuristique préalable (indicatif) : {hint}\n\n"
        f"--- NEWSLETTER ---\n{newsletter_text[:8000]}"
    )

    data, usage = _call(_SECTOR_SYSTEM, user, max_tokens=1200)
    if not isinstance(data, dict):
        return None
    rows = data.get("sectors")
    if not isinstance(rows, list):
        return None

    bias: dict[str, int] = {}
    audit_rows = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sector = str(r.get("sector", ""))
        if sector not in SECTOR_VOCAB:
            continue
        quote = str(r.get("quote", "")).strip()
        if not quote:
            # Anti-hallucination : pas de citation → on rejette le biais.
            continue
        try:
            b = int(r.get("bias", 0))
        except (TypeError, ValueError):
            continue
        b = max(-2, min(2, b))
        bias[sector] = b
        audit_rows.append({"sector": sector, "bias": b, "quote": quote[:200],
                            "rationale": str(r.get("rationale", ""))[:200]})

    if not bias:
        return None

    _log("sector_bias", {"regex_hint": regex_bias, "llm_bias": bias,
                         "detail": audit_rows}, usage)
    return bias


# ── 3. Extraction des trades momentum de la newsletter (fiabilise le regex) ──

_MOMENTUM_SYSTEM = (
    "Tu es analyste actions. On te donne le texte d'une newsletter boursière française "
    "et une extraction heuristique préalable. Pour chaque SOCIÉTÉ FRANÇAISE ayant une "
    "recommandation d'action claire, renvoie un objet. N'invente AUCUN prix : extrais-les "
    "verbatim du texte (objectifs = TP ; seuil de sortie / support cassé = SL). "
    "Réponds UNIQUEMENT par un tableau JSON. Schéma par élément : "
    '{"company": str (nom FR), "action": "BUY"|"SELL"|"HOLD"|"AVOID", '
    '"tp_levels": [float euros], "sl": float euros ou 0, "quote": str (extrait justifiant)}. '
    "Tableau vide [] si aucune reco exploitable."
)


def enrich_momentum_trades(
    newsletter_text: str, regex_trades: list
) -> Optional[list[dict]]:
    """
    Extrait les trades momentum de la newsletter via LLM (classification + prix TP/SL),
    plus robuste que le regex sur les tournures inattendues. Retourne une liste de dicts
    {company, ticker, action, tp_levels, sl, quote} ou None (→ garder le regex).

    Anti-hallucination : société acceptée seulement si dans FR_TICKER_MAP (whitelist),
    action dans le vocabulaire fermé, prix = floats positifs, citation obligatoire.
    """
    if not is_enabled() or not newsletter_text or not newsletter_text.strip():
        return None
    from signals.newsletter_agent import FR_TICKER_MAP

    hint = ", ".join(f"{getattr(t, 'company', '?')}:{getattr(t, 'action', '?')}"
                     for t in (regex_trades or [])) or "(aucune)"
    user = (
        f"Extraction heuristique préalable : {hint}\n\n"
        f"--- NEWSLETTER ---\n{newsletter_text[:12000]}"
    )
    data, usage = _call(_MOMENTUM_SYSTEM, user, max_tokens=2000)
    if not isinstance(data, list):
        return None

    valid_actions = {"BUY", "SELL", "HOLD", "AVOID"}
    out: list[dict] = []
    seen: set[str] = set()
    for it in data:
        if not isinstance(it, dict):
            continue
        company = str(it.get("company", "")).strip().lower()
        ticker = FR_TICKER_MAP.get(company)
        if not ticker or ticker in seen:      # whitelist stricte + dédup
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

    if not out:
        return None
    _log("momentum_trades", {"n": len(out), "trades": out}, usage)
    return out


# ── 4. Post-mortem d'un trade clôturé (catégorisation → boucle d'apprentissage) ──

_POSTMORTEM_SYSTEM = (
    "Tu es analyste risque. On te donne les FAITS d'un trade CLÔTURÉ. Attribue UNE cause "
    "parmi cette liste FERMÉE (renvoie la clé exacte, rien d'autre) : "
    + ", ".join(CAUSE_VOCAB) + ". "
    "Puis écris une leçon courte (1 phrase), actionnable. Fonde-toi UNIQUEMENT sur les "
    'faits fournis. Réponds UNIQUEMENT par un objet JSON : {"cause": str, "lesson": str}.'
)


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
    data, usage = _call(_POSTMORTEM_SYSTEM, facts, max_tokens=300)
    if not isinstance(data, dict):
        return None
    cause = str(data.get("cause", "")).strip()
    if cause not in CAUSE_VOCAB:
        return None
    lesson = str(data.get("lesson", "")).strip()[:200]
    _log("postmortem", {"ticker": trade.get("ticker"), "cause": cause, "lesson": lesson}, usage)
    return {"cause_tag": cause, "lesson": lesson}
