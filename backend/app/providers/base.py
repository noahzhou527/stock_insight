"""Provider protocol, value types and errors (docs/plan-b-draft.md §4.1).

Daily bars travel as a pandas DataFrame indexed by ``trade_date`` (``datetime.date``)
with columns BAR_COLUMNS. Units are normalised inside each provider:
volume in shares (股), amount in the instrument's currency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol, runtime_checkable

import pandas as pd

BAR_COLUMNS = ["open", "high", "low", "close", "volume", "amount", "amount_estimated"]
INTRADAY_COLUMNS = ["price", "avg_price", "volume", "amount"]
CURRENCY_BY_MARKET = {"CN": "CNY", "US": "USD", "KR": "KRW"}


@dataclass(frozen=True)
class Instrument:
    market: str  # CN / US / KR
    symbol: str  # 300308.SZ / AAPL / 005930.KS

    @property
    def id(self) -> str:
        return f"{self.market}:{self.symbol}"

    @property
    def code(self) -> str:
        """Bare exchange code (300308 for 300308.SZ)."""
        return self.symbol.split(".")[0]

    @property
    def suffix(self) -> str:
        return self.symbol.rsplit(".", 1)[1] if "." in self.symbol else ""

    @property
    def currency(self) -> str:
        return CURRENCY_BY_MARKET[self.market]

    @classmethod
    def parse_id(cls, instrument_id: str) -> "Instrument":
        market, symbol = instrument_id.split(":", 1)
        return cls(market, symbol)


@dataclass
class Bars:
    frame: pd.DataFrame  # index: trade_date (date), columns: BAR_COLUMNS
    source: str
    currency: str
    name: str | None = None

    @property
    def empty(self) -> bool:
        return self.frame.empty


@dataclass
class Intraday:
    points: pd.DataFrame  # index: naive market-local datetime, columns: INTRADAY_COLUMNS
    trade_date: date
    pre_close: float
    source: str
    currency: str
    name: str | None = None


@dataclass
class Quote:
    instrument: Instrument
    name: str | None
    price: float | None
    pre_close: float | None
    change_pct: float | None
    amount: float | None
    market_cap: float | None
    pe_ttm: float | None
    quote_time: datetime | None
    trade_date: date | None
    source: str
    extra: dict = field(default_factory=dict)


@dataclass
class Valuation:
    pe_ttm: float | None
    pe_static: float | None
    pe_dynamic: float | None
    market_cap: float | None
    ttm_net_profit: float | None
    source: str
    currency: str


@dataclass(frozen=True)
class ReportRow:
    period_end: date
    report_type: str  # annual / q1 / h1 / q3 / quarterly
    metric: str
    value: float | None
    currency: str | None  # None for ratios / percentages


@dataclass
class Breadth:
    up: int
    down: int
    flat: int
    total: int
    source: str


class DataFetchError(RuntimeError):
    """A classified upstream failure. ``message`` is user-facing Chinese."""

    def __init__(self, category: str, message: str, detail: str | Exception | None = None):
        super().__init__(message)
        self.provider: str | None = None  # set by CompositeProvider
        self.category = category
        self.message = message
        self.detail = None if detail is None else (
            f"{type(detail).__name__}: {detail}" if isinstance(detail, Exception) else str(detail)
        )


class NotSupported(DataFetchError):
    def __init__(self, provider: str, capability: str, inst: Instrument | None = None):
        target = f"（{inst.id}）" if inst else ""
        super().__init__("not_supported", f"{provider} 不支持{capability}{target}")


@runtime_checkable
class MarketDataProvider(Protocol):
    name: str

    def daily_bars(self, inst: Instrument, start: date, end: date) -> Bars: ...
    def intraday(self, inst: Instrument) -> Intraday: ...
    def quotes(self, insts: list[Instrument]) -> list[Quote]: ...
    def valuation(self, inst: Instrument) -> Valuation | None: ...
    def financial_reports(self, inst: Instrument) -> list[ReportRow]: ...
    def market_breadth(self, market: str) -> Breadth | None: ...


class ProviderBase:
    """Default implementations raise NotSupported so subclasses only add what they have."""

    name = "base"

    def daily_bars(self, inst: Instrument, start: date, end: date) -> Bars:
        raise NotSupported(self.name, "日线", inst)

    def intraday(self, inst: Instrument) -> Intraday:
        raise NotSupported(self.name, "分时", inst)

    def quotes(self, insts: list[Instrument]) -> list[Quote]:
        raise NotSupported(self.name, "批量快照")

    def valuation(self, inst: Instrument) -> Valuation | None:
        raise NotSupported(self.name, "估值", inst)

    def financial_reports(self, inst: Instrument) -> list[ReportRow]:
        raise NotSupported(self.name, "财报", inst)

    def market_breadth(self, market: str) -> Breadth | None:
        raise NotSupported(self.name, "涨跌家数")


def empty_bars_frame() -> pd.DataFrame:
    frame = pd.DataFrame(columns=BAR_COLUMNS)
    frame.index.name = "trade_date"
    return frame


def finalize_bars(rows: list[dict], start: date | None = None, end: date | None = None) -> pd.DataFrame:
    """Build a clean bars frame: numeric, de-duplicated, sorted, filtered, amount filled."""
    if not rows:
        return empty_bars_frame()
    frame = pd.DataFrame(rows)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    frame = frame.drop_duplicates("trade_date", keep="last").set_index("trade_date").sort_index()
    for column in ("open", "high", "low", "close", "volume", "amount"):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    estimated = frame["amount"].isna()
    frame["amount"] = frame["amount"].fillna(frame["close"] * frame["volume"])
    frame["amount_estimated"] = estimated | frame.get("amount_estimated", False)
    frame["amount_estimated"] = frame["amount_estimated"].astype(bool)
    if start is not None:
        frame = frame[frame.index >= start]
    if end is not None:
        frame = frame[frame.index <= end]
    frame.index.name = "trade_date"
    return frame[BAR_COLUMNS]
