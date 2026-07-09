"""Couche d'abstraction des ordres : Paper trading et broker réel IBKR."""

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from config import BROKER_CONFIG, IBKR_CONFIG, SLIPPAGE_PCT
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
        """Achat avec slippage réaliste (on paie légèrement plus que le prix affiché)."""
        exec_price = round(price * (1 + SLIPPAGE_PCT), 6)
        fees = compute_fees(exec_price, qty, self.broker_config)
        return {
            "status":     "filled",
            "ticker":     ticker,
            "side":       "buy",
            "qty":        qty,
            "price":      exec_price,
            "fees":       fees,
            "total":      exec_price * qty + fees,
            "date":       datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def sell(self, ticker: str, qty: float, price: float) -> dict:
        """Vente avec slippage réaliste (on reçoit légèrement moins que le prix affiché)."""
        exec_price = round(price * (1 - SLIPPAGE_PCT), 6)
        fees = compute_fees(exec_price, qty, self.broker_config)
        return {
            "status":     "filled",
            "ticker":     ticker,
            "side":       "sell",
            "qty":        qty,
            "price":      exec_price,
            "fees":       fees,
            "total":      exec_price * qty - fees,
            "date":       datetime.now().strftime("%Y-%m-%d %H:%M"),
        }


class DualBroker(OrderBroker):
    """
    Exécute réellement via `real` (IBKR) et calcule EN PARALLÈLE ce que `shadow`
    (PaperBroker) aurait produit, pour valider le modèle de frais/slippage avant
    le go-live. Le portefeuille utilise le fill RÉEL ; la comparaison est loggée.

    Chaque ordre écrit une ligne JSONL dans validation_log :
        {date, ticker, side, qty, real_price, sim_price, price_diff_pct,
         real_fees, sim_fees, fees_diff}
    """

    def __init__(self, real: OrderBroker, shadow: OrderBroker, log_path: Path):
        self.real = real
        self.shadow = shadow
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def buy(self, ticker, qty, price):
        return self._exec("buy", ticker, qty, price)

    def sell(self, ticker, qty, price):
        return self._exec("sell", ticker, qty, price)

    def _exec(self, side, ticker, qty, price):
        real_res = getattr(self.real, side)(ticker, qty, price)
        try:
            sim_res = getattr(self.shadow, side)(ticker, qty, price)
            self._log_delta(side, ticker, qty, real_res, sim_res)
        except Exception:
            # La comparaison ne doit jamais bloquer l'exécution réelle
            pass
        return real_res

    def _log_delta(self, side, ticker, qty, real_res, sim_res):
        rp, sp = real_res.get("price", 0), sim_res.get("price", 0)
        price_diff_pct = ((rp - sp) / sp * 100) if sp else 0.0
        row = {
            "date":           datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ticker":         ticker,
            "side":           side,
            "qty":            qty,
            "real_price":     rp,
            "sim_price":      sp,
            "price_diff_pct": round(price_diff_pct, 4),
            "real_fees":      real_res.get("fees", 0),
            "sim_fees":       sim_res.get("fees", 0),
            "fees_diff":      round(real_res.get("fees", 0) - sim_res.get("fees", 0), 4),
            "ibkr_status":    real_res.get("ibkr_status"),
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ── Stub future intégration ───────────────────────────────────────

class BinanceBroker(OrderBroker):
    """Non implémenté — stub pour connexion future."""

    def buy(self, ticker, qty, price):
        raise NotImplementedError("BinanceBroker non configuré")

    def sell(self, ticker, qty, price):
        raise NotImplementedError("BinanceBroker non configuré")


# ── Factory : sélection du broker selon la config ─────────────────

def make_broker(broker_config: dict = None, validation_log: str = None) -> OrderBroker:
    """
    Renvoie le broker à utiliser selon IBKR_CONFIG.

    - IBKR désactivé  → PaperBroker (comportement historique, aucune régression)
    - IBKR activé      → IBKRBroker (exécution réelle)
    - IBKR + shadow    → DualBroker (réel IBKR + comparaison PaperBroker)

    Import de IBKRBroker paresseux : `ib_async` n'est requis que si IBKR est activé.
    """
    broker_config = broker_config or BROKER_CONFIG

    if not IBKR_CONFIG.get("enabled"):
        return PaperBroker(broker_config)

    from portfolio.ibkr_broker import IBKRBroker
    real = IBKRBroker(IBKR_CONFIG)

    if IBKR_CONFIG.get("shadow"):
        data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
        log_path = Path(validation_log) if validation_log else data_dir / "ibkr_validation.jsonl"
        return DualBroker(real, PaperBroker(broker_config), log_path)

    return real
