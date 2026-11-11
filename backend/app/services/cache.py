"""Read-through cache over ``payload_cache`` (docs/plan-b-draft.md §4.2).

- Fresh (age < TTL): served from the table, no upstream call.
- Stale or missing: one thread per (resource, key) fetches upstream; the others wait for it.
- Upstream failure: the last successful payload is returned with ``stale=True`` plus the error;
  only when nothing was ever stored is the error raised.
- Every upstream attempt is written to ``fetch_log`` (feeds ``/api/health``).
"""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import PayloadCache
from ..providers.base import DataFetchError
from ..providers.composite import Routed
from ..repo import fetch_log

TTL = {
    "intraday": timedelta(seconds=25),
    "quote": timedelta(seconds=25),
    "index_cn": timedelta(seconds=30),
    "index_us": timedelta(minutes=10),
    "index_kr": timedelta(minutes=10),
    "breadth_cn": timedelta(seconds=30),
    "breadth_us": timedelta(minutes=10),
    "index_intraday_cn": timedelta(seconds=30),
    "index_intraday_us": timedelta(minutes=10),
    "index_intraday_kr": timedelta(minutes=10),
    "news": timedelta(minutes=10),
    "valuation": timedelta(minutes=5),
    "fx": timedelta(hours=1),
}


def _default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


@dataclass
class Cached:
    value: Any
    source: str | None
    fetched_at: datetime  # naive UTC
    stale: bool = False  # True: upstream failed, this is the last good payload
    fallback: bool = False
    error: DataFetchError | None = None


class PayloadCacheService:
    def __init__(self, session_factory: sessionmaker[Session], now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.session_factory = session_factory
        self.now = now
        self._locks: dict[tuple[str, str], threading.Lock] = defaultdict(threading.Lock)
        self._guard = threading.Lock()

    def _utc(self) -> datetime:
        return self.now().astimezone(timezone.utc).replace(tzinfo=None)

    def _lock(self, resource: str, key: str) -> threading.Lock:
        with self._guard:
            return self._locks[(resource, key)]

    def _read(self, resource: str, key: str) -> PayloadCache | None:
        with self.session_factory() as session:
            return session.get(PayloadCache, (resource, key))

    def peek(self, resource: str, key: str) -> Cached | None:
        row = self._read(resource, key)
        if row is None:
            return None
        return Cached(json.loads(row.payload_json), row.source, row.fetched_at)

    def get(self, resource: str, key: str, fetch: Callable[[], Routed[Any]], ttl: timedelta | None = None,
            *, encode: Callable[[Any], Any] = lambda v: v, decode: Callable[[Any], Any] = lambda v: v) -> Cached:
        """``fetch`` returns a ``Routed`` (value + provider); ``encode`` makes the value JSON-able."""
        ttl = ttl or TTL[resource]
        row = self._read(resource, key)
        if row is not None and self._utc() - row.fetched_at < ttl:
            return Cached(decode(json.loads(row.payload_json)), row.source, row.fetched_at)
        with self._lock(resource, key):
            row = self._read(resource, key)  # another thread may have refreshed it while we waited
            if row is not None and self._utc() - row.fetched_at < ttl:
                return Cached(decode(json.loads(row.payload_json)), row.source, row.fetched_at)
            started, started_at = time.perf_counter(), self._utc()
            try:
                routed = fetch()
            except DataFetchError as error:
                self.log(resource, key, None, started_at, started, error)
                if row is None:
                    raise
                return Cached(decode(json.loads(row.payload_json)), row.source, row.fetched_at, stale=True, error=error)
            self.log(resource, key, routed, started_at, started, None)
            fetched_at = self._utc()
            payload = json.dumps(encode(routed.value), ensure_ascii=False, default=_default)
            with self.session_factory() as session:
                session.merge(PayloadCache(resource=resource, key=key, payload_json=payload, source=routed.provider,
                                           fetched_at=fetched_at))
                session.commit()
            return Cached(routed.value, routed.provider, fetched_at, fallback=routed.fallback)

    def store(self, resource: str, key: str, value: Any, source: str | None) -> None:
        payload = json.dumps(value, ensure_ascii=False, default=_default)
        with self.session_factory() as session:
            session.merge(PayloadCache(resource=resource, key=key, payload_json=payload, source=source, fetched_at=self._utc()))
            session.commit()

    def log(self, resource: str, key: str, routed: Routed | None, started_at: datetime, started: float,
            error: DataFetchError | None) -> None:
        duration = int((time.perf_counter() - started) * 1000)
        with self.session_factory() as session:
            for failed in (routed.errors if routed else []):
                fetch_log.append(session, provider=_provider_of(failed), resource=resource, key=key, started_at=started_at,
                                 duration_ms=0, status="error", error_category=failed.category, error_message=failed.message)
            if routed is not None:
                fetch_log.append(session, provider=routed.provider, resource=resource, key=key, started_at=started_at,
                                 duration_ms=duration, status="ok")
            for failed in (getattr(error, "attempts", None) or [error]) if error is not None else []:
                fetch_log.append(session, provider=_provider_of(failed), resource=resource, key=key, started_at=started_at,
                                 duration_ms=duration, status="error", error_category=failed.category,
                                 error_message=f"{failed.message} {failed.detail or ''}".strip())
            session.commit()

    def invalidate(self, resource: str, key: str | None = None, *, key_prefix: str | None = None) -> int:
        with self.session_factory() as session:
            stmt = delete(PayloadCache).where(PayloadCache.resource == resource)
            if key is not None:
                stmt = stmt.where(PayloadCache.key == key)
            elif key_prefix is not None:
                stmt = stmt.where(PayloadCache.key.like(f"{key_prefix}%"))
            count = session.execute(stmt).rowcount
            session.commit()
            return count or 0

    def keys(self, resource: str) -> list[str]:
        with self.session_factory() as session:
            return list(session.scalars(select(PayloadCache.key).where(PayloadCache.resource == resource)))


def _provider_of(error: DataFetchError) -> str:
    return getattr(error, "provider", None) or "composite"
