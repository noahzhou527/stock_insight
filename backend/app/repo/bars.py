"""Daily bars / bars_meta / instruments persistence."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ..db.models import BarsMeta, DailyBar
from ..db.models import Instrument as InstrumentRow
from ..db.session import utcnow
from ..providers.base import BAR_COLUMNS, Instrument, empty_bars_frame


def ensure_instrument(session: Session, inst: Instrument, name: str | None = None) -> InstrumentRow:
    row = session.get(InstrumentRow, inst.id)
    now = utcnow()
    if row is None:
        row = InstrumentRow(id=inst.id, market=inst.market, symbol=inst.symbol, name=name, currency=inst.currency,
                            created_at=now, name_updated_at=now if name else None)
        session.add(row)
        session.flush()
    elif name and row.name != name:
        row.name, row.name_updated_at = name, now
    return row


def get_meta(session: Session, inst: Instrument) -> BarsMeta | None:
    return session.get(BarsMeta, inst.id)


def save_meta(session: Session, inst: Instrument, **fields) -> BarsMeta:
    meta = session.get(BarsMeta, inst.id)
    if meta is None:
        meta = BarsMeta(instrument_id=inst.id, adj="qfq", **fields)
        session.add(meta)
    else:
        for key, value in fields.items():
            setattr(meta, key, value)
    session.flush()
    return meta


def load_bars(session: Session, inst: Instrument, start: date | None = None, end: date | None = None) -> pd.DataFrame:
    query = select(DailyBar).where(DailyBar.instrument_id == inst.id)
    if start is not None:
        query = query.where(DailyBar.trade_date >= start)
    if end is not None:
        query = query.where(DailyBar.trade_date <= end)
    rows = session.scalars(query.order_by(DailyBar.trade_date)).all()
    if not rows:
        frame = empty_bars_frame()
        frame["source"] = pd.Series(dtype=object)
        return frame
    frame = pd.DataFrame([{**{c: getattr(r, c) for c in BAR_COLUMNS}, "trade_date": r.trade_date, "source": r.source} for r in rows])
    return frame.set_index("trade_date")


def upsert_bars(session: Session, inst: Instrument, frame: pd.DataFrame, source: str, fetched_at: datetime | None = None,
                *, overwrite: bool = True) -> int:
    if frame.empty:
        return 0
    fetched_at = fetched_at or utcnow()
    records = [
        {
            "instrument_id": inst.id, "trade_date": trade_date,
            "open": float(r.open), "high": float(r.high), "low": float(r.low), "close": float(r.close),
            "volume": None if pd.isna(r.volume) else float(r.volume),
            "amount": None if pd.isna(r.amount) else float(r.amount),
            "amount_estimated": bool(r.amount_estimated), "source": source, "fetched_at": fetched_at,
        }
        for trade_date, r in frame.iterrows()
    ]
    for offset in range(0, len(records), 500):
        stmt = insert(DailyBar).values(records[offset : offset + 500])
        if overwrite:
            stmt = stmt.on_conflict_do_update(
                index_elements=["instrument_id", "trade_date"],
                set_={c: stmt.excluded[c] for c in ("open", "high", "low", "close", "volume", "amount", "amount_estimated", "source", "fetched_at")},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=["instrument_id", "trade_date"])
        session.execute(stmt)
    return len(records)


def delete_bars(session: Session, inst: Instrument) -> None:
    session.execute(delete(DailyBar).where(DailyBar.instrument_id == inst.id))


def count_bars(session: Session, inst: Instrument) -> int:
    from sqlalchemy import func

    return session.scalar(select(func.count()).select_from(DailyBar).where(DailyBar.instrument_id == inst.id)) or 0
