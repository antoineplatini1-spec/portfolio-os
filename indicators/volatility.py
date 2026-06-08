"""Indicateurs de volatilité : Bollinger Bands, ATR, Keltner Channel."""

import pandas as pd
import numpy as np


def add_bollinger(df: pd.DataFrame, length: int = 20, std: float = 2.0) -> pd.DataFrame:
    df  = df.copy()
    ma  = df["Close"].rolling(length).mean()
    sig = df["Close"].rolling(length).std()
    df["BB_lower"] = ma - std * sig
    df["BB_mid"]   = ma
    df["BB_upper"] = ma + std * sig
    df["BB_width"] = (df["BB_upper"] - df["BB_lower"]) / ma.replace(0, np.nan)
    df["BB_pct"]   = (df["Close"] - df["BB_lower"]) / (df["BB_upper"] - df["BB_lower"]).replace(0, np.nan)
    return df


def add_atr(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    df    = df.copy()
    high  = df["High"]
    low   = df["Low"]
    close = df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(alpha=1/length, adjust=False).mean()
    return df


def add_keltner(df: pd.DataFrame, length: int = 20, scalar: float = 2.0) -> pd.DataFrame:
    df    = df.copy()
    high  = df["High"]
    low   = df["Low"]
    close = df["Close"]
    # ATR (Wilder)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr  = tr.ewm(alpha=1/length, adjust=False).mean()
    basis = close.ewm(span=length, adjust=False).mean()
    df["KC_lower"] = basis - scalar * atr
    df["KC_basis"] = basis
    df["KC_upper"] = basis + scalar * atr
    return df


def add_all_volatility(df: pd.DataFrame) -> pd.DataFrame:
    df = add_bollinger(df)
    df = add_atr(df)
    df = add_keltner(df)
    return df
