"""
Système de décision multi-agents pour la sélection de positions.

Architecture :
  🟢 BullAgent   — construit le dossier pour acheter
  🔴 BearAgent   — construit le dossier contre l'achat
  ⚖️  ArbiterAgent — tranche en pesant les deux camps

Chaque agent analyse les signaux techniques, le contexte portefeuille
et formule des arguments typés, quantifiés par une conviction/concern.
L'arbitre applique également des vétos non-négociables (hard rules).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Argument:
    text: str
    weight: int          # Contribution au score conviction/concern


@dataclass
class AgentResult:
    agent: Literal["BULL", "BEAR"]
    score: int           # 0-100 : conviction (bull) ou concern (bear)
    verdict: str
    arguments: list[Argument] = field(default_factory=list)
    bull_cancellation: int = 0   # pts retirés à la conviction Bull par contre-args adversariaux

    def top_args(self, n: int = 5) -> list[str]:
        sorted_args = sorted(self.arguments, key=lambda a: -a.weight)
        return [a.text for a in sorted_args[:n]]


@dataclass
class DebateDecision:
    ticker: str
    decision: Literal["ACHETER", "ACHETER (prudent)", "PASSER", "VETO"]
    reason: str
    net_score: float
    buy: bool
    bull: AgentResult
    bear: AgentResult

    def format_log(self) -> list[str]:
        """Retourne les lignes de log du débat, prêtes à afficher."""
        lines = []
        sep = "─" * 52
        lines.append(sep)
        lines.append(f"  DÉBAT : {self.ticker}")
        lines.append(sep)

        # Camp haussier
        bull_icon = "🟢"
        cancelled = self.bear.bull_cancellation
        eff_score = max(0, self.bull.score - cancelled)
        cancel_str = f" → effectif={eff_score} (−{cancelled} annulés)" if cancelled > 0 else ""
        lines.append(f"  {bull_icon} BULL [conviction={self.bull.score}{cancel_str}] → {self.bull.verdict}")
        for arg in self.bull.top_args(5):
            lines.append(f"     • {arg}")

        lines.append("")

        # Camp baissier
        bear_icon = "🔴"
        lines.append(f"  {bear_icon} BEAR [concern={self.bear.score}] → {self.bear.verdict}")
        if self.bear.arguments:
            for arg in self.bear.top_args(5):
                lines.append(f"     • {arg}")
        else:
            lines.append("     (aucune objection majeure)")

        lines.append("")

        # Décision arbitre
        decision_icon = {
            "ACHETER":         "✅",
            "ACHETER (prudent)": "🟡",
            "PASSER":          "⏭️ ",
            "VETO":            "🚫",
        }.get(self.decision, "⚖️ ")
        lines.append(f"  {decision_icon} ARBITRE → {self.decision}  (net={self.net_score:+.0f})")
        lines.append(f"     {self.reason}")
        lines.append(sep)
        return lines


# ─────────────────────────────────────────────────────────────────────────────
# Règles adversariales : le Bear challenge directement les arguments du Bull
# Chaque règle annule des pts de conviction Bull (pas juste ajoute du concern)
# ─────────────────────────────────────────────────────────────────────────────

COUNTER_RULES = [
    {
        "trigger":      "RSI survendu",
        "condition":    lambda row: row.get("market_regime") == "bear",
        "counter_text": "RSI survendu en régime baissier = piège technique — le downtrend efface souvent ce signal",
        "cancel_pts":   15,
    },
    {
        "trigger":      "Bollinger inférieure",
        "condition":    lambda row: row.get("market_regime") == "bear",
        "counter_text": "BB basse percée en downtrend = support cassé, pas rebond — le prix peut rester sous la bande",
        "cancel_pts":   10,
    },
    {
        "trigger":      "Croisement MACD",
        "condition":    lambda row: row.get("market_regime") == "bear",
        "counter_text": "Croisement MACD haussier en bear market — taux d'échec >60%, faux signal fréquent",
        "cancel_pts":   12,
    },
    {
        "trigger":      "Stoch RSI survendu",
        "condition":    lambda row: row.get("market_regime") == "bear",
        "counter_text": "StochRSI survendu en régime baissier — peut rester extrême longtemps sans rebond",
        "cancel_pts":   8,
    },
    {
        "trigger":      "EMA50",
        "condition":    lambda row: any("EMA200" in f for f in row.get("bear_flags", [])),
        "counter_text": "Soutien EMA50 fragile quand le prix est déjà sous EMA200 — résistance structurelle plus haute",
        "cancel_pts":   6,
    },
    {
        "trigger":      "Momentum 10j fort",
        "condition":    lambda row: row.get("bear_score", 0) >= 25,
        "counter_text": "Rebond technique court terme dans tendance baissière = dead cat bounce potentiel",
        "cancel_pts":   8,
    },
    {
        "trigger":      "RSI bas",
        "condition":    lambda row: row.get("market_regime") == "bear",
        "counter_text": "RSI bas en bear market = momentum baissier, pas accumulation",
        "cancel_pts":   8,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# BullAgent
# ─────────────────────────────────────────────────────────────────────────────

class BullAgent:
    """
    Analyse les signaux techniques haussiers et le potentiel de gain.
    Construit le dossier PRO-achat.
    """

    def argue(self, ticker: str, row: dict, pm_context: dict) -> AgentResult:
        args: list[Argument] = []
        conviction = 0

        score      = row.get("score", 0)
        bull_score = row.get("bull_score", score)
        r_ratio    = row.get("r_ratio", 0)
        details    = row.get("details", {})

        # ── Score global ──────────────────────────────────────────────
        if bull_score >= 70:
            args.append(Argument(f"Score haussier fort ({bull_score}/100)", 20))
            conviction += 20
        elif bull_score >= 55:
            args.append(Argument(f"Score haussier correct ({bull_score}/100)", 10))
            conviction += 10
        elif bull_score >= 40:
            args.append(Argument(f"Score haussier modéré ({bull_score}/100)", 5))
            conviction += 5

        # ── R-ratio ───────────────────────────────────────────────────
        if r_ratio >= 3.0:
            args.append(Argument(f"R-ratio excellent ({r_ratio:.1f}×) — asymétrie gain/risque idéale", 20))
            conviction += 20
        elif r_ratio >= 2.0:
            args.append(Argument(f"R-ratio solide ({r_ratio:.1f}×) — risque/récompense favorable", 12))
            conviction += 12
        elif r_ratio >= 1.5:
            args.append(Argument(f"R-ratio acceptable ({r_ratio:.1f}×)", 5))
            conviction += 5

        # ── RSI ───────────────────────────────────────────────────────
        rsi = details.get("RSI", {}).get("value")
        if rsi is not None:
            if rsi < 30:
                args.append(Argument(f"RSI survendu ({rsi:.0f}) — zone de rebond historique", 15))
                conviction += 15
            elif rsi < 40:
                args.append(Argument(f"RSI bas ({rsi:.0f}) — zone d'accumulation", 8))
                conviction += 8
            elif 45 <= rsi <= 60:
                args.append(Argument(f"RSI sain ({rsi:.0f}) — pas de surachat", 3))
                conviction += 3

        # ── MACD ──────────────────────────────────────────────────────
        macd_pts = details.get("MACD", {}).get("pts", 0)
        if macd_pts >= 15:
            args.append(Argument("Croisement MACD haussier au-dessus de zéro — momentum fort", 15))
            conviction += 15
        elif macd_pts >= 8:
            args.append(Argument("Croisement MACD haussier — signal d'achat", 8))
            conviction += 8
        elif macd_pts >= 5:
            args.append(Argument("MACD positif (pas de croisement récent)", 3))
            conviction += 3

        # ── EMA200 ────────────────────────────────────────────────────
        ema200_pts = details.get("EMA200", {}).get("pts", 0)
        if ema200_pts > 0:
            ema200_val = details["EMA200"].get("value", 0)
            args.append(Argument(
                f"Prix au-dessus EMA200 ({ema200_val:.2f}) — tendance long terme haussière", 12))
            conviction += 12

        # ── EMA50 ─────────────────────────────────────────────────────
        ema50_pts = details.get("EMA50", {}).get("pts", 0)
        if ema50_pts > 0:
            args.append(Argument("Prix au-dessus EMA50 — soutien technique actif", 6))
            conviction += 6

        # ── Volume ────────────────────────────────────────────────────
        vol_ratio = details.get("Volume", {}).get("value")
        if vol_ratio is not None and vol_ratio > 1.5:
            args.append(Argument(f"Volume fort ({vol_ratio:.1f}× la moyenne) — intérêt institutionnel", 8))
            conviction += 8

        # ── Momentum 10j ──────────────────────────────────────────────
        mom = details.get("Momentum10j", {}).get("value")
        if mom is not None:
            if mom > 8:
                args.append(Argument(f"Momentum 10j fort (+{mom:.1f}%) — tendance confirmée", 10))
                conviction += 10
            elif mom > 3:
                args.append(Argument(f"Momentum 10j positif (+{mom:.1f}%)", 5))
                conviction += 5

        # ── CMF ───────────────────────────────────────────────────────
        cmf_pts = details.get("CMF", {}).get("pts", 0)
        if cmf_pts >= 10:
            args.append(Argument("CMF fort — flux acheteur dominant", 8))
            conviction += 8
        elif cmf_pts >= 5:
            args.append(Argument("CMF positif — légère pression acheteuse", 3))
            conviction += 3

        # ── OBV ───────────────────────────────────────────────────────
        obv_pts = details.get("OBV", {}).get("pts", 0)
        if obv_pts > 0:
            args.append(Argument("OBV en hausse — accumulation en cours", 6))
            conviction += 6

        # ── Stochastique RSI ──────────────────────────────────────────
        stoch_pts = details.get("StochRSI", {}).get("pts", 0)
        stoch_val = details.get("StochRSI", {}).get("value")
        if stoch_pts > 0 and stoch_val is not None:
            args.append(Argument(f"Stoch RSI survendu ({stoch_val:.0f}) — retournement imminent", 8))
            conviction += 8

        # ── Bollinger bas ─────────────────────────────────────────────
        bb_pts = details.get("Bollinger", {}).get("pts", 0)
        if bb_pts > 0:
            args.append(Argument("Prix sous bande Bollinger inférieure — compression extrême", 10))
            conviction += 10

        # ── Contexte portefeuille ─────────────────────────────────────
        n_open = pm_context.get("n_open", 0)
        if n_open < 3:
            args.append(Argument(f"Portefeuille peu exposé ({n_open} positions) — capacité à déployer", 5))
            conviction += 5

        conviction = min(conviction, 100)

        if conviction >= 55:
            verdict = "ACHETER"
        elif conviction >= 35:
            verdict = "PENCHÉ POUR"
        else:
            verdict = "NEUTRE"

        return AgentResult(agent="BULL", score=conviction, verdict=verdict, arguments=args)


# ─────────────────────────────────────────────────────────────────────────────
# BearAgent
# ─────────────────────────────────────────────────────────────────────────────

class BearAgent:
    """
    Analyse les risques, contre-signaux et contraintes du portefeuille.
    Construit le dossier CONTRE l'achat.
    """

    def argue(self, ticker: str, row: dict, pm_context: dict, bull_result: "AgentResult | None" = None) -> AgentResult:
        args: list[Argument] = []
        concern = 0

        bear_score = row.get("bear_score", 0)
        bear_flags = row.get("bear_flags", [])
        details    = row.get("details", {})
        r_ratio    = row.get("r_ratio", 0)

        # ── Bear flags issus du scoring ───────────────────────────────
        flag_weights = {
            "EMA200":    25,   # tendance structurelle
            "EMA50":     12,
            "Momentum":  12,
            "ADX":       15,
            "RSI":        8,
            "Bollinger":  6,
            "Volume":     5,
        }
        for flag in bear_flags:
            weight = 8  # default
            for kw, w in flag_weights.items():
                if kw in flag:
                    weight = w
                    break
            args.append(Argument(flag, weight))
            concern += weight

        # ── Score baissier global ─────────────────────────────────────
        if bear_score >= 40:
            args.append(Argument(f"Score baissier élevé ({bear_score} pts) — nombreux signaux négatifs", 15))
            concern += 15
        elif bear_score >= 25:
            args.append(Argument(f"Score baissier modéré ({bear_score} pts)", 8))
            concern += 8

        # ── R-ratio insuffisant ───────────────────────────────────────
        if r_ratio < 1.2:
            args.append(Argument(f"R-ratio faible ({r_ratio:.1f}×) — risque/récompense défavorable", 20))
            concern += 20
        elif r_ratio < 1.5:
            args.append(Argument(f"R-ratio limite ({r_ratio:.1f}×) — marge de sécurité étroite", 10))
            concern += 10

        # ── Exposition portefeuille ───────────────────────────────────
        exposure = pm_context.get("exposure_pct", 0)
        if exposure > 0.75:
            args.append(Argument(
                f"Exposition déjà élevée ({exposure*100:.0f}%) — risque de surconcentration", 20))
            concern += 20
        elif exposure > 0.60:
            args.append(Argument(
                f"Exposition modérée ({exposure*100:.0f}%) — prudence sur les ajouts", 8))
            concern += 8

        # ── Concentration sectorielle ─────────────────────────────────
        sector       = pm_context.get("sector", "Other")
        sector_count = pm_context.get("sector_count", 0)
        if sector_count >= 3:
            args.append(Argument(
                f"Secteur {sector} très concentré ({sector_count} positions) — risque sectoriel", 18))
            concern += 18
        elif sector_count >= 2:
            args.append(Argument(
                f"Secteur {sector} déjà exposé ({sector_count} positions) — diversification limitée", 10))
            concern += 10

        # ── Budget hebdomadaire ───────────────────────────────────────
        cash_pct = pm_context.get("cash_deploy_pct", 1.0)
        if cash_pct < 0.2:
            args.append(Argument(
                f"Budget semaine presque épuisé ({cash_pct*100:.0f}% restant) — conserver pour mieux", 12))
            concern += 12
        elif cash_pct < 0.4:
            args.append(Argument(
                f"Budget semaine limité ({cash_pct*100:.0f}% restant)", 5))
            concern += 5

        # ── Régime de marché ──────────────────────────────────────────────
        market_regime = row.get("market_regime", "neutral")
        if market_regime == "bear":
            args.append(Argument("Marché en régime baissier (SPY sous EMA200) — timing défavorable", 25))
            concern += 25
        elif market_regime == "neutral":
            args.append(Argument("Régime de marché incertain", 8))
            concern += 8

        # ── MACD négatif ──────────────────────────────────────────────
        macd_pts = details.get("MACD", {}).get("pts", 0)
        if macd_pts <= -10:
            args.append(Argument("Croisement MACD baissier — momentum vendeur actif", 12))
            concern += 12

        # ── Momentum fortement négatif ────────────────────────────────
        mom = details.get("Momentum10j", {}).get("value")
        if mom is not None and mom < -5:
            args.append(Argument(f"Chute de {mom:.1f}% sur 10j — attraper un couteau ?", 15))
            concern += 15

        # ── Stochastique suracheté ────────────────────────────────────
        stoch_val = details.get("StochRSI", {}).get("value")
        if stoch_val is not None and stoch_val > 80:
            args.append(Argument(f"Stoch RSI suracheté ({stoch_val:.0f}) — retournement baissier possible", 10))
            concern += 10

        # ── Contre-arguments adversariaux (challenge direct du Bull) ──
        # Ces arguments annulent des pts de conviction Bull 1:1 (pas atténués par 0.6)
        bull_cancellation = 0
        if bull_result is not None:
            for bull_arg in bull_result.arguments:
                for rule in COUNTER_RULES:
                    if rule["trigger"] in bull_arg.text and rule["condition"](row):
                        pts = rule["cancel_pts"]
                        args.append(Argument(
                            f"↩ '{rule['trigger']}' annulé : {rule['counter_text']}", pts
                        ))
                        bull_cancellation += pts
                        break  # une règle par argument Bull

        concern = min(concern, 100)

        if concern >= 50:
            verdict = "ÉVITER"
        elif concern >= 30:
            verdict = "PRUDENCE"
        else:
            verdict = "OK"

        return AgentResult(
            agent="BEAR", score=concern, verdict=verdict,
            arguments=args, bull_cancellation=bull_cancellation,
        )


# ─────────────────────────────────────────────────────────────────────────────
# ArbiterAgent
# ─────────────────────────────────────────────────────────────────────────────

class ArbiterAgent:
    """
    Tranche le débat Bull/Bear.
    Applique des vétos non-négociables, puis pondère les scores.
    Retourne la décision finale avec justification.
    """

    # Vétos absolus — présents dans bear_flags → achat impossible
    HARD_VETO_KEYWORDS = [
        "downtrend structurel",
        "EMA200",
    ]

    def decide(
        self,
        ticker: str,
        bull: AgentResult,
        bear: AgentResult,
        row: dict,
    ) -> dict:
        bear_flags = row.get("bear_flags", [])
        score      = row.get("score", 0)

        # ── Vétos durs ────────────────────────────────────────────────
        for flag in bear_flags:
            for kw in self.HARD_VETO_KEYWORDS:
                if kw.lower() in flag.lower():
                    return {
                        "decision": "VETO",
                        "reason":   f"Règle non-négociable : {flag}",
                        "net_score": -999,
                        "buy":      False,
                    }

        if bear.score >= 70:
            return {
                "decision": "VETO",
                "reason":   f"Concern baissier trop élevé ({bear.score}/100) — risque inacceptable",
                "net_score": bull.score - bear.score,
                "buy":      False,
            }

        # ── Score net : bull pénalisé à 60% par le bear ───────────────
        net          = bull.score - bear.score * 0.60
        min_net_buy  = row.get("min_net_score", 30)   # seuil dynamique de l'agent macro
        min_net_prud = max(10, min_net_buy - 15)
        r   = row.get("r_ratio", 0)

        # ── Décision par palier — le net score fait autorité ─────────
        if net >= min_net_buy:
            return {
                "decision": "ACHETER",
                "reason":   (
                    f"Arguments haussiers l'emportent clairement "
                    f"(conviction={bull.score}, concern={bear.score}, net={net:+.0f})"
                ),
                "net_score": net,
                "buy":      True,
            }

        if net >= min_net_prud:
            return {
                "decision": "ACHETER (prudent)",
                "reason":   (
                    f"Balance légèrement favorable — position sizing réduit conseillé "
                    f"(conviction={bull.score}, concern={bear.score}, net={net:+.0f})"
                ),
                "net_score": net,
                "buy":      True,
            }

        if net >= 0:
            return {
                "decision": "PASSER",
                "reason":   (
                    f"Trop équilibré pour agir — attendre un signal plus net "
                    f"(conviction={bull.score}, concern={bear.score}, net={net:+.0f})"
                ),
                "net_score": net,
                "buy":      False,
            }

        # net < 0 : bear l'emporte
        return {
            "decision": "PASSER",
            "reason":   f"Camp baissier dominant (conviction={bull.score}, concern={bear.score}, net={net:+.0f})",
            "net_score": net,
            "buy":      False,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée public
# ─────────────────────────────────────────────────────────────────────────────

def run_debate(ticker: str, row: dict, pm) -> DebateDecision:
    """
    Lance le débat Bull/Bear/Arbitre pour un candidat.

    Args:
        ticker : symbole boursier
        row    : dict renvoyé par run_screener() (score, details, bear_flags, …)
        pm     : instance PortfolioManager (pour le contexte portefeuille)

    Returns:
        DebateDecision — contient bull, bear, decision, et la méthode format_log()
    """
    from config import SECTOR_MAP, WEEKLY_DEPLOY_PCT

    sector       = SECTOR_MAP.get(ticker, "Other")
    sector_count = sum(
        1 for t in pm.open_positions
        if SECTOR_MAP.get(t, "Other") == sector
    )

    available     = pm.available_deploy_cash(score=row.get("score", 50))
    weekly_budget = pm.initial_cash * WEEKLY_DEPLOY_PCT
    cash_pct      = available / weekly_budget if weekly_budget > 0 else 1.0

    pm_context = {
        "exposure_pct":   pm.exposure_pct,
        "sector":         sector,
        "sector_count":   sector_count,
        "cash_deploy_pct": min(cash_pct, 1.0),
        "n_open":         len(pm.open_positions),
    }

    bull_agent    = BullAgent()
    bear_agent    = BearAgent()
    arbiter_agent = ArbiterAgent()

    bull_result = bull_agent.argue(ticker, row, pm_context)
    bear_result = bear_agent.argue(ticker, row, pm_context, bull_result=bull_result)

    # Appliquer les cancellations adversariales : les contre-args réduisent le Bull 1:1
    effective_bull_score = max(0, bull_result.score - bear_result.bull_cancellation)
    effective_bull = AgentResult(
        agent     = "BULL",
        score     = effective_bull_score,
        verdict   = bull_result.verdict,
        arguments = bull_result.arguments,
    )
    decision = arbiter_agent.decide(ticker, effective_bull, bear_result, row)

    return DebateDecision(
        ticker   = ticker,
        decision = decision["decision"],
        reason   = decision["reason"],
        net_score= decision["net_score"],
        buy      = decision["buy"],
        bull     = bull_result,
        bear     = bear_result,
    )
