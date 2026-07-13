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
                            max_position_size_pct)
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
