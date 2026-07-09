"""État central du portefeuille : cash, positions, historique, allocation progressive."""

import json, os
from datetime import datetime, timedelta
from pathlib import Path

from config import (
    ATR_SL_MULTIPLIER,
    BROKER_CONFIG,
    INITIAL_CASH,
    MAX_SECTOR_POSITIONS,
    MAX_TOTAL_EXPOSURE_PCT,
    MIN_TP_NET_PROFIT,
    RAMP_UP_WEEKS,
    RESERVE_CASH_PCT,
    RESERVE_UNLOCK_SCORE,
    SECTOR_MAP,
    TP_LEVELS,
    TRAILING_STOP_AFTER_TP1,
    WEEKLY_DEPLOY_PCT,
)
from portfolio.orders import make_broker
from portfolio.position import PartialFill, Position, TPLevel
from portfolio.risk import can_open_position, compute_qty, sl_price, tp_prices
from utils.fees import compute_fees, net_pnl

_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE = _data_dir / "portfolio_state.json"


class PortfolioManager:
    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self.broker = make_broker(BROKER_CONFIG)
        self._load()

    # ── Persistence ───────────────────────────────────────────────

    def reload(self):
        """Recharge l'état depuis le fichier JSON (utile si modifié par un process externe)."""
        self._load()

    @property
    def file_mtime(self) -> float:
        """Timestamp de dernière modification du fichier d'état."""
        if self.state_file.exists():
            return self.state_file.stat().st_mtime
        return 0.0

    def _load(self):
        if self.state_file.exists():
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.cash = data.get("cash", INITIAL_CASH)
            self.initial_cash = data.get("initial_cash", INITIAL_CASH)
            self.reserve_cash = data.get("reserve_cash", INITIAL_CASH * RESERVE_CASH_PCT)
            self.start_date = data.get("start_date", datetime.now().strftime("%Y-%m-%d"))
            self.positions: dict[str, Position] = {
                k: Position.from_dict(v) for k, v in data.get("positions", {}).items()
            }
            self.history: list[dict] = data.get("history", [])
            self.weekly_deployed: float = data.get("weekly_deployed", 0.0)
            self.week_start: str = data.get("week_start", datetime.now().strftime("%Y-%m-%d"))
            # Derniers prix connus (mis à jour par update_prices)
            self.last_prices: dict[str, float] = data.get("last_prices", {})
        else:
            self.cash = INITIAL_CASH
            self.initial_cash = INITIAL_CASH
            self.reserve_cash = INITIAL_CASH * RESERVE_CASH_PCT
            self.start_date = datetime.now().strftime("%Y-%m-%d")
            self.positions: dict[str, Position] = {}
            self.history: list[dict] = []
            self.weekly_deployed: float = 0.0
            self.week_start: str = datetime.now().strftime("%Y-%m-%d")
            self.last_prices: dict[str, float] = {}
            self._save()

    def _save(self):
        """Sauvegarde atomique : écrit dans .tmp puis renomme (évite la corruption)."""
        self.state_file.parent.mkdir(exist_ok=True)
        data = {
            "cash": self.cash,
            "initial_cash": self.initial_cash,
            "reserve_cash": self.reserve_cash,
            "start_date": self.start_date,
            "weekly_deployed": self.weekly_deployed,
            "week_start": self.week_start,
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
            "history": self.history,
            "last_prices": self.last_prices,
        }
        tmp = self.state_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(self.state_file)

    # ── Métriques globales ────────────────────────────────────────

    @property
    def operational_cash(self) -> float:
        """Cash disponible hors réserve."""
        return max(0.0, self.cash - self.reserve_cash)

    @property
    def total_invested(self) -> float:
        """Valeur des positions au coût d'entrée (basis)."""
        return sum(p.qty_remaining * p.entry_price for p in self.open_positions.values())

    @property
    def total_market_value(self) -> float:
        """Valeur des positions au dernier prix de marché connu."""
        return sum(
            p.qty_remaining * self.last_prices.get(t, p.entry_price)
            for t, p in self.open_positions.items()
        )

    @property
    def total_value(self) -> float:
        """Valeur totale du portefeuille au dernier prix de marché connu.
        Si aucun prix de marché disponible, utilise le coût d'entrée."""
        return self.cash + self.total_market_value

    @property
    def pnl_unrealized(self) -> float:
        """PnL latent sur les positions ouvertes (prix marché - prix entrée)."""
        return sum(
            (self.last_prices.get(t, p.entry_price) - p.entry_price) * p.qty_remaining
            for t, p in self.open_positions.items()
        )

    @property
    def pnl_realized(self) -> float:
        """PnL réalisé total : trades fermés + fills partiels (TP1/TP2) sur positions encore ouvertes.
        Note : f.price est déjà l'exec_price après slippage (stocké par _partial_sell),
        donc on ne réapplique pas SLIPPAGE_PCT ici."""
        # Trades complètement fermés
        closed = sum(h["pnl"] for h in self.history)
        # Fills partiels sur positions encore ouvertes (TP1, TP2 déjà encaissés)
        # f.price = exec_price (après slippage) → PnL = (exec_price - entry_price) * qty
        partials = sum(
            (f.price - pos.entry_price) * f.qty
            for pos in self.open_positions.values()
            for f in pos.partial_fills
        )
        return closed + partials

    @property
    def exposure_pct(self) -> float:
        """Exposition en % de la valeur totale, calculée au prix de marché."""
        if self.total_value == 0:
            return 0.0
        return self.total_market_value / self.total_value

    @property
    def open_positions(self) -> dict[str, Position]:
        return {k: v for k, v in self.positions.items() if not v.is_closed}

    # ── Allocation progressive ─────────────────────────────────────

    def _is_ramp_up_phase(self) -> bool:
        start = datetime.strptime(self.start_date, "%Y-%m-%d")
        return datetime.now() < start + timedelta(weeks=RAMP_UP_WEEKS)

    def _refresh_weekly_budget(self):
        """Remet le compteur hebdomadaire à zéro si nouvelle semaine (ancré sur le lundi)."""
        week_start = datetime.strptime(self.week_start, "%Y-%m-%d")
        if datetime.now() >= week_start + timedelta(days=7):
            self.weekly_deployed = 0.0
            today = datetime.now()
            monday = today - timedelta(days=today.weekday())
            self.week_start = monday.strftime("%Y-%m-%d")

    def available_deploy_cash(self, score: int = 50) -> float:
        """
        Cash effectivement utilisable pour un nouvel achat,
        en tenant compte de la phase de montée en charge et de la réserve.
        """
        self._refresh_weekly_budget()
        is_opportunity = score >= RESERVE_UNLOCK_SCORE
        base_cash = self.cash if is_opportunity else self.operational_cash

        if self._is_ramp_up_phase() and not is_opportunity:
            weekly_budget = self.initial_cash * WEEKLY_DEPLOY_PCT
            remaining_budget = max(0.0, weekly_budget - self.weekly_deployed)
            return min(base_cash, remaining_budget)
        return base_cash

    def sector_position_count(self, ticker: str) -> int:
        sector = SECTOR_MAP.get(ticker, "Other")
        return sum(
            1 for t, p in self.open_positions.items()
            if SECTOR_MAP.get(t, "Other") == sector
        )

    # ── Actions ───────────────────────────────────────────────────

    def open_position(
        self,
        ticker: str,
        current_price: float,
        atr: float,
        score: int = 50,
    ) -> tuple[bool, str, Position | None]:
        """
        Tente d'ouvrir une position.
        Retourne (succès, message, position_ou_None).
        """
        deploy_cash = self.available_deploy_cash(score)
        sl = sl_price(current_price, atr)
        qty, invested = compute_qty(self.total_value, current_price, sl, score, BROKER_CONFIG)

        if qty <= 0:
            return False, "Quantité calculée nulle (ATR ou sizing invalide)", None

        invested = min(invested, deploy_cash)
        qty = min(qty, invested / current_price)

        ok, reason = can_open_position(
            available_cash=deploy_cash,
            total_portfolio=self.total_value,
            current_exposure_pct=self.exposure_pct,
            sector_positions=self.sector_position_count(ticker),
            invested_amount=invested,
            max_total_exposure=MAX_TOTAL_EXPOSURE_PCT,
            max_sector_positions=MAX_SECTOR_POSITIONS,
        )
        if not ok:
            return False, reason, None

        # Vérifier le cash AVANT de passer l'ordre au broker
        estimated_cost = invested + compute_fees(current_price, qty, BROKER_CONFIG)
        if estimated_cost > self.cash:
            return False, f"Cash insuffisant ({self.cash:.2f} < {estimated_cost:.2f})", None

        order = self.broker.buy(ticker, qty, current_price)
        fees = order["fees"]
        total_cost = order["total"]

        levels = tp_prices(current_price, atr)
        tp_level_objs = [
            TPLevel(price=lvl["price"], sell_pct=lvl["sell_pct"])
            for lvl in levels
        ]

        pos = Position(
            ticker=ticker,
            entry_price=current_price,
            qty_total=qty,
            sl=sl,
            tp_levels=tp_level_objs,
            fees_in=fees,
            entry_score=score,
            entry_atr=atr,
        )

        self.positions[ticker] = pos
        self.cash -= total_cost
        self.weekly_deployed += invested
        self._save()
        return True, f"Achat {qty:.4f} {ticker} à {current_price:.4f} (frais: {fees:.2f})", pos

    def update_prices(self, prices: dict[str, float]):
        """
        Passe en revue les positions ouvertes avec les prix actuels.
        Déclenche les paliers TP/SL si atteints.
        Mémorise les derniers prix connus pour les métriques de marché.
        """
        self.last_prices.update(prices)
        for ticker, pos in list(self.open_positions.items()):
            price = prices.get(ticker)
            if price is None:
                continue
            self._check_sl(pos, price)
            if not pos.is_closed:
                self._check_tp_levels(pos, price)
        self._save()

    def _check_sl(self, pos: Position, price: float):
        sl = pos.trailing_stop_price if pos.trailing_stop else pos.sl
        if price <= sl:
            self._close_position(pos, price, "SL")

    def _check_tp_levels(self, pos: Position, price: float):
        tp1_just_hit = False
        for i, tp in enumerate(pos.tp_levels):
            if not tp.hit and price >= tp.price:
                qty_to_sell = pos.qty_remaining * tp.sell_pct
                # Guard frais : vente seulement si PnL net > MIN_TP_NET_PROFIT.
                # Le TP est quand même marqué "hit" pour activer le trailing stop.
                gross_pnl = (price - pos.entry_price) * qty_to_sell
                fee_out   = compute_fees(price, qty_to_sell, BROKER_CONFIG)
                net_profit = gross_pnl - fee_out
                if net_profit >= MIN_TP_NET_PROFIT:
                    self._partial_sell(pos, qty_to_sell, price, f"TP{i+1}")
                # TP reconnu même si vente skippée (trailing stop + état cohérent)
                tp.hit = True
                tp.hit_date = datetime.now().strftime("%Y-%m-%d")
                if i == 0:
                    tp1_just_hit = True

        if tp1_just_hit and TRAILING_STOP_AFTER_TP1:
            pos.trailing_stop = True
            pos.trailing_stop_price = pos.entry_price

        # Mise à jour trailing stop avec l'ATR réel d'entrée.
        # max() impératif : un trailing stop ne doit JAMAIS redescendre, sinon il
        # relâche la protection des gains dès que le prix recule sans casser le stop.
        if pos.trailing_stop and price > pos.trailing_stop_price:
            atr_ref = pos.entry_atr if pos.entry_atr > 0 else (price * 0.02)
            pos.trailing_stop_price = max(
                pos.trailing_stop_price,
                price - ATR_SL_MULTIPLIER * atr_ref,
            )

        if pos.qty_remaining <= 0:
            pos.status = "closed"

    def _partial_sell(self, pos: Position, qty: float, price: float, reason: str):
        order = self.broker.sell(pos.ticker, qty, price)
        exec_price = order["price"]   # prix réel après slippage
        fees       = order["fees"]
        self.cash += order["total"]
        pos.qty_remaining -= qty
        pos.partial_fills.append(
            PartialFill(
                date=datetime.now().strftime("%Y-%m-%d"),
                qty=qty,
                price=exec_price,    # prix d'exécution réel (avec slippage)
                reason=reason,
            )
        )
        if pos.qty_remaining <= 0.0001:
            pos.status = "closed"
            pos.close_price = exec_price
            pos.close_date = datetime.now().strftime("%Y-%m-%d")
        else:
            pos.status = "partial"

    def _close_position(self, pos: Position, price: float, reason: str):
        order = self.broker.sell(pos.ticker, pos.qty_remaining, price)
        exec_price = order["price"]   # prix réel après slippage
        fees       = order["fees"]
        self.cash += order["total"]
        pos.qty_remaining = 0.0
        pos.status = "closed"
        pos.close_price = exec_price
        pos.close_date = datetime.now().strftime("%Y-%m-%d")
        pos.fees_out = fees
        # PnL final : quantité vendue au close (hors fills partiels déjà comptabilisés)
        qty_closed  = pos.qty_total - sum(f.qty for f in pos.partial_fills)
        pnl_close   = net_pnl(pos.entry_price, exec_price, qty_closed, BROKER_CONFIG)
        # PnL des fills partiels : exec_price déjà stocké avec slippage, fees déduits aussi
        fees_partials  = sum(compute_fees(f.price, f.qty, BROKER_CONFIG) for f in pos.partial_fills)
        pnl_partials   = sum(
            (f.price - pos.entry_price) * f.qty for f in pos.partial_fills
        ) - fees_partials
        pnl_total = pnl_close + pnl_partials
        fees_all  = pos.fees_in + fees + fees_partials
        self.history.append({
            "ticker":       pos.ticker,
            "entry_price":  pos.entry_price,
            "close_price":  exec_price,
            "qty":          pos.qty_total,
            "pnl":          round(pnl_total, 4),
            "fees_total":   round(fees_all, 4),
            "close_reason": reason,
            "entry_date":   pos.entry_date,
            "close_date":   pos.close_date,
        })

    def manual_close(self, ticker: str, price: float):
        pos = self.open_positions.get(ticker)
        if pos:
            self._close_position(pos, price, "manual")
            self._save()

    def reset(self, initial_cash: float = INITIAL_CASH):
        """Réinitialise le portefeuille (paper trading)."""
        self.cash = initial_cash
        self.initial_cash = initial_cash
        self.reserve_cash = initial_cash * RESERVE_CASH_PCT
        self.start_date = datetime.now().strftime("%Y-%m-%d")
        self.positions = {}
        self.history = []
        self.weekly_deployed = 0.0
        self.week_start = datetime.now().strftime("%Y-%m-%d")
        self._save()
