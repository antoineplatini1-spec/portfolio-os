"""Configuration globale du gestionnaire de portefeuille."""

import os

# ── Portefeuille ──────────────────────────────────────────────────
INITIAL_CASH = 10_000.0          # Capital de départ (€)
CURRENCY = "EUR"

# ── Allocation progressive (Phase 1 = mois 1) ────────────────────
RAMP_UP_WEEKS = 4                 # Durée de la montée en charge
WEEKLY_DEPLOY_PCT = 0.25          # % du cash initial déployable par semaine

# ── Poche de réserve ("pépites") ─────────────────────────────────
# Réserve SUPPRIMÉE (2026-07-12, décision utilisateur : pleine latitude pour engager
# le capital). 0 → aucun cash bloqué d'office, déploiement jusqu'à ~100% dans la
# limite des autres plafonds (5%/position, 20%/secteur, exposition max, montée en
# charge). RESERVE_UNLOCK_SCORE devient sans effet (plus rien à débloquer).
RESERVE_CASH_PCT = 0.0            # plus de réserve imposée
RESERVE_UNLOCK_SCORE = 85         # (inopérant tant que RESERVE_CASH_PCT = 0)

# ── Sizing par position ───────────────────────────────────────────
MAX_POSITION_PCT = 0.05               # Position standard : 5% max (€500 sur 10K€)
MAX_POSITION_OPPORTUNITY_PCT = 0.08   # Score ≥ 80 : 8% max (€800)
MAX_POSITION_CONVICTION_PCT = 0.12    # Score ≥ 90 : 12% max (€1200)
OPPORTUNITY_SCORE_THRESHOLD = 80
CONVICTION_SCORE_THRESHOLD = 90

MAX_SECTOR_POSITIONS = 4          # Concentration sectorielle max
MAX_TOTAL_EXPOSURE_PCT = 0.95     # Exposition totale max (hors réserve)

# ── Risque par trade ──────────────────────────────────────────────
SLIPPAGE_PCT = 0.001              # 0.1% slippage (bid-ask spread + impact marché)
RISK_PER_TRADE_PCT = 0.01         # 1% du portefeuille risqué par trade
ATR_SL_MULTIPLIER = 2.0           # SL plus large pour laisser vivre les positions
MAX_LOSS_PCT = 0.08               # Perte max absolue par position (8% du prix d'entrée)
MIN_R_RATIO = 1.5                 # R-ratio minimum sur TP3 (cible finale) — avec SL=1.5×ATR et TP3=3×ATR → R=2.0
MAX_TRADES_PER_DAY = 2              # Max positions ouvertes par jour

# ── Paliers TP par défaut ─────────────────────────────────────────
TP_LEVELS = [
    {"atr_mult": 1.5, "sell_pct": 0.25},   # TP1 : +1.5 ATR, vendre 25%
    {"atr_mult": 3.0, "sell_pct": 0.35},   # TP2 : +3 ATR, vendre 35%
    {"atr_mult": 5.0, "sell_pct": 0.40},   # TP3 : +5 ATR, laisser courir
]
TRAILING_STOP_AFTER_TP1 = True    # Activer trailing stop à Entry après TP1

# ── Niveaux STRUCTURELS (SL/TP calés sur support/résistance + conviction + régime) ──
# Gated : OFF par défaut → comportement ATR historique inchangé. À passer ON UNIQUEMENT
# si le backtest comparatif (structure vs ATR) montre un gain (Sharpe/DD/profit factor).
USE_STRUCTURAL_LEVELS    = False
STRUCT_LOOKBACK          = 20      # fenêtre support/résistance (jours)
STRUCT_CONVICTION_MARGIN = 0.15    # +15% de marge de stop max à pleine conviction
STRUCT_MIN_ATR           = 1.0     # stop jamais plus serré que 1×ATR (anti-bruit)
STRUCT_VIX_MULT          = {"LOW": 0.9, "MEDIUM": 1.0, "HIGH": 1.2}  # stop élargi si VIX haut

# ── Signaux ───────────────────────────────────────────────────────
BUY_SIGNAL_MIN_SCORE = 60         # Score minimum pour suggérer un achat
ADX_TREND_THRESHOLD = 25          # ADX > seuil = marché en tendance

# Bonus/malus de score par unité de biais sectoriel (newsletter/LLM, −2..+2).
# Appliqué à un score EFFECTIF (pré-filtre + classement des candidats) dans TOUS les
# régimes ; le score brut reste inchangé pour le sizing. 3 pts × [−2..+2] = ±6 pts.
SECTOR_BONUS_POINTS = 3

