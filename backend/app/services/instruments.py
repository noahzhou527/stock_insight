"""Instrument lookup, search, and stock-pool groups."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Instrument as InstrumentRow
from ..db.models import UniverseGroup, UniverseMember, WatchlistItem
from ..domain.tickers import TickerFormatError, parse_any
from ..providers.base import Instrument
from ..repo import bars as repo

DEFAULT_WATCHLIST_ID = 1
SEARCH_LIMIT = 20


def row_dict(row: InstrumentRow) -> dict:
    return {"id": row.id, "market": row.market, "symbol": row.symbol, "name": row.name, "currency": row.currency}


class InstrumentService:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def search(self, query: str) -> list[dict]:
        """Local fuzzy match on name / symbol first; otherwise one unverified parsed candidate."""
        text = query.strip()
        if not text:
            return []
        with self.session_factory() as session:
            like = f"%{text}%"
            rows = session.scalars(
                select(InstrumentRow).where(or_(InstrumentRow.name.like(like), InstrumentRow.symbol.like(f"%{text.upper()}%")))
                .order_by(InstrumentRow.market, InstrumentRow.symbol).limit(SEARCH_LIMIT)
            ).all()
            results = [{**row_dict(r), "verified": True} for r in rows]
        try:
            parsed = parse_any(text)
        except TickerFormatError:
            return results
        if not any(r["id"] == parsed.id for r in results):
            with self.session_factory() as session:
                known = session.get(InstrumentRow, parsed.id)
            candidate = {**row_dict(known), "verified": True} if known else {
                "id": parsed.id, "market": parsed.market, "symbol": parsed.symbol, "name": None,
                "currency": parsed.currency, "verified": False}
            results.insert(0, candidate)
        return results

    def info(self, inst: Instrument) -> dict:
        with self.session_factory() as session:
            row = session.get(InstrumentRow, inst.id)
            groups = session.scalars(
                select(UniverseGroup.name).join(UniverseMember, UniverseMember.group_id == UniverseGroup.id)
                .where(UniverseMember.instrument_id == inst.id).order_by(UniverseGroup.sort_order)
            ).all()
            in_watchlist = session.get(WatchlistItem, (DEFAULT_WATCHLIST_ID, inst.id)) is not None
            meta = repo.get_meta(session, inst)
            base = row_dict(row) if row else {"id": inst.id, "market": inst.market, "symbol": inst.symbol, "name": None,
                                              "currency": inst.currency}
            return {**base, "groups": list(groups), "in_watchlist": in_watchlist, "known": row is not None,
                    "history_start": meta.covered_start if meta else None}

    def update_name(self, inst: Instrument, name: str | None) -> None:
        """Record the provider's name. A 股 names (同花顺 / 东方财富) are Chinese and authoritative;
        for 美股 / 韩股 the provider returns English names, so they only fill an empty name and never
        replace a curated Chinese one (e.g. 三星电子)."""
        if not name:
            return
        with self.session_factory() as session:
            row = session.get(InstrumentRow, inst.id)
            if row is not None and row.name and inst.market != "CN":
                return
            repo.ensure_instrument(session, inst, name)
            session.commit()

    def name_of(self, inst: Instrument) -> str | None:
        with self.session_factory() as session:
            row = session.get(InstrumentRow, inst.id)
            return row.name if row else None

    def universe(self) -> list[dict]:
        with self.session_factory() as session:
            groups = session.scalars(select(UniverseGroup).order_by(UniverseGroup.sort_order, UniverseGroup.id)).all()
            result = []
            for group in groups:
                members = session.execute(
                    select(InstrumentRow).join(UniverseMember, UniverseMember.instrument_id == InstrumentRow.id)
                    .where(UniverseMember.group_id == group.id).order_by(UniverseMember.sort_order)
                ).scalars().all()
                result.append({"id": group.id, "name": group.name, "members": [row_dict(m) for m in members]})
            return result

    def peer_group(self, inst: Instrument) -> tuple[str, list[Instrument], dict[str, str | None]] | None:
        """First A-share stock-pool group containing ``inst``: (group name, members, names)."""
        if inst.market != "CN":
            return None
        with self.session_factory() as session:
            group = session.scalar(
                select(UniverseGroup).join(UniverseMember, UniverseMember.group_id == UniverseGroup.id)
                .where(UniverseMember.instrument_id == inst.id).order_by(UniverseGroup.sort_order)
            )
            if group is None:
                return None
            rows = session.execute(
                select(InstrumentRow).join(UniverseMember, UniverseMember.instrument_id == InstrumentRow.id)
                .where(UniverseMember.group_id == group.id, InstrumentRow.market == "CN").order_by(UniverseMember.sort_order)
            ).scalars().all()
            return group.name, [Instrument(r.market, r.symbol) for r in rows], {r.id: r.name for r in rows}

    def cn_universe(self) -> list[tuple[Instrument, str | None, str]]:
        """Every A-share stock-pool member once: (instrument, name, first group name)."""
        seen: dict[str, tuple[Instrument, str | None, str]] = {}
        for group in self.universe():
            for member in group["members"]:
                if member["market"] == "CN" and member["id"] not in seen:
                    seen[member["id"]] = (Instrument("CN", member["symbol"]), member["name"], group["name"])
        return list(seen.values())
