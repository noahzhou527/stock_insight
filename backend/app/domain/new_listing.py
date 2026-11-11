"""Readiness checks for newly listed stocks (ported from new_listing.py)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class NewListingState:
    daily_bars: int
    previous_close: float | None
    trend_ready: bool
    rsi_ready: bool
    macd_ready: bool
    volatility_ready: bool

    def as_dict(self) -> dict:
        return asdict(self)


def new_listing_state(close: pd.Series, rsi_period: int) -> NewListingState:
    values = pd.to_numeric(close, errors="coerce").dropna()
    n = len(values)
    return NewListingState(
        daily_bars=n,
        previous_close=float(values.iloc[-2]) if n >= 2 else None,
        trend_ready=n >= 20,
        rsi_ready=n >= rsi_period + 1,
        macd_ready=n >= 26,
        volatility_ready=n >= 2,
    )


def is_new_listing_history(first_bar: date | None, requested_start: date) -> bool:
    """History starting > 5 business days after the requested start means a new listing."""
    if first_bar is None:
        return False
    return pd.Timestamp(first_bar) > pd.Timestamp(requested_start) + pd.offsets.BDay(5)
