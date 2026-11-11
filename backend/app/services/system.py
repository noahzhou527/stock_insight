"""Preferences, targeted refresh, data-source health, market sessions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import FetchLog, UserPref
from ..db.models import BarsMeta
from ..domain import sessions
from ..providers.base import Instrument
from ..providers.composite import CompositeProvider
from .cache import PayloadCacheService
from .financials import FinancialsService
from .news import NewsService

PREF_MAX_BYTES = 64 * 1024


class PrefsService:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def get(self) -> dict:
        with self.session_factory() as session:
            return {row.key: json.loads(row.value_json) for row in session.scalars(select(UserPref))}

    def update(self, values: dict) -> dict:
        """Merge: keys with ``null`` are deleted, others replaced."""
        for key, value in values.items():
            if len(json.dumps(value, ensure_ascii=False)) > PREF_MAX_BYTES:
                raise ValueError(f"偏好 {key} 过大")
        with self.session_factory() as session:
            for key, value in values.items():
                row = session.get(UserPref, key)
                if value is None:
                    if row is not None:
                        session.delete(row)
                elif row is None:
                    session.add(UserPref(key=key, value_json=json.dumps(value, ensure_ascii=False)))
                else:
                    row.value_json = json.dumps(value, ensure_ascii=False)
            session.commit()
        return self.get()


class RefreshService:
    """Expire only the caches of one target (fix §2.7: a refresh no longer clears everything)."""

    def __init__(self, session_factory: sessionmaker[Session], cache: PayloadCacheService, financials: FinancialsService,
                 news: NewsService):
        self.session_factory = session_factory
        self.cache = cache
        self.financials = financials
        self.news = news

    def refresh(self, target: str, market: str | None = None, symbol: str | None = None, ids: list[str] | None = None) -> dict:
        cleared: list[str] = []
        if target == "stock":
            if not market or not symbol:
                raise ValueError("刷新个股需要 market 与 symbol")
            inst = Instrument(market.upper(), symbol)
            for resource in ("intraday", "valuation", "quote"):
                if self.cache.invalidate(resource, inst.id):
                    cleared.append(resource)
            with self.session_factory() as session:
                meta = session.get(BarsMeta, inst.id)
                if meta is not None:
                    meta.last_checked_at = None  # next bars request re-checks the tail (if not yet complete)
                    session.commit()
                    cleared.append("daily_bars_check")
        elif target in {"watchlist", "rankings"}:
            if ids:
                for instrument_id in ids:
                    self.cache.invalidate("quote", instrument_id)
            else:
                self.cache.invalidate("quote")
            cleared.append("quote")
        elif target == "market":
            if not market:
                raise ValueError("刷新市场概览需要 market")
            key = market.lower()
            for resource in (f"index_{key}", f"breadth_{key}", f"index_intraday_{key}"):
                self.cache.invalidate(resource)
                cleared.append(resource)
        elif target == "news":
            self.news.invalidate()
            cleared.append("news")
        else:
            raise ValueError("target 只能是 stock / watchlist / rankings / market / news")
        return {"target": target, "cleared": cleared}


class HealthService:
    def __init__(self, session_factory: sessionmaker[Session], provider: CompositeProvider):
        self.session_factory = session_factory
        self.provider = provider

    def health(self) -> dict:
        names = {key: p.name for key, p in self.provider.providers.items()}
        result = []
        with self.session_factory() as session:
            for key, name in names.items():
                last_ok = session.scalar(select(func.max(FetchLog.started_at)).where(FetchLog.provider == name, FetchLog.status == "ok"))
                failure = session.scalars(select(FetchLog).where(FetchLog.provider == name, FetchLog.status == "error")
                                          .order_by(FetchLog.started_at.desc()).limit(1)).first()
                http = getattr(self.provider.providers[key], "http", None)
                result.append({
                    "key": key, "name": name, "enabled": key not in self.provider.disabled,
                    "last_success_at": last_ok,
                    "last_failure_at": failure.started_at if failure else None,
                    "last_error": failure.error_message if failure else None,
                    "last_error_category": failure.error_category if failure else None,
                    "backoff_seconds": round(http.blocked_for) if http is not None else 0,
                })
        healthy = all(not p["enabled"] or not p["last_failure_at"] or (p["last_success_at"] and p["last_success_at"] > p["last_failure_at"])
                      for p in result)
        return {"status": "ok" if healthy else "degraded", "time": datetime.now(timezone.utc), "providers": result}


def market_sessions(now: datetime) -> dict:
    return {"time": now, "markets": [
        {"market": m, "trading": sessions.is_trading_session(m, now), "local_time": sessions.local_now(m, now).replace(tzinfo=None),
         "today": sessions.market_today(m, now), "last_settled_day": sessions.last_settled_trading_day(m, now),
         "sessions": [[s.strftime("%H:%M"), e.strftime("%H:%M")] for s, e in sessions.hours(m).sessions],
         "timezone": str(sessions.hours(m).tz)}
        for m in sessions.MARKETS
    ]}
