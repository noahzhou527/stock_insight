"""News timeline: ported aggregator + ``news_items`` table, 10-minute freshness."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import NewsItem as NewsRow
from ..news import fetcher
from .cache import TTL, PayloadCacheService
from .common import Meta

STATE = ("news", "state")


def _naive(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value else None


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value else None


class NewsService:
    def __init__(self, session_factory: sessionmaker[Session], cache: PayloadCacheService,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 collect: Callable = fetcher.collect):
        self.session_factory = session_factory
        self.cache = cache
        self.now = now
        self.collect = collect
        self._lock = threading.Lock()

    def _history(self) -> list[fetcher.NewsItem]:
        with self.session_factory() as session:
            rows = session.scalars(select(NewsRow)).all()
        return [fetcher.NewsItem(r.title, r.url or "", r.source, _aware(r.published_at), _aware(r.observed_at)) for r in rows]

    def _save(self, merged: list[fetcher.NewsItem]) -> None:
        with self.session_factory() as session:
            session.execute(delete(NewsRow))
            seen = set()
            for item in merged:
                key = f"{item.source}:{fetcher.title_key(item.title)}"
                if key in seen:
                    continue
                seen.add(key)
                session.add(NewsRow(id=key, source=item.source, title=item.title, url=item.url,
                                    published_at=_naive(item.published_at), observed_at=_naive(item.observed_at) or _naive(self.now())))
            session.commit()

    def news(self, hours: float = 72) -> dict:
        hours = max(1.0, min(float(hours), 72.0))
        now = self.now()
        state = self.cache.peek(*STATE)
        themes = tuple(state.value.get("themes", [])) if state else ()
        fresh = state is not None and now.astimezone(timezone.utc).replace(tzinfo=None) - state.fetched_at < TTL["news"]
        if fresh:
            items, statuses, fetched_at = fetcher.select(self._history(), hours, now, themes), state.value["statuses"], state.fetched_at
        else:
            with self._lock:
                items, merged, statuses, themes = self.collect(self._history(), themes, now, hours)
                self._save(merged)
                self.cache.store(*STATE, {"statuses": statuses, "themes": list(themes)}, " / ".join(fetcher.SOURCE_ORDER))
                fetched_at = now.astimezone(timezone.utc).replace(tzinfo=None)
        any_unavailable = any("不可用" in s or s.startswith("缓存") for s in statuses.values())
        return {
            "items": [{"title": i.title, "url": i.url, "source": i.source, "published_at": i.published_at,
                       "observed_at": i.observed_at, "time": i.effective_time} for i in items],
            "sources": [{"source": s, "status": statuses.get(s, ""), "quota": fetcher.SOURCE_QUOTAS[s]} for s in fetcher.SOURCE_ORDER],
            "meta": Meta(" / ".join(fetcher.SOURCE_ORDER), items[0].effective_time if items else None, fetched_at,
                         "cached" if any_unavailable else "closed", None,
                         "抖音热点没有发布时间，按首次看到的时间排序" if any(i.source == "抖音" for i in items) else None).as_dict(),
        }

    def invalidate(self) -> None:
        self.cache.invalidate(*STATE)
