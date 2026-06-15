"""Scan multi-actifs et ranking des opportunités d'achat."""

import pandas as pd
from concurrent.futures import ThreadPoolExecutor

from config import DEFAULT_WATCHLIST, SECTOR_MAP
from data.fetcher import fetch_ohlcv
from indicators import compute_all
from portfolio.risk import r_ratio, sl_price, tp_prices
from signals.scoring import compute_score
from utils.fees import break_even_price


def get_market_regime() -> dict:
    """
    Retourne le régime de marché basé sur SPY (fetché une seule fois par session).
    Utilisé pour contextualiser le score de chaque ticker dans le screener.
    """
    try:
        df = fetch_ohlcv("SPY", period="1y")
        if df.empty or len(df) < 50:
            return {}
        df = compute_all(df)
        row    = df.iloc[-1]
        close  = float(row["Close"])
        ema50  = row.get("EMA50")
        ema200 = row.get("EMA200")
        close_20d = float(df["Close"].iloc[-21]) if len(df) >= 21 else close
        return {
            "spy_above_ema50":  bool(pd.notna(ema50)  and close > float(ema50)),
            "spy_above_ema200": bool(pd.notna(ema200) and close > float(ema200)),
            "spy_return_20d":   round((close - close_20d) / close_20d * 100, 2),
        }
    except Exception:
        return {}


def scan_ticker(ticker: str, period: str = "6mo", market_regime: dict | None = None) -> dict:
    """Analyse complète d'un ticker. Retourne un dict résumé."""
    try:
        df = fetch_ohlcv(ticker, period=period)
        if df.empty or len(df) < 30:
            return {"ticker": ticker, "error": "Données insuffisantes", "score": 0}
        df = compute_all(df)
        result = compute_score(df, ticker=ticker, market_regime=market_regime)
        price = result.get("last_close", 0) or 0
        atr = result.get("atr", 0) or 0

        # ── Filtres fondamentaux ──────────────────────────────────────
        _sector = SECTOR_MAP.get(ticker, "Other")
        _is_etf = _sector in ("ETF", "Macro")
        _empty = {"ticker": ticker, "score": 0, "bull_score": 0, "bear_score": 0,
                  "bear_flags": [], "signal": False, "price": round(price, 4),
                  "atr": 0, "sl": 0, "tp1": 0, "break_even": 0,
                  "r_ratio": 0, "perf_pct": 0, "details": {}}
        if price < 5:
            return {**_empty, "error": "prix < 5$"}
        if not _is_etf and "Volume" in df.columns and len(df) >= 21:
            vol_20 = df["Volume"].iloc[-21:-1].mean()
            if vol_20 < 500_000:
                return {**_empty, "error": f"volume < 500K ({vol_20/1e6:.1f}M)"}

        sl = sl_price(price, atr) if atr else price * 0.95
        tps = tp_prices(price, atr) if atr else []
        tp1_price = tps[0]["price"] if tps else price
        # R-ratio calculé sur TP3 (cible finale) — avec SL=1.5×ATR et TP3=3×ATR → R=2.0
        tp_final_price = tps[-1]["price"] if tps else tp1_price
        be = break_even_price(price, 1, None)
        r = r_ratio(price, tp_final_price, sl)

        # Variation sur la période
        first_close = df["Close"].iloc[0]
        perf_pct = (price - first_close) / first_close * 100 if first_close else 0

        return {
            "ticker":     ticker,
            "score":      result["score"],
            "bull_score": result.get("bull_score", result["score"]),
            "bear_score": result.get("bear_score", 0),
            "bear_flags": result.get("bear_flags", []),
            "signal":     result["signal"],
            "price":      round(price, 4),
            "atr":        round(atr, 4),
            "sl":         round(sl, 4),
            "tp1":        round(tp1_price, 4),
            "break_even": round(be, 4),
            "r_ratio":    round(r, 2),
            "perf_pct":   round(perf_pct, 2),
            "details":    result["details"],
            "error":      None,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e), "score": 0, "signal": False}


def run_screener(
    tickers: list[str] = None,
    period: str = "6mo",
    min_score: int = 0,
) -> pd.DataFrame:
    """
    Lance le screener sur une liste d'actifs.
    Retourne un DataFrame trié par score décroissant.
    Le régime de marché (SPY) est fetché une seule fois et injecté dans chaque score.
    """
    if tickers is None:
        tickers = DEFAULT_WATCHLIST

    regime = get_market_regime()

    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(lambda t: scan_ticker(t, period, regime), tickers))
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df[df["error"].isna()].copy()
    df = df[df["score"] >= min_score]
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df
