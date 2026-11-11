"""Quote header + attribute bar metrics (ported from app.compute_snapshot_metrics).

Fix B1: 区间高/低 use the requested display range; 52 周高/低 always use the last year.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta

import pandas as pd

from .indicators import annualized_volatility
from .new_listing import NewListingState


@dataclass
class SnapshotMetrics:
    price: float | None
    pre_close: float | None
    change: float | None
    change_pct: float | None
    price_from_intraday: bool
    range_high: float | None
    range_low: float | None
    high_52w: float | None
    low_52w: float | None
    avg_volume: float | None
    max_amount: float | None
    max_amount_date: date | None
    volatility: float | None

    def as_dict(self) -> dict:
        return asdict(self)


def _num(value) -> float | None:
    return float(value) if value is not None and pd.notna(value) else None


def compute_snapshot(display: pd.DataFrame, last_year: pd.DataFrame, state: NewListingState,
                     intraday_price: float | None = None, intraday_pre_close: float | None = None) -> SnapshotMetrics:
    """``display``: bars in the requested range. ``last_year``: bars for the trailing 52 weeks."""
    close = pd.to_numeric(display["close"], errors="coerce") if not display.empty else pd.Series(dtype=float)
    price = intraday_price if intraday_price is not None else (_num(close.iloc[-1]) if len(close) else None)
    pre_close = intraday_pre_close if intraday_pre_close and intraday_pre_close > 0 else state.previous_close
    change = price - pre_close if price is not None and pre_close else None
    change_pct = change / pre_close * 100 if change is not None else None

    amount = pd.to_numeric(display["amount"], errors="coerce") if not display.empty else pd.Series(dtype=float)
    has_amount = bool(amount.notna().any())
    return SnapshotMetrics(
        price=price, pre_close=pre_close, change=change, change_pct=change_pct,
        price_from_intraday=intraday_price is not None,
        range_high=_num(display["high"].max()) if not display.empty else None,
        range_low=_num(display["low"].min()) if not display.empty else None,
        high_52w=_num(last_year["high"].max()) if not last_year.empty else None,
        low_52w=_num(last_year["low"].min()) if not last_year.empty else None,
        avg_volume=_num(display["volume"].mean()) if not display.empty else None,
        max_amount=_num(amount.max()) if has_amount else None,
        max_amount_date=amount.idxmax() if has_amount else None,
        volatility=annualized_volatility(close) if state.volatility_ready else None,
    )


def one_year_before(day: date) -> date:
    return day - timedelta(days=365)
