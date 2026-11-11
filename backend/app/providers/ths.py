"""同花顺公开页 provider (A 股 沪深北): 日线、分时、F10 估值、财报、现金流.

Ported from data_fetcher.py. Parsers are module-level pure functions so they can be
tested against the golden samples in tests/fixtures/ths/.

口径 (verified 2026-11-11, see tests/test_fixtures.py):
- 日线 URL 中的 ``/01/`` 是前复权；成交量单位为"股"，成交额为"元"。
- 当天那一根在盘中/刚收盘时可能滞后或不完整 —— 由 service 层丢弃并用分时合成。
- 不复权接口 ``/00/`` 的当天行是残缺的，不使用。
- 北交所（920xxx）与沪深同一套 URL 可用，不需要 iFinD。

复权口径实测（2026-11-11，600519 贵州茅台，``/01/`` 对比 ``/00/``）：两者收盘价之比在每个
除息日（2025-06-26、2025-12-19、2026-06-26）跳变，最近一次除息日之后恰为 1.0；成交量完全相同。
即 ``/01/`` 是前复权，且为"减去分红"的加法式调整（比值随价格浮动），而 Yahoo 是按比例调整。
两源在除息日之前的历史价格因此会有细小差异 —— 日线服务的重叠校验（>0.1% 即全量重抓）
保证同一只股票库里只有一种口径。每次除权除息后，旧的历史价格都会整体变化。
"""
from __future__ import annotations

import json
import re
from datetime import date

import numpy as np
import pandas as pd

from .base import (
    Bars,
    DataFetchError,
    Instrument,
    Intraday,
    NotSupported,
    ProviderBase,
    ReportRow,
    Valuation,
    finalize_bars,
)
from .http import HttpClient

LINE_URL = "https://d.10jqka.com.cn/v6/line/hs_{code}/01/{year}.js"
TIME_URL = "https://d.10jqka.com.cn/v6/time/hs_{code}/last.js"
F10_URL = "https://basic.10jqka.com.cn/{code}/"
F10_MOBILE_URLS = ("https://basic.10jqka.com.cn/mobile/{code}/company.html", "https://basic.10jqka.com.cn/mobile/{code}/companyn.html")
FINANCE_URL = "https://basic.10jqka.com.cn/{code}/finance.html"
CASH_URL = "https://basic.10jqka.com.cn/api/stock/finance/{code}_cash.json"

NAME = "同花顺"

REPORT_TYPE_BY_MONTH_DAY = {"03-31": "q1", "06-30": "h1", "09-30": "q3", "12-31": "annual"}
# THS F10 field -> (metric code, is_amount_or_per_share)
FINANCE_METRICS = {
    "营业总收入": ("revenue", True),
    "营业总收入同比增长率": ("revenue_yoy", False),
    "净利润": ("net_profit", True),
    "净利润同比增长率": ("net_profit_yoy", False),
    "扣非净利润": ("net_profit_excl", True),
    "销售毛利率": ("gross_margin", False),
    "基本每股收益": ("eps_basic", True),
    "每股经营现金流": ("ocf_per_share", True),
    "净资产收益率": ("roe", False),
    "资产负债率": ("debt_ratio", False),
}
CAPEX_FIELD = "购建固定资产、无形资产和其他长期资产支付的现金"
TTM_PE_PATTERN = re.compile(r"市盈率\s*\(TTM\)\s*[:：]?\s*([-+]?\d+(?:\.\d+)?|亏损|未公布|不适用|--)", re.I)


# ---------------------------------------------------------------- parsers

def parse_jsonp(text: str) -> dict:
    start, end = text.find("("), text.rfind(")")
    if start < 0 or end <= start:
        raise DataFetchError("ths_schema_changed", "同花顺返回了无法识别的行情格式。")
    return json.loads(text[start + 1 : end])


