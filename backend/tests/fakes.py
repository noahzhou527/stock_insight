"""Deterministic fake upstreams for API tests (no network)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from backend.app.providers.base import (
    Bars, Breadth, DataFetchError, Instrument, Intraday, ProviderBase, Quote, ReportRow, Valuation, finalize_bars,
)

SH = ZoneInfo("Asia/Shanghai")


class Switch:
    """Shared on/off switch: ``online=False`` makes every fake raise a network error."""

    def __init__(self):
        self.online = True
        self.calls: list[str] = []

    def check(self, what: str):
        self.calls.append(what)
        if not self.online:
            raise DataFetchError("network_error", "无法连接（测试断网）")


def daily_rows(start: date, end: date, base: float, listed: date = date(2020, 1, 1)) -> list[dict]:
    rows = []
    for i, day in enumerate(pd.bdate_range(max(start, listed), end)):
        c = base + ((day.date() - date(2020, 1, 1)).days % 37) * 0.5
        rows.append({"trade_date": day.date(), "open": c - 0.3, "high": c + 1, "low": c - 1, "close": c,
                     "volume": 1_000_000 + i, "amount": c * 1_000_000})
    return rows


def intraday_for(day: date, base: float, currency: str) -> Intraday:
    times = pd.date_range(f"{day} 09:30", periods=30, freq="min")
    points = pd.DataFrame({"price": [base + i * 0.1 for i in range(30)], "avg_price": base + 1.0,
                           "volume": 1000.0, "amount": 1000.0 * base}, index=times)
    return Intraday(points, day, base - 1, "fake", currency, None)


class FakeThs(ProviderBase):
    name = "同花顺"

    def __init__(self, switch: Switch, today: date):
        self.switch, self.today = switch, today

    def daily_bars(self, inst, start, end):
        self.switch.check(f"ths.daily:{inst.id}")
        if inst.market != "CN":
            return super().daily_bars(inst, start, end)
        listed = date(2026, 10, 20) if inst.code == "920999" else date(2020, 1, 1)
        return Bars(finalize_bars(daily_rows(start, end, 100.0, listed), start, end), self.name, "CNY")

    def intraday(self, inst):
        self.switch.check(f"ths.intraday:{inst.id}")
        value = intraday_for(self.today, 110.0, "CNY")
        value.name = "中际旭创" if inst.code == "300308" else f"股票{inst.code}"
        return value

    def valuation(self, inst):
        self.switch.check(f"ths.valuation:{inst.id}")
        return Valuation(35.0, 40.0, 30.0, 6e11, 2e10, "同花顺公开 F10", "CNY")

    def financial_reports(self, inst):
        self.switch.check(f"ths.financials:{inst.id}")
        seed = int(inst.code[-2:]) + 1
        rows = []
        for year in (2022, 2023, 2024, 2025):
            p = date(year, 12, 31)
            rows += [ReportRow(p, "annual", "revenue", seed * 1e9 * (year - 2020), "CNY"),
                     ReportRow(p, "annual", "net_profit", seed * 1e8 * (year - 2020), "CNY"),
                     ReportRow(p, "annual", "debt_ratio", 20.0 + seed, None),
                     ReportRow(p, "annual", "capex", seed * 5e7, "CNY")]
        for p, t in ((date(2025, 9, 30), "q3"), (date(2026, 3, 31), "q1"), (date(2026, 6, 30), "h1"), (date(2026, 9, 30), "q3")):
            rows += [ReportRow(p, t, "net_profit", seed * 1e8 * p.month / 12 * (p.year - 2020), "CNY"),
                     ReportRow(p, t, "net_profit_yoy", 12.5, None)]
        return rows


class FakeEastmoney(ProviderBase):
    name = "东方财富"

    def __init__(self, switch: Switch, today: date):
        self.switch, self.today = switch, today

    def quotes(self, insts):
        self.switch.check(f"em.quotes:{len(insts)}")
        now = datetime.combine(self.today, datetime.min.time(), tzinfo=SH) + timedelta(hours=15)
        return [Quote(i, f"股票{i.code}", 10.0 + n, 10.0, float(n % 5 - 2), 1e8 * (n + 1), 1e10 * (n + 1),
                      float(n * 3 - 4), now, self.today, self.name, {"open": 9.9}) for n, i in enumerate(insts)]

    def market_breadth(self, market):
        self.switch.check("em.breadth")
        return Breadth(3000, 1800, 200, 5000, "东方财富全 A 股快照")

    def index_daily(self, secid, start, end):
        self.switch.check(f"em.index_daily:{secid}")
        return Bars(finalize_bars(daily_rows(start, end, 3000.0), start, end), self.name, "CNY")

    def index_intraday(self, secid):
        self.switch.check(f"em.index_intraday:{secid}")
        return intraday_for(self.today, 3100.0, "CNY")

    def index_constituents(self, secid):
        return {"up": 1000, "down": 600, "flat": 50}


class FakeYahoo(ProviderBase):
    name = "Yahoo"

    def __init__(self, switch: Switch, today: date):
        self.switch, self.today = switch, today

    def daily_bars(self, inst, start, end):
        self.switch.check(f"yahoo.daily:{inst.id}")
        base = 70000.0 if inst.market == "KR" else 200.0
        rows = daily_rows(start, end, base)
        for row in rows:
            row["amount"] = None
        return Bars(finalize_bars(rows, start, end), self.name, inst.currency, "Fake Corp")

    def intraday(self, inst):
        self.switch.check(f"yahoo.intraday:{inst.id}")
        return intraday_for(self.today - timedelta(days=1), 70500.0 if inst.market == "KR" else 210.0, inst.currency)

    def valuation(self, inst):
        self.switch.check(f"yahoo.valuation:{inst.id}")
        return Valuation(None, None, None, 3e14 if inst.market == "KR" else 3e12, None, self.name, inst.currency)

    def financial_reports(self, inst):
        self.switch.check(f"yahoo.financials:{inst.id}")
        return [ReportRow(date(2025, 12, 31), "annual", "revenue", 3e14, inst.currency),
                ReportRow(date(2025, 12, 31), "annual", "eps_basic", 5000.0, inst.currency),
                ReportRow(date(2026, 9, 30), "quarterly", "net_profit", 1e13, inst.currency)]

    def market_breadth(self, market):
        self.switch.check("yahoo.breadth")
        return Breadth(2500, 2000, 100, 4600, "Yahoo 可筛选的美国上市普通股")

    def krw_usd_rate(self):
        self.switch.check("yahoo.fx")
        return 1 / 1400
