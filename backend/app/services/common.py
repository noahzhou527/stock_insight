"""Shared response metadata (§4.2): {source, as_of, fetched_at, freshness, currency, note}."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from ..domain import sessions
from ..providers.base import DataFetchError
from .cache import Cached


@dataclass
class Meta:
    source: str | None
    as_of: date | datetime | None
    fetched_at: datetime | None
    freshness: str  # live / closed / provisional / fallback / cached / demo
    currency: str | None = None
    note: str | None = None
    errors: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def error_dict(error: DataFetchError) -> dict:
    return {"category": error.category, "message": error.message, "detail": error.detail}


def session_freshness(market: str | None, now: datetime) -> str:
    if market is None:
        return "closed"
    return "live" if sessions.is_trading_session(market, now) else "closed"


def meta_from_cached(cached: Cached, market: str | None, now: datetime, *, currency: str | None = None,
                     as_of=None, note: str | None = None) -> Meta:
    notes = [note] if note else []
    if cached.stale:
        freshness = "cached"
        notes.insert(0, f"上游取数失败，显示本地缓存：{cached.error.message}" if cached.error else "显示本地缓存")
    elif cached.fallback:
        freshness = "fallback"
        notes.insert(0, f"主数据源不可用，使用备用源：{cached.source}")
    else:
        freshness = session_freshness(market, now)
    return Meta(source=cached.source, as_of=as_of, fetched_at=cached.fetched_at, freshness=freshness, currency=currency,
                note="；".join(notes) or None, errors=[error_dict(cached.error)] if cached.error else [])


def worst_freshness(*values: str) -> str:
    order = ["demo", "cached", "fallback", "provisional", "live", "closed"]
    present = [v for v in values if v]
    return min(present, key=order.index) if present else "closed"
