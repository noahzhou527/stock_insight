"""Stooq provider (美股日线回退). 默认关闭.

2026-11-11 起 ``/q/d/l/`` 返回 JS 工作量证明式的人机校验页而不是 CSV；我们不绕过校验。
HttpClient 识别到校验页时抛 ``provider_blocked``。若 Stooq 恢复直接下载，可通过
``STOCK_INSIGHT_STOOQ_ENABLED=1`` 重新启用。
"""
from __future__ import annotations

from datetime import date
from io import StringIO

import pandas as pd

from .base import Bars, DataFetchError, Instrument, NotSupported, ProviderBase, finalize_bars
from .http import HttpClient

URL = "https://stooq.com/q/d/l/"
NAME = "Stooq"


def stooq_symbol(inst: Instrument) -> str:
    return f"{inst.symbol.replace('-', '.').lower()}.us"


def parse_csv(text: str) -> list[dict]:
    frame = pd.read_csv(StringIO(text))
    if frame.empty or "Date" not in frame.columns:
        raise DataFetchError("fallback_data_unavailable", "Stooq 没有该代码在所选区间的数据。")
    frame.columns = [str(c).lower() for c in frame.columns]
    frame = frame.rename(columns={"date": "trade_date"})
    frame["amount"] = None
    return frame[["trade_date", "open", "high", "low", "close", "volume", "amount"]].to_dict("records")


class StooqProvider(ProviderBase):
    name = NAME

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient(NAME)

    def daily_bars(self, inst: Instrument, start: date, end: date) -> Bars:
        if inst.market != "US":
            raise NotSupported(NAME, "日线", inst)
        response = self.http.get(URL, params={"s": stooq_symbol(inst), "d1": f"{start:%Y%m%d}", "d2": f"{end:%Y%m%d}", "i": "d"})
        return Bars(finalize_bars(parse_csv(response.text), start, end), NAME, "USD")
