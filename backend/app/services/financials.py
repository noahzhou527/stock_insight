"""Financial reports kept in the ``financial_reports`` table (12-hour freshness, stale-on-error)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import FinancialReport
from ..providers.base import DataFetchError, Instrument, ReportRow
from ..providers.composite import CompositeProvider
from ..repo import bars as repo
from .cache import PayloadCacheService

TTL = timedelta(hours=12)


@dataclass
class ReportsResult:
    rows: list[ReportRow]
    source: str | None
    fetched_at: datetime | None
    stale: bool = False
    error: DataFetchError | None = None


class FinancialsService:
    def __init__(self, session_factory: sessionmaker[Session], provider: CompositeProvider, cache: PayloadCacheService,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.session_factory = session_factory
        self.provider = provider
        self.cache = cache
        self.now = now
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._guard = threading.Lock()

    def _utc(self) -> datetime:
        return self.now().astimezone(timezone.utc).replace(tzinfo=None)

    def _stored(self, inst: Instrument) -> ReportsResult:
        with self.session_factory() as session:
            records = session.scalars(select(FinancialReport).where(FinancialReport.instrument_id == inst.id)).all()
            fetched = session.scalar(select(func.max(FinancialReport.fetched_at)).where(FinancialReport.instrument_id == inst.id))
        rows = [ReportRow(r.period_end, r.report_type, r.metric, r.value, r.currency) for r in records]
        return ReportsResult(rows, records[0].source if records else None, fetched)

    def get(self, inst: Instrument, *, fetch: bool = True) -> ReportsResult:
        stored = self._stored(inst)
        if not fetch or (stored.fetched_at and self._utc() - stored.fetched_at < TTL):
            return stored
        with self._guard:
            lock = self._locks[inst.id]
        with lock:
            stored = self._stored(inst)
            if stored.fetched_at and self._utc() - stored.fetched_at < TTL:
                return stored
            started, started_at = time.perf_counter(), self._utc()
            try:
                routed = self.provider.financial_reports(inst)
            except DataFetchError as error:
                self.cache.log("financial_reports", inst.id, None, started_at, started, error)
                if not stored.rows:
                    raise
                stored.stale, stored.error = True, error
                return stored
            self.cache.log("financial_reports", inst.id, routed, started_at, started, None)
            fetched_at = self._utc()
            unique = {(r.period_end, r.report_type, r.metric): r for r in routed.value}
            with self.session_factory() as session:
                repo.ensure_instrument(session, inst)
                session.execute(delete(FinancialReport).where(FinancialReport.instrument_id == inst.id))
                session.add_all(FinancialReport(instrument_id=inst.id, period_end=r.period_end, report_type=r.report_type,
                                                metric=r.metric, value=r.value, currency=r.currency, source=routed.provider,
                                                fetched_at=fetched_at) for r in unique.values())
                session.commit()
            return ReportsResult(list(unique.values()), routed.provider, fetched_at)

    def invalidate(self, inst: Instrument) -> None:
        with self.session_factory() as session:
            session.execute(
                FinancialReport.__table__.update().where(FinancialReport.instrument_id == inst.id)
                .values(fetched_at=datetime(2000, 1, 1))
            )
            session.commit()
