"""Calcul des frais de courtage et du prix de break-even."""

from config import BROKER_CONFIG


def compute_fees(price: float, qty: float, broker: dict = None) -> float:
    """
    Frais pour un ordre (achat ou vente).

    Modèle générique qui couvre les deux courtiers du projet :
      - Alpaca : tout à zéro → frais nuls (comportement historique).
      - IBKR (US, tarif fixe) : per_share_fee=0.005, min_fee=1.00, cap 1% du notionnel
        (max_pct_fee). C'est ce barème que les garde-fous SL/TP doivent voir dès que
        les ordres partent réellement chez IBKR, sinon ils raisonnent avec des frais nuls
        et déclenchent des ventes partielles trop petites pour couvrir la commission.
    """
    if broker is None:
        broker = BROKER_CONFIG
    notional = price * qty
    raw = (
        broker.get("flat_fee", 0.0)
        + broker.get("per_share_fee", 0.0) * qty
        + notional * broker.get("pct_fee", 0.0)
    )
    fee = max(raw, broker.get("min_fee", 0.0))
    max_pct = broker.get("max_pct_fee", 0.0)
    if max_pct and notional > 0:
        # Chez IBKR le plafond (1% du notionnel) prime même sur le minimum : sur un
        # tout petit ordre on paie 1% plutôt que le minimum forfaitaire.
        fee = min(fee, notional * max_pct)
    return fee


def round_trip_fees(price: float, qty: float, broker: dict = None) -> float:
    """Frais totaux aller-retour (achat + vente estimée au même prix)."""
    return compute_fees(price, qty, broker) * 2


def break_even_price(entry: float, qty: float, broker: dict = None) -> float:
    """Prix auquel la position est rentable après frais aller-retour."""
    if qty <= 0:
        return entry
    total = round_trip_fees(entry, qty, broker)
    return entry + total / qty


def net_pnl(entry: float, exit_price: float, qty: float, broker: dict = None) -> float:
    """PnL net après frais aller-retour."""
    gross = (exit_price - entry) * qty
    fees = compute_fees(entry, qty, broker) + compute_fees(exit_price, qty, broker)
    return gross - fees
