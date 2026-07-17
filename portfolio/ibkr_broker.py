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

        # Le compte a un preset qui force TIF=DAY. On l'envoie EXPLICITEMENT pour éviter
        # l'Error 10349 : sinon l'ordre passe transitoirement "Cancelled" (le temps que IBKR
        # ajuste le TIF) puis se re-soumet et REMPLIT → le broker lisait le "Cancelled",
        # croyait l'ordre échoué, ne l'enregistrait pas → position fantôme sur IBKR + cash
        # local jamais décrémenté → surlevier. MOO garde son tif=OPG.
        if self.order_type != "MOO":
            order.tif = "DAY"

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

        # Filet anti-transient : si l'ordre ressort "Cancelled" SANS fill (ex. Error 10349
        # résiduelle), on laisse une re-soumission éventuelle se remplir avant de conclure.
        if (trade.orderStatus.status in ("Cancelled", "ApiCancelled")
                and float(trade.orderStatus.filled or 0) == 0):
            self.ib.sleep(2.0)

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

    # ── Ordre bracket natif (SL/TP intraday, gérés par IBKR) ──────

    def buy_bracket(self, ticker: str, qty: float, price: float,
                    sl: float, tp: float) -> dict:
        """
        Ordre BRACKET natif : entrée MKT + STOP protecteur (SL) + LIMIT (TP), en groupe OCA
        (l'un annule l'autre). IBKR déclenche les sorties INTRADAY sur ses serveurs → le
        portefeuille reste protégé même quand le bot ne tourne pas. Entrée tif=DAY (fix
        10349) ; SL/TP en GTC. Retourne le dict du fill d'ENTRÉE (format buy) + le groupe
        OCA ; les ordres SL/TP restent OUVERTS sur IBKR après retour.
        """
        from ib_async import MarketOrder, Order

        qty_int = max(1, round(qty))
        contract = self._stock_contract(ticker)
        oca = f"br_{ticker}_{int(datetime.now().timestamp())}"

        parent = MarketOrder("BUY", qty_int)
        parent.tif = "DAY"
        parent.transmit = False
        parent.orderId = self.ib.client.getReqId()
        stop = Order(action="SELL", orderType="STP", totalQuantity=qty_int,
                     auxPrice=round(sl, 2), parentId=parent.orderId, tif="GTC",
                     ocaGroup=oca, ocaType=1, transmit=False)
        take = Order(action="SELL", orderType="LMT", totalQuantity=qty_int,
                     lmtPrice=round(tp, 2), parentId=parent.orderId, tif="GTC",
                     ocaGroup=oca, ocaType=1, transmit=True)
        if self.cfg.get("account"):
            parent.account = stop.account = take.account = self.cfg["account"]

        trade = self.ib.placeOrder(contract, parent)
        stop_trade = self.ib.placeOrder(contract, stop)
        take_trade = self.ib.placeOrder(contract, take)

        deadline, waited, step = self.fill_timeout, 0.0, 0.5
        while not trade.isDone() and waited < deadline:
            self.ib.waitOnUpdate(timeout=step)
            waited += step
        if (trade.orderStatus.status in ("Cancelled", "ApiCancelled")
                and float(trade.orderStatus.filled or 0) == 0):
            self.ib.sleep(2.0)

        status = trade.orderStatus.status
        filled_qty = float(trade.orderStatus.filled or 0)
        avg_price = float(trade.orderStatus.avgFillPrice or 0)
        commission = sum(
            abs(float(f.commissionReport.commission))
            for f in trade.fills if f.commissionReport and f.commissionReport.commission
        )
        if filled_qty <= 0:
            return {"status": status or "unfilled", "ticker": ticker, "side": "buy",
                    "qty": 0.0, "price": 0.0, "fees": 0.0, "total": 0.0,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "ibkr_status": status}

        # SÉCURITÉ : ne se déclare "bracketé" QUE si le STOP protecteur est confirmé vivant côté
        # IBKR. Sinon (rejet du child, précaution, etc.) on renvoie le fill SANS clé "bracket" →
        # le bot reprend la gestion SL/TP lui-même : jamais de position nue sans protection.
        LIVE = ("PreSubmitted", "Submitted", "PendingSubmit")
        s_wait = 0.0
        while stop_trade.orderStatus.status not in LIVE and not stop_trade.isDone() and s_wait < 5.0:
            self.ib.waitOnUpdate(timeout=step)
            s_wait += step
        stop_live = stop_trade.orderStatus.status in LIVE

        gross = avg_price * filled_qty
        out = {"status": "filled" if status == "Filled" else status, "ticker": ticker,
               "side": "buy", "qty": filled_qty, "price": round(avg_price, 6),
               "fees": round(commission, 4), "total": round(gross + commission, 4),
               "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "ibkr_status": status}
        if stop_live:
            out["bracket"] = oca
        else:
            # Stop non confirmé → on ANNULE les enfants restants (SL/TP) pour ne pas laisser un
            # ordre serveur orphelin en conflit avec la gestion SL/TP reprise par le bot.
            for t in (stop_trade, take_trade):
                try:
                    if not t.isDone():
                        self.ib.cancelOrder(t.order)
                except Exception:
                    pass
        return out

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

    def recent_exit_fill(self, ticker: str) -> dict | None:
        """
        Prix moyen + frais de la/les VENTE(S) du jour pour ce symbole, agrégés sur les
        exécutions IBKR. Sert à enregistrer au ledger la sortie d'un bracket NATIF qui s'est
        déclenché côté serveur (SL ou TP). None si aucune vente trouvée aujourd'hui.
        """
        sym = ticker[:-3] if ticker.endswith(".PA") else ticker
        tot_qty = tot_val = tot_fee = 0.0
        for f in self.ib.fills():
            try:
                if f.contract.symbol != sym:
                    continue
                if f.execution.side != "SLD":            # BOT = achat, SLD = vente
                    continue
                q = float(f.execution.shares)
                p = float(f.execution.avgPrice or f.execution.price or 0)
                if q <= 0 or p <= 0:
                    continue
                tot_qty += q
                tot_val += q * p
                if f.commissionReport and f.commissionReport.commission:
                    tot_fee += abs(float(f.commissionReport.commission))
            except Exception:
                continue
        if tot_qty <= 0:
            return None
        return {"qty": tot_qty, "price": tot_val / tot_qty, "fees": round(tot_fee, 4)}
