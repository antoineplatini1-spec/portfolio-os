"""Indicateurs de volatilité : Bollinger Bands, ATR, Keltner Channel."""

import pandas as pd
import pandas_ta as ta


def add_bollinger(df: pd.DataFrame, length: int = 20, std: float = 2.0) -> pd.DataFrame:
    df = df.copy()
    bb = ta.bbands(df["Close"], length=length, std=std)
    if bb is not None and not bb.empty:
        df["BB_lower"] = bb.iloc[:, 0]
        df["BB_mid"] = bb.iloc[:, 1]
        df["BB_upper"] = bb.iloc[:, 2]
        df["BB_width"] = bb.iloc[:, 3]
        df["BB_pct"] = bb.iloc[:, 4]
    return df


def add_atr(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    df = df.copy()
    df["ATR"] = ta.atr(df["High"], df["Low"], df["Close"], length=length)
    return df


def add_keltner(df: pd.DataFrame, length: int = 20, scalar: float = 2.0) -> pd.DataFrame:
    df = df.copy()
    kc = ta.kc(df["High"], df["Low"], df["Close"], length=length, scalar=scalar)
    if kc is not None and not kc.empty:
        df["KC_lower"] = kc.iloc[:, 0]
        df["KC_basis"] = kc.iloc[:, 1]
        df["KC_upper"] = kc.iloc[:, 2]
    return df


def add_all_volatility(df: pd.DataFrame) -> pd.DataFrame:
    df = add_bollinger(df)
    df = add_atr(df)
    df = add_keltner(df)
    return df
