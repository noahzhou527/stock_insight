"""Append-only upstream call log (kept 30 days)."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..db.models import FetchLog
from ..db.session import utcnow

RETENTION = timedelta(days=30)


def append(session: Session, *, provider: str, resource: str, key: str | None, started_at: datetime,
           duration_ms: int, status: str, error_category: str | None = None, error_message: str | None = None) -> None:
    session.add(FetchLog(provider=provider, resource=resource, key=key, started_at=started_at, duration_ms=duration_ms,
                         status=status, error_category=error_category, error_message=error_message))


def prune(session: Session, now: datetime | None = None) -> None:
    session.execute(delete(FetchLog).where(FetchLog.started_at < (now or utcnow()) - RETENTION))
