"""Calcul du sizing, R-ratio, et contraintes de risque."""

from config import (
    ATR_SL_MULTIPLIER,
    CONVICTION_SCORE_THRESHOLD,
    MAX_LOSS_PCT,
    MAX_POSITION_CONVICTION_PCT,
    MAX_POSITION_OPPORTUNITY_PCT,
    MAX_POSITION_PCT,
    OPPORTUNITY_SCORE_THRESHOLD,
    RESERVE_CASH_PCT,
    RISK_PER_TRADE_PCT,
    TP_LEVELS,
)
from utils.fees import compute_fees


def sl_price(entry: float, atr: float, support: float = 0.0,
             conviction: float = 0.0, vix_regime: str = "MEDIUM") -> float:
    """
    Stop-loss initial, plafonné à MAX_LOSS_PCT (jamais pire que -8%).

    - Mode ATR (USE_STRUCTURAL_LEVELS=False) : entry - 2×ATR, capé. Comportement historique.
    - Mode STRUCTUREL : stop calé JUSTE SOUS le support réel s'il est dans l'enveloppe de
      risque ; sinon retombe sur l'ATR. Le multiplicateur ATR est modulé par la conviction
      (forte → plus de marge, laisser respirer) et le régime VIX (nerveux → plus large).
      Bornes : jamais plus serré que 1×ATR (anti-bruit), jamais plus bas que -8% (cap).
    """
    from config import USE_STRUCTURAL_LEVELS
    hard_floor = entry * (1 - MAX_LOSS_PCT)
    if not USE_STRUCTURAL_LEVELS:
        return max(entry - ATR_SL_MULTIPLIER * atr, hard_floor)

    from config import STRUCT_CONVICTION_MARGIN, STRUCT_VIX_MULT, STRUCT_MIN_ATR
    mult = (ATR_SL_MULTIPLIER
            * (1 + STRUCT_CONVICTION_MARGIN * min(1.0, max(0.0, conviction)))
            * STRUCT_VIX_MULT.get(vix_regime, 1.0))
    sl = support * 0.995 if (support and 0 < support < entry) else (entry - mult * atr)
    if atr > 0:
        sl = min(sl, entry - STRUCT_MIN_ATR * atr)   # anti-bruit : au moins 1 ATR
    return max(sl, hard_floor)                        # cap -8% prioritaire


def tp_prices(entry: float, atr: float, resistance: float = 0.0,
              sl: float = 0.0) -> list[dict]:
    """
    Paliers TP. Mode ATR par défaut. Mode STRUCTUREL : TP1 calé juste SOUS la résistance
    réelle (prendre le profit avant le mur) et dernier TP garanti à ≥ MIN_R_RATIO × risque.
    """
    levels = [
        {"price": entry + lvl["atr_mult"] * atr,
         "sell_pct": lvl["sell_pct"], "atr_mult": lvl["atr_mult"]}
        for lvl in TP_LEVELS
    ]
    from config import USE_STRUCTURAL_LEVELS
    if not USE_STRUCTURAL_LEVELS or not levels:
        return levels

    from config import MIN_R_RATIO
    if resistance and resistance > entry:
        levels[0]["price"] = min(levels[0]["price"], resistance * 0.99)
    if sl and sl < entry:
        min_final = entry + MIN_R_RATIO * (entry - sl)
        if levels[-1]["price"] < min_final:
            levels[-1]["price"] = min_final
    return levels


def max_position_size_pct(score: int) -> float:
    """Taille maximale d'une position en % du portefeuille selon le score."""
    if score >= CONVICTION_SCORE_THRESHOLD:
        return MAX_POSITION_CONVICTION_PCT
    if score >= OPPORTUNITY_SCORE_THRESHOLD:
        return MAX_POSITION_OPPORTUNITY_PCT
    return MAX_POSITION_PCT


def compute_qty(
    portfolio_value: float,
    entry: float,
    sl: float,
    score: int = 50,
    broker: dict = None,
) -> tuple[float, float]:
    """
    Calcule la quantité à acheter selon le risk management.
    Retourne (qty, montant_investi).
    Contraint par risk% du portefeuille ET taille max% du portefeuille.
    """
    risk_amount = portfolio_value * RISK_PER_TRADE_PCT
    risk_per_share = entry - sl
    if risk_per_share <= 0:
        return 0.0, 0.0

    qty_by_risk = risk_amount / risk_per_share
    max_amount = portfolio_value * max_position_size_pct(score)
    qty_by_size = max_amount / entry

    qty = min(qty_by_risk, qty_by_size)
    qty = max(0.0, qty)
    invested = qty * entry
    return qty, invested


# ── Décisions de SORTIE (partagées live ↔ backtest) ──────────────────────────────
# Fonctions PURES : le manager (live) et le backtest les appellent à l'identique, pour
# que la logique SL/TP/trailing ne puisse plus diverger entre les deux. La mutation de
# l'état (Position vs BtPosition) reste propre à chaque, mais la DÉCISION est commune.

def hit_stop(low: float, stop: float) -> bool:
    """True si le plus-bas du jour touche/perce le stop."""
    return stop > 0 and low <= stop


def newly_hit_tps(high: float, tp_prices: list[float], tp_hit: list[bool]) -> list[int]:
    """Indices des paliers TP nouvellement atteints (non encore touchés) au plus-haut."""
    return [i for i, (p, h) in enumerate(zip(tp_prices, tp_hit)) if not h and high >= p]


def next_trailing(price: float, entry_atr: float, entry_price: float, current: float) -> float:
    """Nouveau niveau de trailing stop (ne redescend JAMAIS). ATR d'entrée, fallback 2%."""
    atr_ref = entry_atr if entry_atr > 0 else price * 0.02
    return max(current, price - ATR_SL_MULTIPLIER * atr_ref)


def r_ratio(entry: float, tp: float, sl: float) -> float:
    """Ratio récompense/risque."""
    risk = entry - sl
    reward = tp - entry
    if risk <= 0:
        return 0.0
    return reward / risk


def can_open_position(
    available_cash: float,
    total_portfolio: float,
    current_exposure_pct: float,
    sector_positions: int,
    invested_amount: float,
    max_total_exposure: float,
    max_sector_positions: int,
) -> tuple[bool, str]:
    """
    Vérifie toutes les contraintes avant d'ouvrir une position.
    Retourne (ok, raison_si_refus).
    """
    if available_cash < invested_amount:
        return False, f"Cash insuffisant ({available_cash:.2f} < {invested_amount:.2f})"
    if current_exposure_pct + invested_amount / total_portfolio > max_total_exposure:
        return False, f"Exposition max atteinte ({max_total_exposure*100:.0f}%)"
    if sector_positions >= max_sector_positions:
        return False, f"Trop de positions dans ce secteur ({max_sector_positions} max)"
    return True, ""
