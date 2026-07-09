"""
Portefeuille Momentum — piloté exclusivement par la newsletter Capital Momentum.

- Poche séparée de 10 000€ (momentum_state.json)
- Positions sur valeurs françaises (tickers .PA)
- TPs et SL extraits de la newsletter ; trailing stop % après TP1
- Pas de screener/scoring : la newsletter fait foi
"""

import json
import os
from datetime import datetime
from pathlib import Path

from config import (
    BROKER_CONFIG,
    MOMENTUM_DEFAULT_SL_PCT,
    MOMENTUM_INITIAL_CASH,
    MOMENTUM_MAX_POSITION_PCT,
    MOMENTUM_TRAIL_PCT,
    SLIPPAGE_PCT,
)
from portfolio.orders import make_broker
from portfolio.position import PartialFill, Position, TPLevel

_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
STATE_FILE = _data_dir / "momentum_state.json"


class MomentumPortfolio:
    """Portefeuille secondaire piloté par la newsletter."""

    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self.broker = make_broker(
            BROKER_CONFIG,
            validation_log=str(_data_dir / "ibkr_validation_momentum.jsonl"),
        )
        self._load()

    # ── Persistence ───────────────────────────────────────────────

    def _load(self):
        if self.state_file.exists():
            with open(self.state_file, encoding="utf-8") as f:
                d = json.load(f)
            self.cash         = d.get("cash", MOMENTUM_INITIAL_CASH)
            self.initial_cash = d.get("initial_cash", MOMENTUM_INITIAL_CASH)
            self.start_date   = d.get("start_date", datetime.now().strftime("%Y-%m-%d"))
            self.positions: dict[str, Position] = {
                k: Position.from_dict(v) for k, v in d.get("positions", {}).items()
            }
            self.history: list[dict] = d.get("history", [])
            self.last_prices: dict[str, float] = d.get("last_prices", {})
        else:
            self.cash         = MOMENTUM_INITIAL_CASH
            self.initial_cash = MOMENTUM_INITIAL_CASH
            self.start_date   = datetime.now().strftime("%Y-%m-%d")
            self.positions    = {}
            self.history      = []
            self.last_prices  = {}
            self._save()

    def _save(self):
        self.state_file.parent.mkdir(exist_ok=True)
        data = {
            "cash":         self.cash,
            "initial_cash": self.initial_cash,
            "start_date":   self.start_date,
            "positions":    {k: v.to_dict() for k, v in self.positions.items()},
            "history":      self.history,
            "last_prices":  self.last_prices,
        }
        tmp = self.state_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(self.state_file)

    def reload(self):
        self._load()

    # ── Métriques ─────────────────────────────────────────────────

    @property
    def open_positions(self) -> dict[str, Position]:
        return {k: v for k, v in self.positions.items() if not v.is_closed}

    @property
    def total_market_value(self) -> float:
        return sum(
            p.qty_remaining * self.last_prices.get(t, p.entry_price)
            for t, p in self.open_positions.items()
        )

    @property
    def total_value(self) -> float:
        return self.cash + self.total_market_value

    @property
    def pnl_unrealized(self) -> float:
        return sum(
            (self.last_prices.get(t, p.entry_price) - p.entry_price) * p.qty_remaining
            for t, p in self.open_positions.items()
        )

    @property
    def pnl_realized(self) -> float:
        closed = sum(h["pnl"] for h in self.history)
        partials = sum(
            (f.price - pos.entry_price) * f.qty
            for pos in self.open_positions.values()
            for f in pos.partial_fills
        )
        return closed + partials

    # ── Actions ───────────────────────────────────────────────────

    def open_position(
        self,
        ticker: str,
        company: str,
        price: float,
        tp_prices: list[float],
        sl: float = 0.0,
    ) -> tuple[bool, str, Position | None]:
        """
        Ouvre une position Momentum.
        - tp_prices : liste de prix cibles absolus extraits de la newsletter
        - sl        : prix de stop-loss (0 → défaut 7% sous entry)
        """
        if ticker in self.open_positions:
            return False, f"{ticker} déjà en portefeuille Momentum", None
        if price <= 0:
            return False, "Prix invalide", None

        invest = self.initial_cash * MOMENTUM_MAX_POSITION_PCT
        if invest > self.cash:
            return False, f"Cash insuffisant ({self.cash:.0f}€ < {invest:.0f}€)", None

        order = self.broker.buy(ticker, invest / price, price)
        qty   = order["qty"] if "qty" in order else invest / (price * (1 + SLIPPAGE_PCT))
        cost  = order["total"]

        if cost > self.cash:
            return False, f"Cash insuffisant après frais ({cost:.0f}€)", None

        # SL par défaut si non fourni
        if sl <= 0:
            sl = price * (1 - MOMENTUM_DEFAULT_SL_PCT)

        # TP levels avec sell_pct uniformes
        n = len(tp_prices)
        if n == 0:
            return False, "Aucun TP fourni", None
        base_pct = 1.0 / n
        tp_levels = [
            TPLevel(price=tp, sell_pct=base_pct)
            for tp in sorted(tp_prices)
        ]

        pos = Position(
            ticker=ticker,
            entry_price=price * (1 + SLIPPAGE_PCT),
            qty_total=qty,
            sl=sl,
            tp_levels=tp_levels,
            entry_score=0,   # newsletter-driven, pas de score algo
        )
        # Stocker le nom de la société dans entry_score field (hack léger)
        # On passe par les metadata : on le loge dans l'historique à la clôture.

        self.positions[ticker] = pos
        self.cash -= cost
        self._save()

        tps_str = " / ".join(f"{tp:.2f}" for tp in tp_prices)
        return True, (
            f"[MOMENTUM] {company} ({ticker}) {qty:.3f}× à {price:.2f}€ "
            f"| SL={sl:.2f} | TPs={tps_str} | investi={invest:.0f}€"
        ), pos

    def update_prices(self, prices: dict[str, float]):
        """Met à jour les prix et déclenche SL/TP."""
        self.last_prices.update(prices)
        for ticker, pos in list(self.open_positions.items()):
            price = prices.get(ticker)
            if price is None:
                continue
            self._check_sl(pos, price)
            if not pos.is_closed:
                self._check_tp(pos, price)
        self._save()

    def _check_sl(self, pos: Position, price: float):
        sl = pos.trailing_stop_price if pos.trailing_stop else pos.sl
        if price <= sl:
            self._close(pos, price, "SL")

    def _check_tp(self, pos: Position, price: float):
        tp1_just_hit = False
        for i, tp in enumerate(pos.tp_levels):
            if not tp.hit and price >= tp.price:
                qty_sell = pos.qty_remaining * tp.sell_pct
                self._partial_sell(pos, qty_sell, price, f"TP{i+1}")
                tp.hit = True
                tp.hit_date = datetime.now().strftime("%Y-%m-%d")
                if i == 0:
                    tp1_just_hit = True

        if tp1_just_hit:
            pos.trailing_stop       = True
            pos.trailing_stop_price = pos.entry_price   # protection capital dès TP1

        # Trailing stop : 5% sous le plus haut
        if pos.trailing_stop and price > pos.trailing_stop_price:
            pos.trailing_stop_price = max(
                pos.trailing_stop_price,
                price * (1 - MOMENTUM_TRAIL_PCT),
            )

        if pos.qty_remaining <= 0:
            pos.status = "closed"

    def _partial_sell(self, pos: Position, qty: float, price: float, reason: str):
        exec_price = price * (1 - SLIPPAGE_PCT)
        proceeds   = exec_price * qty
        self.cash += proceeds
        pos.qty_remaining -= qty
        pos.partial_fills.append(PartialFill(
            date=datetime.now().strftime("%Y-%m-%d"),
            qty=qty, price=exec_price, reason=reason,
        ))
        if pos.qty_remaining <= 0.0001:
            pos.status      = "closed"
            pos.close_price = exec_price
            pos.close_date  = datetime.now().strftime("%Y-%m-%d")
        else:
            pos.status = "partial"

    def _close(self, pos: Position, price: float, reason: str):
        exec_price = price * (1 - SLIPPAGE_PCT)
        proceeds   = exec_price * pos.qty_remaining
        pnl_close  = (exec_price - pos.entry_price) * pos.qty_remaining
        pnl_parts  = sum((f.price - pos.entry_price) * f.qty for f in pos.partial_fills)
        self.cash += proceeds
        pos.qty_remaining  = 0.0
        pos.status         = "closed"
        pos.close_price    = exec_price
        pos.close_date     = datetime.now().strftime("%Y-%m-%d")
        self.history.append({
            "ticker":       pos.ticker,
            "entry_price":  pos.entry_price,
            "close_price":  exec_price,
            "qty":          pos.qty_total,
            "pnl":          round(pnl_close + pnl_parts, 4),
            "close_reason": reason,
            "entry_date":   pos.entry_date,
            "close_date":   pos.close_date,
        })

    def manual_close(self, ticker: str, price: float):
        pos = self.open_positions.get(ticker)
        if pos:
            self._close(pos, price, "manual")
            self._save()
