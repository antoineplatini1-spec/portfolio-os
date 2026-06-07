"""Lexique — définitions de tous les termes utilisés dans Zentry."""

import streamlit as st
from ui.theme import COLORS as C


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _card(title: str, body: str, tag: str = "", tag_color: str = ""):
    tag_html = ""
    if tag:
        col = tag_color or C["accent"]
        tag_html = (
            f"<span style='float:right;font:600 0.65rem/1 monospace;"
            f"color:{col};background:rgba(45,212,191,0.08);"
            f"padding:2px 8px;border-radius:4px;letter-spacing:0.05em'>{tag}</span>"
        )
    st.markdown(
        f"""
        <div style='background:{C["surf2"]};border:1px solid {C["border"]};
                    border-radius:10px;padding:18px 22px;margin-bottom:12px'>
            <div style='margin-bottom:8px'>
                {tag_html}
                <span style='font:700 1rem/1 Inter,sans-serif;color:{C["text1"]}'>{title}</span>
            </div>
            <div style='font:400 0.875rem/1.65 Inter,sans-serif;color:{C["text2"]}'>{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _section(title: str, icon: str = ""):
    st.markdown(
        f"""
        <div style='margin:2rem 0 1rem'>
            <span style='font:700 0.6rem/1 monospace;color:{C["text3"]};
                         letter-spacing:0.15em;text-transform:uppercase'>
                {icon} {title}
            </span>
            <div style='height:1px;background:{C["border"]};margin-top:6px'></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _ex(text: str):
    """Bloc exemple en teal."""
    return (
        f"<div style='margin-top:8px;padding:8px 12px;"
        f"background:rgba(45,212,191,0.06);border-left:3px solid {C['accent']};"
        f"border-radius:4px;font:0.82rem/1.55 monospace;color:{C['accent']}'>"
        f"💡 {text}</div>"
    )


def _formula(text: str):
    text1 = C["text1"]
    surf3 = C["surf3"]
    return (
        f"<div style='margin-top:6px;padding:6px 12px;"
        f"background:{surf3};border-radius:4px;"
        f"font:0.82rem/1.5 JetBrains Mono,monospace;color:{text1}'>"
        f"{text}</div>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Page principale
# ─────────────────────────────────────────────────────────────────────────────

def render(_pm=None):
    st.markdown(
        f"""
        <div style='margin-bottom:2rem'>
            <div style='font:700 0.6rem/1 monospace;color:{C["text3"]};
                        letter-spacing:0.15em;text-transform:uppercase;
                        margin-bottom:0.4rem'>ZENTRY · GLOSSAIRE</div>
            <div style='font:700 2rem/1 Inter,sans-serif;color:{C["text1"]};
                        letter-spacing:-0.04em;margin-bottom:0.5rem'>Lexique</div>
            <div style='font:400 0.95rem/1.6 Inter,sans-serif;color:{C["text2"]}'>
                Définitions de tous les termes techniques, indicateurs et mécanismes
                utilisés dans la plateforme.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Filtrage rapide ───────────────────────────────────────────────────────
    search = st.text_input("🔍  Rechercher un terme...", placeholder="ex: RSI, ATR, drawdown...")
    s = search.lower().strip()

    def _visible(terms: list[str]) -> bool:
        if not s:
            return True
        return any(s in t.lower() for t in terms)

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. INDICATEURS TECHNIQUES
    # ═══════════════════════════════════════════════════════════════════════════
    if _visible(["indicateur", "technique", "rsi", "macd", "bollinger", "adx", "stoch",
                 "obv", "cmf", "ema", "vwap", "atr", "momentum"]):
        _section("Indicateurs techniques", "📈")

    if _visible(["rsi", "relative strength", "suracheté", "survendu"]):
        _card(
            "RSI — Relative Strength Index",
            "Mesure la vitesse et l'ampleur des mouvements de prix sur 14 jours. "
            "Oscillateur entre 0 et 100.<br><br>"
            "<b>Interprétation dans Zentry :</b><br>"
            "• &lt; 30 → survendu = signal fort d'achat (+15 pts)<br>"
            "• 30–40 → faiblesse récente (+10 pts)<br>"
            "• 40–55 → zone momentum neutre-positive (+4 pts)<br>"
            "• 55–70 → neutre (0 pt)<br>"
            "• &gt; 70 → suracheté = alerte baissière (bear flag)"
            + _ex("RSI = 28 sur NVDA après une correction de 15% → signal d'achat fort"),
            tag="Oscillateur",
        )

    if _visible(["macd", "moving average convergence", "signal", "crossover"]):
        _card(
            "MACD — Moving Average Convergence Divergence",
            "Différence entre deux moyennes mobiles exponentielles (EMA 12 et EMA 26). "
            "La ligne Signal est une EMA 9 du MACD.<br><br>"
            "<b>Interprétation :</b><br>"
            "• Croisement MACD au-dessus du Signal → momentum haussier (+8 à +15 pts)<br>"
            "• Croisement au-dessus de zéro = signal encore plus fort (+15 pts)<br>"
            "• Croisement baissier → signal de vente (-10 pts)<br>"
            "• MACD simplement &gt; Signal (sans cross récent) → tendance positive (+5 pts)"
            + _ex("MACD croise au-dessus du Signal à +0.8 → croisement haussier au-dessus de zéro = signal maximal"),
            tag="Momentum",
        )

    if _visible(["bollinger", "bande", "bb", "volatilité", "écart-type"]):
        _card(
            "Bandes de Bollinger",
            "Enveloppe de prix à ±2 écarts-types autour d'une moyenne mobile 20j. "
            "S'élargissent en période de forte volatilité, se resserrent en consolidation.<br><br>"
            "<b>Interprétation :</b><br>"
            "• Prix sous la bande inférieure → compression extrême = signal d'achat (+12 pts)<br>"
            "• Prix au-dessus de la bande supérieure → surachat = alerte baissière (bear flag)<br>"
            "• Zone médiane → neutre (0 pt)"
            + _ex("AAPL touche la bande basse à 165$ alors que la moyenne est à 182$ → setup de retour à la moyenne"),
            tag="Volatilité",
        )

    if _visible(["adx", "average directional", "tendance", "dmp", "dmn", "dm+"]):
        _card(
            "ADX + DMP / DMN",
            "L'ADX (Average Directional Index) mesure la <i>force</i> d'une tendance, "
            "sans indiquer sa direction. DMP (+DI) et DMN (-DI) indiquent respectivement "
            "la pression acheteuse et vendeuse.<br><br>"
            "<b>Interprétation :</b><br>"
            "• ADX &gt; 25 et DMP &gt; DMN → tendance haussière forte (+10 pts)<br>"
            "• ADX &gt; 25 et DMN &gt; DMP → tendance baissière forte (bear flag, +15 pts bear)<br>"
            "• ADX &lt; 20 → marché sans direction, signaux peu fiables (-5 pts)"
            + _ex("ADX = 44 avec DMP = 32 > DMN = 11 sur QCOM → tendance haussière très forte"),
            tag="Tendance",
        )

    if _visible(["stochastique", "stoch", "stochrsi", "k%"]):
        _card(
            "Stochastic RSI",
            "RSI du RSI : applique l'oscillateur stochastique au RSI au lieu des prix. "
            "Plus sensible que le RSI simple, idéal pour détecter les retournements court terme.<br><br>"
            "<b>Interprétation :</b><br>"
            "• K &lt; 20 → survendu court terme (+10 pts)<br>"
            "• K &gt; 80 → suracheté court terme (−8 pts)<br>"
            "• Zone 20–80 → neutre"
            + _ex("StochRSI K = 2.8 sur QCOM → extrême de survente court terme malgré une tendance haussière = timing d'entrée"),
            tag="Oscillateur",
        )

    if _visible(["obv", "on-balance", "volume", "accumulation"]):
        _card(
            "OBV — On-Balance Volume",
            "Cumule le volume selon la direction du prix : ajoute le volume les jours "
            "haussiers, le soustrait les jours baissiers. Détecte l'accumulation ou "
            "la distribution avant que le prix ne bouge.<br><br>"
            "<b>Interprétation :</b><br>"
            "• OBV en hausse → flux acheteur dominant (+8 pts)<br>"
            "• OBV en baisse → distribution silencieuse (−5 pts)"
            + _ex("Le prix de SMH stagne mais OBV monte → des institutionnels accumulent discrètement"),
            tag="Volume",
        )

    if _visible(["cmf", "chaikin", "money flow", "flux"]):
        _card(
            "CMF — Chaikin Money Flow",
            "Mesure la pression acheteuse/vendeuse sur 20 jours en pondérant "
            "le volume par la position de la clôture dans le range journalier. "
            "Entre −1 et +1.<br><br>"
            "<b>Interprétation :</b><br>"
            "• CMF &gt; 0.1 → flux acheteur fort (+10 pts)<br>"
            "• CMF entre 0 et 0.1 → flux légèrement positif (+5 pts)<br>"
            "• CMF &lt; −0.1 → flux vendeur fort (−8 pts)"
            + _ex("CMF = +0.18 sur AMZN → les acheteurs contrôlent la séance, clôture systématiquement haute"),
            tag="Volume",
        )

    if _visible(["ema", "moyenne mobile", "ema50", "ema200", "exponentielle"]):
        _card(
            "EMA 50 / EMA 200",
            "Moyennes mobiles exponentielles qui donnent plus de poids aux prix récents. "
            "L'EMA 50 suit la tendance à moyen terme, l'EMA 200 la tendance long terme.<br><br>"
            "<b>EMA 50 :</b><br>"
            "• Prix &gt; EMA50 → soutien technique actif (+8 pts)<br>"
            "• EMA50 en baisse sur 5j → piège haussier possible (bear flag, +12 pts bear)<br><br>"
            "<b>EMA 200 :</b><br>"
            "• Prix &gt; EMA200 × 1.02 → tendance haussière confirmée (+10 pts)<br>"
            "• Prix entre EMA200 et EMA200 × 1.02 → structure naissante (+4 pts)<br>"
            "• Prix &lt; EMA200 → downtrend structurel (−20 pts, +20 pts bear)"
            + _ex("NVDA à 227$ > EMA200 à 198$ (+14.6%) → tendance haussière structurelle solide"),
            tag="Tendance",
        )

    if _visible(["vwap", "volume weighted", "prix moyen pondéré"]):
        _card(
            "VWAP — Volume Weighted Average Price",
            "Prix moyen pondéré par le volume depuis le début de l'année (calcul cumulé). "
            "Référence clé pour les institutionnels : ils achètent souvent au VWAP.<br><br>"
            "<b>Interprétation :</b><br>"
            "• Prix &gt; VWAP → momentum intraday positif (+7 pts)<br>"
            "• Prix &lt; VWAP → faiblesse relative (−3 pts)"
            + _ex("QCOM à 203$ > VWAP à 161$ → les acheteurs ont le contrôle depuis l'année"),
            tag="Référence",
        )

    if _visible(["atr", "average true range", "volatilité", "range"]):
        _card(
            "ATR — Average True Range",
            "Mesure la volatilité moyenne sur 14 jours en prenant le plus grand écart entre : "
            "haut−bas, haut−clôture précédente, bas−clôture précédente.<br><br>"
            "<b>Utilisation dans Zentry :</b><br>"
            "• Stop Loss placé à <b>2× ATR</b> sous le prix d'entrée<br>"
            "• TP1 à 1.5× ATR (vente 25% de la position)<br>"
            "• TP2 à 3× ATR (vente 35%)<br>"
            "• TP3 à 5× ATR (vente 40%)"
            + _ex("ATR = 5$ sur une action à 100$ → SL à 90$, TP1 à 107.5$, TP2 à 115$, TP3 à 125$"),
            tag="Risque",
        )

    if _visible(["momentum", "mom10", "10j", "tendance court"]):
        _card(
            "Momentum 10j",
            "Performance du prix sur les 10 dernières séances de bourse. "
            "Capture l'élan récent indépendamment des oscillateurs.<br><br>"
            "<b>Interprétation :</b><br>"
            "• &gt; +5% → rebond confirmé, élan fort (+8 pts)<br>"
            "• +2% à +5% → progression modérée (+3 pts)<br>"
            "• −2% à −5% → faiblesse récente (bear, −5 à −6 pts)<br>"
            "• &lt; −5% → chute forte (bear, −10 à −12 pts)"
            + _ex("Momentum 10j = +15.1% sur QCOM → le titre sort d'une correction et reprend de la vigueur"),
            tag="Momentum",
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. SYSTÈME DE DÉCISION
    # ═══════════════════════════════════════════════════════════════════════════
    if _visible(["score", "bull", "bear", "arbitre", "débat", "agent", "net score",
                 "conviction", "concern", "véto", "screener"]):
        _section("Système de décision multi-agents", "🤖")

    if _visible(["score", "scoring", "0-100", "composite"]):
        _card(
            "Score composite (0–100)",
            "Score technique calculé sur la dernière bougie pour chaque ticker. "
            "Agrège les signaux des 11 indicateurs en un seul chiffre.<br><br>"
            "<b>Architecture :</b><br>"
            "• <b>Bull pts</b> : somme des points haussiers (RSI survendu, MACD cross, etc.)<br>"
            "• <b>Bear pts</b> : somme des contre-arguments (EMA200 sous prix, volume faible, etc.)<br>"
            "• <b>Pénalité</b> : bear_pts / 2 (plafonnée à 40 pts)<br>"
            "• <b>Score final</b> : max(0, min(100, bull_pts − pénalité))"
            + _formula("Score = clamp(bull_pts − min(bear_pts, 40) / 2, 0, 100)")
            + _ex("Bull = 70, Bear = 20 → Pénalité = 10 → Score = 60"),
            tag="Scoring",
        )

    if _visible(["bull agent", "bull score", "conviction", "argument haussier"]):
        _card(
            "Bull Agent — Conviction (0–100)",
            "Agent qui construit le dossier <i>pour</i> acheter un titre. "
            "Il analyse le score screener, le R-ratio, les indicateurs techniques "
            "et le contexte portefeuille pour estimer sa conviction.<br><br>"
            "<b>Exemples d'arguments :</b><br>"
            "• « R-ratio solide (2.5×) — risque/récompense favorable »<br>"
            "• « Momentum 10j fort (+14.6%) — tendance confirmée »<br>"
            "• « Stoch RSI survendu (2) — retournement imminent »<br>"
            "• « Prix au-dessus EMA200 — tendance long terme haussière »<br><br>"
            "La conviction est plafonnée à 100 et réduite par les contre-arguments du Bear.",
            tag="Agent",
        )

    if _visible(["bear agent", "bear score", "concern", "argument baissier", "contre-argument"]):
        _card(
            "Bear Agent — Concern (0–100)",
            "Agent qui cherche les raisons de <i>ne pas</i> acheter. "
            "Il analyse les risques techniques, le contexte macro et les faiblesses du dossier Bull. "
            "Il peut annuler directement des points Bull via des contre-arguments adversariaux.<br><br>"
            "<b>Exemples d'arguments :</b><br>"
            "• « Secteur Semi déjà exposé (2 positions) — diversification limitée »<br>"
            "• « Volume faible (0.3× moyenne) »<br>"
            "• « EMA50 en baisse — piège haussier possible »<br>"
            "• « Prix sous EMA200 — downtrend structurel »",
            tag="Agent",
        )

    if _visible(["arbitre", "arbitrage", "net score", "décision", "acheter", "passer", "veto"]):
        _card(
            "Arbitre — Décision finale",
            "L'arbitre reçoit les scores Bull et Bear et tranche. "
            "Il calcule le Net Score et applique la matrice de décision.<br><br>"
            + _formula("Net Score = Bull_effectif − Bear × 0.6")
            + "<br><b>Matrice de décision (régime BULL, seuil = 10) :</b><br>"
            "• Net ≥ 30 → <span style='color:#34d399'>ACHETER</span><br>"
            "• Net ≥ 10 → <span style='color:#34d399'>ACHETER (prudent)</span><br>"
            "• Net ≥ 0 → <span style='color:#fbbf24'>PASSER</span><br>"
            "• Net &lt; 0 ou prix sous EMA200 → <span style='color:#fb7185'>PASSER / VETO</span>"
            + _ex("Bull=50, Bear=20 → Net = 50 − 20×0.6 = 38 → ACHETER"),
            tag="Décision",
        )

    if _visible(["véto", "veto", "secteur", "concentration"]):
        _card(
            "Véto sectoriel",
            "Règle portefeuille <i>non-négociable</i> : maximum 2 positions par secteur. "
            "S'applique après le débat — même si l'arbitre dit ACHETER, le véto bloque si "
            "le secteur est déjà saturé.<br><br>"
            "Les secteurs sont définis dans la configuration : Semi, Tech, Finance, Santé, "
            "Energie, Industrie, Conso, ConsoBase, REIT, Telecoms, Materiaux, ETF, Macro.",
            tag="Risque",
        )

    if _visible(["macro", "régime", "bull bear neutral", "spy", "vix", "ema200 spy"]):
        _card(
            "MacroAgent — Régime de marché",
            "Analyse hebdomadaire du contexte macro pour calibrer les paramètres de trading.<br><br>"
            "<b>3 régimes :</b><br>"
            "• <b>BULL</b> (SPY &gt; EMA200 +1%) : 3 trades/j max, seuil net ≥ 10<br>"
            "• <b>NEUTRAL</b> (−1% à +1% EMA200) : 2 trades/j, seuil net ≥ 20<br>"
            "• <b>BEAR</b> (SPY &lt; EMA200 −1%) : 1 trade/j, seuil net ≥ 30<br><br>"
            "<b>VIX :</b><br>"
            "• &lt; 20 (LOW) : paramètres normaux<br>"
            "• 20–30 (MEDIUM) : vigilance<br>"
            "• &gt; 30 (HIGH) : −1 trade/j et seuil net +10"
            + _ex("SPY +10.4% vs EMA200, VIX=18 → BULL → 3 trades/j, net ≥ 10"),
            tag="Macro",
        )

    if _visible(["newsletter", "signal", "secteur", "bias", "momentum capital"]):
        _card(
            "Newsletter Momentum (Capital)",
            "Newsletter quotidienne analysant des valeurs françaises (CAC40). "
            "Lue automatiquement via Gmail, ses signaux sont convertis en biais sectoriels "
            "appliqués au MacroAgent.<br><br>"
            "<b>Mapping :</b><br>"
            "• Recommandation BUY → secteur +1 pts de performance relative<br>"
            "• AVOID/SELL → secteur −2 pts de performance relative<br>"
            "• CAC40 BEARISH → régime légèrement durci (si SPY proche EMA200)"
            + _ex("Newsletter : STMicro AVOID → Semi −2pts, Orange BUY → Telecoms +1pt"),
            tag="Macro",
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. GESTION DU RISQUE
    # ═══════════════════════════════════════════════════════════════════════════
    if _visible(["risque", "sl", "stop", "tp", "take profit", "trailing", "sizing",
                 "position", "r-ratio", "kelly", "exposition", "réserve"]):
        _section("Gestion du risque", "🛡️")

    if _visible(["sl", "stop loss", "stop", "perte maximale"]):
        _card(
            "SL — Stop Loss",
            "Seuil de prix en dessous duquel la position est automatiquement fermée "
            "pour limiter la perte.<br><br>"
            "<b>Calcul dans Zentry :</b><br>"
            + _formula("SL = Prix d'entrée − 2 × ATR")
            + "<br>Exemple : entrée à 200$, ATR = 5$ → SL = 190$ (perte max −5%)<br><br>"
            "Après TP1, un <b>trailing stop</b> remplace le SL fixe.",
            tag="Risque",
        )

    if _visible(["tp", "take profit", "tp1", "tp2", "tp3", "palier"]):
        _card(
            "TP — Take Profit (3 paliers)",
            "Ventes partielles automatiques à des niveaux prédéfinis. "
            "La position est vendue progressivement plutôt qu'en une seule fois.<br><br>"
            "<b>Paliers :</b><br>"
            + _formula("TP1 = entrée + 1.5 × ATR  → vente de 25% (encaisse tôt)")
            + _formula("TP2 = entrée + 3.0 × ATR  → vente de 35% (profit substantiel)")
            + _formula("TP3 = entrée + 5.0 × ATR  → vente de 40% (laisser courir)")
            + _ex("Entrée 200$, ATR=5$ → TP1=207.5$, TP2=215$, TP3=225$"),
            tag="Risque",
        )

    if _visible(["trailing stop", "stop suiveur", "tp1"]):
        _card(
            "Trailing Stop",
            "Stop loss qui <i>suit</i> le prix à la hausse une fois TP1 atteint. "
            "Protège les gains sans plafonner les gains potentiels.<br><br>"
            "<b>Fonctionnement :</b><br>"
            "• Activé automatiquement quand TP1 est touché<br>"
            "• Positionné à : prix courant − 2 × ATR<br>"
            "• Monte avec le prix, ne descend jamais"
            + _ex("Prix monte à 230$, ATR=5$ → trailing stop remonte à 220$ et sécurise le gain"),
            tag="Risque",
        )

    if _visible(["r-ratio", "r ratio", "risque récompense", "reward"]):
        _card(
            "R-Ratio (Risk/Reward)",
            "Rapport entre le gain potentiel et la perte maximale. "
            "Calculé sur le TP3 (objectif final).<br><br>"
            + _formula("R-Ratio = (TP3 − Entrée) / (Entrée − SL)")
            + "<br><b>Exemple :</b> Entrée 200$, SL 190$, TP3 225$ → R = 25/10 = <b>2.5×</b><br><br>"
            "Dans Zentry, le R-ratio minimum pour déclencher un achat est <b>1.5×</b>. "
            "Avec SL=2×ATR et TP3=5×ATR, le R théorique est de 2.5×.",
            tag="Risque",
        )

    if _visible(["sizing", "taille", "position", "allocation", "kelly", "invest"]):
        _card(
            "Sizing de position",
            "Calcul de la quantité achetée pour chaque trade, basé sur la valeur totale "
            "du portefeuille et le score.<br><br>"
            "<b>Principes :</b><br>"
            "• Risque par trade : environ 1–2% du portefeuille<br>"
            "• Score élevé → légèrement plus de capital alloué<br>"
            "• Plafonné par le cash disponible et le budget hebdomadaire",
            tag="Risque",
        )

    if _visible(["exposition", "exposure", "investi", "cash"]):
        _card(
            "Exposition",
            "Pourcentage du portefeuille actuellement investi en positions ouvertes.<br><br>"
            + _formula("Exposition = Total investi / Valeur totale du portefeuille")
            + "<br>Zentry plafonne l'exposition à <b>80%</b> maximum pour toujours conserver du cash.",
            tag="Portefeuille",
        )

    if _visible(["réserve", "reserve cash", "unlock"]):
        _card(
            "Réserve cash",
            "Portion du cash verrouillée, non utilisable pour les achats habituels. "
            "Sert de coussin de sécurité.<br><br>"
            "<b>Déblocage :</b> la réserve est accessible si le score d'un candidat "
            "dépasse le seuil RESERVE_UNLOCK (opportunité exceptionnelle).",
            tag="Portefeuille",
        )

    if _visible(["montée en charge", "ramp", "ramp-up", "budget", "hebdomadaire"]):
        _card(
            "Montée en charge (Ramp-up)",
            "Phase de démarrage du portefeuille pour éviter d'investir tout le capital "
            "d'un coup. Le système déploie un pourcentage fixe du capital initial par semaine.<br><br>"
            "Durée par défaut : 8 semaines. "
            "Une opportunité exceptionnelle (score &gt; seuil de réserve) ignore cette contrainte.",
            tag="Portefeuille",
        )

    if _visible(["time stop", "stagnation", "25 jours"]):
        _card(
            "Time Stop",
            "Fermeture automatique d'une position qui stagne trop longtemps sans performer.<br><br>"
            "<b>Condition :</b> position ouverte depuis &gt; 25 jours <i>et</i> en perte de plus de 2%<br>"
            "→ Fermeture au prix du marché, capital recyclé vers de meilleures opportunités.",
            tag="Risque",
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. MÉTRIQUES BACKTEST
    # ═══════════════════════════════════════════════════════════════════════════
    if _visible(["backtest", "sharpe", "calmar", "drawdown", "profit factor",
                 "win rate", "annualisé", "volatilité"]):
        _section("Métriques de performance (Backtest)", "⏱️")

    if _visible(["sharpe", "ratio sharpe", "rendement ajusté"]):
        _card(
            "Sharpe Ratio",
            "Mesure le rendement excédentaire par unité de risque. "
            "Plus il est élevé, meilleur est le rapport performance/volatilité.<br><br>"
            + _formula("Sharpe = (Rendement annualisé − Taux sans risque) / Volatilité annualisée")
            + "<br>• &gt; 1.5 → excellent<br>• 0.5–1.5 → correct<br>• &lt; 0 → perd de l'argent ajusté au risque",
            tag="Performance",
        )

    if _visible(["calmar", "calmar ratio", "drawdown", "rendement"]):
        _card(
            "Calmar Ratio",
            "Ratio rendement / max drawdown. Mesure combien de rendement annuel on obtient "
            "par unité de perte maximale subie.<br><br>"
            + _formula("Calmar = Rendement annualisé / |Max Drawdown|")
            + "<br>• &gt; 1 → le rendement compense largement les pertes<br>"
            "• &lt; 0.5 → le drawdown est trop important par rapport aux gains",
            tag="Performance",
        )

    if _visible(["drawdown", "perte maximale", "dd", "underwater"]):
        _card(
            "Max Drawdown",
            "Perte maximale observée depuis un pic de portefeuille jusqu'au creux suivant. "
            "Mesure le pire scénario historique.<br><br>"
            + _formula("Drawdown = (Valeur creux − Valeur pic) / Valeur pic")
            + _ex("Portefeuille à 12 000€ (pic), descend à 10 200€ (creux) → Drawdown = −15%"),
            tag="Risque",
        )

    if _visible(["profit factor", "pf", "gains pertes"]):
        _card(
            "Profit Factor",
            "Ratio entre la somme des gains et la somme des pertes sur toutes les positions fermées.<br><br>"
            + _formula("Profit Factor = Somme des gains / Somme des pertes (en valeur absolue)")
            + "<br>• &gt; 1.5 → système profitable<br>"
            "• = 1.0 → break-even<br>"
            "• &lt; 1.0 → le système perd de l'argent",
            tag="Performance",
        )

    if _visible(["win rate", "taux de réussite", "trades gagnants"]):
        _card(
            "Win Rate",
            "Pourcentage de trades fermés en profit.<br><br>"
            + _formula("Win Rate = Trades gagnants / Total trades fermés")
            + "<br>Un win rate de 40% peut être profitable si les gains sont bien plus grands que les pertes "
            "(c'est pour ça que le R-ratio doit être &gt; 1.5).",
            tag="Performance",
        )

    if _visible(["annualisé", "rendement annualisé", "cagr"]):
        _card(
            "Rendement annualisé",
            "Rendement total converti en équivalent annuel pour comparer des stratégies "
            "sur des durées différentes.<br><br>"
            + _formula("Rendement annualisé = (1 + Rendement total)^(365/jours) − 1")
            + _ex("Portefeuille +12% en 6 mois → Rendement annualisé ≈ +25%"),
            tag="Performance",
        )

    if _visible(["holding", "durée", "jours", "moyenne holding"]):
        _card(
            "Durée moyenne de détention",
            "Nombre moyen de jours entre l'ouverture et la fermeture d'une position. "
            "Reflète le style de trading (court terme vs swing).<br><br>"
            "Dans Zentry, la durée typique est de 5–30 jours (swing trading).",
            tag="Performance",
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. NAVIGATION DU SITE
    # ═══════════════════════════════════════════════════════════════════════════
    if _visible(["dashboard", "screener", "backtest", "analyse", "historique",
                 "rapport", "navigation", "onglet"]):
        _section("Navigation du site", "🧭")

    tabs_info = [
        ("📊 Dashboard",       "dashboard", "Vue d'ensemble temps réel : valeur du portefeuille, exposition, PnL des positions ouvertes, métriques clés."),
        ("📋 Ordres ouverts",  "ordres",    "Tableau de toutes les positions actuelles avec prix d'entrée, SL, TP et PnL latent."),
        ("🎯 Positions SL/TP", "positions", "Visualisation graphique des niveaux SL/TP pour chaque position. Permet la fermeture manuelle."),
        ("📜 Historique",      "historique","Journal de tous les trades fermés avec PnL réalisé, frais et durée de détention."),
        ("🔍 Analyse",         "analyse",   "Graphique technique interactif pour un ticker donné : indicateurs, niveaux clés, signal de scoring."),
        ("📡 Screener",        "screener",  "Lance le screener sur toute la watchlist et classe les tickers par score décroissant. Permet de lancer un débat à la demande."),
        ("⏱ Backtest",        "backtest",  "Rejoue la stratégie sur des données historiques. Affiche les métriques de performance et la courbe d'équité."),
        ("📰 Rapport",         "rapport",   "Log quotidien du système : scans, débats, achats, résumé macro."),
        ("📖 Lexique",         "lexique",   "Cette page."),
    ]

    for icon_name, key, desc in tabs_info:
        if _visible([key, icon_name.lower()]):
            _card(icon_name, desc)

    st.markdown("<div style='height:3rem'></div>", unsafe_allow_html=True)
