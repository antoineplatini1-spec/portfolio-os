"""
Moteur de backtest jour par jour.
Rejoue la stratégie depuis une date de début, sans biais de lookahead.
Les prix d'exécution utilisent l'Open du jour suivant (réaliste).
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from config import (
    INITIAL_CASH, RESERVE_CASH_PCT, WEEKLY_DEPLOY_PCT, RAMP_UP_WEEKS,
    BUY_SIGNAL_MIN_SCORE, MAX_TOTAL_EXPOSURE_PCT, MAX_SECTOR_POSITIONS,
    RESERVE_UNLOCK_SCORE, TP_LEVELS, ATR_SL_MULTIPLIER,
    TRAILING_STOP_AFTER_TP1, BROKER_CONFIG, SECTOR_MAP,
    MAX_POSITION_PCT, MAX_POSITION_OPPORTUNITY_PCT, MAX_POSITION_CONVICTION_PCT,
    OPPORTUNITY_SCORE_THRESHOLD, CONVICTION_SCORE_THRESHOLD, RISK_PER_TRADE_PCT,
    MAX_LOSS_PCT, MIN_R_RATIO,
)
from indicators import compute_all
from signals.scoring import compute_score
from utils.fees import compute_fees, net_pnl


# ── Structures de données ─────────────────────────────────────────

@dataclass
class BtPosition:
    ticker: str
    entry_date: date
    entry_price: float
    qty: float
    sl: float
    tp_prices: list[float]       # [TP1, TP2, TP3]
    tp_sell_pcts: list[float]    # [0.30, 0.30, 0.40]
    tp_hit: list[bool] = field(default_factory=lambda: [False, False, False])
    trailing_stop: bool = False
    trailing_price: float = 0.0
    qty_remaining: float = 0.0
    fees_in: float = 0.0

    def __post_init__(self):
        if self.qty_remaining == 0.0:
            self.qty_remaining = self.qty
        if self.trailing_price == 0.0:
            self.trailing_price = self.entry_price


@dataclass
class BtTrade:
    ticker: str
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    fees: float
    reason: str   # TP1/TP2/TP3/SL/end
    score_at_entry: int


@dataclass
class FixedAllocation:
    ticker: str
    amount: float          # € à investir au total
    alloc_start: date      # début de la période d'achat
    alloc_end: date        # fin de la période d'achat
    mode: str              # "lump" (un seul achat) ou "dca" (réparti hebdo)


@dataclass
class DaySnapshot:
    day: date
    portfolio_value: float
    cash: float
    strategy_value: float  # valeur positions stratégie
    alloc_value: float     # valeur positions allocation fixe
    n_positions: int
    exposure_pct: float
    daily_pnl: float


# ── Moteur principal ──────────────────────────────────────────────

class BacktestEngine:

    def __init__(
        self,
        tickers: list[str],
        start: date,
        end: date,
        initial_cash: float = INITIAL_CASH,
        min_score: int = 45,
        fixed_allocations: list[FixedAllocation] = None,
    ):
        self.tickers = tickers
        self.start = start
        self.end = end
        self.initial_cash = initial_cash
        self.min_score = min_score
        self.fixed_allocations: list[FixedAllocation] = fixed_allocations or []

        # Cash réservé aux allocations fixes (déduit du capital stratégie)
        self.alloc_budget = sum(a.amount for a in self.fixed_allocations)
        self.strategy_cash = initial_cash - self.alloc_budget
        self.alloc_cash = self.alloc_budget       # cash restant pour les achats DCA

        # État courant
        self.cash = self.strategy_cash            # cash disponible pour la stratégie
        self.reserve = self.strategy_cash * RESERVE_CASH_PCT
        self.positions: dict[str, BtPosition] = {}          # positions stratégie
        self.alloc_positions: dict[str, BtPosition] = {}    # positions allocation fixe
        self.trades: list[BtTrade] = []
        self.alloc_trades: list[BtTrade] = []
        self.equity_curve: list[DaySnapshot] = []
        self.log: list[str] = []
        self.signals_per_day: dict[date, int] = {}

        # Calendrier DCA (ticker → liste de dates d'achat)
        self._dca_schedule: dict[str, list[date]] = {}

        # Allocation progressive (stratégie uniquement)
        self.ramp_end = start + timedelta(weeks=RAMP_UP_WEEKS)
        self.weekly_deployed = 0.0
        self.week_start = start

        # Cache des DataFrames historiques (chargé une seule fois)
        self._data: dict[str, pd.DataFrame] = {}
        self._trading_days: list[date] = []

    # ── Chargement des données ─────────────────────────────────────

    def load_data(self, progress_cb=None) -> dict[str, str]:
        """
        Charge les données historiques pour tous les tickers.
        Retourne un dict {ticker: erreur} pour les tickers en échec.
        """
        import yfinance as yf
        errors = {}
        # On charge depuis 8 mois avant start pour avoir assez d'historique
        # pour les indicateurs (EMA200 etc.)
        fetch_start = (pd.Timestamp(self.start) - pd.DateOffset(months=8)).strftime("%Y-%m-%d")
        fetch_end = pd.Timestamp(self.end).strftime("%Y-%m-%d")

        for i, ticker in enumerate(self.tickers):
            if progress_cb:
                progress_cb(i, len(self.tickers), ticker)
            try:
                df = yf.download(
                    ticker, start=fetch_start, end=fetch_end,
                    interval="1d", auto_adjust=True, progress=False,
                )
                if df.empty or len(df) < 30:
                    errors[ticker] = "Données insuffisantes"
                    continue
                df.index = pd.to_datetime(df.index).tz_localize(None)
                df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
                df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                self._data[ticker] = df
            except Exception as e:
                errors[ticker] = str(e)

        # Charger aussi les tickers d'allocation fixe si pas déjà dedans
        alloc_tickers = [a.ticker for a in self.fixed_allocations if a.ticker not in self._data]
        for ticker in alloc_tickers:
            try:
                df = yf.download(
                    ticker, start=fetch_start, end=fetch_end,
                    interval="1d", auto_adjust=True, progress=False,
                )
                if not df.empty:
                    df.index = pd.to_datetime(df.index).tz_localize(None)
                    df.columns = df.columns.get_level_values(0) if isinstance(df.columns, pd.MultiIndex) else df.columns
                    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                    self._data[ticker] = df
            except Exception:
                pass

        # Jours de trading disponibles (union des index)
        all_dates = set()
        for df in self._data.values():
            all_dates.update(df.index.date)

        self._trading_days = sorted(
            d for d in all_dates
            if self.start <= d <= self.end
        )

        # Précalcule le calendrier DCA
        self._build_dca_schedule()
        return errors

    def _build_dca_schedule(self):
        """Calcule les dates d'achat pour chaque allocation DCA (hebdomadaire)."""
        for alloc in self.fixed_allocations:
            if alloc.mode == "lump":
                # Un seul achat le premier jour de trading disponible >= alloc_start
                day = next(
                    (d for d in self._trading_days if d >= alloc.alloc_start),
                    None,
                )
                self._dca_schedule[alloc.ticker] = [day] if day else []
            else:
                # DCA : un achat par semaine sur la période
                days = [
                    d for d in self._trading_days
                    if alloc.alloc_start <= d <= alloc.alloc_end
                ]
                # Garder un jour par semaine (lundi ou premier jour dispo)
                weekly, seen_weeks = [], set()
                for d in days:
                    week = d.isocalendar()[:2]  # (année, semaine)
                    if week not in seen_weeks:
                        weekly.append(d)
                        seen_weeks.add(week)
                self._dca_schedule[alloc.ticker] = weekly

    # ── Boucle principale ──────────────────────────────────────────

    def run(self, progress_cb=None) -> None:
        n = len(self._trading_days)
        for i, day in enumerate(self._trading_days):
            if progress_cb:
                progress_cb(i, n, day)
            self._refresh_weekly_budget(day)
            self._process_fixed_allocations(day)   # Allocations fixes en premier
            self._update_positions(day)             # TP/SL stratégie
            self._open_signals(day)                 # Nouveaux achats stratégie
            self._record_snapshot(day)

    # ── Allocations fixes ─────────────────────────────────────────

    def _process_fixed_allocations(self, day: date):
        """
        Injecte les positions initiales comme de vraies positions stratégie
        avec SL/TP calculés sur l'ATR au jour d'entrée.
        """
        for alloc in self.fixed_allocations:
            schedule = self._dca_schedule.get(alloc.ticker, [])
            if day not in schedule:
                continue
            if alloc.ticker in self.positions:
                continue  # déjà ouverte
            df = self._data.get(alloc.ticker)
            if df is None:
                continue
            row = df[df.index.date == day]
            if row.empty:
                continue

            exec_price = float(row["Open"].iloc[0])
            invest = min(alloc.amount, self.alloc_cash)
            if invest <= 0 or exec_price <= 0:
                continue

            qty = invest / exec_price
            fees = compute_fees(exec_price, qty, BROKER_CONFIG)
            self.alloc_cash -= invest + fees

            # ATR au jour d'entrée (sur l'historique disponible)
            hist = df[df.index.date < day]
            atr = 0.0
            if len(hist) >= 14:
                try:
                    import pandas_ta as ta
                    atr_series = ta.atr(hist["High"], hist["Low"], hist["Close"], length=14)
                    if atr_series is not None and not atr_series.empty:
                        atr = float(atr_series.dropna().iloc[-1])
                except Exception:
                    pass
            # Fallback : 2% du prix si ATR indisponible
            if atr <= 0:
                atr = exec_price * 0.02

            sl = exec_price - ATR_SL_MULTIPLIER * atr
            tp_prices_list = [exec_price + lvl["atr_mult"] * atr for lvl in TP_LEVELS]
            tp_sell_pcts   = [lvl["sell_pct"] for lvl in TP_LEVELS]

            pos = BtPosition(
                ticker=alloc.ticker,
                entry_date=day,
                entry_price=exec_price,
                qty=qty,
                sl=sl,
                tp_prices=tp_prices_list,
                tp_sell_pcts=tp_sell_pcts,
                fees_in=fees,
            )
            self.positions[alloc.ticker] = pos
            self.log.append(
                f"{day} INIT {alloc.ticker} @ {exec_price:.2f} "
                f"qty={qty:.4f} sl={sl:.2f} tp1={tp_prices_list[0]:.2f}"
            )

    # ── Allocation progressive ─────────────────────────────────────

    def _is_ramp_up(self, day: date) -> bool:
        return day < self.ramp_end

    def _refresh_weekly_budget(self, day: date):
        if day >= self.week_start + timedelta(days=7):
            self.weekly_deployed = 0.0
            self.week_start = day

    def _available_cash(self, score: int, day: date) -> float:
        is_gem = score >= RESERVE_UNLOCK_SCORE
        base = self.cash if is_gem else max(0.0, self.cash - self.reserve)
        if self._is_ramp_up(day) and not is_gem:
            budget = self.initial_cash * WEEKLY_DEPLOY_PCT
            remaining = max(0.0, budget - self.weekly_deployed)
            return min(base, remaining)
        return base

    # ── Mise à jour des positions ──────────────────────────────────

    def _update_positions(self, day: date):
        for ticker in list(self.positions.keys()):
            pos = self.positions[ticker]
            df = self._data.get(ticker)
            if df is None:
                continue
            row = df[df.index.date == day]
            if row.empty:
                continue
            high = float(row["High"].iloc[0])
            low  = float(row["Low"].iloc[0])
            close = float(row["Close"].iloc[0])

            self._check_sl(pos, ticker, day, low, close)
            if ticker in self.positions:
                self._check_tp(pos, ticker, day, high)

    def _check_sl(self, pos: BtPosition, ticker: str, day: date, low: float, close: float):
        if pos.trailing_stop:
            sl_level = pos.trailing_price
            reason = "Trail"
        else:
            sl_level = pos.sl
            reason = "SL"
        # Hard stop : perte max absolue (gap down protection)
        hard_stop = pos.entry_price * (1 - MAX_LOSS_PCT)
        effective_sl = max(sl_level, hard_stop) if not pos.trailing_stop else sl_level

        if low <= effective_sl:
            # Gap down : on exécute à l'Open du jour, pas au SL théorique
            df = self._data.get(ticker)
            row = df[df.index.date == day] if df is not None else None
            open_price = float(row["Open"].iloc[0]) if row is not None and not row.empty else close
            # Si gap down (open sous le SL), on subit le gap
            exec_price = min(open_price, effective_sl)
            self._close_position(pos, ticker, day, exec_price, reason)

    def _check_tp(self, pos: BtPosition, ticker: str, day: date, high: float):
        tp1_just_hit = False
        for i, (tp_price, sell_pct, hit) in enumerate(
            zip(pos.tp_prices, pos.tp_sell_pcts, pos.tp_hit)
        ):
            if hit or high < tp_price:
                continue
            qty_sell = pos.qty_remaining * sell_pct
            fees = compute_fees(tp_price, qty_sell, BROKER_CONFIG)
            self.cash += tp_price * qty_sell - fees
            pos.qty_remaining -= qty_sell
            pos.tp_hit[i] = True
            if i == 0:
                tp1_just_hit = True
            reason = f"TP{i+1}"
            self.trades.append(BtTrade(
                ticker=ticker,
                entry_date=pos.entry_date,
                exit_date=day,
                entry_price=pos.entry_price,
                exit_price=tp_price,
                qty=qty_sell,
                pnl=(tp_price - pos.entry_price) * qty_sell - fees - pos.fees_in * sell_pct,
                fees=fees,
                reason=reason,
                score_at_entry=0,
            ))
            self.log.append(f"{day} {reason} {ticker} @ {tp_price:.2f} qty={qty_sell:.4f}")

        if tp1_just_hit and TRAILING_STOP_AFTER_TP1:
            pos.trailing_stop = True
            pos.trailing_price = pos.entry_price

        # Trailing stop update
        if pos.trailing_stop:
            df = self._data[ticker]
            row = df[df.index.date == day]
            if not row.empty:
                close = float(row["Close"].iloc[0])
                atr_approx = pos.entry_price * 0.015
                new_ts = close - atr_approx
                if new_ts > pos.trailing_price:
                    pos.trailing_price = new_ts

        if pos.qty_remaining <= 0.0001:
            del self.positions[ticker]

    def _close_position(self, pos: BtPosition, ticker: str, day: date, price: float, reason: str):
        fees = compute_fees(price, pos.qty_remaining, BROKER_CONFIG)
        pnl = (price - pos.entry_price) * pos.qty_remaining - fees - pos.fees_in
        self.cash += price * pos.qty_remaining - fees
        self.trades.append(BtTrade(
            ticker=ticker,
            entry_date=pos.entry_date,
            exit_date=day,
            entry_price=pos.entry_price,
            exit_price=price,
            qty=pos.qty_remaining,
            pnl=pnl,
            fees=fees,
            reason=reason,
            score_at_entry=0,
        ))
        self.log.append(f"{day} {reason} {ticker} @ {price:.2f}")
        del self.positions[ticker]

    # ── Ouverture de positions ─────────────────────────────────────

    def _open_signals(self, day: date):
        candidates = []
        for ticker in self._data:
            if ticker in self.positions:
                continue
            df = self._data[ticker]
            # Historique jusqu'à la veille incluse (pas de lookahead)
            hist = df[df.index.date < day]
            if len(hist) < 50:
                continue
            hist = compute_all(hist)
            result = compute_score(hist)
            if result["score"] < self.min_score:
                continue
            # Prix d'exécution = Open du jour courant
            today_row = df[df.index.date == day]
            if today_row.empty:
                continue
            exec_price = float(today_row["Open"].iloc[0])
            atr = result.get("atr") or 0
            if atr <= 0:
                continue
            candidates.append((result["score"], ticker, exec_price, atr))

        self.signals_per_day[day] = len(candidates)

        # Trier par score décroissant
        candidates.sort(reverse=True)

        for score, ticker, price, atr in candidates:
            self._try_buy(ticker, price, atr, score, day)

    def _try_buy(self, ticker: str, price: float, atr: float, score: int, day: date):
        # Sizing
        total = self._portfolio_value(day)
        if score >= CONVICTION_SCORE_THRESHOLD:
            max_pct = MAX_POSITION_CONVICTION_PCT
        elif score >= OPPORTUNITY_SCORE_THRESHOLD:
            max_pct = MAX_POSITION_OPPORTUNITY_PCT
        else:
            max_pct = MAX_POSITION_PCT

        sl = price - ATR_SL_MULTIPLIER * atr
        # Hard stop : jamais plus de MAX_LOSS_PCT sous le prix d'entrée
        hard_stop = price * (1 - MAX_LOSS_PCT)
        sl = max(sl, hard_stop)

        risk_per_share = price - sl
        if risk_per_share <= 0:
            return

        # Filtre R-ratio : TP1 doit valoir au moins MIN_R_RATIO × le risque
        tp1 = price + TP_LEVELS[0]["atr_mult"] * atr
        r_ratio = (tp1 - price) / risk_per_share
        if r_ratio < MIN_R_RATIO:
            return

        qty_by_risk = (total * RISK_PER_TRADE_PCT) / risk_per_share
        qty_by_size = (total * max_pct) / price
        qty = min(qty_by_risk, qty_by_size)
        if qty <= 0:
            return

        invest = qty * price
        avail = self._available_cash(score, day)
        if invest > avail:
            qty = avail / price
            invest = qty * price
        if qty <= 0:
            return

        # Exposition totale
        exposure = self._total_invested(day) / total if total else 0
        if exposure + invest / total > MAX_TOTAL_EXPOSURE_PCT:
            return

        # Anti-concentration sectorielle
        sector = SECTOR_MAP.get(ticker, "Other")
        sector_count = sum(
            1 for t in self.positions
            if SECTOR_MAP.get(t, "Other") == sector
        )
        if sector_count >= MAX_SECTOR_POSITIONS:
            return

        fees = compute_fees(price, qty, BROKER_CONFIG)
        total_cost = invest + fees
        if total_cost > self.cash:
            return

        # TP levels
        tp_prices_list = [price + lvl["atr_mult"] * atr for lvl in TP_LEVELS]
        tp_sell_pcts   = [lvl["sell_pct"] for lvl in TP_LEVELS]

        pos = BtPosition(
            ticker=ticker,
            entry_date=day,
            entry_price=price,
            qty=qty,
            sl=sl,
            tp_prices=tp_prices_list,
            tp_sell_pcts=tp_sell_pcts,
            fees_in=fees,
        )
        self.positions[ticker] = pos
        self.cash -= total_cost
        self.weekly_deployed += invest
        self.log.append(f"{day} BUY {ticker} @ {price:.2f} qty={qty:.4f} score={score} sl={sl:.2f}")

    # ── Snapshot journalier ────────────────────────────────────────

    def _portfolio_value(self, day: date) -> float:
        return self.cash + self.alloc_cash + self._strategy_value(day) + self._alloc_value(day)

    def _strategy_value(self, day: date) -> float:
        return self._value_of(self.positions, day)

    def _alloc_value(self, day: date) -> float:
        return self._value_of(self.alloc_positions, day)

    def _value_of(self, positions: dict, day: date) -> float:
        total = 0.0
        for ticker, pos in positions.items():
            df = self._data.get(ticker)
            if df is None:
                total += pos.qty_remaining * pos.entry_price
                continue
            row = df[df.index.date <= day]
            total += pos.qty_remaining * float(row["Close"].iloc[-1]) if not row.empty else pos.qty_remaining * pos.entry_price
        return total

    def _total_invested(self, day: date) -> float:
        return self._strategy_value(day)

    def _record_snapshot(self, day: date):
        invested = self._strategy_value(day)
        pv = self.cash + self.alloc_cash + invested
        prev_pv = self.equity_curve[-1].portfolio_value if self.equity_curve else self.initial_cash
        self.equity_curve.append(DaySnapshot(
            day=day,
            portfolio_value=pv,
            cash=self.cash,
            strategy_value=invested,
            alloc_value=0.0,
            n_positions=len(self.positions),
            exposure_pct=invested / pv if pv else 0,
            daily_pnl=pv - prev_pv,
        ))

    # ── Clôture finale ────────────────────────────────────────────

    def close_all_at_end(self):
        """Clôture toutes les positions ouvertes au dernier jour disponible."""
        last_day = self._trading_days[-1] if self._trading_days else self.end

        for ticker in list(self.positions.keys()):
            pos = self.positions[ticker]
            df = self._data.get(ticker)
            price = float(df["Close"].iloc[-1]) if df is not None and not df.empty else pos.entry_price
            self._close_position(pos, ticker, last_day, price, "end")

    # ── Statistiques ──────────────────────────────────────────────

    def stats(self) -> dict:
        if not self.equity_curve:
            return {}

        equity = pd.DataFrame([s.__dict__ for s in self.equity_curve])
        final_value = float(self.equity_curve[-1].portfolio_value)

        # ── Vérité de terrain : final_value - initial_cash ───────────
        total_pnl     = final_value - self.initial_cash
        total_pnl_pct = total_pnl / self.initial_cash * 100

        strat_pnl = sum(t.pnl for t in self.trades)
        alloc_pnl = 0.0   # plus de poche séparée

        # ── Stats trades stratégie ────────────────────────────────────
        if self.trades:
            df = pd.DataFrame([t.__dict__ for t in self.trades])
            wins   = df[df["pnl"] > 0]
            losses = df[df["pnl"] <= 0]
            win_rate     = len(wins) / len(df) * 100
            avg_win      = float(wins["pnl"].mean())  if len(wins)   else 0.0
            avg_loss     = float(losses["pnl"].mean()) if len(losses) else 0.0
            pf_num = wins["pnl"].sum()
            pf_den = losses["pnl"].sum()
            profit_factor = abs(pf_num / pf_den) if pf_den != 0 else float("inf")
            total_fees    = float(df["fees"].sum())
            best_trade    = df.loc[df["pnl"].idxmax()].to_dict()
            worst_trade   = df.loc[df["pnl"].idxmin()].to_dict()
            n_trades      = len(df)
        else:
            win_rate = avg_win = avg_loss = total_fees = 0.0
            profit_factor = 0.0
            best_trade = worst_trade = {}
            n_trades = 0

        # ── Drawdown sur portefeuille total ───────────────────────────
        eq = equity["portfolio_value"]
        roll_max = eq.cummax()
        dd = (eq - roll_max) / roll_max * 100
        max_dd = float(dd.min())

        # ── Sharpe (rendements journaliers du portefeuille total) ─────
        prev = equity["portfolio_value"].shift(1).fillna(self.initial_cash)
        daily_ret = equity["daily_pnl"] / prev
        sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0.0

        return {
            # ── Portefeuille total (cohérent) ─────────────────────────
            "final_value":     final_value,
            "total_pnl":       total_pnl,        # final - initial
            "total_pnl_pct":   total_pnl_pct,
            # ── Décomposition ─────────────────────────────────────────
            "strategy_pnl":    strat_pnl,
            "alloc_pnl":       alloc_pnl,
            # ── Métriques stratégie ───────────────────────────────────
            "total_trades":    n_trades,
            "win_rate":        win_rate,
            "avg_win":         avg_win,
            "avg_loss":        avg_loss,
            "profit_factor":   profit_factor,
            "total_fees":      total_fees,
            "best_trade":      best_trade,
            "worst_trade":     worst_trade,
            # ── Risque ───────────────────────────────────────────────
            "max_drawdown_pct": max_dd,
            "sharpe":           sharpe,
        }
