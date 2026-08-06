"""Cached latest-quarter financial rankings for the A-share watchlist."""

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from data_fetcher import _financial_amount_to_yuan, fetch_a_share_financial_reports


def _percent(value) -> float | None:
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _financial_row(stock: dict) -> dict:
    try:
        reports = fetch_a_share_financial_reports(stock["ticker"])
        quarters = reports[reports["报告类型"] != "年报"]
        if quarters.empty:
            raise DataFetchError("quarterly_financials_empty", "未提供季度报告")
        latest = quarters.iloc[0]
        return {
            **stock,
            "报告期": latest["报告期"],
            "最新季度净利润": _financial_amount_to_yuan(latest["净利润"]),
            "净利润同比": _percent(latest["净利润同比"]),
        }
    except Exception:
        return {**stock, "报告期": None, "最新季度净利润": None, "净利润同比": None}


def fetch_latest_quarter_net_profit_ranking(stocks: list[dict]) -> pd.DataFrame:
    """Fetch watchlist quarterly results concurrently, reusing F10 disk cache."""
    rows = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(_financial_row, stock) for stock in stocks]
        for future in as_completed(futures):
            rows.append(future.result())
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["最新季度净利润"] = pd.to_numeric(result["最新季度净利润"], errors="coerce")
    result["净利润同比"] = pd.to_numeric(result["净利润同比"], errors="coerce")
    result = result.sort_values("最新季度净利润", ascending=False, na_position="last", kind="mergesort").reset_index(drop=True)
    result.insert(0, "排名", result.index + 1)
    return result
