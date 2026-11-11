"""Response / request DTOs. These define the OpenAPI schema the frontend types are generated from."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Freshness = Literal["live", "closed", "provisional", "fallback", "cached", "demo"]
Market = Literal["CN", "US", "KR"]


class ErrorInfo(BaseModel):
    category: str = Field(description="稳定的错误类别代码，如 network_error / not_found")
    message: str = Field(description="面向用户的中文说明")
    detail: str | None = Field(None, description="技术细节（可展开查看）")


class ErrorResponse(BaseModel):
    error: ErrorInfo


class Meta(BaseModel):
    source: str | None = Field(None, description="数据来源，如 同花顺 / 东方财富 / Yahoo")
    as_of: date | datetime | None = Field(None, description="数据所对应的日期或时间")
    fetched_at: datetime | None = Field(None, description="最近一次从上游取数的时间（UTC）")
    freshness: Freshness = Field(description="live 实时 / closed 已收盘 / provisional 盘中合成 / fallback 备用源 / cached 本地缓存 / demo 演示")
    currency: str | None = None
    note: str | None = Field(None, description="需要提示给用户的说明（中文）")
    errors: list[ErrorInfo] = []


class FxInfo(BaseModel):
    from_: str = Field(alias="from")
    to: str
    rate: float = Field(description="1 单位 from 货币折合多少 to 货币")
    source: str | None = None
    fetched_at: datetime | None = None
    note: str | None = None

    model_config = {"populate_by_name": True}


class InstrumentInfo(BaseModel):
    id: str = Field(examples=["CN:300308.SZ"])
    market: Market
    symbol: str
    name: str | None
    currency: str
    groups: list[str] = []
    in_watchlist: bool = False
    known: bool = False
    history_start: date | None = None


class SearchResult(BaseModel):
    id: str
    market: Market
    symbol: str
    name: str | None
    currency: str
    verified: bool = Field(description="false：仅按代码规则解析，尚未从数据源确认")


class UniverseMember(BaseModel):
    id: str
    market: Market
    symbol: str
    name: str | None
    currency: str


class UniverseGroup(BaseModel):
    id: int
    name: str
    members: list[UniverseMember]


class NewListing(BaseModel):
    daily_bars: int
    previous_close: float | None
    trend_ready: bool
    rsi_ready: bool
    macd_ready: bool
    volatility_ready: bool
    is_new_listing: bool


class Bar(BaseModel):
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None = Field(description="成交量，单位：股")
    amount: float | None
    amount_estimated: bool = Field(description="成交额为 收盘价 × 成交量 估算")
    provisional: bool = Field(description="由当日分时合成的 K 线")
    source: str


class BarsResponse(BaseModel):
    instrument: InstrumentInfo
    bars: list[Bar]
    indicators: dict[str, list[float | None]] = Field(description="与 bars 一一对应；键如 ma5 / bbi / boll_upper / rsi14 / macd / macd_signal / macd_hist")
    new_listing: NewListing
    fx: FxInfo | None = None
    meta: Meta


class IntradayPoint(BaseModel):
    time: datetime
    price: float | None
    avg_price: float | None
    volume: float | None
    amount: float | None


class IntradayResponse(BaseModel):
    points: list[IntradayPoint]
    pre_close: float
    trade_date: date
    name: str | None = None
    fx: FxInfo | None = None
    meta: Meta


class SnapshotMetrics(BaseModel):
    price: float | None
    pre_close: float | None
    change: float | None
    change_pct: float | None
    price_from_intraday: bool
    range_high: float | None = Field(description="所选区间最高价")
    range_low: float | None = Field(description="所选区间最低价")
    high_52w: float | None
    low_52w: float | None
    avg_volume: float | None
    max_amount: float | None
    max_amount_date: date | None
    volatility: float | None = Field(description="年化波动率（%），数据不足时为空")


class Valuation(BaseModel):
    pe_ttm: float | None
    pe_static: float | None
    pe_dynamic: float | None
    market_cap: float | None
    ttm_net_profit: float | None
    source: str


class SnapshotResponse(BaseModel):
    instrument: InstrumentInfo
    metrics: SnapshotMetrics
    valuation: Valuation | None
    valuation_meta: dict[str, Any] | None
    new_listing: NewListing
    fx: FxInfo | None = None
    meta: Meta


class ReportRowOut(BaseModel):
    period_end: date
    report_type: Literal["annual", "q1", "h1", "q3", "quarterly"]
    metric: str = Field(description="revenue / net_profit / net_profit_yoy / gross_margin / eps_basic / debt_ratio / capex …")
    value: float | None
    currency: str | None = Field(description="金额与每股指标的币种；比率类为空（单位 %）")


class FinancialsResponse(BaseModel):
    rows: list[ReportRowOut]
    annual_periods: list[date]
    quarterly_periods: list[date]
    ttm_net_profit: float | None
    fx: FxInfo | None = None
    meta: Meta


class PeerRow(BaseModel):
    id: str
    symbol: str
    name: str | None
    period_end: date | None
    revenue: float | None
    net_profit: float | None
    net_margin: float | None
    debt_ratio: float | None
    capex: float | None
    capex_ratio: float | None


class PeersResponse(BaseModel):
    supported: bool
    message: str | None
    group: str | None
    rows: list[PeerRow]
    target: PeerRow | None
    meta: Meta


class SignalOut(BaseModel):
    key: str
    name: str
    status: str
    description: str
    tone: Literal["up", "down", "neutral", "warn", "info"]


class SignalsResponse(BaseModel):
    title: str
    disclaimer: str
    signals: list[SignalOut]
    fundamentals_supported: bool
    meta: Meta


class WatchlistItem(BaseModel):
    id: str
    market: Market
    symbol: str
    name: str | None
    added_at: datetime
    sort_order: int


class WatchlistAdd(BaseModel):
    code: str = Field(description="支持 300308、300308.SZ、SZ300308 等写法", examples=["300308"])
    name: str | None = None


class WatchlistRestore(BaseModel):
    sort_order: int
    added_at: datetime | None = None


class WatchlistRemoved(BaseModel):
    id: str
    sort_order: int
    added_at: datetime


QuoteStatus = Literal["latest", "cached", "old_date", "missing"]


class WatchlistQuoteRow(WatchlistItem):
    price: float | None = None
    pre_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    amount: float | None = None
    market_cap: float | None = None
    pe_ttm: float | None = None
    quote_time: datetime | None = None
    trade_date: date | None = None
    status: QuoteStatus = Field(description="latest 最新 / cached 缓存 / old_date 旧日期 / missing 缺失")
    stale: bool
    source: str | None = None
    extra: dict[str, float | None] = Field(default={}, description="open / high / low / amplitude / turnover")
    change_5d: float | None = None
    change_20d: float | None = None
    suspended: bool = False


class SummaryStock(BaseModel):
    id: str
    symbol: str
    name: str | None
    change_pct: float | None


class WatchlistSummary(BaseModel):
    date: date | None
    count: int = Field(description="有效样本数")
    total: int
    average: float | None = Field(description="等权平均涨跌幅（%）")
    up: int
    down: int
    flat: int
    leader: SummaryStock | None
    laggard: SummaryStock | None
    csi300_change_pct: float | None
    relative_to_csi300: float | None


class WatchlistQuotesResponse(BaseModel):
    title: str
    summary: WatchlistSummary
    rows: list[WatchlistQuoteRow]
    meta: Meta


class RankingRow(BaseModel):
    rank: int
    id: str
    symbol: str
    name: str | None
    group: str
    price: float | None
    change_pct: float | None
    amount: float | None
    market_cap: float | None
    pe_ttm: float | None
    quote_time: datetime | None
    trade_date: date | None
    status: QuoteStatus
    stale: bool
    quarter_profit: float | None
    quarter_profit_yoy: float | None
    quarter_period: date | None


class RankingsResponse(BaseModel):
    metric: str
    rows: list[RankingRow]
    meta: Meta


class Constituents(BaseModel):
    up: int
    down: int
    flat: int


class IndexCard(BaseModel):
    name: str
    symbol: str
    display_code: str
    price: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    amount: float | None = None
    previous_amount: float | None = None
    amount_change: float | None = None
    amount_change_pct: float | None = None
    trade_date: date | None = None
    source: str | None = None
    constituents: Constituents | None = None
    error: ErrorInfo | None = None


class BreadthOut(BaseModel):
    up: int | None = None
    down: int | None = None
    flat: int | None = None
    total: int | None = None
    source: str | None = None
    full_market: bool = Field(description="false：回退为本地股票池统计（非全市场）")
    meta: Meta | None = None
    error: ErrorInfo | None = None


class MarketOverview(BaseModel):
    market: Market
    indices: list[IndexCard]
    breadth: BreadthOut | None
    meta: Meta


class IndexRef(BaseModel):
    name: str
    symbol: str
    display_code: str


class IndexIntraday(BaseModel):
    index: IndexRef
    trade_date: date
    pre_close: float
    points: list[IntradayPoint]
    meta: Meta


class MarketSession(BaseModel):
    market: Market
    trading: bool
    local_time: datetime
    today: date
    last_settled_day: date
    sessions: list[list[str]]
    timezone: str


class SessionsResponse(BaseModel):
    time: datetime
    markets: list[MarketSession]


class NewsItemOut(BaseModel):
    title: str
    url: str
    source: str
    published_at: datetime | None
    observed_at: datetime | None
    time: datetime


class NewsSource(BaseModel):
    source: str
    status: str
    quota: int


class NewsResponse(BaseModel):
    items: list[NewsItemOut]
    sources: list[NewsSource]
    meta: Meta


class RefreshRequest(BaseModel):
    target: Literal["stock", "watchlist", "rankings", "market", "news"]
    market: Market | None = None
    symbol: str | None = None
    ids: list[str] | None = Field(None, description="只刷新这些标的的快照（自选 / 排行）")


class RefreshResponse(BaseModel):
    target: str
    cleared: list[str]


class ProviderStatus(BaseModel):
    key: str
    name: str
    enabled: bool
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error: str | None
    last_error_category: str | None
    backoff_seconds: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    time: datetime
    providers: list[ProviderStatus]
