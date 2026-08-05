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

    @staticmethod
    def _alloc_shares(qty_int: int, fracs: list[float]) -> list[int]:
        """
        Répartit qty_int actions (entier) sur des tranches de poids `fracs` (somme≈1). Corrige
        l'arrondi sur la plus grosse tranche pour que la somme == qty_int EXACTEMENT (le stop
        total doit couvrir 100% de la position). Les tranches à 0 action sont laissées à 0
        (l'appelant les ignore) — leur part est absorbée par la tranche corrigée.
        """
        raw = [max(0, int(round(qty_int * f))) for f in fracs]
        diff = qty_int - sum(raw)
        if raw:
            idx = max(range(len(fracs)), key=lambda i: fracs[i])
            raw[idx] = max(0, raw[idx] + diff)
        return raw

    def buy_bracket(self, ticker: str, qty: float, price: float,
                    sl: float, tps) -> dict:
        """
        Ordre BRACKET natif LADDER : entrée MKT + N tranches (TP LMT + STOP STP), une PAIRE OCA
        par tranche, tous les stops au MÊME prix (SL). IBKR déclenche les sorties INTRADAY sur
        ses serveurs → protégé même bot éteint. Chaque paire OCA s'auto-annule (TP rempli →
        son stop tombe ; le prix touche SL → tous les stops partent et tous les TP tombent).

        `tps` : float (1 TP, tout vendu) OU liste de (prix_tp, fraction) sommant ≈ 1.
        Entrée tif=DAY (fix 10349) ; SL/TP en GTC. Retourne le dict du fill d'ENTRÉE + la clé
        "bracket" (id de base) UNIQUEMENT si TOUS les stops sont confirmés vivants côté IBKR.
        """
        from ib_async import MarketOrder, Order

        qty_int = max(1, round(qty))
        contract = self._stock_contract(ticker)
        base = f"br_{ticker}_{int(datetime.now().timestamp())}"

        # Normalise `tps` → tranches [(prix, actions)] sommant à qty_int.
        if isinstance(tps, (int, float)):
            tranches_spec = [(float(tps), 1.0)]
        else:
            tranches_spec = [(float(p), float(f)) for p, f in tps if p and p > 0]
        if not tranches_spec:
            tranches_spec = [(price * 1.10, 1.0)]
        fracs = [f for _, f in tranches_spec]
        tot = sum(fracs) or 1.0
        shares = self._alloc_shares(qty_int, [f / tot for f in fracs])
        tranches = [(prc, sh) for (prc, _), sh in zip(tranches_spec, shares) if sh > 0]
        if not tranches:                                   # sécurité : au moins 1 tranche full
            tranches = [(tranches_spec[0][0], qty_int)]

        parent = MarketOrder("BUY", qty_int)
        parent.tif = "DAY"
        parent.transmit = False
        parent.orderId = self.ib.client.getReqId()
        if self.cfg.get("account"):
            parent.account = self.cfg["account"]

        # Enfants : pour chaque tranche, un STP + un LMT dans une paire OCA dédiée. Seul le TOUT
        # DERNIER ordre transmet (transmit=True) → IBKR active tout le lot d'un coup.
        children = []            # [(kind, order)]
        for i, (tp_prc, sh) in enumerate(tranches):
            oca = f"{base}_{i}"
            stop = Order(action="SELL", orderType="STP", totalQuantity=sh,
                         auxPrice=round(sl, 2), parentId=parent.orderId, tif="GTC",
                         ocaGroup=oca, ocaType=1, transmit=False)
            take = Order(action="SELL", orderType="LMT", totalQuantity=sh,
                         lmtPrice=round(tp_prc, 2), parentId=parent.orderId, tif="GTC",
                         ocaGroup=oca, ocaType=1, transmit=False)
            if self.cfg.get("account"):
                stop.account = take.account = self.cfg["account"]
            children.append(("stop", stop))
            children.append(("take", take))
        children[-1][1].transmit = True                    # dernier ordre → transmet le lot

        trade = self.ib.placeOrder(contract, parent)
        child_trades = [(kind, self.ib.placeOrder(contract, o)) for kind, o in children]

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

        # SÉCURITÉ : ne se déclare "bracketé" QUE si TOUS les STOPS protecteurs sont confirmés
        # vivants côté IBKR (couverture 100% de la position). Sinon on ANNULE tous les enfants et
        # on renvoie le fill SANS clé "bracket" → le bot reprend la gestion : jamais de position nue.
        LIVE = ("PreSubmitted", "Submitted", "PendingSubmit")
        stop_trades = [t for kind, t in child_trades if kind == "stop"]
        s_wait = 0.0
        while (any(t.orderStatus.status not in LIVE and not t.isDone() for t in stop_trades)
               and s_wait < 5.0):
            self.ib.waitOnUpdate(timeout=step)
            s_wait += step
        stops_live = all(t.orderStatus.status in LIVE for t in stop_trades)

        gross = avg_price * filled_qty
        out = {"status": "filled" if status == "Filled" else status, "ticker": ticker,
               "side": "buy", "qty": filled_qty, "price": round(avg_price, 6),
               "fees": round(commission, 4), "total": round(gross + commission, 4),
               "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "ibkr_status": status}
        if stops_live:
            out["bracket"] = base
        else:
            for _, t in child_trades:
                try:
                    if not t.isDone():
                        self.ib.cancelOrder(t.order)
                except Exception:
                    pass
        return out

    def protect_position(self, ticker: str, qty: float, sl: float, tps,
                         cancel_ids: list[int] | None = None) -> dict:
        """
        Pose un bracket de PROTECTION sur une position DÉJÀ détenue (aucun ordre d'entrée) :
        N tranches (STP + LMT) en paires OCA, tous les stops au MÊME prix (SL) — comme
        buy_bracket mais sans parent. Retrofit des positions historiques laissées nues.

        Ordre SÛR : on POSE d'abord, on confirme que TOUS les stops sont vivants, PUIS
        seulement on annule les anciens ordres (`cancel_ids`, ex. un stop manuel) → jamais de
        fenêtre sans protection. Si les stops ne se confirment pas, on annule le nouveau bracket
        et on NE touche PAS aux anciens ordres. Retourne {ok, oca, stops_live}.
        """
        from ib_async import Order

        qty_int = max(1, int(round(qty)))
        contract = self._stock_contract(ticker)
        base = f"rf_{ticker}_{int(datetime.now().timestamp())}"

        if isinstance(tps, (int, float)):
            spec = [(float(tps), 1.0)]
        else:
            spec = [(float(p), float(f)) for p, f in tps if p and p > 0]
        if not spec:
            spec = [(round(sl, 2) * 1.25, 1.0)]
        tot = sum(f for _, f in spec) or 1.0
        shares = self._alloc_shares(qty_int, [f / tot for _, f in spec])
        tranches = [(p, sh) for (p, _), sh in zip(spec, shares) if sh > 0]
        if not tranches:
            tranches = [(spec[0][0], qty_int)]

        children = []
        for i, (tp_prc, sh) in enumerate(tranches):
            oca = f"{base}_{i}"
            stop = Order(action="SELL", orderType="STP", totalQuantity=sh,
                         auxPrice=round(sl, 2), tif="GTC", ocaGroup=oca, ocaType=1, transmit=False)
            take = Order(action="SELL", orderType="LMT", totalQuantity=sh,
                         lmtPrice=round(tp_prc, 2), tif="GTC", ocaGroup=oca, ocaType=1, transmit=False)
            if self.cfg.get("account"):
                stop.account = take.account = self.cfg["account"]
            children.append(("stop", stop))
            children.append(("take", take))
        # SANS ordre parent, chaque ordre DOIT être transmit=True : un `transmit=False` ne serait
        # jamais relâché (rien pour le déclencher) → l'ordre reste retenu, non actif. (C'était le
        # bug du 1er retrofit : seul le dernier partait.)
        for _, o in children:
            o.transmit = True

        child_trades = [(k, self.ib.placeOrder(contract, o)) for k, o in children]

        n_stops = sum(1 for k, _ in children if k == "stop")
        LIVE = ("PreSubmitted", "Submitted", "PendingSubmit")
        waited, step = 0.0, 0.5
        while waited < 8.0:
            self.ib.waitOnUpdate(timeout=step)
            waited += step

        # CONFIRMATION ROBUSTE : ne PAS se fier au trade.orderStatus (montre "PreSubmitted" même
        # pour un ordre retenu). On RE-LIT les ordres RÉELLEMENT ouverts côté IBKR et on compte les
        # STP live de CE bracket (ocaGroup préfixé par `base`) — pas les stops préexistants. Il en
        # faut au moins `n_stops` vraiment actifs pour valider (sinon on n'annule PAS l'ancien stop).
        live_stops = sum(
            1 for t in self.ib.reqAllOpenOrders()
            if t.order.orderType == "STP" and t.orderStatus.status in LIVE
            and (t.order.ocaGroup or "").startswith(base)
        )
        stops_live = live_stops >= n_stops

        if not stops_live:
            for _, t in child_trades:                      # échec → on retire le nouveau bracket
                try:
                    if not t.isDone():
                        self.ib.cancelOrder(t.order)
                except Exception:
                    pass
            return {"ok": False, "oca": None, "stops_live": False, "live_stops": live_stops}

        # Stops confirmés → SEULEMENT MAINTENANT on annule les anciens ordres (stop manuel).
        for oid in (cancel_ids or []):
            for t in self.ib.openTrades():
                if t.order.orderId == oid:
                    try:
                        self.ib.cancelOrder(t.order)
                    except Exception:
                        pass
        return {"ok": True, "oca": base, "stops_live": True}

    def open_orders_by_symbol(self) -> dict[str, list[dict]]:
        """Ordres ouverts groupés par symbole : [{orderId, type, action, qty, price, oca}]."""
        out: dict[str, list[dict]] = {}
        for t in self.ib.reqAllOpenOrders():
            o, c = t.order, t.contract
            px = o.auxPrice if o.orderType == "STP" else o.lmtPrice
            out.setdefault(c.symbol, []).append({
                "orderId": o.orderId, "type": o.orderType, "action": o.action,
                "qty": float(o.totalQuantity), "price": float(px or 0), "oca": o.ocaGroup or ""})
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

    def account_marks(self) -> dict[str, float]:
        """Prix de marché RÉELS des positions détenues {ticker: marketPrice} (valorisation vérité)."""
        out = {}
        for it in self.ib.portfolio(self.cfg.get("account") or ""):
            sym = it.contract.symbol
            if it.contract.currency == "EUR":
                sym = f"{sym}.PA"
            if it.marketPrice and it.marketPrice > 0:
                out[sym] = float(it.marketPrice)
        return out

    def account_cash(self) -> float:
        """Cash disponible (NetLiquidation - valeur positions) via summary."""
        rows = self.ib.accountSummary(self.cfg.get("account") or "")
        for r in rows:
            if r.tag == "TotalCashValue":
                return float(r.value)
        return 0.0

    def account_nlv(self) -> float:
        """NetLiquidation OFFICIELLE d'IBKR — LA valeur du compte (celle de l'app). 0 si absente."""
        rows = self.ib.accountSummary(self.cfg.get("account") or "")
        for r in rows:
            if r.tag == "NetLiquidation":
                return float(r.value)
        return 0.0

    def recent_exit_fill(self, ticker: str, lookback_days: int = 5) -> dict | None:
        """
        Prix moyen + frais des VENTE(S) RÉCENTES (fenêtre `lookback_days`) pour ce symbole,
        agrégés sur les exécutions IBKR. Sert à enregistrer au ledger la sortie d'un bracket
        NATIF déclenché côté serveur (SL ou TP). None si aucune vente trouvée.

        ⚠️ Un bracket se déclenche EN SÉANCE et n'est réconcilié qu'au run SUIVANT (= le
        lendemain) → une fenêtre "jour même" raterait TOUS les fills bracketés (PnL alors
        approximé sur last_price). On interroge donc reqExecutions sur `lookback_days` jours
        (récupère jusqu'à 7 j côté serveur IBKR, survit à un restart Gateway qui vide fills()).
        Repli sur ib.fills() si reqExecutions échoue → jamais pire que l'ancien comportement.
        La qty rebookée vient TOUJOURS de la divergence ledger↔IBKR (pas de ces fills) : au
        pire le PRIX est un léger blend si le symbole a plusieurs A/R dans la fenêtre — borné,
        et le cash se recale de toute façon sur IBKR (seed).
        """
        from datetime import timezone, timedelta
        sym = ticker[:-3] if ticker.endswith(".PA") else ticker
        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date()

        fills = None
        try:
            from ib_async import ExecutionFilter
            since = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y%m%d-%H:%M:%S")
            fills = self.ib.reqExecutions(ExecutionFilter(time=since))
        except Exception:
            fills = None
        if not fills:                                    # repli : fills de session (ancien comportement)
            fills = self.ib.fills()

        tot_qty = tot_val = tot_fee = 0.0
        realized = 0.0
        has_realized = False
        for f in fills:
            try:
                if f.contract.symbol != sym:
                    continue
                if f.execution.side != "SLD":            # BOT = achat, SLD = vente
                    continue
                t = getattr(f.execution, "time", None)
                if t is not None and hasattr(t, "date") and t.date() < cutoff:
                    continue
                q = float(f.execution.shares)
                p = float(f.execution.avgPrice or f.execution.price or 0)
                if q <= 0 or p <= 0:
                    continue
                tot_qty += q
                tot_val += q * p
                if f.commissionReport and f.commissionReport.commission:
                    tot_fee += abs(float(f.commissionReport.commission))
                # PnL RÉALISÉ calculé par IBKR (vérité) — évite la reconstruction entry×exit.
                if f.commissionReport:
                    rp = getattr(f.commissionReport, "realizedPNL", None)
                    if rp is not None and abs(float(rp)) < 1e12:   # 1e18 = sentinel "non renseigné"
                        realized += float(rp)
                        has_realized = True
            except Exception:
                continue
        if tot_qty <= 0:
            return None
        return {"qty": tot_qty, "price": tot_val / tot_qty, "fees": round(tot_fee, 4),
                "realized_pnl": realized if has_realized else None}
