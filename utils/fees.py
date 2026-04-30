"""Calcul des frais de courtage et du prix de break-even."""

from config import BROKER_CONFIG


def compute_fees(price: float, qty: float, broker: dict = None) -> float:
    """Frais pour un ordre (achat ou vente)."""
    if broker is None:
        broker = BROKER_CONFIG
    raw = broker["flat_fee"] + price * qty * broker["pct_fee"]
    return max(raw, broker.get("min_fee", 0.0))


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
