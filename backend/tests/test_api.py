"""End-to-end API tests over fake upstreams (offline)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db.models import UniverseGroup, UniverseMember
from backend.app.main import create_app
from backend.app.news.fetcher import NewsItem
from backend.app.providers.base import Instrument
from backend.app.providers.composite import CompositeProvider
from backend.app.repo import bars as repo
from backend.app.services.container import Container

from .fakes import SH, FakeEastmoney, FakeThs, FakeYahoo, Switch

TODAY = date(2026, 11, 11)  # Wednesday


class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def fake_news(history, themes, now, hours):
    items = [NewsItem("A股收盘上涨", "https://news.10jqka.com.cn/1.shtml", "同花顺", now - timedelta(hours=1), now),
             NewsItem("Fed holds rates", "https://finance.yahoo.com/n/1", "Yahoo", now - timedelta(hours=2), now)]
    return items, items, {"Yahoo": "RSS · 1/3 条", "同花顺": "7×24 · 1/4 条", "抖音": "不可用 · 0/3 条（测试）"}, ("CPO",)


@pytest.fixture
def env(tmp_path):
    switch = Switch()
    clock = Clock(datetime(2026, 11, 11, 16, 0, tzinfo=SH))
    provider = CompositeProvider({"ths": FakeThs(switch, TODAY), "eastmoney": FakeEastmoney(switch, TODAY),
                                  "yahoo": FakeYahoo(switch, TODAY)})
    container = Container(Settings(db_path=tmp_path / "api.db", frontend_dist=tmp_path / "no-dist"), provider, clock, fake_news)
    with container.session_factory() as session:
        for order, (name, members) in enumerate((("CPO", ["300308.SZ", "300502.SZ", "000988.SZ"]), ("AI PC", ["920190.BJ"]),
                                                 ("美股常用", ["US:AAPL"]))):
            group = UniverseGroup(name=name, sort_order=order)
            session.add(group)
            session.flush()
            for i, symbol in enumerate(members):
                inst = Instrument.parse_id(symbol) if ":" in symbol else Instrument("CN", symbol)
                repo.ensure_instrument(session, inst, {"300308.SZ": "中际旭创", "US:AAPL": "Apple"}.get(symbol))
                session.add(UniverseMember(group_id=group.id, instrument_id=inst.id, sort_order=i))
        session.commit()
    app = create_app(container.settings, container)
    with TestClient(app) as client:
        yield client, switch, clock, container


def ok(response):
    assert response.status_code < 300, response.text
    return response.json()


def test_openapi_lists_every_endpoint(env):
    client, *_ = env
    paths = ok(client.get("/openapi.json"))["paths"]
    for path in ["/api/instruments/search", "/api/universe", "/api/instruments/{market}/{symbol}",
                 "/api/instruments/{market}/{symbol}/bars", "/api/instruments/{market}/{symbol}/bars.csv",
                 "/api/instruments/{market}/{symbol}/intraday", "/api/instruments/{market}/{symbol}/snapshot",
                 "/api/instruments/{market}/{symbol}/financials", "/api/instruments/{market}/{symbol}/peers",
                 "/api/instruments/{market}/{symbol}/signals", "/api/watchlist/items", "/api/watchlist/quotes",
                 "/api/rankings", "/api/market/{market}/overview", "/api/market/{market}/indices/{symbol}/intraday",
                 "/api/market/sessions", "/api/news", "/api/prefs", "/api/refresh", "/api/health"]:
        assert path in paths, path
    assert client.get("/docs").status_code == 200


def test_search_local_and_parsed(env):
    client, *_ = env
    names = ok(client.get("/api/instruments/search", params={"q": "中际"}))
    assert names[0]["id"] == "CN:300308.SZ" and names[0]["verified"]
    parsed = ok(client.get("/api/instruments/search", params={"q": "sz300308"}))
    assert parsed[0]["id"] == "CN:300308.SZ"
    for q, expected in (("AAPL", "US:AAPL"), ("005930.KS", "KR:005930.KS"), ("920190", "CN:920190.BJ"), ("NVDA", "US:NVDA")):
        assert ok(client.get("/api/instruments/search", params={"q": q}))[0]["id"] == expected
    assert ok(client.get("/api/instruments/search", params={"q": "NVDA"}))[0]["verified"] is False


def test_bars_with_indicators_and_warmup(env):
    client, *_ = env
    body = ok(client.get("/api/instruments/CN/300308.SZ/bars", params={"start": "2026-10-01", "end": "2026-11-11",
                                                                     "ma": "5,20,120", "bbi": True, "boll": True}))
    assert body["bars"][0]["date"] == "2026-10-01" and body["bars"][-1]["date"] == "2026-11-11"
    n = len(body["bars"])
    for key in ("ma5", "ma20", "ma120", "bbi", "boll_upper", "rsi14", "macd", "macd_signal", "macd_hist"):
        assert len(body["indicators"][key]) == n
        assert body["indicators"][key][0] is not None, key  # warm-up makes the left edge valid
    assert body["meta"]["freshness"] == "closed" and body["meta"]["source"] == "同花顺"
    assert body["instrument"]["name"] == "中际旭创"


def test_bars_accept_code_variants_and_reject_bad_input(env):
    client, *_ = env
    assert ok(client.get("/api/instruments/CN/300308/bars"))["instrument"]["id"] == "CN:300308.SZ"
    bad = client.get("/api/instruments/CN/abc/bars")
    assert bad.status_code == 400 and bad.json()["error"]["category"] == "invalid_ticker"
    assert "A股代码" in bad.json()["error"]["message"]
    wrong = client.get("/api/instruments/CN/300308.SZ/bars", params={"start": "2026-11-01", "end": "2026-10-01"})
    assert wrong.status_code == 400 and "结束日期" in wrong.json()["error"]["message"]
    invalid = client.get("/api/instruments/CN/300308.SZ/bars", params={"rsi": 999})
    assert invalid.status_code == 422 and invalid.json()["error"]["message"].startswith("请求参数不正确")
    assert client.get("/api/nope").json()["error"]["message"] == "接口不存在"


def test_us_symbol_with_special_characters(env):
    client, *_ = env
    body = ok(client.get(f"/api/instruments/US/{quote('BRK-B')}/bars"))
    assert body["instrument"]["id"] == "US:BRK-B" and all(b["amount_estimated"] for b in body["bars"])
    assert ok(client.get(f"/api/instruments/US/{quote('BRK-B')}"))["name"] == "Fake Corp"  # empty name gets filled


def test_provider_names_do_not_replace_curated_us_kr_names(env):
    client, *_ = env
    ok(client.get("/api/instruments/US/AAPL/bars"))  # fake Yahoo answers "Fake Corp"
    assert ok(client.get("/api/instruments/US/AAPL"))["name"] == "Apple"


def test_intraday_provisional_overlay_during_session(env):
    client, _, clock, _ = env
    clock.value = datetime(2026, 11, 11, 10, 0, tzinfo=SH)
    body = ok(client.get("/api/instruments/CN/300502.SZ/bars", params={"start": "2026-11-01"}))
    last = body["bars"][-1]
    assert last["date"] == "2026-11-11" and last["provisional"] and body["meta"]["freshness"] == "provisional"
    assert "分时合成" in body["meta"]["note"]
    intraday = ok(client.get("/api/instruments/CN/300502.SZ/intraday"))
    assert len(intraday["points"]) == 30 and intraday["meta"]["freshness"] == "live"


def test_snapshot_fields_b1(env):
    client, *_ = env
    body = ok(client.get("/api/instruments/CN/300308.SZ/snapshot", params={"start": "2026-10-20", "end": "2026-11-11"}))
    m = body["metrics"]
    for key in ("price", "change_pct", "range_high", "range_low", "high_52w", "low_52w", "avg_volume", "max_amount",
                "max_amount_date", "volatility"):
        assert m[key] is not None, key
    assert m["high_52w"] >= m["range_high"] and m["low_52w"] <= m["range_low"]
    assert m["price_from_intraday"] and body["valuation"]["pe_ttm"] == 35.0


def test_korean_usd_conversion(env):
    client, *_ = env
    krw = ok(client.get("/api/instruments/KR/005930.KS/bars", params={"start": "2026-11-01"}))
    usd = ok(client.get("/api/instruments/KR/005930.KS/bars", params={"start": "2026-11-01", "currency": "USD"}))
    assert usd["bars"][-1]["close"] == pytest.approx(krw["bars"][-1]["close"] / 1400)
    assert usd["bars"][-1]["volume"] == krw["bars"][-1]["volume"]
    assert usd["fx"]["rate"] == pytest.approx(1 / 1400) and usd["meta"]["currency"] == "USD"
    snap = ok(client.get("/api/instruments/KR/005930.KS/snapshot", params={"currency": "USD"}))
    assert snap["valuation"]["market_cap"] == pytest.approx(3e14 / 1400)
    fin = ok(client.get("/api/instruments/KR/005930.KS/financials", params={"currency": "USD"}))
    eps = next(r for r in fin["rows"] if r["metric"] == "eps_basic")
    assert eps["value"] == pytest.approx(5000 / 1400) and eps["currency"] == "USD"
    bad = client.get("/api/instruments/CN/300308.SZ/bars", params={"currency": "EUR"})
    assert bad.status_code == 400


def test_financials_peers_signals(env):
    client, *_ = env
    fin = ok(client.get("/api/instruments/CN/300308.SZ/financials"))
    assert len(fin["annual_periods"]) == 4 and len(fin["quarterly_periods"]) == 4
    assert fin["ttm_net_profit"] is not None and "累计口径" in fin["meta"]["note"]
    peers = ok(client.get("/api/instruments/CN/300308.SZ/peers"))
    assert peers["supported"] and peers["group"] == "CPO" and len(peers["rows"]) == 3
    assert peers["target"]["id"] == "CN:300308.SZ" and peers["target"]["net_margin"] == pytest.approx(10.0)
    assert not ok(client.get("/api/instruments/US/AAPL/peers"))["supported"]
    signals = ok(client.get("/api/instruments/CN/300308.SZ/signals"))
    assert signals["title"] == "技术信号摘要" and "不构成投资建议" in signals["disclaimer"]
    assert [s["key"] for s in signals["signals"]] == ["trend", "rsi", "macd", "volatility", "debt_ratio", "capex"]
    assert signals["signals"][4]["status"] != "数据不足"


def test_new_listing_states(env):
    client, *_ = env
    body = ok(client.get("/api/instruments/CN/920999.BJ/bars", params={"start": "2026-06-01"}))
    assert body["new_listing"]["is_new_listing"] and body["new_listing"]["daily_bars"] < 20
    assert not body["new_listing"]["trend_ready"]
    signals = ok(client.get("/api/instruments/CN/920999.BJ/signals"))
    assert signals["signals"][0]["status"] == "数据不足"


def test_watchlist_crud_quotes_and_undo(env):
    client, *_ = env
    assert ok(client.post("/api/watchlist/items", json={"code": "sz300308"}))["id"] == "CN:300308.SZ"
    ok(client.post("/api/watchlist/items", json={"code": "688525"}))
    duplicate = client.post("/api/watchlist/items", json={"code": "300308.SZ"})
    assert duplicate.status_code == 409 and "已在自选中" in duplicate.json()["error"]["message"]
    bad = client.post("/api/watchlist/items", json={"code": "AAPL"})
    assert bad.status_code == 400 and "A股代码" in bad.json()["error"]["message"]
    quotes = ok(client.get("/api/watchlist/quotes"))
    assert quotes["summary"]["total"] == 2 and quotes["summary"]["count"] == 2
    assert quotes["summary"]["csi300_change_pct"] is not None and quotes["summary"]["relative_to_csi300"] is not None
    assert quotes["title"] == "当日表现" and {r["status"] for r in quotes["rows"]} == {"latest"}
    removed = ok(client.delete("/api/watchlist/items/CN/300308.SZ"))
    assert [i["id"] for i in ok(client.get("/api/watchlist/items"))] == ["CN:688525.SH"]
    ok(client.put("/api/watchlist/items/CN/300308.SZ", json={"sort_order": removed["sort_order"], "added_at": removed["added_at"]}))
    assert [i["id"] for i in ok(client.get("/api/watchlist/items"))] == ["CN:300308.SZ", "CN:688525.SH"]


def test_rankings(env):
    client, *_ = env
    body = ok(client.get("/api/rankings", params={"metric": "pe_ttm"}))
    assert len(body["rows"]) == 4
    pes = [r["pe_ttm"] for r in body["rows"]]
    valid = [p for p in pes if p and p > 0]
    assert pes[: len(valid)] == sorted(valid)  # invalid PE last
    profit = ok(client.get("/api/rankings", params={"metric": "quarter_profit"}))
    assert profit["rows"][0]["quarter_profit"] is not None and profit["rows"][0]["rank"] == 1
    assert client.get("/api/rankings", params={"metric": "bogus"}).status_code == 400


def test_market_overview_breadth_and_index_intraday(env):
    client, switch, *_ = env
    cn = ok(client.get("/api/market/CN/overview"))
    assert len(cn["indices"]) == 5 and cn["breadth"]["full_market"] and cn["indices"][0]["constituents"]["up"] == 1000
    assert cn["indices"][0]["amount_change"] is not None
    us = ok(client.get("/api/market/us/overview"))
    assert len(us["indices"]) == 4 and us["breadth"]["total"] == 4600
    kr = ok(client.get("/api/market/KR/overview"))
    assert kr["breadth"] is None and len(kr["indices"]) == 1
    chart = ok(client.get(f"/api/market/US/indices/{quote('^GSPC')}/intraday"))
    assert chart["index"]["name"] == "标普500" and len(chart["points"]) == 30
    assert ok(client.get("/api/market/CN/indices/000001/intraday"))["index"]["symbol"] == "1A0001"


def test_breadth_falls_back_to_pool_statistics(env):
    client, _, _, container = env
    em = container.provider.providers["eastmoney"]

    def broken(market):
        from backend.app.providers.base import DataFetchError
        raise DataFetchError("eastmoney_breadth_incomplete", "东方财富返回的 A 股涨跌数据不完整。")

    em.market_breadth = broken
    breadth = ok(client.get("/api/market/CN/overview"))["breadth"]
    assert breadth["full_market"] is False and breadth["total"] == 4  # the 4 stock-pool members
    assert "非全市场" in breadth["source"] and breadth["meta"]["freshness"] == "fallback"


def test_news_prefs_sessions_refresh_health(env):
    client, *_ = env
    news = ok(client.get("/api/news"))
    assert len(news["items"]) == 2 and [s["source"] for s in news["sources"]] == ["Yahoo", "同花顺", "抖音"]
    assert news["meta"]["freshness"] == "cached"  # 抖音 unavailable
    assert ok(client.put("/api/prefs", json={"theme": "dark", "ma": [5, 10]})) == {"theme": "dark", "ma": [5, 10]}
    assert ok(client.put("/api/prefs", json={"theme": None})) == {"ma": [5, 10]}
    sessions = ok(client.get("/api/market/sessions"))
    assert {m["market"] for m in sessions["markets"]} == {"CN", "US", "KR"}
    ok(client.get("/api/instruments/CN/300308.SZ/intraday"))
    refreshed = ok(client.post("/api/refresh", json={"target": "stock", "market": "CN", "symbol": "300308.SZ"}))
    assert "intraday" in refreshed["cleared"]
    assert client.post("/api/refresh", json={"target": "stock"}).status_code == 400
    health = ok(client.get("/api/health"))
    by_name = {p["name"]: p for p in health["providers"]}
    assert by_name["同花顺"]["last_success_at"] is not None


def test_refresh_only_expires_its_target(env):
    client, switch, *_ = env
    ok(client.get("/api/instruments/CN/300308.SZ/intraday"))
    ok(client.get("/api/instruments/CN/300502.SZ/intraday"))
    switch.calls.clear()
    ok(client.post("/api/refresh", json={"target": "stock", "market": "CN", "symbol": "300308.SZ"}))
    ok(client.get("/api/instruments/CN/300308.SZ/intraday"))
    ok(client.get("/api/instruments/CN/300502.SZ/intraday"))
    assert switch.calls == ["ths.intraday:CN:300308.SZ"]


def test_offline_cached_stock_still_served_and_marked_cached(env):
    """P2 acceptance: with the network down, an already-cached stock returns data flagged ``cached``."""
    client, switch, clock, _ = env
    ok(client.get("/api/instruments/CN/300308.SZ/bars", params={"start": "2026-08-01"}))
    ok(client.get("/api/instruments/CN/300308.SZ/snapshot"))
    ok(client.get("/api/instruments/CN/300308.SZ/financials"))
    clock.value = datetime(2026, 11, 13, 16, 0, tzinfo=SH)  # two days later: tail, intraday and valuation are stale
    switch.online = False
    bars = ok(client.get("/api/instruments/CN/300308.SZ/bars", params={"start": "2026-08-01"}))
    assert bars["meta"]["freshness"] == "cached" and bars["bars"][-1]["date"] == "2026-11-11"
    assert bars["meta"]["errors"][0]["category"] == "network_error" and "本地缓存" in bars["meta"]["note"]
    snap = ok(client.get("/api/instruments/CN/300308.SZ/snapshot"))
    assert snap["meta"]["freshness"] == "cached" and snap["valuation"] is not None
    intraday = ok(client.get("/api/instruments/CN/300308.SZ/intraday"))
    assert intraday["meta"]["freshness"] == "cached"
    clock.value += timedelta(hours=13)  # financials TTL passed too
    assert ok(client.get("/api/instruments/CN/300308.SZ/financials"))["meta"]["freshness"] == "cached"
    never = client.get("/api/instruments/CN/600519.SH/bars")
    assert never.status_code == 502 and never.json()["error"]["category"] == "network_error"
    assert never.json()["error"]["message"]
    health = ok(client.get("/api/health"))
    assert health["status"] == "degraded"


def test_csv_export(env):
    client, *_ = env
    response = client.get("/api/instruments/CN/300308.SZ/bars.csv", params={"start": "2026-11-01", "end": "2026-11-11"})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    lines = response.text.lstrip("﻿").splitlines()
    assert lines[0].startswith("日期,开盘") and len(lines) == 1 + 8  # 11-02 … 11-11 weekdays
