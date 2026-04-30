"""Téléchargement et mise en cache des données OHLCV via yfinance."""

import hashlib, os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from config import CACHE_TTL_MINUTES, DEFAULT_INTERVAL, DEFAULT_PERIOD

_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))
CACHE_DIR = _data_dir / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(ticker: str, period: str, interval: str) -> Path:
    key = hashlib.md5(f"{ticker}{period}{interval}".encode()).hexdigest()[:12]
    return CACHE_DIR / f"{ticker.replace('/', '_')}_{key}.parquet"


def _is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < CACHE_TTL_MINUTES * 60


def fetch_ohlcv(
    ticker: str,
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Retourne un DataFrame OHLCV pour le ticker demandé.
    Utilise un cache Parquet pour éviter les appels répétés.
    """
    path = _cache_path(ticker, period, interval)

    if not force_refresh and _is_fresh(path):
        return pd.read_parquet(path)

    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        df.index = df.index.tz_localize(None) if df.index.tzinfo else df.index
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        df.to_parquet(path)
        return df
    except Exception as e:
        if path.exists():
            return pd.read_parquet(path)
        raise RuntimeError(f"Impossible de récupérer {ticker}: {e}") from e


def fetch_info(ticker: str) -> dict:
    """Métadonnées basiques du ticker (nom, devise, secteur)."""
    try:
        info = yf.Ticker(ticker).info
        return {
            "name": info.get("shortName", ticker),
            "currency": info.get("currency", ""),
            "sector": info.get("sector", ""),
            "market_cap": info.get("marketCap", None),
        }
    except Exception:
        return {"name": ticker, "currency": "", "sector": "", "market_cap": None}


def fetch_multiple(
    tickers: list[str],
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
) -> dict[str, pd.DataFrame]:
    """Fetch en batch, retourne un dict ticker → DataFrame."""
    return {t: fetch_ohlcv(t, period, interval) for t in tickers}
