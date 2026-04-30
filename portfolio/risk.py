"""Calcul du sizing, R-ratio, et contraintes de risque."""

from config import (
    ATR_SL_MULTIPLIER,
    CONVICTION_SCORE_THRESHOLD,
    MAX_POSITION_CONVICTION_PCT,
    MAX_POSITION_OPPORTUNITY_PCT,
    MAX_POSITION_PCT,
    OPPORTUNITY_SCORE_THRESHOLD,
    RESERVE_CASH_PCT,
    RISK_PER_TRADE_PCT,
    TP_LEVELS,
)
from utils.fees import compute_fees


def sl_price(entry: float, atr: float) -> float:
    """Stop-loss initial basé sur l'ATR."""
    return entry - ATR_SL_MULTIPLIER * atr


def tp_prices(entry: float, atr: float) -> list[dict]:
    """Retourne les paliers TP avec prix calculés."""
    return [
        {
            "price": entry + lvl["atr_mult"] * atr,
            "sell_pct": lvl["sell_pct"],
            "atr_mult": lvl["atr_mult"],
        }
        for lvl in TP_LEVELS
    ]


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
