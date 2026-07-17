"""
Suite de tests des fonctions PURES et critiques (déterministes, sans réseau).
Filet de sécurité avant tout refactor : risque, frais, score de décision, attribution,
EDGAR, parseur newsletter. Lancer : `pytest tests/ -q`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from portfolio.risk import (sl_price, tp_prices, compute_qty, r_ratio,
                            max_position_size_pct, hit_stop, newly_hit_tps, next_trailing,
                            live_exposure_cap)
from utils.fees import compute_fees, net_pnl
from signals import decision as D
from signals import attribution as A

ALPACA = {"name": "Alpaca", "flat_fee": 0.0, "pct_fee": 0.0, "min_fee": 0.0}
IBKR   = {"name": "IBKR", "flat_fee": 0.0, "per_share_fee": 0.005, "pct_fee": 0.0,
          "min_fee": 1.0, "max_pct_fee": 0.01}


# ── Risque : SL / TP / sizing ─────────────────────────────────────

def test_sl_atr_mode():
    # entry 100, ATR 2 → 2×ATR = 96, dans le cap −8% (92) → 96
    assert sl_price(100, 2) == pytest.approx(96.0)

def test_sl_capped_at_max_loss():
    # ATR large → le cap −8% doit primer (jamais pire que 92)
    assert sl_price(100, 5) == pytest.approx(92.0)

def test_tp_ladder():
    tps = tp_prices(100, 2)          # +1.5/3/5 × ATR
    assert [round(t["price"], 2) for t in tps] == [103.0, 106.0, 110.0]
    assert [t["sell_pct"] for t in tps] == [0.25, 0.35, 0.40]

def test_r_ratio():
    assert r_ratio(100, 110, 96) == pytest.approx(2.5)   # (110-100)/(100-96)

def test_position_size_tiers():
    assert max_position_size_pct(50) == 0.05
    assert max_position_size_pct(80) == 0.08
    assert max_position_size_pct(90) == 0.12

def test_compute_qty_size_cap_binds():
    # 250k, entry 100, sl 96, score 50 → cap taille (5% = 12500) borne à 125 actions
    qty, invested = compute_qty(250_000, 100, 96, 50, ALPACA)
    assert qty == pytest.approx(125.0)
    assert invested == pytest.approx(12_500.0)

def test_compute_qty_null_when_sl_above_entry():
    qty, invested = compute_qty(250_000, 100, 100, 50, ALPACA)
    assert qty == 0.0


# ── Décisions de sortie (partagées live ↔ backtest) ──────────────

def test_hit_stop():
    assert hit_stop(95, 96) is True      # low sous le stop
    assert hit_stop(97, 96) is False     # low au-dessus
    assert hit_stop(95, 0) is False      # pas de stop

def test_newly_hit_tps():
    # high 106, paliers [103,106,110], aucun encore touché → TP1 et TP2
    assert newly_hit_tps(106, [103, 106, 110], [False, False, False]) == [0, 1]
    # TP1 déjà touché → seul TP2 est nouveau
    assert newly_hit_tps(106, [103, 106, 110], [True, False, False]) == [1]
    assert newly_hit_tps(101, [103, 106, 110], [False, False, False]) == []

def test_next_trailing_never_descends():
    # prix monte → trailing monte ; ATR entrée 2, mult 2 → prix-4
    assert next_trailing(110, 2, 100, 100) == pytest.approx(106.0)
    # prix baisse mais trailing ne redescend pas
    assert next_trailing(104, 2, 100, 106) == pytest.approx(106.0)


# ── Rampe go-live adaptative (prove-to-scale) ─────────────────────

def test_live_ramp_starts_low():
    assert live_exposure_cap(0, 0.0, 0.25, 0.15, -0.05, 0.95) == pytest.approx(0.25)

def test_live_ramp_grows_when_healthy():
    assert live_exposure_cap(2, 0.0, 0.25, 0.15, -0.05, 0.95) == pytest.approx(0.55)

def test_live_ramp_capped():
    assert live_exposure_cap(10, 0.0, 0.25, 0.15, -0.05, 0.95) == pytest.approx(0.95)

def test_live_ramp_derisks_on_drawdown():
    # drawdown pire que -5% → retour au plancher malgré le temps écoulé
    assert live_exposure_cap(6, -0.06, 0.25, 0.15, -0.05, 0.95) == pytest.approx(0.25)


# ── Frais ─────────────────────────────────────────────────────────

def test_fees_alpaca_zero():
    assert compute_fees(200, 15, ALPACA) == 0.0

def test_fees_ibkr_min():
    # 15 actions × 0.005 = 0.075 → min 1$ ; cap 1% de 3000 = 30 → 1$
    assert compute_fees(200, 15, IBKR) == pytest.approx(1.0)

def test_fees_ibkr_cap_beats_min():
    # 1 action à 5$ : min 1$ mais cap 1% de 5$ = 0.05 → le cap prime
    assert compute_fees(5, 1, IBKR) == pytest.approx(0.05)

def test_net_pnl():
    # gain brut 10×5=50, frais alpaca 0 → 50
    assert net_pnl(100, 110, 5, ALPACA) == pytest.approx(50.0)


# ── Score de décision ─────────────────────────────────────────────

WEIGHTS = {"sector": 3, "news": 8, "conviction": 5}

def test_news_feature_bidirectional():
    assert D.news_feature("bullish", 0.8) == pytest.approx(0.8)
    assert D.news_feature("bearish", 0.8) == pytest.approx(-0.8)
    assert D.news_feature("neutral", 0.8) == 0.0

def test_decision_score_combines():
    f = D.Features(momentum=70, sector=2, news=D.news_feature("bullish", 0.8), conviction=1.0)
    total, contrib = D.decision_score(f, WEIGHTS)
    assert contrib["momentum"] == 70
    assert contrib["sector"] == pytest.approx(6.0)     # 3 × 2
    assert contrib["news"] == pytest.approx(6.4)       # 8 × 0.8
    assert contrib["conviction"] == pytest.approx(5.0)
    assert total == pytest.approx(87.4)

def test_decision_bearish_lowers_score():
    up = D.decision_score(D.Features(70, 2, D.news_feature("bullish", 0.8), 1), WEIGHTS)[0]
    dn = D.decision_score(D.Features(70, 2, D.news_feature("bearish", 0.8), 1), WEIGHTS)[0]
    assert dn < up

def test_features_clamp():
    f = D.Features(momentum=70, sector=5, news=3, conviction=2).clamp()
    assert f.sector == 2 and f.news == 1 and f.conviction == 1


# ── Attribution (corrélation) ─────────────────────────────────────

def test_pearson_positive():
    c = A._pearson([1, 2, 3, 4], [2, 4, 6, 8])
    assert c == pytest.approx(1.0)

def test_pearson_none_on_constant():
    assert A._pearson([1, 1, 1], [2, 4, 6]) is None


# ── EDGAR (mapping déterministe) ──────────────────────────────────

def test_edgar_item_labels():
    from signals import edgar
    assert edgar.ITEM_LABELS["2.02"] == "Résultats financiers"
    assert "2.02" in edgar.MATERIAL_ITEMS       # earnings = matériel
    assert "9.01" not in edgar.MATERIAL_ITEMS   # annexes = pas matériel


# ── Parseur newsletter (classification) ───────────────────────────

def _classify(rec):
    from signals.newsletter_agent import NewsletterAgent
    return NewsletterAgent()._classify_recommendation(rec, "")

def test_newsletter_buy():
    assert _classify("achetez l'action pour viser 20 euros") == "BUY"

def test_newsletter_buy_priority_over_stop_clause():
    # une reco d'achat AVEC clause de sortie (stop) reste un BUY, pas un SELL
    assert _classify("achetez, mais en cas d'enfoncement il faudra vendre") == "BUY"

def test_newsletter_sell():
    assert _classify("réduisez la position, vendez") == "SELL"

def test_newsletter_negation_not_buy():
    assert _classify("n'achetez pas cette action") != "BUY"


# ── Ordres bracket natifs (entrée + réconciliation) ───────────────

class _FakeBracketBroker:
    """Broker factice exposant buy_bracket (comme IBKR). stop_live=False simule un STOP
    non confirmé → pas de clé 'bracket' → repli gestion bot."""
    def __init__(self, stop_live=True):
        self.stop_live = stop_live
        self.calls = []

    def _fill(self, ticker, qty, price):
        q = max(1, round(qty))
        return {"status": "filled", "ticker": ticker, "side": "buy", "qty": q,
                "price": price, "fees": 1.0, "total": price * q + 1.0}

    def buy(self, ticker, qty, price):
        self.calls.append(("buy", ticker))
        return self._fill(ticker, qty, price)

    def buy_bracket(self, ticker, qty, price, sl, tps):
        self.calls.append(("bracket", ticker, sl, tps))
        r = self._fill(ticker, qty, price)
        if self.stop_live:
            r["bracket"] = f"br_{ticker}"
        return r

    def sell(self, ticker, qty, price):
        return {"status": "filled", "ticker": ticker, "side": "sell", "qty": qty,
                "price": price, "fees": 1.0, "total": price * qty - 1.0}


def _fresh_pm(tmp_path, broker, native, monkeypatch):
    from portfolio import manager as M
    monkeypatch.setattr(M, "USE_NATIVE_BRACKETS", native)
    pm = M.PortfolioManager(state_file=tmp_path / "state.json")
    pm.broker = broker
    pm.cash = 100_000.0
    return pm


def test_bracket_entry_keeps_full_ladder(tmp_path, monkeypatch):
    br = _FakeBracketBroker(stop_live=True)
    pm = _fresh_pm(tmp_path, br, native=True, monkeypatch=monkeypatch)
    ok, msg, pos = pm.open_position("AAA", 100.0, atr=2.0, score=60, resistance=130.0)
    assert ok, msg
    assert pos.bracket_oca == "br_AAA"          # marqué bracketé
    assert len(pos.tp_levels) >= 2              # LADDER complet conservé (pas réduit à 1 TP)
    assert sum(t.sell_pct for t in pos.tp_levels) == pytest.approx(1.0)
    # les tranches (prix, fraction) ont bien été transmises au bracket natif
    tranches = [c[3] for c in br.calls if c[0] == "bracket"][0]
    assert isinstance(tranches, list) and len(tranches) == len(pos.tp_levels)


def test_alloc_shares_sums_exactly():
    from portfolio.ibkr_broker import IBKRBroker
    for q in (1, 2, 3, 7, 10, 137, 250):
        a = IBKRBroker._alloc_shares(q, [0.25, 0.35, 0.40])
        assert sum(a) == q                       # le stop total couvre 100% de la position
        assert all(x >= 0 for x in a)


def test_book_native_partial_reduces_and_keeps_open(tmp_path, monkeypatch):
    br = _FakeBracketBroker(stop_live=True)
    pm = _fresh_pm(tmp_path, br, native=True, monkeypatch=monkeypatch)
    ok, _, pos = pm.open_position("FFF", 100.0, atr=2.0, score=60, resistance=130.0)
    assert ok
    qty0 = pos.qty_remaining
    cash0 = pm.cash
    sold = max(1.0, qty0 * 0.25)
    ok2 = pm.book_native_partial("FFF", sold, exit_price=115.0, fees=1.0, reason="TP")
    assert ok2
    p = pm.open_positions["FFF"]
    assert not p.is_closed                        # reste ouverte (ladder en cours)
    assert p.qty_remaining == pytest.approx(qty0 - sold)
    assert pm.cash == pytest.approx(cash0 + 115.0 * sold - 1.0)
    assert p.partial_fills[-1].reason == "TP"


def test_bracket_skips_bot_sl_tp(tmp_path, monkeypatch):
    br = _FakeBracketBroker(stop_live=True)
    pm = _fresh_pm(tmp_path, br, native=True, monkeypatch=monkeypatch)
    ok, _, pos = pm.open_position("BBB", 100.0, atr=2.0, score=60)
    assert ok
    # Prix qui plonge SOUS le SL : le bot ne doit PAS clôturer (IBKR gère côté serveur).
    pm.update_prices({"BBB": pos.sl * 0.5})
    assert "BBB" in pm.open_positions
    assert not pm.open_positions["BBB"].is_closed


def test_bracket_fallback_when_stop_not_live(tmp_path, monkeypatch):
    # STOP non confirmé → pas de clé 'bracket' → position gérée par le bot (bracket_oca vide).
    br = _FakeBracketBroker(stop_live=False)
    pm = _fresh_pm(tmp_path, br, native=True, monkeypatch=monkeypatch)
    ok, _, pos = pm.open_position("CCC", 100.0, atr=2.0, score=60)
    assert ok
    assert pos.bracket_oca == ""
    # Le bot reprend : un prix sous le SL déclenche la clôture classique.
    pm.update_prices({"CCC": pos.sl * 0.5})
    assert pm.open_positions.get("CCC") is None or pm.open_positions["CCC"].is_closed


def test_native_disabled_uses_plain_buy(tmp_path, monkeypatch):
    br = _FakeBracketBroker(stop_live=True)
    pm = _fresh_pm(tmp_path, br, native=False, monkeypatch=monkeypatch)
    ok, _, pos = pm.open_position("DDD", 100.0, atr=2.0, score=60, resistance=130.0)
    assert ok
    assert pos.bracket_oca == ""
    assert all(c[0] != "bracket" for c in br.calls)   # jamais de bracket si flag OFF
    assert len(pos.tp_levels) >= 1                     # ladder ATR classique conservé


def test_book_native_exit_records_pnl_and_closes(tmp_path, monkeypatch):
    br = _FakeBracketBroker(stop_live=True)
    pm = _fresh_pm(tmp_path, br, native=True, monkeypatch=monkeypatch)
    ok, _, pos = pm.open_position("EEE", 100.0, atr=2.0, score=60)
    assert ok
    qty = pos.qty_total
    cash_before = pm.cash
    booked = pm.book_native_exit("EEE", exit_price=110.0, fees=1.0, reason="BRACKET")
    assert booked
    assert pm.open_positions.get("EEE") is None       # fermée
    assert pm.cash == pytest.approx(cash_before + 110.0 * qty - 1.0)
    assert pm.history[-1]["close_reason"] == "BRACKET"
    assert pm.history[-1]["pnl"] > 0                   # sortie à +10% → gain net
