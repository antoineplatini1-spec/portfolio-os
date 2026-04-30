"""Score composite 0–100 basé sur les indicateurs techniques."""

import pandas as pd

from config import ADX_TREND_THRESHOLD, BUY_SIGNAL_MIN_SCORE


def compute_score(df: pd.DataFrame) -> dict:
    """
    Calcule un score d'achat 0–100 sur la dernière bougie disponible.
    Retourne un dict avec le score total et le détail des contributions.
    """
    if df.empty or len(df) < 2:
        return {"score": 0, "details": {}, "signal": False}

    row = df.iloc[-1]
    prev = df.iloc[-2]
    details = {}
    score = 0

    # ── RSI ────────────────────────────────────────────────────────
    rsi = row.get("RSI")
    if pd.notna(rsi):
        if rsi < 30:
            pts = 15
        elif rsi < 40:
            pts = 10
        elif rsi > 70:
            pts = -10
        else:
            pts = 0
        details["RSI"] = {"value": round(rsi, 1), "pts": pts}
        score += pts

    # ── Bollinger ──────────────────────────────────────────────────
    bb_low = row.get("BB_lower")
    bb_up = row.get("BB_upper")
    close = row.get("Close")
    if pd.notna(bb_low) and pd.notna(close):
        if close < bb_low:
            pts = 12
        elif pd.notna(bb_up) and close > bb_up:
            pts = -8
        else:
            pts = 0
        details["Bollinger"] = {"value": round(close, 4), "pts": pts}
        score += pts

    # ── MACD ───────────────────────────────────────────────────────
    macd = row.get("MACD")
    macd_sig = row.get("MACD_signal")
    macd_prev = prev.get("MACD")
    macd_sig_prev = prev.get("MACD_signal")
    if all(pd.notna(x) for x in [macd, macd_sig, macd_prev, macd_sig_prev]):
        crossed_up = macd_prev < macd_sig_prev and macd >= macd_sig
        crossed_down = macd_prev > macd_sig_prev and macd <= macd_sig
        if crossed_up:
            pts = 15
        elif crossed_down:
            pts = -10
        elif macd > macd_sig:
            pts = 5
        else:
            pts = 0
        details["MACD"] = {"value": round(macd, 4), "pts": pts}
        score += pts

    # ── ADX (filtre tendance) ──────────────────────────────────────
    adx = row.get("ADX")
    dmp = row.get("DMP")
    dmn = row.get("DMN")
    if pd.notna(adx):
        if adx > ADX_TREND_THRESHOLD and pd.notna(dmp) and pd.notna(dmn) and dmp > dmn:
            pts = 10
        elif adx < 20:
            pts = -5  # marché sans tendance
        else:
            pts = 0
        details["ADX"] = {"value": round(adx, 1), "pts": pts}
        score += pts

    # ── Stochastic RSI ─────────────────────────────────────────────
    stoch_k = row.get("StochRSI_K")
    if pd.notna(stoch_k):
        if stoch_k < 20:
            pts = 10
        elif stoch_k > 80:
            pts = -8
        else:
            pts = 0
        details["StochRSI"] = {"value": round(stoch_k, 1), "pts": pts}
        score += pts

    # ── OBV (tendance volume) ──────────────────────────────────────
    obv = row.get("OBV")
    obv_prev = prev.get("OBV")
    if pd.notna(obv) and pd.notna(obv_prev):
        pts = 8 if obv > obv_prev else -5
        details["OBV"] = {"value": round(obv, 0), "pts": pts}
        score += pts

    # ── CMF ────────────────────────────────────────────────────────
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
        score += pts

    # ── EMA (prix au-dessus EMA50) ─────────────────────────────────
    ema50 = row.get("EMA50")
    if pd.notna(ema50) and pd.notna(close):
        pts = 8 if close > ema50 else -5
        details["EMA50"] = {"value": round(ema50, 4), "pts": pts}
        score += pts

    # ── VWAP ───────────────────────────────────────────────────────
    vwap = row.get("VWAP")
    if pd.notna(vwap) and pd.notna(close):
        pts = 7 if close > vwap else -3
        details["VWAP"] = {"value": round(vwap, 4), "pts": pts}
        score += pts

    score = max(0, min(100, score))
    return {
        "score": score,
        "details": details,
        "signal": score >= BUY_SIGNAL_MIN_SCORE,
        "last_close": float(close) if pd.notna(close) else None,
        "atr": float(row.get("ATR", 0)) if pd.notna(row.get("ATR")) else None,
    }
