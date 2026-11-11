"""Provider parsers vs golden samples, plus parity with the legacy parsers (§9).

The legacy-parity tests import the root Streamlit-era modules; they are skipped
automatically once those are deleted in P6.
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from backend.app.providers import eastmoney, ths, yahoo
from backend.app.providers.base import DataFetchError, Instrument, NotSupported, ProviderBase
from backend.app.providers.composite import CompositeProvider
from backend.app.providers.http import HttpClient

FIX = Path(__file__).resolve().parent / "fixtures"
YEAR = int(next(p.name for p in (FIX / "ths").glob("daily_300308_*.js")).split("_")[-1][:4])


def text(rel: str) -> str:
    return (FIX / rel).read_text(encoding="utf-8")


def raw(rel: str) -> bytes:
    return (FIX / rel).read_bytes()


def jload(rel: str) -> dict:
    return json.loads(text(rel))


def close(a, b, rel=1e-9):
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=1e-9)


# ------------------------------------------------------------------ 同花顺

def test_ths_daily_parses_shares_and_yuan():
    rows = ths.parse_daily(text(f"ths/daily_300308_{YEAR}.js"))
    assert len(rows) > 150
    last = rows[-1]
    assert last["trade_date"] == f"{YEAR}1111"
    assert float(last["volume"]) == 60735000  # 股
    assert float(last["amount"]) == 31229066000.0


def test_ths_intraday_has_name_and_pre_close():
    intraday = ths.parse_intraday(text("ths/intraday_300308.js"), "300308")
    assert intraday.name == "中际旭创"
    assert intraday.pre_close == 471.0
    assert intraday.trade_date == date(2026, 11, 11)
    assert list(intraday.points.columns) == ["price", "avg_price", "volume", "amount"]
    assert intraday.points.index[0] == pd.Timestamp("2026-11-11 09:30")


def test_ths_beijing_intraday():
    intraday = ths.parse_intraday(text("ths/intraday_920190.js"), "920190")
    assert len(intraday.points) > 10 and intraday.pre_close > 0


def test_ths_finance_reports_long_rows():
    rows = ths.parse_finance_reports(ths.parse_finance_payload(raw("ths/finance_300308.html").decode("gb18030", "ignore")))
    by_key = {(r.period_end, r.metric): r for r in rows}
    q3 = by_key[(date(2026, 9, 30), "net_profit")]
    assert q3.report_type == "q3" and q3.value == pytest.approx(222.38e8) and q3.currency == "CNY"
    assert by_key[(date(2026, 9, 30), "net_profit_yoy")].value == pytest.approx(211.81)
    assert by_key[(date(2026, 9, 30), "debt_ratio")].currency is None
    assert by_key[(date(2025, 12, 31), "revenue")].report_type == "annual"


def test_ths_capex_annual():
    rows = ths.parse_cash_capex(jload("ths/cash_300308.json"))
    assert rows[0].period_end == date(2025, 12, 31) and rows[0].value == pytest.approx(27.60e8)


def test_ths_valuation_pages():
    parsed = ths.parse_valuation_pages(ths.decode_page(raw("ths/f10_desktop_300308.html")),
                                       ths.decode_page(raw("ths/f10_mobile_company_300308.html")))
    assert parsed["market_cap"] and parsed["market_cap"] > 1e11
    assert parsed["pe_static"] and parsed["pe_dynamic"]


@pytest.mark.parametrize("value, expected", [("281.96亿", 281.96e8), ("1.2万亿", 1.2e12), ("-3.5万", -3.5e4),
                                             ("23.46%", 23.46), ("--", None), (False, None), (12, 12.0)])
def test_ths_amount_to_number(value, expected):
    assert ths.amount_to_number(value) == (pytest.approx(expected) if expected is not None else None)


@pytest.mark.parametrize("value, expected", [("35.2", 35.2), ("亏损", None), ("-3", None), ("--", None), (None, None)])
def test_ths_parse_pe(value, expected):
    assert ths.parse_pe(value) == expected


# ------------------------------------------------------------------ 东方财富

def test_eastmoney_kline_volume_converted_to_shares():
    rows, name = eastmoney.parse_kline(jload("eastmoney/kline_0.300308.json"))
    assert name == "中际旭创"
    assert rows[-1]["trade_date"] == "2026-11-11" and rows[-1]["volume"] == 607350 * 100


def test_eastmoney_secid_rules():
    assert eastmoney.secid(Instrument("CN", "600519.SH")) == "1.600519"
    assert eastmoney.secid(Instrument("CN", "300308.SZ")) == "0.300308"
    assert eastmoney.secid(Instrument("CN", "920190.BJ")) == "0.920190"


def test_eastmoney_ulist_quotes():
    insts = [Instrument("CN", s) for s in ("300308.SZ", "600519.SH", "000001.SZ", "920190.BJ", "688525.SH")]
    quotes = eastmoney.parse_ulist(jload("eastmoney/ulist_snapshot.json"), {i.code: i for i in insts})
    q = next(q for q in quotes if q.instrument.code == "300308")
    assert q.price == 542.0 and q.pre_close == 471.0 and q.trade_date == date(2026, 11, 11)
    assert q.quote_time.tzinfo is not None
    assert len(quotes) == 5


def test_eastmoney_clist_breadth_page():
    values, total = eastmoney.parse_clist_changes(jload("eastmoney/clist_breadth_page1.json"))
    assert total > 1000 and len(values) == 100


def test_eastmoney_trends_synthetic():
    # Golden sample not yet recorded (IP was rate limited); format per legacy _eastmoney_intraday.
    payload = {"data": {"name": "中际旭创", "preClose": 471.0, "trends": [
        "2026-11-11 09:30,480.42,480.42,480.42,480.42,4661,223916560.00,480.420",
        "2026-11-11 09:31,480.42,484.65,484.65,480.42,23472,1135573440.00,483.233"]}}
    intraday = eastmoney.parse_trends(payload)
    assert intraday.pre_close == 471.0 and intraday.points["volume"].iloc[1] == 2347200
    assert intraday.trade_date == date(2026, 11, 11)


def test_eastmoney_trends_fixture_if_recorded():
    path = FIX / "eastmoney/trends_0.300308.json"
    if not path.exists():
        pytest.skip("东方财富分时金样本尚未录制")
    intraday = eastmoney.parse_trends(json.loads(path.read_text(encoding="utf-8")))
    thsi = ths.parse_intraday(text("ths/intraday_300308.js"), "300308")
    common = intraday.points.index.intersection(thsi.points.index)[:-1]
    ratio = intraday.points.loc[common, "volume"].sum() / thsi.points.loc[common, "volume"].sum()
    assert 0.95 < ratio < 1.05


# ------------------------------------------------------------------ Yahoo

def test_yahoo_daily_adjusted_and_estimated_amount():
    rows, name = yahoo.parse_chart_daily(jload("yahoo/chart_daily_AAPL.json"))
    frame = __import__("backend.app.providers.base", fromlist=["finalize_bars"]).finalize_bars(rows)
    assert name and "Apple" in name
    assert frame["amount_estimated"].all()
    raw_rows, _ = yahoo.parse_chart_daily(jload("yahoo/chart_daily_AAPL.json"), adjust=False)
    # adjusted closes never exceed raw closes (dividends only lower history)
    assert all(a["close"] <= r["close"] + 1e-9 for a, r in zip(rows, raw_rows))


def test_yahoo_intraday_single_session():
    intraday = yahoo.parse_chart_intraday(jload("yahoo/chart_5m_005930.KS.json"), jload("yahoo/chart_daily_005930.KS.json"), "Asia/Seoul")
    assert set(intraday.points.index.date) == {intraday.trade_date}
    assert intraday.currency == "KRW" and intraday.pre_close > 0


def test_yahoo_fx_rate():
    rate = yahoo.parse_fx_rate(jload("yahoo/chart_KRW=X.json"))
    assert 1 / 2000 < rate < 1 / 900


def test_yahoo_fundamentals():
    rows = yahoo.parse_fundamentals(jload("yahoo/fundamentals_AAPL.json"))
    metrics = {(r.report_type, r.metric) for r in rows}
    assert ("annual", "revenue") in metrics and ("quarterly", "net_profit") in metrics
    assert all(r.currency == "USD" for r in rows)


def test_yahoo_symbol_mapping():
    assert yahoo.yahoo_symbol(Instrument("CN", "600519.SH")) == "600519.SS"
    assert yahoo.yahoo_symbol(Instrument("US", "BRK-B")) == "BRK-B"


# ------------------------------------------------------------------ http / composite

def test_http_backoff_after_repeated_failures():
    now = [1000.0]

    class Session:
        def get(self, *a, **k):
            raise RuntimeError("Connection closed abruptly")

    client = HttpClient("测试", min_interval=0, clock=lambda: now[0], sleep=lambda s: None)
    client._session = Session()
    for _ in range(3):
        with pytest.raises(DataFetchError) as info:
            client.get("https://example.invalid")
        assert info.value.category == "network_error"
    with pytest.raises(DataFetchError) as info:
        client.get("https://example.invalid")
    assert info.value.category == "provider_backoff"
    now[0] += 31
    with pytest.raises(DataFetchError) as info:
        client.get("https://example.invalid")
    assert info.value.category == "network_error"


def test_http_detects_bot_verification_page():
    page = SimpleNamespace(status_code=200, content=b'<html><script>fetch("/__verify")</script></html>')
    client = HttpClient("Stooq", min_interval=0)
    client._session = SimpleNamespace(get=lambda *a, **k: page)
    with pytest.raises(DataFetchError) as info:
        client.get("https://stooq.com/q/d/l/")
    assert info.value.category == "provider_blocked"


class _Fake(ProviderBase):
    def __init__(self, name, result=None, error=None):
        self.name, self.result, self.error = name, result, error

    def intraday(self, inst):
        if self.error:
            raise self.error
        return self.result


def test_composite_falls_back_and_reports():
    inst = Instrument("CN", "300308.SZ")
    comp = CompositeProvider({"ths": _Fake("同花顺", error=DataFetchError("network_error", "x")),
                              "eastmoney": _Fake("东方财富", result="ok")})
    routed = comp.intraday(inst)
    assert routed.value == "ok" and routed.provider == "东方财富" and routed.fallback


def test_composite_respects_disabled_and_reports_all_failures():
    inst = Instrument("CN", "300308.SZ")
    comp = CompositeProvider({"ths": _Fake("同花顺", result="ths"), "eastmoney": _Fake("东方财富", result="em")}, {"ths"})
    routed = comp.intraday(inst)
    assert routed.value == "em" and not routed.fallback  # first *enabled* provider is not a fallback
    comp = CompositeProvider({"ths": _Fake("同花顺", error=DataFetchError("timeout", "超时")),
                              "eastmoney": _Fake("东方财富", error=NotSupported("东方财富", "分时"))})
    with pytest.raises(DataFetchError) as info:
        comp.intraday(inst)
    assert info.value.category == "timeout" and "not_supported" in info.value.detail


# ------------------------------------------------------------------ legacy parity (§9)

legacy = pytest.importorskip("data_fetcher", reason="legacy modules removed")


class _Resp:
    def __init__(self, body: bytes):
        self.content, self.status_code = body, 200
        self.text = body.decode("utf-8", errors="replace")

    def raise_for_status(self):
        pass

    def json(self):
        return json.loads(self.content)


def _legacy_session(routes: dict[str, str]):
    def get(url, *a, **k):
        for needle, rel in routes.items():
            if needle in url:
                return _Resp(raw(rel))
        raise AssertionError(f"unexpected url {url}")
    return SimpleNamespace(get=get)


def test_parity_ths_daily():
    with patch.object(legacy, "_create_yahoo_session", return_value=_legacy_session({"line/hs_300308": f"ths/daily_300308_{YEAR}.js"})):
        old = legacy._fetch_a_share_year("300308.SZ", YEAR)
    from backend.app.providers.base import finalize_bars
    new = finalize_bars(ths.parse_daily(text(f"ths/daily_300308_{YEAR}.js")))
    assert len(old) == len(new)
    for column in ("Open", "High", "Low", "Close", "Volume", "Amount"):
        assert list(old[column].astype(float)) == list(new[column.lower()].astype(float)), column


def test_parity_ths_intraday():
    with patch.object(legacy, "_create_yahoo_session", return_value=_legacy_session({"time/hs_300308": "ths/intraday_300308.js"})):
        old = legacy.fetch_a_share_intraday("300308.SZ")
    new = ths.parse_intraday(text("ths/intraday_300308.js"), "300308")
    assert old.attrs["pre_close"] == new.pre_close
    for old_col, new_col in (("Price", "price"), ("AvgPrice", "avg_price"), ("Volume", "volume"), ("Amount", "amount")):
        assert list(old[old_col]) == list(new.points[new_col]), old_col


def test_parity_ths_finance_and_ttm():
    with patch.object(legacy, "_create_yahoo_session", return_value=_legacy_session({"finance.html": "ths/finance_300308.html"})), \
         patch.object(legacy, "_load_financial_cache", return_value=pd.DataFrame()), \
         patch.object(legacy, "_save_financial_cache"):
        old = legacy.fetch_a_share_financial_reports("300308.SZ")
    payload = ths.parse_finance_payload(raw("ths/finance_300308.html").decode("gb18030", "ignore"))
    rows = {(r.period_end.isoformat(), r.metric): r.value for r in ths.parse_finance_reports(payload)}
    mapping = {"营业总收入": "revenue", "营收同比": "revenue_yoy", "净利润": "net_profit", "扣非净利润": "net_profit_excl",
               "销售毛利率": "gross_margin", "资产负债率": "debt_ratio", "基本每股收益": "eps_basic"}
    for _, row in old.iterrows():
        for label, metric in mapping.items():
            expected = legacy._financial_amount_to_yuan(row[label]) if row[label] != "—" else None
            assert close(rows[(row["报告期"], metric)], expected), (row["报告期"], metric)
    periods, fields = ths.finance_fields(payload)
    assert close(ths.calculate_ttm_net_profit(periods, fields["净利润"]), old.attrs["ttm_net_profit"])


def test_parity_ths_valuation():
    routes = {"/mobile/300308/company.html": "ths/f10_mobile_company_300308.html", "finance.html": "ths/finance_300308.html",
              "basic.10jqka.com.cn/300308/": "ths/f10_desktop_300308.html"}
    with patch.object(legacy, "_create_yahoo_session", return_value=_legacy_session(routes)), \
         patch.object(legacy, "_load_financial_cache", return_value=pd.DataFrame()), \
         patch.object(legacy, "_save_financial_cache"):
        old = legacy.fetch_a_share_valuation("300308.SZ")

    class Http:
        def get(self, url, **k):
            for needle, rel in routes.items():
                if needle in url:
                    return _Resp(raw(rel))
            raise DataFetchError("not_found", "x")

    new = ths.ThsProvider(Http()).valuation(Instrument("CN", "300308.SZ"))
    for key in ("pe_ttm", "pe_static", "pe_dynamic", "market_cap", "ttm_net_profit"):
        assert close(getattr(new, key), old[key]), key
    assert new.source == old["source"]


def test_parity_ths_capex():
    with patch.object(legacy, "_create_yahoo_session", return_value=_legacy_session({"_cash.json": "ths/cash_300308.json"})):
        period, value = legacy.fetch_a_share_annual_investment_spending.__wrapped__("300308.SZ")
    newest = ths.parse_cash_capex(jload("ths/cash_300308.json"))[0]
    assert newest.period_end.isoformat() == period and close(newest.value, value)


def test_parity_yahoo_fundamentals():
    old = legacy._parse_yahoo_financial_timeseries(jload("yahoo/fundamentals_AAPL.json"))
    new = {(r.period_end.isoformat(), "年报" if r.report_type == "annual" else "季报", r.metric): r.value
           for r in yahoo.parse_fundamentals(jload("yahoo/fundamentals_AAPL.json"))}
    labels = {"营业总收入": "revenue", "毛利润": "gross_profit", "营业利润": "operating_income", "净利润": "net_profit", "基本每股收益": "eps_basic"}
    count = 0
    for _, row in old.iterrows():
        for label, metric in labels.items():
            if pd.notna(row[label]):
                assert close(new[(row["报告期"], row["报告类型"], metric)], row[label])
                count += 1
    assert count == len(new)


def test_parity_eastmoney_kline_except_volume_unit():
    overview = pytest.importorskip("services.market_overview_data")

    class S:
        def get(self, *a, **k):
            return _Resp(raw("eastmoney/kline_0.300308.json"))

    with patch.object(overview.requests, "Session", return_value=S()):
        old = overview._eastmoney_daily("0.300308")
    rows, _ = eastmoney.parse_kline(jload("eastmoney/kline_0.300308.json"), volume_multiplier=1)
    from backend.app.providers.base import finalize_bars
    new = finalize_bars(rows)
    assert list(old["Close"]) == list(new["close"]) and list(old["Volume"]) == list(new["volume"])
