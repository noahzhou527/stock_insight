"""Number formatting, kept in step with the frontend's lib/format.ts (ported from formatters.py).

A 股 / 韩股 use 万 / 亿 / 万亿; 美股 uses K / M / B / T; missing values render "—".
"""
from __future__ import annotations

import math


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _compact(value, tiers: tuple[tuple[float, str], ...], suffix: str) -> str:
    number = _number(value)
    if number is None:
        return "—"
    for divisor, unit in tiers:
        if abs(number) >= divisor:
            return f"{number / divisor:.2f}{unit}"
    return f"{number:,.0f}{suffix}"


def format_volume(value, market: str = "CN") -> str:
    if market.upper() == "CN":
        return _compact(value, ((1e8, "亿股"), (1e4, "万股")), "股")
    return _compact(value, ((1e9, "B股"), (1e6, "M股"), (1e3, "K股")), "股")


def format_amount(value, market: str = "CN") -> str:
    market = market.upper()
    if market == "CN":
        return _compact(value, ((1e12, "万亿元"), (1e8, "亿元"), (1e4, "万元")), "元")
    if market == "KR":
        return _compact(value, ((1e12, "万亿韩元"), (1e8, "亿韩元"), (1e4, "万韩元")), "韩元")
    return _compact(value, ((1e12, "T美元"), (1e9, "B美元"), (1e6, "M美元"), (1e3, "K美元")), "美元")
