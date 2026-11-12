"""Built-in stock pool (股票池 + 美股、韩股常用清单) written into an empty database on first start."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import UniverseGroup, UniverseMember
from ..providers.base import Instrument
from ..repo import bars as repo

UNIVERSE_FILE = Path(__file__).with_name("universe.json")
NON_CN_GROUP_ORDER = 1000  # 美股、韩股常用排在 A 股分组之后


def load_universe(path: Path = UNIVERSE_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["groups"]


def seed_universe(session: Session, groups: list[dict] | None = None) -> tuple[int, int]:
    """Idempotently add groups and members by name. Returns (new groups, new members). Does not commit."""
    groups = load_universe() if groups is None else groups
    new_groups = new_members = 0
    cn_order = other_order = 0
    for spec in groups:
        market = spec.get("market", "CN")
        if market == "CN":
            order, cn_order = cn_order, cn_order + 1
        else:
            order, other_order = NON_CN_GROUP_ORDER + other_order, other_order + 1
        group = session.scalar(select(UniverseGroup).where(UniverseGroup.name == spec["name"]))
        if group is None:
            group = UniverseGroup(name=spec["name"], sort_order=order)
            session.add(group)
            session.flush()
            new_groups += 1
        for position, member in enumerate(spec["members"]):
            inst = Instrument(market, member["symbol"])
            row = repo.ensure_instrument(session, inst)
            if member.get("name") and not row.name:
                row.name = member["name"]
            if session.get(UniverseMember, (group.id, inst.id)) is None:
                session.add(UniverseMember(group_id=group.id, instrument_id=inst.id, sort_order=position))
                new_members += 1
    session.flush()
    return new_groups, new_members


def seed_if_empty(session: Session) -> bool:
    """First start only: once any group exists, the database is the source of truth."""
    if session.scalar(select(func.count()).select_from(UniverseGroup)):
        return False
    seed_universe(session)
    session.commit()
    return True
