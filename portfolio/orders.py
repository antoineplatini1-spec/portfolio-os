"""Couche d'abstraction des ordres : Paper trading et futur broker réel."""

from abc import ABC, abstractmethod
from datetime import datetime

from utils.fees import compute_fees


class OrderBroker(ABC):
    @abstractmethod
    def buy(self, ticker: str, qty: float, price: float) -> dict:
        """Passe un ordre d'achat. Retourne un dict order_result."""

    @abstractmethod
    def sell(self, ticker: str, qty: float, price: float) -> dict:
        """Passe un ordre de vente. Retourne un dict order_result."""


class PaperBroker(OrderBroker):
    """Simulation locale — aucune connexion externe."""

    def __init__(self, broker_config: dict):
        self.broker_config = broker_config

    def buy(self, ticker: str, qty: float, price: float) -> dict:
        fees = compute_fees(price, qty, self.broker_config)
        return {
            "status": "filled",
            "ticker": ticker,
            "side": "buy",
            "qty": qty,
            "price": price,
            "fees": fees,
            "total": price * qty + fees,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def sell(self, ticker: str, qty: float, price: float) -> dict:
        fees = compute_fees(price, qty, self.broker_config)
        return {
            "status": "filled",
            "ticker": ticker,
            "side": "sell",
            "qty": qty,
            "price": price,
            "fees": fees,
            "total": price * qty - fees,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }


# ── Stubs pour futures intégrations ──────────────────────────────

class BinanceBroker(OrderBroker):
    """Non implémenté — stub pour connexion future."""

    def buy(self, ticker, qty, price):
        raise NotImplementedError("BinanceBroker non configuré")

    def sell(self, ticker, qty, price):
        raise NotImplementedError("BinanceBroker non configuré")


class IBKRBroker(OrderBroker):
    """Non implémenté — stub pour connexion Interactive Brokers."""

    def buy(self, ticker, qty, price):
        raise NotImplementedError("IBKRBroker non configuré")

    def sell(self, ticker, qty, price):
        raise NotImplementedError("IBKRBroker non configuré")
