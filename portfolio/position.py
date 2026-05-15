"""Dataclass représentant une position ouverte avec ses paliers TP/SL."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class TPLevel:
    price: float          # Prix cible
    sell_pct: float       # Fraction de la position à vendre (0–1)
    hit: bool = False     # Palier atteint ?
    hit_date: str = ""    # Date d'exécution


@dataclass
class PartialFill:
    date: str
    qty: float
    price: float
    reason: str           # "TP1", "TP2", "TP3", "SL", "manual"


@dataclass
class Position:
    ticker: str
    entry_price: float
    qty_total: float      # Quantité initiale achetée
    sl: float             # Stop-loss initial
    tp_levels: list[TPLevel]
    entry_date: str = ""
    fees_in: float = 0.0
    status: Literal["open", "partial", "closed"] = "open"
    trailing_stop: bool = False
    trailing_stop_price: float = 0.0  # Niveau courant du trailing stop
    qty_remaining: float = 0.0        # Initialisé dans __post_init__
    partial_fills: list[PartialFill] = field(default_factory=list)
    entry_score: int = 0            # Score signal à l'entrée
    entry_atr: float = 0.0          # ATR réel à l'entrée (pour trailing stop)
    close_price: float = 0.0
    close_date: str = ""
    fees_out: float = 0.0

    def __post_init__(self):
        if self.qty_remaining == 0.0:
            self.qty_remaining = self.qty_total
        if not self.entry_date:
            self.entry_date = datetime.now().strftime("%Y-%m-%d")
        if self.trailing_stop_price == 0.0:
            self.trailing_stop_price = self.entry_price

    @property
    def current_value(self) -> float:
        """Valeur restante au prix d'entrée (estimation)."""
        return self.qty_remaining * self.entry_price

    @property
    def is_closed(self) -> bool:
        return self.status == "closed"

    def next_tp(self) -> TPLevel | None:
        for tp in self.tp_levels:
            if not tp.hit:
                return tp
        return None

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "entry_price": self.entry_price,
            "qty_total": self.qty_total,
            "qty_remaining": self.qty_remaining,
            "sl": self.sl,
            "trailing_stop": self.trailing_stop,
            "trailing_stop_price": self.trailing_stop_price,
            "entry_date": self.entry_date,
            "fees_in": self.fees_in,
            "status": self.status,
            "close_price": self.close_price,
            "close_date": self.close_date,
            "entry_score": self.entry_score,
            "entry_atr":   self.entry_atr,
            "fees_out": self.fees_out,
            "tp_levels": [
                {
                    "price": t.price,
                    "sell_pct": t.sell_pct,
                    "hit": t.hit,
                    "hit_date": t.hit_date,
                }
                for t in self.tp_levels
            ],
            "partial_fills": [
                {
                    "date": f.date,
                    "qty": f.qty,
                    "price": f.price,
                    "reason": f.reason,
                }
                for f in self.partial_fills
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Position":
        tp_levels = [
            TPLevel(
                price=t["price"],
                sell_pct=t["sell_pct"],
                hit=t["hit"],
                hit_date=t.get("hit_date", ""),
            )
            for t in d.get("tp_levels", [])
        ]
        partial_fills = [
            PartialFill(
                date=f["date"],
                qty=f["qty"],
                price=f["price"],
                reason=f["reason"],
            )
            for f in d.get("partial_fills", [])
        ]
        return cls(
            ticker=d["ticker"],
            entry_price=d["entry_price"],
            qty_total=d["qty_total"],
            qty_remaining=d.get("qty_remaining", d["qty_total"]),
            sl=d["sl"],
            tp_levels=tp_levels,
            entry_date=d.get("entry_date", ""),
            fees_in=d.get("fees_in", 0.0),
            status=d.get("status", "open"),
            trailing_stop=d.get("trailing_stop", False),
            trailing_stop_price=d.get("trailing_stop_price", d["entry_price"]),
            partial_fills=partial_fills,
            entry_score=d.get("entry_score", 0),
            entry_atr=d.get("entry_atr", 0.0),
            close_price=d.get("close_price", 0.0),
            close_date=d.get("close_date", ""),
            fees_out=d.get("fees_out", 0.0),
        )
