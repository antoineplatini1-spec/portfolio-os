"""Configuration globale du gestionnaire de portefeuille."""

# ── Portefeuille ──────────────────────────────────────────────────
INITIAL_CASH = 10_000.0          # Capital de départ (€)
CURRENCY = "EUR"

# ── Allocation progressive (Phase 1 = mois 1) ────────────────────
RAMP_UP_WEEKS = 4                 # Durée de la montée en charge
WEEKLY_DEPLOY_PCT = 0.25          # % du cash initial déployable par semaine

# ── Poche de réserve ("pépites") ─────────────────────────────────
RESERVE_CASH_PCT = 0.10           # 10% toujours conservé
RESERVE_UNLOCK_SCORE = 85         # Score minimum pour débloquer la réserve

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

# ── Signaux ───────────────────────────────────────────────────────
BUY_SIGNAL_MIN_SCORE = 60         # Score minimum pour suggérer un achat
ADX_TREND_THRESHOLD = 25          # ADX > seuil = marché en tendance

# ── Frais ─────────────────────────────────────────────────────────
# Alpaca broker : commission-free sur actions US, mais on simule les frais
# réalistes pour anticiper le live trading (spread + impact marché).
# Ajuster flat_fee selon le courtier réel : Alpaca=0, IBKR≈3€, Degiro≈2€.
BROKER_CONFIG = {
    "name": "Alpaca",
    "flat_fee": 0.0,              # Alpaca : zéro commission sur actions US
    "pct_fee": 0.0,               # pas de frais %
    "min_fee": 0.0,
}

# Profit net minimum par vente partielle TP pour qu'elle soit exécutée.
# Alpaca étant gratuit, 0 = tout PnL positif déclenche la vente.
# À ajuster si on change de broker (ex: IBKR → 15€+).
MIN_TP_NET_PROFIT = 0.0

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
