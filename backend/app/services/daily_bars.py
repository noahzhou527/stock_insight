"""Incremental daily-bar cache (docs/plan-b-draft.md §5.2).

All feeds return 前复权 prices, so history changes after every 除权除息. Rules:

1. Per-instrument lock.
2. Head gap (start < covered_start): fetch [start, covered_start + overlap]; covered_start = start
   even when upstream returns nothing (not yet listed) so the gap is never re-requested.
3. Tail refresh: when covered_end < last settled trading day and last check > 5 min ago,
   fetch [covered_end − 10 days, today].
4. Adjustment check: compare fetched closes with stored closes on overlapping dates
   (excluding the newest stored date, which may have been an incomplete same-day row).
   Any relative difference > 0.1% → delete all bars and refetch [covered_start, today]
   in the same transaction, so old and new 复权 bases never mix.
5. Rows dated on/after the first unsettled day (today until close + 30 min) are never stored;
   today's bar is synthesised from intraday and overlaid (freshness=provisional).
6. Upstream failure → serve stored rows (freshness=cached); raise only when nothing is stored.

``covered_end`` advances only to the newest date upstream actually returned, so a lagging
feed (or a holiday) is simply re-checked after the 5-minute throttle.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable

import pandas as pd
from sqlalchemy.orm import Session, sessionmaker

from ..domain import sessions
from ..providers.base import BAR_COLUMNS, Bars, DataFetchError, Instrument, Intraday
from ..providers.composite import CompositeProvider, Routed
from ..repo import bars as repo
from ..repo import fetch_log

TAIL_OVERLAP = timedelta(days=10)
HEAD_OVERLAP = timedelta(days=10)
RECHECK_AFTER = timedelta(minutes=5)
ADJ_TOLERANCE = 0.001
PROVISIONAL_SOURCE = "分时合成"
PROVISIONAL_NOTE = "当日 K 线由分时合成，成交额可能与结算值略有偏差"

_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks[key]


@dataclass
class ResponseMeta:
    source: str | None
    as_of: date | None
    fetched_at: datetime | None
    freshness: str  # live / closed / provisional / fallback / cached / demo
    currency: str
    note: str | None = None
    errors: list[dict] = field(default_factory=list)


@dataclass
class BarsResult:
    frame: pd.DataFrame  # BAR_COLUMNS + source + provisional, index trade_date
    meta: ResponseMeta
    name: str | None = None


def synthesize_bar(intraday: Intraday) -> pd.DataFrame:
    """One provisional OHLCV bar from the intraday session (ported from _intraday_daily_bar)."""
    prices = pd.to_numeric(intraday.points["price"], errors="coerce").dropna()
    if prices.empty:
        return pd.DataFrame()
    frame = pd.DataFrame([{
        "open": float(prices.iloc[0]), "high": float(prices.max()), "low": float(prices.min()),
        "close": float(prices.iloc[-1]), "volume": float(intraday.points["volume"].fillna(0).sum()),
        "amount": float(intraday.points["amount"].fillna(0).sum()), "amount_estimated": False,
        "source": PROVISIONAL_SOURCE, "provisional": True,
    }], index=pd.Index([intraday.trade_date], name="trade_date"))
    return frame


def closes_mismatch(stored: pd.DataFrame, fetched: pd.DataFrame, tolerance: float = ADJ_TOLERANCE) -> bool:
    if stored.empty or fetched.empty:
        return False
    newest_stored = stored.index.max()
    common = [d for d in stored.index.intersection(fetched.index) if d != newest_stored]
    if not common:
        return False
    old = stored.loc[common, "close"].astype(float)
    new = fetched.loc[common, "close"].astype(float)
    return bool(((new - old).abs() / old.abs()).gt(tolerance).any())


class DailyBarService:
    def __init__(self, session_factory: sessionmaker[Session], provider: CompositeProvider,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.session_factory = session_factory
        self.provider = provider
        self.now = now

    # ------------------------------------------------------------------ upstream
    def _fetch(self, logs: list[dict], inst: Instrument, start: date, end: date) -> Routed[Bars]:
        started = time.perf_counter()
        base = {"resource": "daily_bars", "key": f"{inst.id}:{start}:{end}", "started_at": self.now().astimezone(timezone.utc).replace(tzinfo=None)}
        def log_failures(errors):
            for failed in errors:
                logs.append({**base, "provider": getattr(failed, "provider", None) or "composite", "duration_ms": 0,
                             "status": "error", "error_category": failed.category, "error_message": failed.message})

        try:
            routed = self.provider.daily_bars(inst, start, end)
        except DataFetchError as error:
            log_failures(getattr(error, "attempts", None) or [error])
            raise
        log_failures(routed.errors)
        logs.append({**base, "provider": routed.provider, "duration_ms": int((time.perf_counter() - started) * 1000), "status": "ok"})
        return routed

    @staticmethod
    def _settled(frame: pd.DataFrame, first_unsettled: date) -> pd.DataFrame:
        return frame[frame.index < first_unsettled]

    def _full_refresh(self, session: Session, logs: list[dict], inst: Instrument, start: date, today: date, first_unsettled: date,
                      now_naive: datetime) -> Routed[Bars]:
        routed = self._fetch(logs, inst, start, today)
        settled = self._settled(routed.value.frame, first_unsettled)
        repo.delete_bars(session, inst)
        repo.upsert_bars(session, inst, settled, routed.provider, now_naive)
        covered_end = settled.index.max() if not settled.empty else start - timedelta(days=1)
        repo.save_meta(session, inst, covered_start=start, covered_end=covered_end, last_checked_at=now_naive,
                       last_full_refresh_at=now_naive, source=routed.provider)
        return routed

    def _sync(self, session: Session, logs: list[dict], inst: Instrument, start: date, end: date) -> list[Routed[Bars]]:
        now = self.now()
        now_naive = now.astimezone(timezone.utc).replace(tzinfo=None)
        today = sessions.market_today(inst.market, now)
        first_unsettled = sessions.first_unsettled_day(inst.market, now)
        last_settled = sessions.last_settled_trading_day(inst.market, now)
        calls: list[Routed[Bars]] = []

        meta = repo.get_meta(session, inst)
        if meta is None:
            routed = self._fetch(logs, inst, start, today)
            calls.append(routed)
            settled = self._settled(routed.value.frame, first_unsettled)
            repo.upsert_bars(session, inst, settled, routed.provider, now_naive)
            repo.save_meta(session, inst, covered_start=start,
                           covered_end=settled.index.max() if not settled.empty else start - timedelta(days=1),
                           last_checked_at=now_naive, last_full_refresh_at=None, source=routed.provider)
            return calls

        if start < meta.covered_start:
            fetch_end = min(meta.covered_start + HEAD_OVERLAP, today)
            routed = self._fetch(logs, inst, start, fetch_end)
            calls.append(routed)
            fetched = self._settled(routed.value.frame, first_unsettled)
            stored = repo.load_bars(session, inst, meta.covered_start, fetch_end)
            if closes_mismatch(stored, fetched):
                calls.append(self._full_refresh(session, logs, inst, start, today, first_unsettled, now_naive))
                return calls
            repo.upsert_bars(session, inst, fetched, routed.provider, now_naive, overwrite=False)
            repo.save_meta(session, inst, covered_start=start)

        stale = meta.last_checked_at is None or now_naive - meta.last_checked_at > RECHECK_AFTER
        if end > meta.covered_end and meta.covered_end < last_settled and stale:
            fetch_start = meta.covered_end - TAIL_OVERLAP
            routed = self._fetch(logs, inst, fetch_start, today)
            calls.append(routed)
            fetched = self._settled(routed.value.frame, first_unsettled)
            stored = repo.load_bars(session, inst, fetch_start, meta.covered_end)
            if closes_mismatch(stored, fetched):
                calls.append(self._full_refresh(session, logs, inst, meta.covered_start, today, first_unsettled, now_naive))
                return calls
            repo.upsert_bars(session, inst, fetched, routed.provider, now_naive)
            newest = fetched.index.max() if not fetched.empty else meta.covered_end
            repo.save_meta(session, inst, covered_end=max(meta.covered_end, newest), last_checked_at=now_naive,
                           source=routed.provider)
        return calls

    # ------------------------------------------------------------------ public
    def get(self, inst: Instrument, start: date, end: date, *, with_provisional: bool = True,
            intraday: Callable[[Instrument], Routed[Intraday]] | None = None) -> BarsResult:
        if end < start:
            raise DataFetchError("invalid_date_range", "结束日期不能早于开始日期。")
        errors: list[DataFetchError] = []
        calls: list[Routed[Bars]] = []
        with _lock_for(inst.id):
            with self.session_factory() as session:
                logs: list[dict] = []
                try:
                    repo.ensure_instrument(session, inst)
                    calls = self._sync(session, logs, inst, start, end)
                except DataFetchError as error:
                    session.rollback()  # never keep half of a sync (e.g. a delete before a failed refetch)
                    errors.append(error)
                    calls = []
                name = next((c.value.name for c in calls if c.value.name), None)
                repo.ensure_instrument(session, inst)  # naming rules live in InstrumentService.update_name
                for entry in logs:
                    fetch_log.append(session, **entry)
                session.commit()
                frame = repo.load_bars(session, inst, start, end)
                meta_row = repo.get_meta(session, inst)
                fetched_at = meta_row.last_checked_at if meta_row else None

        frame = frame.copy()
        frame["provisional"] = False

        now = self.now()
        notes: list[str] = []
        provisional = False
        if with_provisional:
            loader = intraday or self.provider.intraday
            try:
                routed_intraday = loader(inst)
                name = name or routed_intraday.value.name
                bar = synthesize_bar(routed_intraday.value)
                trade_date = routed_intraday.value.trade_date
                first_unsettled = sessions.first_unsettled_day(inst.market, now)
                newest = frame.index.max() if not frame.empty else None
                if not bar.empty and start <= trade_date <= end and (trade_date >= first_unsettled or newest is None or trade_date > newest):
                    frame = pd.concat([frame[frame.index != trade_date], bar[frame.columns]]).sort_index()
                    provisional = True
                    notes.append(PROVISIONAL_NOTE)
            except DataFetchError:
                pass  # no intraday: just show settled bars

        if frame.empty and errors:
            raise errors[0]

        fallback = next((c for c in calls if c.fallback), None)
        if errors:
            freshness = "cached"
            notes.insert(0, f"上游取数失败，显示本地缓存：{errors[0].message}")
        elif fallback is not None:
            freshness = "fallback"
            notes.insert(0, f"主数据源不可用，使用备用源：{fallback.provider}")
        elif provisional:
            freshness = "provisional"
        else:
            freshness = "live" if sessions.is_trading_session(inst.market, now) else "closed"

        settled_sources = frame.loc[~frame["provisional"].astype(bool), "source"] if not frame.empty else pd.Series(dtype=object)
        meta = ResponseMeta(
            source=calls[-1].provider if calls else (settled_sources.iloc[-1] if len(settled_sources) else None),
            as_of=frame.index.max() if not frame.empty else None,
            fetched_at=fetched_at,
            freshness=freshness,
            currency=inst.currency,
            note="；".join(notes) or None,
            errors=[{"category": e.category, "message": e.message, "detail": e.detail} for e in errors],
        )
        return BarsResult(frame[[*BAR_COLUMNS, "source", "provisional"]], meta, name)
