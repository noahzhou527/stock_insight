"""A-share batch quotes with a per-instrument 25-second cache (自选、排行、涨跌家数回退).

Ported from market_snapshot.fetch_a_share_market_snapshot: one batched upstream call for every
instrument whose cached quote is older than the TTL; instruments the upstream does not return
fall back to their last cached quote (``stale``), and those never seen are ``missing``.
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime, timezone
from typing import Callable

from ..domain import sessions
from ..providers.base import DataFetchError, Instrument, Quote
from ..providers.composite import CompositeProvider, Routed
from .cache import TTL, PayloadCacheService

RESOURCE = "quote"


def quote_to_dict(q: Quote) -> dict:
    change = q.price - q.pre_close if q.price is not None and q.pre_close else None
    return {"name": q.name, "price": q.price, "pre_close": q.pre_close, "change": change, "change_pct": q.change_pct,
            "amount": q.amount, "market_cap": q.market_cap, "pe_ttm": q.pe_ttm,
            "quote_time": q.quote_time.isoformat() if q.quote_time else None,
            "trade_date": q.trade_date.isoformat() if q.trade_date else None, "extra": q.extra}


class QuoteService:
    def __init__(self, cache: PayloadCacheService, provider: CompositeProvider,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.cache = cache
        self.provider = provider
        self.now = now
        self._lock = threading.Lock()

    def get(self, insts: list[Instrument]) -> tuple[dict[str, dict], DataFetchError | None, str | None]:
        """Returns ({instrument id: row}, upstream error if any, source). Rows carry ``status``.

        status: ``latest`` (fresh), ``cached`` (upstream failed or omitted it), ``missing`` (never fetched);
        ``old_date`` is assigned later by callers that compare trade dates.
        """
        ttl = TTL[RESOURCE]
        utc = self.now().astimezone(timezone.utc).replace(tzinfo=None)
        rows: dict[str, dict] = {}
        error: DataFetchError | None = None
        source = None
        with self._lock:
            need: list[Instrument] = []
            for inst in insts:
                cached = self.cache.peek(RESOURCE, inst.id)
                if cached and utc - cached.fetched_at < ttl:
                    rows[inst.id] = {**cached.value, "status": "latest", "stale": False, "source": cached.source}
                else:
                    need.append(inst)
            if need:
                started, started_at = time.perf_counter(), utc
                try:
                    routed: Routed[list[Quote]] = self.provider.quotes("CN", need)
                except DataFetchError as failure:
                    error = failure
                    self.cache.log(RESOURCE, f"batch:{len(need)}", None, started_at, started, failure)
                else:
                    self.cache.log(RESOURCE, f"batch:{len(need)}", routed, started_at, started, None)
                    source = routed.provider
                    for quote in routed.value:
                        value = quote_to_dict(quote)
                        self.cache.store(RESOURCE, quote.instrument.id, value, routed.provider)
                        rows[quote.instrument.id] = {**value, "status": "latest", "stale": False, "source": routed.provider}
                for inst in need:
                    if inst.id in rows:
                        continue
                    cached = self.cache.peek(RESOURCE, inst.id)
                    if cached:
                        rows[inst.id] = {**cached.value, "status": "cached", "stale": True, "source": cached.source}
                    else:
                        rows[inst.id] = {"name": None, "price": None, "pre_close": None, "change": None, "change_pct": None,
                                         "amount": None, "market_cap": None, "pe_ttm": None, "quote_time": None,
                                         "trade_date": None, "extra": {}, "status": "missing", "stale": True, "source": None}
        for row in rows.values():
            if isinstance(row.get("trade_date"), str):
                row["trade_date"] = date.fromisoformat(row["trade_date"])
        source = source or next((r["source"] for r in rows.values() if r.get("source")), None)
        return rows, error, source

    @staticmethod
    def mark_old_dates(rows: list[dict]) -> None:
        dates = [r["trade_date"] for r in rows if r.get("trade_date")]
        newest = max(dates) if dates else None
        for row in rows:
            if row["status"] == "latest" and newest and row.get("trade_date") and row["trade_date"] < newest:
                row["status"] = "old_date"

    def completed_close(self, row: dict) -> float | None:
        """Close of the latest completed daily bar: yesterday's before 15:00 on a trading day, else the price."""
        now = self.now()
        if (row.get("trade_date") == sessions.market_today("CN", now)
                and sessions.local_now("CN", now).time() < sessions.hours("CN").close and row.get("pre_close")):
            return row["pre_close"]
        return row.get("price") or row.get("pre_close")
