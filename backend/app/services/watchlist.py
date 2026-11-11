"""Default watchlist (A 股 only in v1): CRUD, quotes, summary vs 沪深300."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Instrument as InstrumentRow
from ..db.models import Watchlist, WatchlistItem
from ..db.session import utcnow
from ..domain import sessions
from ..domain.tickers import normalize_a_share
from ..domain.watchlist import summarize
from ..providers.base import DataFetchError, Instrument
from ..repo import bars as repo
from .common import Meta, error_dict, session_freshness
from .instruments import DEFAULT_WATCHLIST_ID
from .quotes import QuoteService

CSI300 = Instrument("CN", "000300.SH")  # 东方财富 secid 1.000300 (沪深300 指数)


class WatchlistError(ValueError):
    def __init__(self, category: str, message: str, status: int = 400):
        super().__init__(message)
        self.category, self.message, self.status = category, message, status


class WatchlistService:
    def __init__(self, session_factory: sessionmaker[Session], quotes: QuoteService,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self.session_factory = session_factory
        self.quotes = quotes
        self.now = now

    def _ensure_list(self, session: Session) -> None:
        if session.get(Watchlist, DEFAULT_WATCHLIST_ID) is None:
            session.add(Watchlist(id=DEFAULT_WATCHLIST_ID, name="默认", sort_order=0))
            session.flush()

    def items(self) -> list[dict]:
        with self.session_factory() as session:
            rows = session.execute(
                select(WatchlistItem, InstrumentRow).join(InstrumentRow, InstrumentRow.id == WatchlistItem.instrument_id)
                .where(WatchlistItem.watchlist_id == DEFAULT_WATCHLIST_ID).order_by(WatchlistItem.sort_order, WatchlistItem.added_at)
            ).all()
            return [{"id": inst.id, "market": inst.market, "symbol": inst.symbol, "name": inst.name, "added_at": item.added_at,
                     "sort_order": item.sort_order} for item, inst in rows]

    def add(self, code: str, name: str | None = None) -> dict:
        try:
            inst = Instrument("CN", normalize_a_share(code))
        except ValueError as error:
            raise WatchlistError("invalid_ticker", str(error)) from error
        with self.session_factory() as session:
            self._ensure_list(session)
            if session.get(WatchlistItem, (DEFAULT_WATCHLIST_ID, inst.id)) is not None:
                raise WatchlistError("duplicate", f"{inst.symbol} 已在自选中。", 409)
            repo.ensure_instrument(session, inst, name)
            order = session.scalar(select(func.coalesce(func.max(WatchlistItem.sort_order), -1))
                                   .where(WatchlistItem.watchlist_id == DEFAULT_WATCHLIST_ID)) + 1
            session.add(WatchlistItem(watchlist_id=DEFAULT_WATCHLIST_ID, instrument_id=inst.id, added_at=utcnow(), sort_order=order))
            session.commit()
        return next(item for item in self.items() if item["id"] == inst.id)

    def remove(self, inst: Instrument) -> dict:
        with self.session_factory() as session:
            item = session.get(WatchlistItem, (DEFAULT_WATCHLIST_ID, inst.id))
            if item is None:
                raise WatchlistError("not_found", f"{inst.symbol} 不在自选中。", 404)
            removed = {"id": inst.id, "sort_order": item.sort_order, "added_at": item.added_at}
            session.delete(item)
            session.commit()
            return removed

    def restore(self, inst: Instrument, sort_order: int, added_at: datetime | None) -> dict:
        """撤销移除：put the item back at its previous position."""
        with self.session_factory() as session:
            self._ensure_list(session)
            if session.get(WatchlistItem, (DEFAULT_WATCHLIST_ID, inst.id)) is None:
                repo.ensure_instrument(session, inst)
                session.add(WatchlistItem(watchlist_id=DEFAULT_WATCHLIST_ID, instrument_id=inst.id,
                                          added_at=added_at or utcnow(), sort_order=sort_order))
                session.commit()
        return next(item for item in self.items() if item["id"] == inst.id)

    def _momentum(self, inst: Instrument) -> dict:
        """5 / 20 日涨幅 from stored daily bars only (no upstream request)."""
        with self.session_factory() as session:
            frame = repo.load_bars(session, inst)
        close = frame["close"].astype(float) if not frame.empty else None
        result = {}
        for days in (5, 20):
            result[f"change_{days}d"] = (float(close.iloc[-1] / close.iloc[-1 - days] - 1) * 100
                                         if close is not None and len(close) > days else None)
        return result

    def quotes_view(self) -> dict:
        items = self.items()
        insts = [Instrument(i["market"], i["symbol"]) for i in items]
        rows_by_id, error, source = self.quotes.get([*insts, CSI300]) if insts else ({}, None, None)
        rows = []
        for item, inst in zip(items, insts):
            quote = rows_by_id.get(inst.id, {})
            if not item["name"] and quote.get("name"):
                item["name"] = quote["name"]
            rows.append({**item, **{k: v for k, v in quote.items() if k != "name"}, **self._momentum(inst),
                         # 停牌：行情最新但当日无成交
                         "suspended": quote.get("status") == "latest" and quote.get("amount") == 0})
        QuoteService.mark_old_dates(rows)
        summary = summarize(rows)
        index = rows_by_id.get(CSI300.id)
        index_change = index.get("change_pct") if index and index.get("trade_date") == summary["date"] else None
        summary["csi300_change_pct"] = index_change
        summary["relative_to_csi300"] = summary["average"] - index_change if summary["average"] is not None and index_change is not None else None
        for key in ("leader", "laggard"):
            if summary[key]:
                summary[key] = {k: summary[key][k] for k in ("id", "symbol", "name", "change_pct")}
        today = sessions.market_today("CN", self.now())
        title = "当日表现" if summary["date"] == today else (f"最近交易日 · {summary['date']}" if summary["date"] else "暂无行情")
        stale = error is not None or any(r["status"] in {"cached", "missing"} for r in rows)
        note = f"行情接口暂不可用，部分数据为本地缓存：{error.message}" if error else None
        return {"title": title, "summary": summary, "rows": rows,
                "meta": Meta(source, summary["date"], None, "cached" if stale else session_freshness("CN", self.now()),
                             "CNY", note, [error_dict(error)] if error else []).as_dict()}
