"""Technical indicators (ported from analysis.py; formulas unchanged).

All functions take a close-price Series ordered by date. Callers compute on the
warm-up-inclusive history and trim to the display range afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

MA_CHOICES = (5, 10, 20, 30, 50, 60, 120)
BBI_PERIODS = (3, 6, 12, 24)
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BOLL_PERIOD, BOLL_STD = 20, 2


def ma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(window=period).mean()


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def bbi(close: pd.Series, periods: tuple[int, ...] = BBI_PERIODS) -> pd.Series:
    return pd.concat([ma(close, p) for p in periods], axis=1).mean(axis=1, skipna=False)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + gain / loss))


def macd(close: pd.Series, fast: int = MACD_FAST, slow: int = MACD_SLOW, signal: int = MACD_SIGNAL) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    signal_line = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": line, "signal": signal_line, "hist": line - signal_line})


def bollinger(close: pd.Series, period: int = BOLL_PERIOD, std_dev: float = BOLL_STD) -> pd.DataFrame:
    middle = ma(close, period)
    std = close.rolling(window=period).std()
    return pd.DataFrame({"upper": middle + std * std_dev, "middle": middle, "lower": middle - std * std_dev})


def annualized_volatility(close: pd.Series) -> float | None:
    value = close.pct_change().std() * (252 ** 0.5) * 100
    return float(value) if pd.notna(value) else None


@dataclass(frozen=True)
class IndicatorParams:
    ma: tuple[int, ...] = (5, 10, 20)
    bbi: bool = False
    boll: bool = False
    rsi: int = 14
    macd: bool = True

    @property
    def required_sessions(self) -> int:
        """Sessions needed before the display start (ported from indicator_warmup_start)."""
        needed = [35, self.rsi + 1, *self.ma]
        if self.bbi:
            needed.append(max(BBI_PERIODS))
        if self.boll:
            needed.append(BOLL_PERIOD)
        return max(needed)


def warmup_start(display_start: date, params: IndicatorParams) -> date:
    """Business days back from the display start: required sessions + 15 (holiday slack)."""
    return (pd.Timestamp(display_start) - pd.offsets.BDay(params.required_sessions + 15)).date()


def compute(close: pd.Series, params: IndicatorParams) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for period in params.ma:
        out[f"ma{period}"] = ma(close, period)
    if params.bbi:
        out["bbi"] = bbi(close)
    if params.boll:
        bands = bollinger(close)
        out.update({f"boll_{k}": v for k, v in bands.items()})
    if params.rsi:
        out[f"rsi{params.rsi}"] = rsi(close, params.rsi)
    if params.macd:
        lines = macd(close)
        out.update({f"macd_{k}" if k != "macd" else "macd": v for k, v in lines.items()})
    return out
