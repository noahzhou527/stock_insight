"""Yahoo Finance provider (美股、韩股；A 股兜底): 日线、5 分钟分时、财报、市值、汇率、美股涨跌家数.

Parses the chart / fundamentals-timeseries JSON directly instead of going through
yfinance (only the screener still uses yfinance).

口径：日线 OHLC 按 ``adjclose / close`` 比例调整 —— 与 yfinance ``auto_adjust=True``
（旧代码的默认）一致，相当于前复权；成交量不调整，单位"股"；Yahoo 不提供成交额，
用 close × volume 估算并标记 ``amount_estimated``。
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .base import Bars, Breadth, DataFetchError, Instrument, Intraday, ProviderBase, ReportRow, Valuation, finalize_bars
from .http import HttpClient, clear_broken_local_proxy

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
FUNDAMENTALS_URL = "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"
QUOTE_PAGE_URL = "https://finance.yahoo.com/quote/{symbol}/"
NAME = "Yahoo"
FUNDAMENTAL_METRICS = {
    "TotalRevenue": "revenue",
    "GrossProfit": "gross_profit",
    "OperatingIncome": "operating_income",
    "NetIncome": "net_profit",
    "BasicEPS": "eps_basic",
}
FUNDAMENTAL_TYPES = ",".join(f"{p}{m}" for p in ("annual", "quarterly") for m in FUNDAMENTAL_METRICS)
DEFAULT_TZ = {"CN": "Asia/Shanghai", "US": "America/New_York", "KR": "Asia/Seoul"}


def yahoo_symbol(inst: Instrument) -> str:
    return f"{inst.code}.SS" if inst.market == "CN" and inst.suffix == "SH" else inst.symbol


def _chart_result(payload: dict) -> dict:
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise DataFetchError("ticker_or_data_unavailable", "Yahoo 没有该代码的行情数据。", str(chart["error"]))
    results = chart.get("result") or []
    if not results:
        raise DataFetchError("ticker_or_data_unavailable", "Yahoo 没有该代码的行情数据。")
    return results[0]


def _local_index(result: dict, fallback_tz: str) -> pd.DatetimeIndex:
    tz = (result.get("meta") or {}).get("exchangeTimezoneName") or fallback_tz
    return pd.to_datetime(result.get("timestamp") or [], unit="s", utc=True).tz_convert(tz).tz_localize(None)


def parse_chart_daily(payload: dict, fallback_tz: str = "America/New_York", adjust: bool = True) -> tuple[list[dict], str | None]:
    result = _chart_result(payload)
    index = _local_index(result, fallback_tz)
    if len(index) == 0:
        return [], None
    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame({k: pd.to_numeric(pd.Series(quote.get(k)), errors="coerce") for k in ("open", "high", "low", "close", "volume")})
    frame.index = index
    if adjust:
        adjclose = (result["indicators"].get("adjclose") or [{}])[0].get("adjclose")
        if adjclose is not None:
            ratio = pd.to_numeric(pd.Series(adjclose, index=index), errors="coerce") / frame["close"]
            for column in ("open", "high", "low", "close"):
                frame[column] = frame[column] * ratio
    meta = result.get("meta") or {}
    rows = [
        {"trade_date": ts.date(), "open": r.open, "high": r.high, "low": r.low, "close": r.close,
         "volume": r.volume, "amount": None}
        for ts, r in frame.iterrows()
    ]
    return rows, meta.get("longName") or meta.get("shortName")


def filter_suspicious_korean_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop implausible KRX placeholder rows (volume ~1/1000 of neighbours) — ported as-is."""
    if frame.empty:
        return frame
    volume = pd.to_numeric(frame["volume"], errors="coerce")
    nearby = volume.rolling(window=5, center=True, min_periods=2).median()
    suspicious = (nearby >= 1_000_000) & (volume > 0) & (volume < nearby / 1_000)
    return frame.loc[~suspicious]


def parse_chart_intraday(payload: dict, pre_close_daily: dict | None, fallback_tz: str) -> Intraday:
    """Latest regular session of 5-minute bars; pre_close from a separate unadjusted daily chart."""
    result = _chart_result(payload)
    index = _local_index(result, fallback_tz)
    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame({
        "price": pd.to_numeric(pd.Series(quote.get("close")), errors="coerce"),
        "volume": pd.to_numeric(pd.Series(quote.get("volume")), errors="coerce").fillna(0),
    })
    frame.index = index
    frame = frame.dropna(subset=["price"]).sort_index()
    if frame.empty:
        raise DataFetchError("yahoo_intraday_empty", "Yahoo 没有该代码最近的分时数据。")
    trade_date = frame.index[-1].date()
    frame = frame[frame.index.date == trade_date].copy()
    frame["amount"] = frame["price"] * frame["volume"]
    cumulative = frame["volume"].cumsum().replace(0, np.nan)
    frame["avg_price"] = (frame["amount"].cumsum() / cumulative).fillna(frame["price"])

    pre_close = None
    if pre_close_daily is not None:
        rows, _ = parse_chart_daily(pre_close_daily, fallback_tz, adjust=False)
        prior = [r["close"] for r in rows if r["trade_date"] < trade_date and pd.notna(r["close"])]
        pre_close = float(prior[-1]) if prior else None
    if pre_close is None or not np.isfinite(pre_close):
        pre_close = float(frame["price"].iloc[0])
    meta = result.get("meta") or {}
    return Intraday(frame[["price", "avg_price", "volume", "amount"]], trade_date, pre_close, NAME,
                    meta.get("currency") or "USD", meta.get("longName") or meta.get("shortName"))