def parse_daily(text: str) -> list[dict]:
    """``YYYYMMDD,open,high,low,close,volume(股),amount(元),...;`` rows."""
    rows = []
    for raw in parse_jsonp(text).get("data", "").split(";"):
        values = raw.split(",")
        if len(values) < 7:
            continue
        rows.append({
            "trade_date": values[0], "open": values[1], "high": values[2], "low": values[3],
            "close": values[4], "volume": values[5], "amount": values[6] or None,
        })
    return rows


def parse_intraday(text: str, code: str) -> Intraday:
    payload = parse_jsonp(text)
    quote = payload.get(f"hs_{code}", payload)
    try:
        trade_date = pd.Timestamp(str(quote["date"])).date()
        pre_close = float(quote["pre"])
    except (KeyError, TypeError, ValueError) as error:
        raise DataFetchError("ths_schema_changed", "同花顺分时缺少日期或昨收。", error) from error
    rows = []
    for raw in quote.get("data", "").split(";"):
        values = raw.split(",")
        if len(values) < 5:
            continue
        price = float(values[1])
        rows.append({
            "time": pd.Timestamp(f"{trade_date:%Y%m%d}{values[0]}"),
            "price": price,
            "amount": float(values[2] or 0),
            "avg_price": float(values[3] or price),
            "volume": float(values[4] or 0),  # 股
        })
    if not rows:
        raise DataFetchError("ths_intraday_empty", "同花顺暂未返回该股票的当日分时数据。")
    points = pd.DataFrame(rows).set_index("time").sort_index()[["price", "avg_price", "volume", "amount"]]
    name = str(quote.get("name") or "").strip() or None
    return Intraday(points, trade_date, pre_close, NAME, "CNY", name)


def decode_page(content: bytes) -> str:
    """THS pages still mix GBK and UTF-8."""
    for encoding in ("gb18030", "utf-8"):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "同花顺" in text or "市盈率" in text:
            return text
    return content.decode("gb18030", errors="ignore")


def amount_to_number(value) -> float | None:
    """``281.96亿`` / ``12.3万`` / ``19.78`` / ``23.46%`` -> float (yuan / plain / percent)."""
    if value is False or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if np.isfinite(value) else None
    normalized = re.sub(r"<[^>]+>", " ", str(value)).replace(",", "").replace(" ", "").strip()
    if normalized in {"", "--", "—", "-"}:
        return None
    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(万亿|亿|万|元)?", normalized)
    if not match:
        return None
    multiplier = {"万亿": 1e12, "亿": 1e8, "万": 1e4, "元": 1.0, None: 1.0}[match.group(2)]
    number = float(match.group(1)) * multiplier
    return number if np.isfinite(number) else None


def parse_pe(value: str | None) -> float | None:
    """Positive finite PE or None (亏损 / 未公布 / -- / 不适用)."""
    if not value:
        return None
    normalized = re.sub(r"<[^>]+>", " ", value).replace(",", "").strip()
    if any(word in normalized for word in ("亏损", "未公布", "--", "不适用")):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    number = float(match.group())
    return number if number > 0 and np.isfinite(number) else None