# Poids du SCORE DE DÉCISION unifié (signals/decision.py) — points par unité de feature.
# Chaque source devient une feature pondérée et bidirectionnelle. À valider/tuner via
# l'attribution (live) et le backtest (secteur seulement). news ±1 → ±8 pts, etc.
DECISION_WEIGHTS = {
    "sector":     SECTOR_BONUS_POINTS,   # biais −2..+2  → ±6 pts
    "news":       8.0,                   # actu −1..+1   → ±8 pts (bullish AIDE)
    "conviction": 5.0,                   # nommé newsletter 0/1 → +5 pts
}

# ── Frais ─────────────────────────────────────────────────────────
# On maintient DEUX barèmes et on sélectionne l'effectif selon le broker réellement
# utilisé (IBKR_ENABLED). C'est essentiel : les garde-fous de risque (sizing,
# ventes partielles TP) estiment les frais via BROKER_CONFIG. Si on exécute chez
# IBKR mais qu'on laisse le barème Alpaca (frais=0), les garde-fous croient
# l'aller-retour gratuit et déclenchent des TP partiels trop petits pour couvrir
# la commission → grignotage silencieux du PnL.
_IBKR_ENABLED = os.environ.get("IBKR_ENABLED", "0") == "1"

ALPACA_BROKER_CONFIG = {
    "name": "Alpaca",
    "flat_fee": 0.0,              # Alpaca : zéro commission sur actions US
    "pct_fee": 0.0,               # pas de frais %
    "min_fee": 0.0,
}

# IBKR US, tarif fixe : 0,005$/action, min 1$/ordre, plafonné à 1% du notionnel.
# (Devise : compte US en USD ; le portefeuille raisonne en EUR — l'écart USD/EUR
# est négligeable pour un simple garde-fou de frais, on ne convertit pas ici.)
IBKR_BROKER_CONFIG = {
    "name": "IBKR",
    "flat_fee": 0.0,
    "per_share_fee": 0.005,
    "pct_fee": 0.0,
    "min_fee": 1.0,
    "max_pct_fee": 0.01,
}

BROKER_CONFIG = IBKR_BROKER_CONFIG if _IBKR_ENABLED else ALPACA_BROKER_CONFIG

# Profit NET minimum (après frais de vente) pour qu'une vente partielle TP soit
# exécutée. Le palier reste marqué "hit" (le trailing stop s'active), mais on ne
# vend pas si le gain net ne dépasse pas ce seuil : on garde les titres pour un TP
# plus haut ou le trailing, plutôt que de payer une commission pour un gain minuscule.
#   - Alpaca (gratuit)  : 0 → tout PnL positif déclenche.
#   - IBKR (frais réels): 2 unités de marge AU-DELÀ de la commission de vente déjà
#     déduite dans le garde-fou du manager (≈ couvre le round-trip + petit tampon).
MIN_TP_NET_PROFIT = 2.0 if _IBKR_ENABLED else 0.0

# ── Broker réel : Interactive Brokers (paper puis live) ───────────
# Le bot bascule du PaperBroker simulé vers IBKR quand IBKR_ENABLED=True.
# Toute la config sensible passe par variables d'environnement (jamais en dur).
#   IBKR_ENABLED       : "1" pour router les ordres vers IB Gateway
#   IBKR_HOST          : hôte du Gateway (localhost sur le VPS)
#   IBKR_PORT          : 4002 = paper, 4001 = live, 7497/7496 = TWS
#   IBKR_CLIENT_ID     : id de session API (unique par connexion)
#   IBKR_ACCOUNT       : code compte (DU… en paper), optionnel
#   IBKR_ORDER_TYPE    : MKT (défaut), MOO (market-on-open, adapté au cron pré-ouverture), LMT
#   IBKR_SHADOW        : "1" pour exécuter EN PARALLÈLE le PaperBroker et logger sim-vs-réel
IBKR_CONFIG = {
    "enabled":    os.environ.get("IBKR_ENABLED", "0") == "1",
    "host":       os.environ.get("IBKR_HOST", "127.0.0.1"),
    "port":       int(os.environ.get("IBKR_PORT", "4002")),
    "client_id":  int(os.environ.get("IBKR_CLIENT_ID", "17")),
    "account":    os.environ.get("IBKR_ACCOUNT", "") or None,
    "order_type": os.environ.get("IBKR_ORDER_TYPE", "MKT").upper(),
    "shadow":     os.environ.get("IBKR_SHADOW", "1") == "1",
    "fill_timeout_sec": int(os.environ.get("IBKR_FILL_TIMEOUT", "60")),
}

