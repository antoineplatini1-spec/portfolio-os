"""Indicateurs de tendance : RSI, EMA, MACD, ADX, Stochastic RSI."""

import pandas as pd
import numpy as np


def add_rsi(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    df = df.copy()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(length).mean()
    loss = (-delta.clip(upper=0)).rolling(length).mean()
    rs = gain / loss.replace(0, np.inf)
    df["RSI"] = 100 - 100 / (1 + rs)
    return df


def add_ema(df: pd.DataFrame, periods: list[int] = [20, 50, 200]) -> pd.DataFrame:
    df = df.copy()
    for p in periods:
        df[f"EMA{p}"] = df["Close"].ewm(span=p, adjust=False).mean()
    return df


def add_macd(
    df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    df = df.copy()
    ema_fast = df["Close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["Close"].ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    df["MACD"]        = macd
    df["MACD_signal"] = macd_signal
    df["MACD_hist"]   = macd - macd_signal
    return df


def add_adx(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    df   = df.copy()
    high = df["High"]
    low  = df["Low"]
    close = df["Close"]

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    up   = high.diff()
    down = -low.diff()
    dm_plus  = up.where((up > down) & (up > 0), 0.0)
    dm_minus = down.where((down > up) & (down > 0), 0.0)

    alpha = 1 / length
    atr  = tr.ewm(alpha=alpha, adjust=False).mean()
    dmp  = dm_plus.ewm(alpha=alpha, adjust=False).mean()
    dmn  = dm_minus.ewm(alpha=alpha, adjust=False).mean()

    di_plus  = 100 * dmp / atr.replace(0, np.nan)
    di_minus = 100 * dmn / atr.replace(0, np.nan)
    dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)

    df["ADX"] = dx.ewm(alpha=alpha, adjust=False).mean()
    df["DMP"] = di_plus
    df["DMN"] = di_minus
    return df


def add_stoch_rsi(
    df: pd.DataFrame, length: int = 14, rsi_length: int = 14, k: int = 3, d: int = 3
) -> pd.DataFrame:
    df    = df.copy()
    delta = df["Close"].diff()
    gain  = delta.clip(lower=0).rolling(rsi_length).mean()
    loss  = (-delta.clip(upper=0)).rolling(rsi_length).mean()
    rsi   = 100 - 100 / (1 + gain / loss.replace(0, np.inf))

    rsi_min = rsi.rolling(length).min()
    rsi_max = rsi.rolling(length).max()
    stoch   = (rsi - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan)

    df["StochRSI_K"] = stoch.rolling(k).mean() * 100
    df["StochRSI_D"] = df["StochRSI_K"].rolling(d).mean()
    return df


def add_all_trend(df: pd.DataFrame) -> pd.DataFrame:
    df = add_rsi(df)
    df = add_ema(df)
    df = add_macd(df)
    df = add_adx(df)
    df = add_stoch_rsi(df)
    return df
