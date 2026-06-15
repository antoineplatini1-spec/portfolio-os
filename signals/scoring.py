"""Score composite 0-100 - architecture Bull/Bear inspirée du Claude Portfolio.

Pour chaque signal haussier, un contre-argument baissier est évalué.
- bull_score  : raisons d'acheter
- bear_score  : raisons de NE PAS acheter
- score final : bull_score pénalisé par bear_score
- bear_flags  : liste des alertes baissières (affichées dans le screener)
"""

import pandas as pd

from config import ADX_TREND_THRESHOLD, BUY_SIGNAL_MIN_SCORE, SECTOR_MAP

# Ensemble des tickers pour lesquels le volume n'est pas un signal de conviction
# (ETFs + ETPs macro : liquidité via marché primaire, pas secondaire)
_ETF_TICKERS: set[str] = {
    t for t, s in SECTOR_MAP.items() if s in ("ETF", "Macro")
}


def compute_score(
    df: pd.DataFrame,
    ticker: str | None = None,
    market_regime: dict | None = None,
) -> dict:
    """
    Calcule un score d'achat 0-100 sur la dernière bougie disponible.
    Retourne un dict avec le score total, bull/bear séparés, et les flags baissiers.

    market_regime (optionnel) : dict fourni par get_market_regime()
        spy_above_ema50  : bool
        spy_above_ema200 : bool
        spy_return_20d   : float  (performance SPY sur 20 jours, en %)
    """
    if df.empty or len(df) < 20:
        return {"score": 0, "bull_score": 0, "bear_score": 0,
                "bear_flags": [], "details": {}, "signal": False}

    row     = df.iloc[-1]
    prev    = df.iloc[-2]
    row_5d  = df.iloc[-6]  if len(df) >= 6  else df.iloc[0]
    row_10d = df.iloc[-11] if len(df) >= 11 else df.iloc[0]
    row_20d = df.iloc[-21] if len(df) >= 21 else df.iloc[0]

    vol_avg_20 = (
        df["Volume"].iloc[-21:-1].mean()
        if "Volume" in df.columns and len(df) >= 21
        else None
    )

    close    = row.get("Close")
    details  = {}
    bull_pts = 0
    bear_pts = 0
    bear_flags: list[str] = []

    # ══════════════════════════════════════════════════════════════
    # SIGNAUX HAUSSIERS (bull case)
    # ══════════════════════════════════════════════════════════════

    # ── RSI ───────────────────────────────────────────────────────
    rsi = row.get("RSI")
    if pd.notna(rsi):
        if rsi < 30:
            pts = 15
        elif rsi < 40:
            pts = 10
        elif rsi < 55:          # zone momentum bull (40-55) : légèrement positif
            pts = 4
        elif rsi > 70:
            pts = 0
            bear_pts += 8
            bear_flags.append(f"RSI suracheté ({rsi:.0f})")
        else:                   # 55-70 : neutre
            pts = 0
        details["RSI"] = {"value": round(rsi, 1), "pts": pts}
        bull_pts += pts

    # ── Bollinger ─────────────────────────────────────────────────
    bb_low = row.get("BB_lower")
    bb_up  = row.get("BB_upper")
    if pd.notna(bb_low) and pd.notna(close):
        if close < bb_low:
            pts = 12
        elif pd.notna(bb_up) and close > bb_up:
            pts = 0
            bear_pts += 6
            bear_flags.append(f"Prix au-dessus BB supérieure (surachat)")
        else:
            pts = 0
        details["Bollinger"] = {"value": round(close, 4), "pts": pts}
        bull_pts += pts

    # ── MACD (cross au-dessus/en-dessous de 0 = force différente) ─
    macd          = row.get("MACD")
    macd_sig      = row.get("MACD_signal")
    macd_prev     = prev.get("MACD")
    macd_sig_prev = prev.get("MACD_signal")
    if all(pd.notna(x) for x in [macd, macd_sig, macd_prev, macd_sig_prev]):
        crossed_up   = macd_prev < macd_sig_prev and macd >= macd_sig
        crossed_down = macd_prev > macd_sig_prev and macd <= macd_sig
        if crossed_up:
            pts = 15 if macd > 0 else 8   # cross au-dessus de 0 = signal plus fort
        elif crossed_down:
            pts = -10
        elif macd > macd_sig:
            pts = 5
        else:
            pts = 0
        details["MACD"] = {"value": round(macd, 4), "pts": pts}
        bull_pts += pts

    # ── ADX ───────────────────────────────────────────────────────
    adx = row.get("ADX")
    dmp = row.get("DMP")
    dmn = row.get("DMN")
    if pd.notna(adx):
        if adx > ADX_TREND_THRESHOLD and pd.notna(dmp) and pd.notna(dmn) and dmp > dmn:
            pts = 10
        elif adx < 20:
            pts = -5
        else:
            pts = 0
        details["ADX"] = {"value": round(adx, 1), "pts": pts}
        bull_pts += pts

    # ── Stochastic RSI ────────────────────────────────────────────
    stoch_k = row.get("StochRSI_K")
    if pd.notna(stoch_k):
        if stoch_k < 20:
            pts = 10
        elif stoch_k > 80:
            pts = -8
        else:
            pts = 0
        details["StochRSI"] = {"value": round(stoch_k, 1), "pts": pts}
        bull_pts += pts

    # ── OBV ───────────────────────────────────────────────────────
    obv      = row.get("OBV")
    obv_prev = prev.get("OBV")
    if pd.notna(obv) and pd.notna(obv_prev):
        pts = 8 if obv > obv_prev else -5
        details["OBV"] = {"value": round(obv, 0), "pts": pts}
        bull_pts += pts

    # ── CMF ───────────────────────────────────────────────────────
    cmf = row.get("CMF")
    if pd.notna(cmf):
        if cmf > 0.1:
            pts = 10
        elif cmf > 0:
            pts = 5
        elif cmf < -0.1:
            pts = -8
        else:
            pts = 0
        details["CMF"] = {"value": round(cmf, 3), "pts": pts}
        bull_pts += pts

    # ── EMA50 (position + pente) ──────────────────────────────────
    ema50    = row.get("EMA50")
    ema50_5d = row_5d.get("EMA50")
    if pd.notna(ema50) and pd.notna(close):
        if close > ema50:
            pts = 8
        else:
            pts = -5
        details["EMA50"] = {"value": round(ema50, 4), "pts": pts}
        bull_pts += pts

    # ── VWAP ──────────────────────────────────────────────────────
    vwap = row.get("VWAP")
    if pd.notna(vwap) and pd.notna(close):
        pts = 7 if close > vwap else -3
        details["VWAP"] = {"value": round(vwap, 4), "pts": pts}
        bull_pts += pts

    # ── EMA200 (tendance long terme) ──────────────────────────────
    ema200 = row.get("EMA200")
    if pd.notna(ema200) and pd.notna(close):
        if close < ema200:
            pts = -20
        elif close > ema200 * 1.02:
            pts = 10
        else:                   # 0-2% au-dessus : structure haussière naissante
            pts = 4
        details["EMA200"] = {"value": round(ema200, 4), "pts": pts}
        bull_pts += pts

    # ══════════════════════════════════════════════════════════════
    # CONTRE-ARGUMENTS BAISSIERS (bear case)
    # Chaque flag réduit le score final — inspiré du débat multi-agents
    # ══════════════════════════════════════════════════════════════

    # ── Bear 1 : Pente EMA50 négative ─────────────────────────────
    # Prix au-dessus EMA50 mais EMA50 en train de descendre = piège haussier
    if pd.notna(ema50) and pd.notna(ema50_5d):
        if ema50 < ema50_5d:
            bear_pts += 12
            bear_flags.append(f"EMA50 en baisse (pente négative)")

    # ── Bear 2 : Downtrend structurel (EMA200) ────────────────────
    if pd.notna(ema200) and pd.notna(close):
        if close < ema200:
            bear_pts += 20
            bear_flags.append("Prix sous EMA200 (downtrend structurel)")

    # ── Bear 3 : Momentum 10 jours négatif ───────────────────────
    # Attrape-t-on un couteau qui tombe encore ?
    close_10d = row_10d.get("Close")
    if pd.notna(close) and pd.notna(close_10d) and float(close_10d) > 0:
        mom10 = (float(close) - float(close_10d)) / float(close_10d) * 100
        if mom10 < -5:
            bear_pts += 12
            bear_flags.append(f"Momentum 10j : {mom10:.1f}% (chute forte)")
            pts = -10
        elif mom10 < -2:
            bear_pts += 6
            bear_flags.append(f"Momentum 10j : {mom10:.1f}% (faible)")
            pts = -5
        elif mom10 > 5:
            pts = 8   # rebond confirmé = signal positif
        elif mom10 > 2:
            pts = 3   # tendance haussière modérée (+2% à +5%) = signal positif faible
        else:
            pts = 0
        details["Momentum10j"] = {"value": round(mom10, 1), "pts": pts}
        bull_pts += pts

    # ── Bear 4 : Volume faible = signal sans conviction ───────────
    # Pour les ETFs, le volume secondaire ne reflète pas la conviction réelle
    # (les flux passent par le mécanisme de création/rachat en nature) → pas de pénalité
    is_etf = ticker is not None and ticker.upper() in _ETF_TICKERS
    vol = row.get("Volume")
    if pd.notna(vol) and vol_avg_20 and vol_avg_20 > 0:
        vol_ratio = float(vol) / float(vol_avg_20)
        if vol_ratio > 1.5:
            pts = 8   # volume fort = conviction haussière
        elif vol_ratio < 0.7 and not is_etf:
            pts = -5
            bear_pts += 5
            bear_flags.append(f"Volume faible ({vol_ratio:.1f}× moyenne)")
        else:
            pts = 0
        details["Volume"] = {"value": round(vol_ratio, 2), "pts": pts}
        bull_pts += pts

    # ── Bear 5 : ADX fort avec DMN > DMP = tendance baissière forte
    if pd.notna(adx) and pd.notna(dmp) and pd.notna(dmn):
        if adx > ADX_TREND_THRESHOLD and dmn > dmp:
            bear_pts += 15
            bear_flags.append(f"Tendance baissière forte (ADX={adx:.0f}, DMN>DMP)")

    # ══════════════════════════════════════════════════════════════
    # RÉGIME DE MARCHÉ + FORCE RELATIVE (contexte SPY)
    # Signaux soft : renforcent ou affaiblissent sans bloquer
    # ══════════════════════════════════════════════════════════════
    if market_regime:
        spy_above_ema50  = market_regime.get("spy_above_ema50",  True)
        spy_above_ema200 = market_regime.get("spy_above_ema200", True)
        spy_ret_20d      = market_regime.get("spy_return_20d",   0.0)

        # ── Régime SPY ────────────────────────────────────────────
        if not spy_above_ema200:
            bear_pts += 25
            bear_flags.append("SPY sous EMA200 — marché baissier structurel")
        elif not spy_above_ema50:
            bear_pts += 15
            bear_flags.append("SPY sous EMA50 — marché en correction")
        else:
            bull_pts += 5   # marché en tendance haussière = légère prime

        # ── Force relative vs SPY (20 jours) ─────────────────────
        close_20d = row_20d.get("Close")
        if pd.notna(close_20d) and float(close_20d) > 0 and pd.notna(close):
            stock_ret_20d = (float(close) - float(close_20d)) / float(close_20d) * 100
            rs = stock_ret_20d - spy_ret_20d
            if rs > 5:
                pts = 10
                bull_pts += pts
            elif rs < -5:
                pts = -8
                bear_pts += 8
                bear_flags.append(f"Force relative négative vs SPY ({rs:+.1f}% sur 20j)")
            else:
                pts = 0
            details["RelStrength"] = {"value": round(rs, 1), "pts": pts}

    # ══════════════════════════════════════════════════════════════
    # SCORE FINAL
    # bull pénalisé par la moitié du bear_score (cap relevé à 60 pts)
    # → max pénalité = 30 pts au lieu de 20 (signaux baissiers pèsent plus)
    # ══════════════════════════════════════════════════════════════
    bear_penalty = min(bear_pts, 60) // 2
    final_score  = max(0, min(100, bull_pts - bear_penalty))

    return {
        "score":      final_score,
        "bull_score": max(0, bull_pts),
        "bear_score": bear_pts,
        "bear_flags": bear_flags,
        "details":    details,
        "signal":     final_score >= BUY_SIGNAL_MIN_SCORE,
        "last_close": float(close) if pd.notna(close) else None,
        "atr":        float(row.get("ATR", 0)) if pd.notna(row.get("ATR")) else None,
    }