def parse_market_cap(value: str | None) -> float | None:
    if not value:
        return None
    normalized = re.sub(r"<[^>]+>", " ", value).replace(",", "").replace(" ", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(万亿|亿|万|元)?", normalized)
    if not match:
        return None
    multiplier = {"万亿": 1e12, "亿": 1e8, "万": 1e4, "元": 1.0}.get(match.group(2))
    if multiplier is None:
        return None
    result = float(match.group(1)) * multiplier
    return result if result > 0 and np.isfinite(result) else None


def _span(html: str, element_id: str) -> str | None:
    match = re.search(rf'id=["\']{element_id}["\'][^>]*>(.*?)</span>', html, flags=re.S | re.I)
    return match.group(1) if match else None


def parse_valuation_pages(desktop_html: str, mobile_html: str | None) -> dict:
    """PE 静/动、总市值 from the desktop F10 page; PE(TTM) from the mobile page."""
    ttm = None
    if mobile_html:
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", mobile_html))
        match = TTM_PE_PATTERN.search(text)
        ttm = match.group(1) if match else None
    return {
        "pe_dynamic": parse_pe(_span(desktop_html, "dtsyl")),
        "pe_static": parse_pe(_span(desktop_html, "jtsyl")),
        "market_cap": parse_market_cap(_span(desktop_html, "stockzsz")),
        "pe_ttm_text": ttm,
        "pe_ttm": parse_pe(ttm),
    }


def parse_finance_payload(html: str) -> dict:
    match = re.search(r'<p\s+id="main">\s*(.*?)\s*</p>', html, flags=re.S)
    if not match:
        raise DataFetchError("ths_schema_changed", "同花顺财报页缺少数据区块。")
    payload = json.loads(match.group(1))
    report = payload.get("report", [])
    if len(report) < 2 or not report[0]:
        raise DataFetchError("ths_financials_empty", "同花顺暂未提供该公司的财务报告。")
    return payload


def finance_fields(payload: dict) -> tuple[list[str], dict[str, list]]:
    titles = [item[0] if isinstance(item, list) else item for item in payload.get("title", [])]
    report = payload["report"]
    periods = [str(value) for value in report[0]]
    fields = {title: report[index] for index, title in enumerate(titles[1:], start=1) if index < len(report)}
    return periods, fields


def parse_finance_reports(payload: dict) -> list[ReportRow]:
    """F10 ``report`` block -> long rows. 季报为累计口径 (q1/h1/q3), 不拆单季."""
    periods, fields = finance_fields(payload)
    rows = []
    for index, period in enumerate(periods):
        report_type = REPORT_TYPE_BY_MONTH_DAY.get(period[5:])
        if report_type is None:
            continue
        period_end = date.fromisoformat(period)
        for field_name, (metric, has_currency) in FINANCE_METRICS.items():
            values = fields.get(field_name, [])
            raw = values[index] if index < len(values) else None
            rows.append(ReportRow(period_end, report_type, metric, amount_to_number(raw), "CNY" if has_currency else None))
    return rows


def calculate_ttm_net_profit(periods: list[str], net_profit_values: list) -> float | None:
    """TTM = 最新年报 − 上年同期累计 + 今年最新累计 (F10 季报为累计口径)."""
    if len(periods) != len(net_profit_values):
        return None
    dates = [str(p) for p in periods]
    annual_dates = [d for d in dates if d.endswith("-12-31")]
    if not annual_dates:
        return None
    latest_annual = max(annual_dates)
    latest_year = int(latest_annual[:4])
    current = [d for d in dates if int(d[:4]) == latest_year + 1 and not d.endswith("-12-31")]
    if not current:
        return None
    current_period = max(current)
    prior = f"{latest_year}-{current_period[5:]}"
    if prior not in dates:
        return None
    values = {d: amount_to_number(net_profit_values[i]) for i, d in enumerate(dates)}
    annual, now, before = values.get(latest_annual), values.get(current_period), values.get(prior)
    if annual is None or now is None or before is None:
        return None
    ttm = annual - before + now
    return ttm if np.isfinite(ttm) else None


def parse_cash_capex(outer: dict) -> list[ReportRow]:
    """Annual 购建固定资产等支付的现金 from ``{code}_cash.json`` (``year`` block)."""
    payload = outer.get("flashData", {})
    if isinstance(payload, str):
        payload = json.loads(payload)
    titles = [t[0] if isinstance(t, list) else t for t in payload.get("title", [])]
    annual = payload.get("year", [])
    if not annual:
        return []
    years = annual[0]
    for index, title in enumerate(titles):
        if str(title).lstrip("*") == CAPEX_FIELD and index < len(annual):
            return [
                ReportRow(date(int(year), 12, 31), "annual", "capex", amount_to_number(value), "CNY")
                for year, value in zip(years, annual[index])
            ]
    return []


# ---------------------------------------------------------------- provider

def _referer(code: str, kind: str = "stockpage") -> dict:
    base = "https://stockpage.10jqka.com.cn" if kind == "stockpage" else "https://basic.10jqka.com.cn"
    return {"User-Agent": "Mozilla/5.0", "Referer": f"{base}/{code}/"}


class ThsProvider(ProviderBase):
    name = NAME

    def __init__(self, http: HttpClient | None = None):
        self.http = http or HttpClient(NAME)

    @staticmethod
    def _check(inst: Instrument, capability: str) -> None:
        if inst.market != "CN":
            raise NotSupported(NAME, capability, inst)

    def daily_bars(self, inst: Instrument, start: date, end: date) -> Bars:
        """Fetched per calendar year (THS granularity); filtered to [start, end]."""
        self._check(inst, "日线")
        rows, errors, not_found = [], [], 0
        for year in range(start.year, end.year + 1):
            try:
                response = self.http.get(LINE_URL.format(code=inst.code, year=year), headers=_referer(inst.code))
                rows.extend(parse_daily(response.text))
            except DataFetchError as error:
                if error.category == "not_found":  # year before listing
                    not_found += 1
                    continue
                errors.append(error)
        if errors and not rows:
            raise errors[0]
        if errors:
            # Partial years would leave holes that look like "not listed"; fail the whole call.
            raise DataFetchError("incomplete_history", "同花顺部分年份的日线获取失败。", errors[0].detail)
        return Bars(finalize_bars(rows, start, end), NAME, "CNY")

    def intraday(self, inst: Instrument) -> Intraday:
        self._check(inst, "分时")
        response = self.http.get(TIME_URL.format(code=inst.code), headers=_referer(inst.code))
        return parse_intraday(response.text, inst.code)

    def financial_reports(self, inst: Instrument) -> list[ReportRow]:
        self._check(inst, "财报")
        response = self.http.get(FINANCE_URL.format(code=inst.code), headers=_referer(inst.code, "basic"))
        rows = parse_finance_reports(parse_finance_payload(response.content.decode("gb18030", errors="ignore")))
        try:
            cash = self.http.get(
                CASH_URL.format(code=inst.code),
                headers={"User-Agent": "Mozilla/5.0", "Referer": FINANCE_URL.format(code=inst.code)},
            )
            rows.extend(parse_cash_capex(cash.json()))
        except (DataFetchError, ValueError):
            pass  # capex is optional; the signal falls back to "数据不足"
        return rows

    def valuation(self, inst: Instrument) -> Valuation:
        self._check(inst, "估值")
        headers = _referer(inst.code, "basic")
        desktop = decode_page(self.http.get(F10_URL.format(code=inst.code), headers=headers).content)
        parsed = None
        for url in F10_MOBILE_URLS:  # the two mobile routes are equivalent; one is sometimes a shell
            try:
                mobile = decode_page(self.http.get(url.format(code=inst.code), headers=headers).content)
            except DataFetchError:
                continue
            parsed = parse_valuation_pages(desktop, mobile)
            if parsed["pe_ttm_text"] is not None:
                break
        parsed = parsed or parse_valuation_pages(desktop, None)

        pe_ttm, ttm_profit, source = parsed["pe_ttm"], None, "同花顺公开 F10"
        if parsed["market_cap"]:
            try:
                response = self.http.get(FINANCE_URL.format(code=inst.code), headers=headers)
                periods, fields = finance_fields(parse_finance_payload(response.content.decode("gb18030", errors="ignore")))
                ttm_profit = calculate_ttm_net_profit(periods, fields.get("净利润", []))
                if ttm_profit is not None and ttm_profit > 0:
                    pe_ttm = parsed["market_cap"] / ttm_profit
                    source = "同花顺公开 F10（按财报推算 TTM）"
            except DataFetchError:
                pass
        return Valuation(pe_ttm, parsed["pe_static"], parsed["pe_dynamic"], parsed["market_cap"], ttm_profit, source, "CNY")
