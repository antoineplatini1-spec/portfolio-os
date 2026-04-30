"""Indicateurs de tendance : RSI, EMA, MACD, ADX, Stochastic RSI."""

import pandas as pd
import pandas_ta as ta


def add_rsi(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    df = df.copy()
    df["RSI"] = ta.rsi(df["Close"], length=length)
    return df


def add_ema(df: pd.DataFrame, periods: list[int] = [20, 50, 200]) -> pd.DataFrame:
    df = df.copy()
    for p in periods:
        df[f"EMA{p}"] = ta.ema(df["Close"], length=p)
    return df


def add_macd(
    df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    df = df.copy()
    macd = ta.macd(df["Close"], fast=fast, slow=slow, signal=signal)
    if macd is not None and not macd.empty:
        df["MACD"] = macd.iloc[:, 0]
        df["MACD_signal"] = macd.iloc[:, 1]
        df["MACD_hist"] = macd.iloc[:, 2]
    return df


def add_adx(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    df = df.copy()
    adx = ta.adx(df["High"], df["Low"], df["Close"], length=length)
    if adx is not None and not adx.empty:
        df["ADX"] = adx.iloc[:, 0]
        df["DMP"] = adx.iloc[:, 1]
        df["DMN"] = adx.iloc[:, 2]
    return df


def add_stoch_rsi(
    df: pd.DataFrame, length: int = 14, rsi_length: int = 14, k: int = 3, d: int = 3
) -> pd.DataFrame:
    df = df.copy()
    stoch = ta.stochrsi(df["Close"], length=length, rsi_length=rsi_length, k=k, d=d)
    if stoch is not None and not stoch.empty:
        df["StochRSI_K"] = stoch.iloc[:, 0]
        df["StochRSI_D"] = stoch.iloc[:, 1]
    return df


def add_all_trend(df: pd.DataFrame) -> pd.DataFrame:
    df = add_rsi(df)
    df = add_ema(df)
    df = add_macd(df)
    df = add_adx(df)
    df = add_stoch_rsi(df)
    return df
