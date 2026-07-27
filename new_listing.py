"""Readiness checks for newly listed stocks with limited daily history."""

import pandas as pd


def get_new_listing_state(history: pd.DataFrame, rsi_period: int) -> dict:
    """Return one shared set of safe UI guards for incomplete price history."""
    raw_close = history["Close"] if "Close" in history else pd.Series(dtype=float)
    close = pd.to_numeric(raw_close, errors="coerce").dropna()
    daily_bars = len(close)
    return {
        "daily_bars": daily_bars,
        "previous_close": float(close.iloc[-2]) if daily_bars >= 2 else None,
        "show_rows_slider": daily_bars > 1,
        "trend_ready": daily_bars >= 20,
        "rsi_ready": daily_bars >= rsi_period + 1,
        "macd_ready": daily_bars >= 26,
        "volatility_ready": daily_bars >= 2,
    }


def pad_single_daily_bar_chart(history: pd.DataFrame, sessions: int = 252) -> pd.DataFrame:
    """Reserve blank future trading slots so a first-day candle stays left-aligned and one-day wide."""
    if len(history) != 1:
        return history

    attrs = history.attrs.copy()
    first_date = pd.Timestamp(history.index[-1]).normalize()
    index = pd.bdate_range(start=first_date, periods=sessions)
    padded = history.reindex(index)
    padded.attrs.update(attrs)
    return padded
