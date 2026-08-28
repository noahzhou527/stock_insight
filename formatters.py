from __future__ import annotations

import math

import pandas as pd


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
    absolute = abs(number)
    for divisor, unit in tiers:
        if absolute >= divisor:
            return f"{number / divisor:.2f}{unit}"
    return f"{number:,.0f}{suffix}"


def format_volume(value, market: str = "CN") -> str:
    """Format a share count using the convention of the selected market."""
    market = market.upper()
    if market == "CN":
        return _compact(value, ((1e8, "亿股"), (1e4, "万股")), "股")
    return _compact(value, ((1e9, "B股"), (1e6, "M股"), (1e3, "K股")), "股")


def format_amount(value, market: str = "CN") -> str:
    """Format a traded amount with a compact, market-appropriate currency unit."""
    market = market.upper()
    if market == "CN":
        return _compact(value, ((1e12, "万亿元"), (1e8, "亿元"), (1e4, "万元")), "元")
    if market == "KR":
        return _compact(value, ((1e12, "万亿韩元"), (1e8, "亿韩元"), (1e4, "万韩元")), "韩元")
    return _compact(value, ((1e12, "T美元"), (1e9, "B美元"), (1e6, "M美元"), (1e3, "K美元")), "美元")


def format_financial_report_table(
    frame: pd.DataFrame,
    market: str,
    currency_multiplier: float = 1.0,
) -> pd.DataFrame:
    """Apply readable currency units to Yahoo financial-statement amounts."""
    if market.upper() == "CN":
        return frame
    result = frame.copy()
    for column in ("营业总收入", "毛利润", "营业利润", "净利润"):
        if column in result:
            result[column] = result[column].map(
                lambda value: format_amount(_number(value) * currency_multiplier, market)
                if _number(value) is not None
                else "—"
            )
    if "基本每股收益" in result:
        result["基本每股收益"] = result["基本每股收益"].map(
            lambda value: "—" if _number(value) is None else f"{float(value) * currency_multiplier:.2f}"
        )
        if market.upper() == "US" and currency_multiplier != 1:
            result = result.rename(columns={"基本每股收益": "基本每股收益（美元）"})
    return result


def chart_unit(metric: str, market: str = "CN") -> tuple[float, str]:
    """Return the scale and label used by a chart axis for a large-value metric."""
    market = market.upper()
    if metric == "volume":
        return (1e4, "万股") if market == "CN" else (1e6, "百万股")
    if metric != "amount":
        raise ValueError(f"Unsupported chart metric: {metric}")
    if market == "CN":
        return 1e8, "亿元"
    if market == "KR":
        return 1e8, "亿韩元"
    return 1e6, "百万美元"


def format_statistics(frame: pd.DataFrame, market: str = "CN") -> pd.DataFrame:
    """Return a localized descriptive-statistics table for the data-details view."""
    summary = frame.describe().drop(index="count", errors="ignore").round(2)
    for column, formatter in (("Volume", format_volume), ("Amount", format_amount)):
        if column in summary:
            summary[column] = [formatter(value, market) for value in summary[column]]
    summary.index = summary.index.map(
        {
            "mean": "平均值",
            "std": "标准差",
            "min": "最小值",
            "25%": "25% 分位数",
            "50%": "50% 分位数（中位数）",
            "75%": "75% 分位数",
            "max": "最大值",
        }
    )
    summary.index.name = "统计项"
    return summary.rename(
        columns={
            "Open": "开盘价",
            "High": "最高价",
            "Low": "最低价",
            "Close": "收盘价",
            "Volume": "成交量",
            "Amount": "成交额",
            "RSI": "RSI（相对强弱指标）",
        }
    )
