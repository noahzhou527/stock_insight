"""
技术分析指标计算模块
"""

import pandas as pd
import numpy as np


def calculate_ma(df: pd.DataFrame, period: int, column: str = 'Close') -> pd.Series:
    """
    计算简单移动平均线 (SMA)

    Formula: SMA = (P1 + P2 + ... + Pn) / n
    """
    return df[column].rolling(window=period).mean()


def calculate_ema(df: pd.DataFrame, period: int, column: str = 'Close') -> pd.Series:
    """
    计算指数移动平均线 (EMA)

    Formula: EMA_today = (Price_today * k) + (EMA_yesterday * (1-k))
    where k = 2 / (period + 1)
    """
    return df[column].ewm(span=period, adjust=False).mean()


def calculate_rsi(df: pd.DataFrame, period: int = 14, column: str = 'Close') -> pd.Series:
    """
    计算相对强弱指标 (RSI)

    Formula: RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss

    Interpretation:
    - RSI > 70: Overbought condition
    - RSI < 30: Oversold condition
    """
    delta = df[column].diff()

    # 分离上涨和下跌
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # 计算相对强度
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_macd(df: pd.DataFrame,
                   fast: int = 12,
                   slow: int = 26,
                   signal: int = 9,
                   column: str = 'Close') -> pd.DataFrame:
    """
    计算 MACD (Moving Average Convergence Divergence)

    Formula:
    - MACD Line = EMA(12) - EMA(26)
    - Signal Line = EMA(9) of MACD Line
    - Histogram = MACD Line - Signal Line

    Interpretation:
    - MACD > Signal: Bullish signal
    - MACD < Signal: Bearish signal
    """
    df_copy = df.copy()

    # 计算 EMA
    ema_fast = calculate_ema(df_copy, fast, column)
    ema_slow = calculate_ema(df_copy, slow, column)

    # MACD 线
    df_copy['MACD'] = ema_fast - ema_slow

    # Signal 线
    df_copy['Signal'] = df_copy['MACD'].ewm(span=signal, adjust=False).mean()

    # Histogram
    df_copy['Histogram'] = df_copy['MACD'] - df_copy['Signal']

    return df_copy


def calculate_bollinger_bands(df: pd.DataFrame,
                              period: int = 20,
                              std_dev: int = 2,
                              column: str = 'Close') -> pd.DataFrame:
    """
    计算布林带 (Bollinger Bands)

    Formula:
    - Middle Band = SMA(20)
    - Upper Band = SMA(20) + 2 * StdDev
    - Lower Band = SMA(20) - 2 * StdDev
    """
    df_copy = df.copy()
    df_copy['BB_Middle'] = calculate_ma(df_copy, period, column)
    rolling_std = df_copy[column].rolling(window=period).std()
    df_copy['BB_Upper'] = df_copy['BB_Middle'] + (rolling_std * std_dev)
    df_copy['BB_Lower'] = df_copy['BB_Middle'] - (rolling_std * std_dev)

    return df_copy