# ── Momentum PTF (newsletter Capital Momentum) ────────────────────
MOMENTUM_INITIAL_CASH     = 10_000.0   # Poche dédiée newsletter
MOMENTUM_MAX_POSITION_PCT = 0.10       # 10% par position = ~1000€
MOMENTUM_DEFAULT_SL_PCT   = 0.07       # SL par défaut si non mentionné : -7%
MOMENTUM_TRAIL_PCT        = 0.05       # Trailing stop : 5% sous le plus haut après TP1

# ── Trades US directs issus de la newsletter (Capital Momentum) ───
# Quand la newsletter recommande un instrument US (ETF/action), il est exécuté sur le
# book RÉEL aux termes de la newsletter (TP/SL du texte), sans passer par le screener.
# La newsletter ne donne pas de taille → position fixe. Le SL est plafonné à MAX_LOSS_PCT
# (backstop : jamais pire que -8%, même si la newsletter dit plus large).
NEWSLETTER_US_POSITION_PCT = 0.05      # 5% du portefeuille par trade newsletter US

# ── Données ───────────────────────────────────────────────────────
DEFAULT_PERIOD = "6mo"
DEFAULT_INTERVAL = "1d"
CACHE_TTL_MINUTES = 30

# ── Watchlist Alpaca (US markets uniquement) ──────────────────────
DEFAULT_WATCHLIST = [
    # ── Tech mega-cap ─────────────────────────────────────────────
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "META", "AMZN", "TSLA",
    "ORCL", "CRM", "ADBE", "NOW", "SHOP", "UBER", "ABNB", "SNOW",
    "PLTR", "COIN", "RBLX", "NET", "DDOG", "ZS", "CRWD", "PANW",

    # ── Semi-conducteurs ──────────────────────────────────────────
    "AMD", "INTC", "QCOM", "AVGO", "MU", "AMAT", "LRCX", "KLAC",
    "TSM", "ASML", "MRVL", "ON", "WOLF",

    # ── Finance ───────────────────────────────────────────────────
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW",
    "V", "MA", "PYPL", "AXP", "COF",

    # ── Santé / Biotech ───────────────────────────────────────────
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT",
    "AMGN", "GILD", "BIIB", "REGN", "MRNA", "VRTX", "ISRG",

    # ── Energie ───────────────────────────────────────────────────
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "OXY",

    # ── Consommation discrétionnaire ──────────────────────────────
    "COST", "WMT", "HD", "TGT", "LOW", "NKE", "MCD", "SBUX",
    "AMZN", "BKNG", "MAR", "HLT",

    # ── Consommation de base ──────────────────────────────────────
    "PG", "KO", "PEP", "PM", "MO", "CL", "EL",

    # ── Industrie / Défense ───────────────────────────────────────
    "CAT", "DE", "BA", "HON", "GE", "RTX", "LMT", "NOC", "UPS", "FDX",

    # ── Télécoms / Médias ─────────────────────────────────────────
    "T", "VZ", "TMUS", "NFLX", "DIS", "CMCSA",

    # ── Immobilier (REITs) ────────────────────────────────────────
    "AMT", "PLD", "EQIX", "SPG", "O", "VICI",

    # ── Matériaux ─────────────────────────────────────────────────
    "LIN", "APD", "FCX", "NEM", "AA", "NUE",

    # ── ETF larges (indices) ──────────────────────────────────────
    "SPY", "QQQ", "IWM", "VTI", "DIA", "RSP",

    # ── ETF sectoriels ────────────────────────────────────────────
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
    "SMH", "SOXX", "IBB", "XBI", "ARKK", "ARKG",

    # ── ETF thématiques ───────────────────────────────────────────
    "BOTZ", "ROBO", "ICLN", "LIT", "CIBR", "HACK",

    # ── Macro (obligations, or, volatilité) ───────────────────────
    "GLD", "SLV", "GDX", "TLT", "IEF", "HYG", "LQD", "VXX", "UVXY",
]

# Déduplique en préservant l'ordre
DEFAULT_WATCHLIST = list(dict.fromkeys(DEFAULT_WATCHLIST))

