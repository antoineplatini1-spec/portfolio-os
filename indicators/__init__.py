"""Calcule tous les indicateurs sur un DataFrame OHLCV."""

import pandas as pd

from .trend import add_all_trend
from .volatility import add_all_volatility
from .volume import add_all_volume


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute tous les indicateurs techniques au DataFrame."""
    if df.empty or len(df) < 30:
        return df
    df = add_all_trend(df)
    df = add_all_volatility(df)
    df = add_all_volume(df)
    return df
