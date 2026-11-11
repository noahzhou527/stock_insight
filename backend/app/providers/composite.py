"""Route each (market, capability) to a primary provider plus a fallback chain (§4.1)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

from .base import DataFetchError, NotSupported

T = TypeVar("T")

# Provider keys: ths / eastmoney / yahoo / stooq
ROUTES: dict[tuple[str, str], tuple[str, ...]] = {
    ("CN", "daily_bars"): ("ths", "eastmoney", "yahoo"),
    ("US", "daily_bars"): ("yahoo", "stooq"),
    ("KR", "daily_bars"): ("yahoo",),
    ("CN", "intraday"): ("ths", "eastmoney"),
    ("US", "intraday"): ("yahoo",),
    ("KR", "intraday"): ("yahoo",),
    ("CN", "quotes"): ("eastmoney",),
    ("CN", "valuation"): ("ths",),
    ("US", "valuation"): ("yahoo",),
    ("KR", "valuation"): ("yahoo",),
    ("CN", "financial_reports"): ("ths",),
    ("US", "financial_reports"): ("yahoo",),
    ("KR", "financial_reports"): ("yahoo",),
    ("CN", "market_breadth"): ("eastmoney",),
    ("US", "market_breadth"): ("yahoo",),
}


@dataclass
class Routed(Generic[T]):
    value: T
    provider: str  # display name, e.g. 东方财富
    fallback: bool  # True when not served by the first enabled provider
    errors: list[DataFetchError] = field(default_factory=list)  # failures of earlier providers


class CompositeProvider:
    def __init__(self, providers: dict[str, Any], disabled: set[str] | frozenset[str] = frozenset(),
                 routes: dict[tuple[str, str], tuple[str, ...]] | None = None):
        self.providers = providers
        self.disabled = set(disabled)
        self.routes = routes or ROUTES

    def chain(self, market: str, capability: str) -> list[Any]:
        keys = self.routes.get((market, capability), ())
        return [self.providers[k] for k in keys if k in self.providers and k not in self.disabled]

    def call(self, market: str, capability: str, invoke: Callable[[Any], T]) -> Routed[T]:
        chain = self.chain(market, capability)
        if not chain:
            raise DataFetchError("not_supported", f"没有可用的数据源提供该功能（{market} · {capability}）。")
        errors: list[DataFetchError] = []
        for position, provider in enumerate(chain):
            try:
                value = invoke(provider)
            except DataFetchError as error:  # includes NotSupported
                error.provider = provider.name
                errors.append(error)
                continue
            return Routed(value, provider.name, position > 0, errors)
        real = [e for e in errors if not isinstance(e, NotSupported)] or errors
        first = real[0]
        detail = "; ".join(f"{e.category}: {e.message}" + (f" ({e.detail})" if e.detail else "") for e in errors)
        final = DataFetchError(first.category, first.message if len(real) == 1 else f"{first.message}（备用数据源也不可用）", detail)
        final.provider = getattr(first, "provider", None)
        final.attempts = errors
        raise final

    # Convenience wrappers ------------------------------------------------
    def daily_bars(self, inst, start, end):
        return self.call(inst.market, "daily_bars", lambda p: p.daily_bars(inst, start, end))

    def intraday(self, inst):
        return self.call(inst.market, "intraday", lambda p: p.intraday(inst))

    def quotes(self, market, insts):
        return self.call(market, "quotes", lambda p: p.quotes(insts))

    def valuation(self, inst):
        return self.call(inst.market, "valuation", lambda p: p.valuation(inst))

    def financial_reports(self, inst):
        return self.call(inst.market, "financial_reports", lambda p: p.financial_reports(inst))

    def market_breadth(self, market):
        return self.call(market, "market_breadth", lambda p: p.market_breadth(market))


def build_default(settings=None) -> CompositeProvider:
    from ..config import get_settings
    from .eastmoney import EastmoneyProvider
    from .http import HttpClient
    from .stooq import StooqProvider
    from .ths import ThsProvider
    from .yahoo import YahooProvider

    s = settings or get_settings()

    def client(name, **kw):
        return HttpClient(name, min_interval=s.min_request_interval_s, timeout=s.request_timeout_s, **kw)

    from .eastmoney import HEADERS as EM_HEADERS
    providers = {
        "ths": ThsProvider(client("同花顺")),
        "eastmoney": EastmoneyProvider(client("东方财富", force_http11=True, default_headers=EM_HEADERS)),
        "yahoo": YahooProvider(client("Yahoo")),
        "stooq": StooqProvider(client("Stooq")),
    }
    disabled = set(s.disabled_providers)
    if not s.stooq_enabled:
        disabled.add("stooq")
    return CompositeProvider(providers, disabled)
