"""All JSON endpoints (docs/plan-b-draft.md §4.3). Route functions are plain ``def``: FastAPI runs them
in its thread pool, matching the synchronous upstream clients."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from ..domain import indicators as ind
from ..domain import sessions
from ..domain.rankings import RANK_METRICS
from ..domain.tickers import TickerFormatError, normalize_a_share
from ..providers.base import Instrument
from ..services.container import Container
from ..services.system import market_sessions
from . import schemas as s

ERRORS = {400: {"model": s.ErrorResponse, "description": "参数错误"},
          404: {"model": s.ErrorResponse, "description": "没有该数据"},
          502: {"model": s.ErrorResponse, "description": "上游数据源失败且本地无缓存"}}

router = APIRouter(prefix="/api", responses=ERRORS)


def container(request: Request) -> Container:
    return request.app.state.container


C = Annotated[Container, Depends(container)]
MarketPath = Annotated[str, Path(description="CN / US / KR", pattern="^(?i:cn|us|kr)$")]
SymbolPath = Annotated[str, Path(description="如 300308.SZ、AAPL、BRK-B、005930.KS；特殊字符请 URL 编码")]
StartQ = Annotated[date | None, Query(description="显示区间开始，默认结束日前一年")]
EndQ = Annotated[date | None, Query(description="显示区间结束，默认该市场今天")]
CurrencyQ = Annotated[str | None, Query(description="换算币种；目前仅支持韩股 currency=USD", pattern="^(?i:[a-z]{3})$")]


def instrument(market: str, symbol: str) -> Instrument:
    market = market.upper()
    symbol = symbol.strip().upper()
    if market == "CN":
        symbol = normalize_a_share(symbol)
    elif not symbol:
        raise TickerFormatError("请输入股票代码。")
    return Instrument(market, symbol)


def date_range(c: Container, inst: Instrument, start: date | None, end: date | None) -> tuple[date, date]:
    end = end or sessions.market_today(inst.market, c.now())
    start = start or end - timedelta(days=365)
    if end < start:
        raise ValueError("结束日期不能早于开始日期。")
    return start, end


def parse_ma(value: str | None) -> tuple[int, ...]:
    if value is None or value.strip() == "":
        return ()
    try:
        periods = tuple(dict.fromkeys(int(v) for v in value.split(",") if v.strip()))
    except ValueError as error:
        raise ValueError("ma 参数格式应为逗号分隔的整数，如 5,10,20") from error
    if any(p < 2 or p > 250 for p in periods):
        raise ValueError("均线周期需在 2–250 之间")
    return periods


# ------------------------------------------------------------------------- instruments
@router.get("/instruments/search", response_model=list[s.SearchResult], tags=["标的"], summary="统一搜索")
def search(c: C, q: Annotated[str, Query(min_length=1, description="名称或代码：300308 / SZ300308 / 中际 / AAPL / 005930.KS")]):
    return c.instruments.search(q)


@router.get("/universe", response_model=list[s.UniverseGroup], tags=["标的"], summary="股票池分组（含美股、韩股常用清单）")
def universe(c: C):
    return c.instruments.universe()


@router.get("/instruments/{market}/{symbol}", response_model=s.InstrumentInfo, tags=["标的"], summary="标的信息")
def instrument_info(c: C, market: MarketPath, symbol: SymbolPath):
    return c.instruments.info(instrument(market, symbol))


@router.get("/instruments/{market}/{symbol}/bars", response_model=s.BarsResponse, tags=["个股"], summary="日线 + 指标")
def bars(c: C, market: MarketPath, symbol: SymbolPath, start: StartQ = None, end: EndQ = None,
         ma: Annotated[str | None, Query(description="均线周期，逗号分隔")] = "5,10,20",
         bbi: bool = False, boll: bool = False,
         rsi: Annotated[int, Query(ge=0, le=60, description="RSI 周期（0 表示不计算）")] = 14,
         macd: bool = True, currency: CurrencyQ = None):
    inst = instrument(market, symbol)
    start, end = date_range(c, inst, start, end)
    params = ind.IndicatorParams(ma=parse_ma(ma), bbi=bbi, boll=boll, rsi=rsi, macd=macd)
    return c.stock.bars(inst, start, end, params, currency)


@router.get("/instruments/{market}/{symbol}/bars.csv", tags=["个股"], summary="导出日线 CSV",
            response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def bars_csv(c: C, market: MarketPath, symbol: SymbolPath, start: StartQ = None, end: EndQ = None, currency: CurrencyQ = None):
    inst = instrument(market, symbol)
    start, end = date_range(c, inst, start, end)
    text = c.stock.bars_csv(inst, start, end, currency)
    filename = f"{inst.symbol}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    return Response("﻿" + text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/instruments/{market}/{symbol}/intraday", response_model=s.IntradayResponse, tags=["个股"], summary="当日分时")
def intraday(c: C, market: MarketPath, symbol: SymbolPath, currency: CurrencyQ = None):
    return c.stock.intraday(instrument(market, symbol), currency)


@router.get("/instruments/{market}/{symbol}/snapshot", response_model=s.SnapshotResponse, tags=["个股"], summary="报价头与属性条")
def snapshot(c: C, market: MarketPath, symbol: SymbolPath, start: StartQ = None, end: EndQ = None,
             rsi: Annotated[int, Query(ge=2, le=60)] = 14, currency: CurrencyQ = None):
    inst = instrument(market, symbol)
    start, end = date_range(c, inst, start, end)
    return c.stock.snapshot(inst, start, end, rsi, currency)


@router.get("/instruments/{market}/{symbol}/financials", response_model=s.FinancialsResponse, tags=["个股"], summary="财报（近 4 个财年 + 近 4 个季度）")
def financials(c: C, market: MarketPath, symbol: SymbolPath, currency: CurrencyQ = None):
    return c.stock.financials(instrument(market, symbol), currency)


@router.get("/instruments/{market}/{symbol}/peers", response_model=s.PeersResponse, tags=["个股"], summary="同赛道对比（仅股票池内 A 股）")
def peers(c: C, market: MarketPath, symbol: SymbolPath):
    return c.stock.peers(instrument(market, symbol))


@router.get("/instruments/{market}/{symbol}/signals", response_model=s.SignalsResponse, tags=["个股"], summary="技术信号摘要")
def signals(c: C, market: MarketPath, symbol: SymbolPath, rsi: Annotated[int, Query(ge=7, le=21)] = 14):
    return c.stock.signals(instrument(market, symbol), rsi)


# ------------------------------------------------------------------------- watchlist
@router.get("/watchlist/items", response_model=list[s.WatchlistItem], tags=["自选"], summary="自选列表")
def watchlist_items(c: C):
    return c.watchlist.items()


@router.post("/watchlist/items", response_model=s.WatchlistItem, status_code=201, tags=["自选"], summary="加入自选（仅 A 股）",
             responses={409: {"model": s.ErrorResponse, "description": "已在自选中"}})
def watchlist_add(c: C, body: s.WatchlistAdd):
    return c.watchlist.add(body.code, body.name)


@router.delete("/watchlist/items/{market}/{symbol}", response_model=s.WatchlistRemoved, tags=["自选"], summary="移出自选（返回原位置，用于撤销）")
def watchlist_remove(c: C, market: MarketPath, symbol: SymbolPath):
    return c.watchlist.remove(instrument(market, symbol))


@router.put("/watchlist/items/{market}/{symbol}", response_model=s.WatchlistItem, tags=["自选"], summary="撤销移除：按原位置恢复")
def watchlist_restore(c: C, market: MarketPath, symbol: SymbolPath, body: s.WatchlistRestore):
    return c.watchlist.restore(instrument(market, symbol), body.sort_order, body.added_at)


@router.get("/watchlist/quotes", response_model=s.WatchlistQuotesResponse, tags=["自选"], summary="自选行情与汇总")
def watchlist_quotes(c: C):
    return c.watchlist.quotes_view()


# ------------------------------------------------------------------------- rankings / market / news
@router.get("/rankings", response_model=s.RankingsResponse, tags=["排行"], summary="A 股股票池排行")
def rankings(c: C, metric: Annotated[str, Query(description=" / ".join(RANK_METRICS))] = "change_pct"):
    return c.rankings.rankings(metric)


@router.get("/market/sessions", response_model=s.SessionsResponse, tags=["市场"], summary="各市场是否处于交易时段")
def market_sessions_route(c: C):
    return market_sessions(c.now())


@router.get("/market/{market}/overview", response_model=s.MarketOverview, tags=["市场"], summary="指数卡片 + 涨跌家数")
def market_overview(c: C, market: MarketPath):
    return c.market.overview(market)


@router.get("/market/{market}/indices/{symbol}/intraday", response_model=s.IndexIntraday, tags=["市场"], summary="指数分时")
def index_intraday(c: C, market: MarketPath, symbol: SymbolPath):
    return c.market.index_intraday(market, symbol)


@router.get("/news", response_model=s.NewsResponse, tags=["新闻"], summary="财经新闻（含各来源状态）")
def news(c: C, hours: Annotated[float, Query(gt=0, le=72)] = 72):
    return c.news.news(hours)


# ------------------------------------------------------------------------- system
@router.get("/prefs", response_model=dict[str, Any], tags=["系统"], summary="用户偏好")
def prefs_get(c: C):
    return c.prefs.get()


@router.put("/prefs", response_model=dict[str, Any], tags=["系统"], summary="更新用户偏好（合并；值为 null 表示删除）")
def prefs_put(c: C, body: dict[str, Any]):
    return c.prefs.update(body)


@router.post("/refresh", response_model=s.RefreshResponse, tags=["系统"], summary="手动刷新：只让指定目标的缓存过期")
def refresh(c: C, body: s.RefreshRequest):
    return c.refresh.refresh(body.target, body.market, body.symbol, body.ids)


@router.get("/health", response_model=s.HealthResponse, tags=["系统"], summary="数据源状态")
def health(c: C):
    return c.health.health()
