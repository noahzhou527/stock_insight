"""Financial-report derived rows (ported from financial_rankings.py / data_fetcher TTM)."""
from __future__ import annotations

from datetime import date

from ..providers.base import ReportRow

CUMULATIVE_TYPES = ("q1", "h1", "q3")


def _by_period(rows: list[ReportRow], report_types: tuple[str, ...]) -> dict[date, dict[str, float | None]]:
    periods: dict[date, dict[str, float | None]] = {}
    for row in rows:
        if row.report_type in report_types:
            periods.setdefault(row.period_end, {})[row.metric] = row.value
    return periods


def annual_comparison_row(stock: dict, rows: list[ReportRow]) -> dict:
    """Latest annual report: revenue, net profit, net margin (产品表现代理), debt ratio, capex."""
    annual = _by_period(rows, ("annual",))
    result = {**stock, "period_end": None, "revenue": None, "net_profit": None, "net_margin": None,
              "debt_ratio": None, "capex": None, "capex_ratio": None}
    with_income = [p for p, v in annual.items() if v.get("revenue") is not None or v.get("net_profit") is not None]
    if not with_income:
        return result
    latest = max(with_income)
    values = annual[latest]
    revenue, profit = values.get("revenue"), values.get("net_profit")
    capex = values.get("capex")
    if capex is None:  # legacy used the newest annual capex regardless of period
        capex_periods = [p for p, v in annual.items() if v.get("capex") is not None]
        capex = annual[max(capex_periods)]["capex"] if capex_periods else None
    result.update({
        "period_end": latest,
        "revenue": revenue,
        "net_profit": profit,
        "net_margin": profit / revenue * 100 if revenue and profit is not None else None,
        "debt_ratio": values.get("debt_ratio"),
        "capex": capex,
        "capex_ratio": capex / revenue * 100 if revenue and capex is not None else None,
    })
    return result


def latest_quarter_profit(rows: list[ReportRow]) -> dict:
    """Newest non-annual report's net profit and YoY (排行 quarter_profit; A 股为累计口径)."""
    quarters = {p: v for p, v in _by_period(rows, (*CUMULATIVE_TYPES, "quarterly")).items() if v.get("net_profit") is not None}
    if not quarters:
        return {"period_end": None, "net_profit": None, "net_profit_yoy": None}
    latest = max(quarters)
    return {"period_end": latest, "net_profit": quarters[latest]["net_profit"],
            "net_profit_yoy": quarters[latest].get("net_profit_yoy")}


def ttm_net_profit(rows: list[ReportRow]) -> float | None:
    """TTM = 最新年报 − 上年同期累计 + 今年最新累计 (A 股 F10 累计口径)."""
    profit = {(r.period_end, r.report_type): r.value for r in rows if r.metric == "net_profit" and r.value is not None}
    annual = [p for p, t in profit if t == "annual"]
    if not annual:
        return None
    latest = max(annual)
    current = [(p, t) for p, t in profit if t in CUMULATIVE_TYPES and p.year == latest.year + 1]
    if not current:
        return None
    now, report_type = max(current)
    prior = profit.get((now.replace(year=latest.year), report_type))
    if prior is None:
        return None
    return profit[(latest, "annual")] - prior + profit[(now, report_type)]