SECTOR_MAP = {
    # Tech
    "AAPL": "Tech", "MSFT": "Tech", "NVDA": "Tech", "GOOGL": "Tech",
    "GOOG": "Tech", "META": "Tech", "AMZN": "Tech", "TSLA": "Tech",
    "ORCL": "Tech", "CRM": "Tech", "ADBE": "Tech", "NOW": "Tech",
    "SHOP": "Tech", "UBER": "Tech", "ABNB": "Tech", "SNOW": "Tech",
    "PLTR": "Tech", "COIN": "Tech", "RBLX": "Tech", "NET": "Tech",
    "DDOG": "Tech", "ZS": "Tech", "CRWD": "Tech", "PANW": "Tech",
    # Semi-conducteurs
    "AMD": "Semi", "INTC": "Semi", "QCOM": "Semi", "AVGO": "Semi",
    "MU": "Semi", "AMAT": "Semi", "LRCX": "Semi", "KLAC": "Semi",
    "TSM": "Semi", "ASML": "Semi", "MRVL": "Semi", "ON": "Semi", "WOLF": "Semi",
    # Finance
    "JPM": "Finance", "BAC": "Finance", "WFC": "Finance", "GS": "Finance",
    "MS": "Finance", "C": "Finance", "BLK": "Finance", "SCHW": "Finance",
    "V": "Finance", "MA": "Finance", "PYPL": "Finance", "SQ": "Finance",
    "AXP": "Finance", "COF": "Finance",
    # Santé
    "UNH": "Santé", "JNJ": "Santé", "LLY": "Santé", "ABBV": "Santé",
    "MRK": "Santé", "PFE": "Santé", "TMO": "Santé", "ABT": "Santé",
    "AMGN": "Santé", "GILD": "Santé", "BIIB": "Santé", "REGN": "Santé",
    "MRNA": "Santé", "VRTX": "Santé", "ISRG": "Santé",
    # Energie
    "XOM": "Energie", "CVX": "Energie", "COP": "Energie", "SLB": "Energie",
    "EOG": "Energie", "MPC": "Energie", "PSX": "Energie", "OXY": "Energie",
    # Conso discrétionnaire
    "COST": "Conso", "WMT": "Conso", "HD": "Conso", "TGT": "Conso",
    "LOW": "Conso", "NKE": "Conso", "MCD": "Conso", "SBUX": "Conso",
    "BKNG": "Conso", "MAR": "Conso", "HLT": "Conso",
    # Conso de base
    "PG": "ConsoBase", "KO": "ConsoBase", "PEP": "ConsoBase",
    "PM": "ConsoBase", "MO": "ConsoBase", "CL": "ConsoBase", "EL": "ConsoBase",
    # Industrie
    "CAT": "Industrie", "DE": "Industrie", "BA": "Industrie", "HON": "Industrie",
    "GE": "Industrie", "RTX": "Industrie", "LMT": "Industrie",
    "NOC": "Industrie", "UPS": "Industrie", "FDX": "Industrie",
    # Télécoms / Médias
    "T": "Telecoms", "VZ": "Telecoms", "TMUS": "Telecoms",
    "NFLX": "Media", "DIS": "Media", "CMCSA": "Media", "PARA": "Media",
    # REITs
    "AMT": "REIT", "PLD": "REIT", "EQIX": "REIT",
    "SPG": "REIT", "O": "REIT", "VICI": "REIT",
    # Matériaux
    "LIN": "Materiaux", "APD": "Materiaux", "FCX": "Materiaux",
    "NEM": "Materiaux", "AA": "Materiaux", "NUE": "Materiaux",
    # ETF
    "SPY": "ETF", "QQQ": "ETF", "IWM": "ETF", "VTI": "ETF",
    "DIA": "ETF", "RSP": "ETF",
    "XLK": "ETF", "XLF": "ETF", "XLE": "ETF", "XLV": "ETF",
    "XLI": "ETF", "XLY": "ETF", "XLP": "ETF", "XLU": "ETF",
    "XLB": "ETF", "XLRE": "ETF",
    "SMH": "ETF", "SOXX": "ETF", "IBB": "ETF", "XBI": "ETF",
    "ARKK": "ETF", "ARKG": "ETF",
    "BOTZ": "ETF", "ROBO": "ETF", "ICLN": "ETF",
    "LIT": "ETF", "CIBR": "ETF", "HACK": "ETF",
    # Macro
    "GLD": "Macro", "SLV": "Macro", "GDX": "Macro",
    "TLT": "Macro", "IEF": "Macro", "HYG": "Macro",
    "LQD": "Macro", "VXX": "Macro", "UVXY": "Macro",
}