def parse_fundamentals(payload: dict) -> list[ReportRow]:
    rows = []
    for series in (payload.get("timeseries") or {}).get("result") or []:
        types = (series.get("meta") or {}).get("type") or []
        if not types:
            continue
        series_type = str(types[0])
        report_type = "annual" if series_type.startswith("annual") else "quarterly"
        metric = FUNDAMENTAL_METRICS.get(series_type.removeprefix("annual").removeprefix("quarterly"))
        if metric is None:
            continue
        for item in series.get(series_type) or []:
            if not item:
                continue
            value = pd.to_numeric((item.get("reportedValue") or {}).get("raw"), errors="coerce")
            period = item.get("asOfDate")
            if not period or pd.isna(value):
                continue
            rows.append(ReportRow(date.fromisoformat(period), report_type, metric, float(value), item.get("currencyCode")))
    return rows


def parse_market_cap_page(html: str) -> float | None:
    match = re.search(r'data-field=["\']marketCap["\'][^>]*>(.*?)</', html, flags=re.S | re.I)
    if not match:
        return None
    label = re.sub(r"<[^>]+>", "", match.group(1)).replace(",", "").strip().upper()
    value = re.search(r"(\d+(?:\.\d+)?)\s*([KMBTQ])?", label)
    if not value:
        return None
    number = float(value.group(1)) * {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12, "Q": 1e15}.get(value.group(2), 1.0)
    return number if number > 0 and np.isfinite(number) else None


def parse_fx_rate(payload: dict) -> float:
    """``KRW=X`` chart -> USD per 1 KRW."""
    closes = _chart_result(payload)["indicators"]["quote"][0].get("close") or []
    krw_per_usd = next((float(v) for v in reversed(closes) if v is not None and float(v) > 0), None)
    if krw_per_usd is None:
        raise DataFetchError("krw_usd_rate_empty", "Yahoo 未返回可用的韩元兑美元汇率。")
    return 1 / krw_per_usd


def _epoch(day: date, tz: str) -> int:
    return int(datetime.combine(day, time(0), tzinfo=ZoneInfo(tz)).timestamp())


class YahooProvider(ProviderBase):
    name = NAME

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient(NAME)

    def _chart(self, inst_or_symbol, params: dict) -> dict:
        symbol = yahoo_symbol(inst_or_symbol) if isinstance(inst_or_symbol, Instrument) else inst_or_symbol
        response = self.http.get(CHART_URL.format(symbol=symbol), params=params)
        try:
            return response.json()
        except ValueError as error:
            raise DataFetchError("yahoo_schema_changed", "Yahoo 返回了无法解析的数据。", error) from error

    def daily_bars(self, inst: Instrument, start: date, end: date) -> Bars:
        tz = DEFAULT_TZ[inst.market]
        payload = self._chart(inst, {
            "period1": _epoch(start, tz), "period2": _epoch(end + timedelta(days=1), tz),
            "interval": "1d", "events": "div,split", "includeAdjustedClose": "true",
        })
        rows, name = parse_chart_daily(payload, tz)
        frame = finalize_bars(rows, start, end)
        if inst.market == "KR":
            frame = filter_suspicious_korean_bars(frame)
        currency = (_chart_result(payload).get("meta") or {}).get("currency") or inst.currency
        return Bars(frame, NAME, currency, name)

    def intraday(self, inst: Instrument) -> Intraday:
        tz = DEFAULT_TZ[inst.market]
        bars = self._chart(inst, {"range": "5d", "interval": "5m", "includePrePost": "false"})
        try:
            daily = self._chart(inst, {"range": "10d", "interval": "1d"})
        except DataFetchError:
            daily = None
        return parse_chart_intraday(bars, daily, tz)

    def financial_reports(self, inst: Instrument) -> list[ReportRow]:
        symbol = yahoo_symbol(inst)
        response = self.http.get(FUNDAMENTALS_URL.format(symbol=symbol), params={
            "symbol": symbol, "type": FUNDAMENTAL_TYPES, "period1": "1577836800", "period2": "1924992000",
        })
        rows = parse_fundamentals(response.json())
        if not rows:
            raise DataFetchError("yahoo_financials_empty", "Yahoo 暂未提供该股票的年度或季度财务报表。")
        return rows

    def valuation(self, inst: Instrument) -> Valuation | None:
        response = self.http.get(QUOTE_PAGE_URL.format(symbol=yahoo_symbol(inst)), headers={"User-Agent": "Mozilla/5.0"})
        market_cap = parse_market_cap_page(response.text)
        if market_cap is None:
            return None
        return Valuation(None, None, None, market_cap, None, NAME, inst.currency)

    def krw_usd_rate(self) -> float:
        return parse_fx_rate(self._chart("KRW=X", {"range": "5d", "interval": "1d"}))

    def market_breadth(self, market: str) -> Breadth | None:
        if market != "US":
            return super().market_breadth(market)
        import yfinance as yf  # screener only
        from curl_cffi import requests
        from yfinance.screener.query import EquityQuery

        clear_broken_local_proxy()
        session = requests.Session(impersonate="chrome", trust_env=False)
        base = EquityQuery("eq", ["region", "us"])

        def count(query) -> int:
            return int(yf.screen(query, size=1, session=session).get("total", 0))

        try:
            total = count(base)
            up = count(EquityQuery("and", [base, EquityQuery("gt", ["percentchange", 0])]))
            down = count(EquityQuery("and", [base, EquityQuery("lt", ["percentchange", 0])]))
        except Exception as error:
            raise DataFetchError("yahoo_breadth_failed", "Yahoo 美股涨跌家数暂时不可用。", error) from error
        return Breadth(up, down, max(total - up - down, 0), total, "Yahoo 可筛选的美国上市普通股")
