"""东方财富公开接口 provider (A 股): 个股日线、分时、批量快照、全市场涨跌家数.

口径 (verified 2026-11-11, see tests/test_fixtures.py):
- K 线 ``fqt=1`` 为前复权，与同花顺 ``/01/`` 历史收盘价差异 < 0.1%。
- A 股成交量单位是"手"，入库前 ×100 换成"股"；成交额单位为"元"。
- secid：上海 ``1.代码``，深圳与北京 ``0.代码``。
- push2/push2his 在 HTTP/2 下 TLS 握手失败，必须 HTTP/1.1 + Connection: close；
  短时间连续约 20 次请求后会临时拒绝连接（curl 56），依赖 HttpClient 的限速与退避。
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .base import Bars, Breadth, DataFetchError, Instrument, Intraday, NotSupported, ProviderBase, Quote, finalize_bars
from .http import HttpClient

KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
TRENDS_URL = "https://push2.eastmoney.com/api/qt/stock/trends2/get"
ULIST_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
HEADERS = {"Referer": "https://quote.eastmoney.com/"}
NAME = "东方财富"
CHINA_TZ = ZoneInfo("Asia/Shanghai")
LOT = 100  # 1 手 = 100 股
ULIST_BATCH = 43
# f2 价 f3 涨跌幅 f6 额 f12 代码 f14 名称 f18 昨收 f20 总市值 f115 PE(TTM) f124 时间 f297 交易日
# f7 振幅 f8 换手率 f15 高 f16 低 f17 开 (自选可选列, §8)
ULIST_FIELDS = "f12,f14,f2,f18,f3,f6,f20,f115,f124,f297,f7,f8,f15,f16,f17"
BREADTH_GROUPS = ("m:0+t:6,m:0+t:80", "m:1+t:2,m:1+t:23", "m:0+t:81+s:2048")  # 深 / 沪 / 北
BREADTH_PAGE_SIZE = 1000
BREADTH_MINIMUM = 3000


def secid(inst: Instrument) -> str:
    return f"{'1' if inst.suffix == 'SH' else '0'}.{inst.code}"


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _data(payload: dict) -> dict:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DataFetchError("eastmoney_empty", "东方财富未返回数据。", f"rc={payload.get('rc')}")
    return data


def parse_kline(payload: dict, volume_multiplier: float = LOT) -> tuple[list[dict], str | None]:
    """f51 日期 f52 开 f53 收 f54 高 f55 低 f56 量(手) f57 额 f58 振幅."""
    data = _data(payload)
    rows = []
    for raw in data.get("klines") or []:
        v = raw.split(",")
        if len(v) < 7:
            continue
        volume = _number(v[5])
        rows.append({
            "trade_date": v[0], "open": v[1], "close": v[2], "high": v[3], "low": v[4],
            "volume": None if volume is None else volume * volume_multiplier, "amount": v[6] or None,
        })
    return rows, data.get("name")


def parse_trends(payload: dict, volume_multiplier: float = LOT) -> Intraday:
    """f51 时间 f52 开 f53 价 f54 高 f55 低 f56 量(手) f57 额 f58 均价."""
    data = _data(payload)
    rows = []
    for raw in data.get("trends") or []:
        v = raw.split(",")
        if len(v) < 8:
            continue
        price = float(v[2])
        rows.append({
            "time": pd.Timestamp(v[0]), "price": price, "avg_price": float(v[7] or price),
            "volume": float(v[5] or 0) * volume_multiplier, "amount": float(v[6] or 0),
        })
    if not rows:
        raise DataFetchError("eastmoney_intraday_empty", "东方财富未返回分时数据。")
    points = pd.DataFrame(rows).set_index("time").sort_index()[["price", "avg_price", "volume", "amount"]]
    pre_close = _number(data.get("preClose")) or _number(data.get("prePrice"))
    if pre_close is None:
        raise DataFetchError("eastmoney_schema_changed", "东方财富分时缺少昨收价。")
    return Intraday(points, points.index[-1].date(), pre_close, NAME, "CNY", data.get("name"))


def _quote_time(value) -> datetime | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    if number > 10_000_000_000:
        number /= 1000
    return datetime.fromtimestamp(number, tz=CHINA_TZ)


def _trade_date(value) -> date | None:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:]))
    return None


def parse_ulist(payload: dict, by_code: dict[str, Instrument]) -> list[Quote]:
    data = _data(payload)
    rows = data.get("diff") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    quotes = []
    for raw in rows:
        inst = by_code.get(str(raw.get("f12", "")).strip())
        if inst is None:
            continue
        price, pre_close, change_pct = _number(raw.get("f2")), _number(raw.get("f18")), _number(raw.get("f3"))
        if change_pct is None and price is not None and pre_close:
            change_pct = (price / pre_close - 1) * 100
        quotes.append(Quote(
            instrument=inst, name=raw.get("f14") or None, price=price, pre_close=pre_close, change_pct=change_pct,
            amount=_number(raw.get("f6")), market_cap=_number(raw.get("f20")), pe_ttm=_number(raw.get("f115")),
            quote_time=_quote_time(raw.get("f124")), trade_date=_trade_date(raw.get("f297")), source=NAME,
            extra={k: _number(raw.get(f)) for k, f in
                   (("open", "f17"), ("high", "f15"), ("low", "f16"), ("amplitude", "f7"), ("turnover", "f8")) if f in raw},
        ))
    return quotes


def parse_clist_changes(payload: dict) -> tuple[list[float], int]:
    data = _data(payload)
    rows = data.get("diff") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    total = int(data.get("total", 0))
    if total and not rows:
        raise DataFetchError("eastmoney_schema_changed", "东方财富返回了空的涨跌家数分页。")
    return [v for row in rows if (v := _number(row.get("f3"))) is not None], total


class EastmoneyProvider(ProviderBase):
    name = NAME

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient(NAME, force_http11=True, default_headers=HEADERS)

    @staticmethod
    def _check(inst: Instrument, capability: str) -> None:
        if inst.market != "CN":
            raise NotSupported(NAME, capability, inst)

    def _json(self, url: str, params: dict) -> dict:
        response = self.http.get(url, params=params)
        try:
            return response.json()
        except ValueError as error:
            raise DataFetchError("eastmoney_schema_changed", "东方财富返回了无法解析的数据。", error) from error

    def daily_bars(self, inst: Instrument, start: date, end: date) -> Bars:
        self._check(inst, "日线")
        payload = self._json(KLINE_URL, {
            "secid": secid(inst), "klt": "101", "fqt": "1", "beg": f"{start:%Y%m%d}", "end": f"{end:%Y%m%d}",
            "lmt": "100000", "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        })
        if payload.get("data") is None:
            # Unknown secid → data null. Treat as "no rows" rather than a source failure.
            return Bars(finalize_bars([]), NAME, "CNY")
        rows, name = parse_kline(payload)
        return Bars(finalize_bars(rows, start, end), NAME, "CNY", name)

    def intraday(self, inst: Instrument) -> Intraday:
        self._check(inst, "分时")
        return parse_trends(self._json(TRENDS_URL, {
            "secid": secid(inst), "ndays": "1", "iscr": "0", "iscca": "0",
            "fields1": "f1,f2,f3,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f17",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        }))

    def quotes(self, insts: list[Instrument]) -> list[Quote]:
        cn = [inst for inst in insts if inst.market == "CN"]
        if not cn:
            raise NotSupported(NAME, "非 A 股批量快照")
        result = []
        for offset in range(0, len(cn), ULIST_BATCH):
            chunk = cn[offset : offset + ULIST_BATCH]
            payload = self._json(ULIST_URL, {
                "fltt": "2", "invt": "2", "fields": ULIST_FIELDS, "secids": ",".join(secid(i) for i in chunk),
            })
            if payload.get("rc") != 0:
                raise DataFetchError("eastmoney_error", "东方财富批量行情返回错误。", f"rc={payload.get('rc')}")
            result.extend(parse_ulist(payload, {i.code: i for i in chunk}))
        return result

    def market_breadth(self, market: str) -> Breadth:
        if market != "CN":
            raise NotSupported(NAME, f"{market} 涨跌家数")
        changes: list[float] = []
        for fs in BREADTH_GROUPS:
            page = 1
            while True:
                payload = self._json(CLIST_URL, {
                    "pn": page, "pz": BREADTH_PAGE_SIZE, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                    "fid": "f3", "fs": fs, "fields": "f12,f3",
                })
                values, total = parse_clist_changes(payload)
                changes.extend(values)
                if page * BREADTH_PAGE_SIZE >= total:
                    break
                page += 1
        if len(changes) < BREADTH_MINIMUM:
            raise DataFetchError("eastmoney_breadth_incomplete", "东方财富返回的 A 股涨跌数据不完整。", f"rows={len(changes)}")
        up = sum(v > 0 for v in changes)
        down = sum(v < 0 for v in changes)
        return Breadth(up, down, len(changes) - up - down, len(changes), "东方财富全 A 股快照")

    # ---------------------------------------------------------------- indices (by explicit secid)
    def index_daily(self, index_secid: str, start: date, end: date) -> Bars:
        payload = self._json(KLINE_URL, {
            "secid": index_secid, "klt": "101", "fqt": "1", "beg": f"{start:%Y%m%d}", "end": f"{end:%Y%m%d}",
            "lmt": "100000", "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        })
        rows, name = parse_kline(payload)
        return Bars(finalize_bars(rows, start, end), NAME, "CNY", name)

    def index_intraday(self, index_secid: str) -> Intraday:
        return parse_trends(self._json(TRENDS_URL, {
            "secid": index_secid, "ndays": "1", "iscr": "0", "iscca": "0",
            "fields1": "f1,f2,f3,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f17",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        }))

    def index_constituents(self, index_secid: str) -> dict | None:
        """f113 上涨 / f114 下跌 / f115 平盘 constituent counts."""
        data = (self._json(QUOTE_URL, {"secid": index_secid, "fields": "f113,f114,f115"}).get("data") or {})
        values = {"up": _number(data.get("f113")), "down": _number(data.get("f114")), "flat": _number(data.get("f115"))}
        if any(v is None for v in values.values()):
            return None
        return {k: int(v) for k, v in values.items()}
