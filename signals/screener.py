"""Scan multi-actifs et ranking des opportunités d'achat."""

import pandas as pd

from config import DEFAULT_WATCHLIST
from data.fetcher import fetch_ohlcv
from indicators import compute_all
from portfolio.risk import r_ratio, sl_price, tp_prices
from signals.scoring import compute_score
from utils.fees import break_even_price


def scan_ticker(ticker: str, period: str = "6mo") -> dict:
    """Analyse complète d'un ticker. Retourne un dict résumé."""
    try:
        df = fetch_ohlcv(ticker, period=period)
        if df.empty or len(df) < 30:
            return {"ticker": ticker, "error": "Données insuffisantes", "score": 0}
        df = compute_all(df)
        result = compute_score(df)
        price = result.get("last_close", 0) or 0
        atr = result.get("atr", 0) or 0

        sl = sl_price(price, atr) if atr else price * 0.95
        tps = tp_prices(price, atr) if atr else []
        tp1_price = tps[0]["price"] if tps else price
        be = break_even_price(price, 1, None)
        r = r_ratio(price, tp1_price, sl)

        # Variation sur la période
        first_close = df["Close"].iloc[0]
        perf_pct = (price - first_close) / first_close * 100 if first_close else 0

        return {
            "ticker": ticker,
            "score": result["score"],
            "signal": result["signal"],
            "price": round(price, 4),
            "atr": round(atr, 4),
            "sl": round(sl, 4),
            "tp1": round(tp1_price, 4),
            "break_even": round(be, 4),
            "r_ratio": round(r, 2),
            "perf_pct": round(perf_pct, 2),
            "details": result["details"],
            "error": None,
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
    """
    if tickers is None:
        tickers = DEFAULT_WATCHLIST

    rows = [scan_ticker(t, period) for t in tickers]
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df[df["error"].isna()].copy()
    df = df[df["score"] >= min_score]
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df
