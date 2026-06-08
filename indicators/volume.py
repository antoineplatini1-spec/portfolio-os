"""Indicateurs de volume : OBV, VWAP, CMF, Fibonacci auto."""

import numpy as np
import pandas as pd


def add_obv(df: pd.DataFrame) -> pd.DataFrame:
    df        = df.copy()
    direction = df["Close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    df["OBV"] = (direction * df["Volume"]).cumsum()
    return df


def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """VWAP journalier (recalculé sur toute la série pour données daily)."""
    df       = df.copy()
    typical  = (df["High"] + df["Low"] + df["Close"]) / 3
    cumvol   = df["Volume"].cumsum()
    cumtpvol = (typical * df["Volume"]).cumsum()
    df["VWAP"] = cumtpvol / cumvol
    return df


def add_cmf(df: pd.DataFrame, length: int = 20) -> pd.DataFrame:
    df   = df.copy()
    hl   = (df["High"] - df["Low"]).replace(0, np.nan)
    mfm  = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / hl
    mfv  = mfm.fillna(0) * df["Volume"]
    vol_sum = df["Volume"].rolling(length).sum()
    df["CMF"] = mfv.rolling(length).sum() / vol_sum.replace(0, np.nan)
    return df


def add_fibonacci(df: pd.DataFrame, lookback: int = 60) -> pd.DataFrame:
    df     = df.copy()
    recent = df["Close"].iloc[-lookback:]
    high   = recent.max()
    low    = recent.min()
    diff   = high - low
    for level, pct in [(0, 0.0), (236, 0.236), (382, 0.382), (500, 0.5),
                       (618, 0.618), (786, 0.786), (1000, 1.0)]:
        df[f"FIB_{level}"] = high - diff * pct
    return df


def add_all_volume(df: pd.DataFrame) -> pd.DataFrame:
    df = add_obv(df)
    df = add_vwap(df)
    df = add_cmf(df)
    df = add_fibonacci(df)
    return df
