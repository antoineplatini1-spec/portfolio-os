"""
Broker Interactive Brokers — exécution réelle sur compte paper (puis live).

Se connecte à un IB Gateway / TWS via `ib_async` (fork maintenu de ib_insync).
Renvoie exactement le même dict que PaperBroker pour rester drop-in :
    {status, ticker, side, qty, price, fees, total, date}
où `price` = prix de fill RÉEL et `fees` = commission RÉELLE remontée par IBKR.

`ib_async` est importé paresseusement : tant qu'IBKR n'est pas activé, ce module
n'est jamais chargé et le reste du projet (GitHub Actions, backtest) tourne sans
la dépendance.

Doc setup Gateway : voir docker/README.md
"""

from __future__ import annotations

from datetime import datetime


class IBKRConnectionError(RuntimeError):
    """Le Gateway est injoignable ou la session n'est pas authentifiée."""


class IBKRBroker:
    """Exécution d'ordres sur Interactive Brokers (actions US)."""

    def __init__(self, ibkr_config: dict, connect: bool = True):
        self.cfg = ibkr_config
        self.order_type = ibkr_config.get("order_type", "MKT")
        self.fill_timeout = ibkr_config.get("fill_timeout_sec", 60)
        self._ib = None
        if connect:
            self.connect()

    # ── Connexion ─────────────────────────────────────────────────

    def connect(self):
        """Ouvre la connexion au Gateway. Idempotent."""
        try:
            from ib_async import IB
        except ImportError as e:  # pragma: no cover
            raise IBKRConnectionError(
                "ib_async non installé — `pip install ib_async`"
            ) from e

        if self._ib is not None and self._ib.isConnected():
            return

        ib = IB()
        try:
            ib.connect(
                host=self.cfg["host"],
                port=self.cfg["port"],
                clientId=self.cfg["client_id"],
                timeout=self.cfg.get("connect_timeout_sec", 15),
                readonly=False,
            )
        except Exception as e:
            raise IBKRConnectionError(
                f"Connexion IB Gateway {self.cfg['host']}:{self.cfg['port']} échouée : {e}"
            ) from e

        if not ib.isConnected():
            raise IBKRConnectionError("Gateway joignable mais session non connectée")

        self._ib = ib

    def disconnect(self):
        if self._ib is not None and self._ib.isConnected():
            self._ib.disconnect()

    @property
    def ib(self):
        if self._ib is None or not self._ib.isConnected():
            self.connect()
        return self._ib

    # ── Contrats ──────────────────────────────────────────────────

    def _stock_contract(self, ticker: str):
        """
        Construit un contrat action. Les tickers US passent en SMART/USD.
        Les tickers .PA (Euronext Paris) sont routés SBF/EUR.
        """
        from ib_async import Stock

        if ticker.endswith(".PA"):
            symbol = ticker[:-3]
            contract = Stock(symbol, "SBF", "EUR")
        else:
            contract = Stock(ticker, "SMART", "USD")

        qualified = self.ib.qualifyContracts(contract)
        if not qualified:
            raise IBKRConnectionError(f"Contrat introuvable pour {ticker}")
        return qualified[0]

    # ── Ordres ────────────────────────────────────────────────────

    def buy(self, ticker: str, qty: float, price: float) -> dict:
        return self._place(ticker, "BUY", qty, price)

    def sell(self, ticker: str, qty: float, price: float) -> dict:
        return self._place(ticker, "SELL", qty, price)

    def _place(self, ticker: str, action: str, qty: float, price: float) -> dict:
        """
        Place un ordre, attend le fill, et renvoie le résultat au format PaperBroker.
        IBKR ne permet pas les fractions d'actions sur tous les contrats : on arrondit
        à l'entier le plus proche (>=1). Le sizing amont raisonne en montant €, donc on
        recadre la qty et on renvoie la qty réellement exécutée.
        """
        from ib_async import MarketOrder, LimitOrder, Order

        qty_int = max(1, round(qty))
        contract = self._stock_contract(ticker)

        if self.order_type == "LMT":
            order = LimitOrder(action, qty_int, round(price, 2))
        elif self.order_type == "MOO":
            # Market-On-Open : adapté au cron pré-ouverture US
            order = Order(action=action, orderType="MKT", totalQuantity=qty_int, tif="OPG")
        else:
            order = MarketOrder(action, qty_int)

        if self.cfg.get("account"):
            order.account = self.cfg["account"]

        trade = self.ib.placeOrder(contract, order)

        # Attente du fill (bloquant, borné par fill_timeout)
        deadline = self.fill_timeout
        waited = 0.0
        step = 0.5
        while not trade.isDone() and waited < deadline:
            self.ib.waitOnUpdate(timeout=step)
            waited += step

        status = trade.orderStatus.status
        filled_qty = float(trade.orderStatus.filled or 0)
        avg_price = float(trade.orderStatus.avgFillPrice or 0)

        # Commission réelle : somme des commissionReport des fills
        commission = 0.0
        for f in trade.fills:
            if f.commissionReport and f.commissionReport.commission:
                commission += abs(float(f.commissionReport.commission))

        if filled_qty <= 0:
            return {
                "status":     status or "unfilled",
                "ticker":     ticker,
                "side":       action.lower(),
                "qty":        0.0,
                "price":      0.0,
                "fees":       0.0,
                "total":      0.0,
                "date":       datetime.now().strftime("%Y-%m-%d %H:%M"),
                "ibkr_status": status,
            }

        gross = avg_price * filled_qty
        total = gross + commission if action == "BUY" else gross - commission
        return {
            "status":      "filled" if status == "Filled" else status,
            "ticker":      ticker,
            "side":        action.lower(),
            "qty":         filled_qty,
            "price":       round(avg_price, 6),
            "fees":        round(commission, 4),
            "total":       round(total, 4),
            "date":        datetime.now().strftime("%Y-%m-%d %H:%M"),
            "ibkr_status": status,
        }

    # ── Réconciliation ────────────────────────────────────────────

    def account_positions(self) -> dict[str, dict]:
        """Positions réelles du compte IBKR {ticker: {qty, avg_cost}}."""
        out = {}
        for p in self.ib.positions(account=self.cfg.get("account") or ""):
            sym = p.contract.symbol
            if p.contract.currency == "EUR":
                sym = f"{sym}.PA"
            out[sym] = {"qty": float(p.position), "avg_cost": float(p.avgCost)}
        return out

    def account_cash(self) -> float:
        """Cash disponible (NetLiquidation - valeur positions) via summary."""
        rows = self.ib.accountSummary(self.cfg.get("account") or "")
        for r in rows:
            if r.tag == "TotalCashValue":
                return float(r.value)
        return 0.0
