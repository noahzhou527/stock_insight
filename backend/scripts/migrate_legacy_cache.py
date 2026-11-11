"""Import the Streamlit-era cache into SQLite (docs/plan-b-draft.md §5.3).

Run from repo root:  .venv\\Scripts\\python -m backend.scripts.migrate_legacy_cache [--db PATH]

- Read-only towards ``data/cache/`` (README 缓存保留政策): nothing is moved or deleted.
- Idempotent: re-running inserts nothing twice. An instrument whose bars have already been
  refreshed from a live source is skipped (its legacy CSV may be on an older 复权 basis).
- Legacy Python config files are parsed with ``ast`` (not imported) and skipped if absent.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import REPO_ROOT, get_settings
from backend.app.db.models import UniverseGroup, UniverseMember, Watchlist, WatchlistItem
from backend.app.db.session import make_engine, make_session_factory, upgrade, utcnow
from backend.app.domain import sessions
from backend.app.providers.base import Instrument, finalize_bars
from backend.app.repo import bars as repo

LEGACY_SOURCE = "legacy-cache"
NON_TICKER_FILES = {"a_share_market_snapshot"}
CN_FILE = re.compile(r"^(\d{6})_(SH|SZ|BJ)$")
KR_FILE = re.compile(r"^(\d{6})_(KS|KQ)$")
LABEL = re.compile(r"^(.*?)\s*\(([^)]+)\)\s*$")


@dataclass
class Report:
    instruments: int = 0
    groups: int = 0
    members: int = 0
    watchlist_items: int = 0
    files: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def instrument_for_file(stem: str) -> Instrument | None:
    if stem in NON_TICKER_FILES:
        return None
    if m := CN_FILE.match(stem):
        return Instrument("CN", f"{m.group(1)}.{m.group(2)}")
    if m := KR_FILE.match(stem):
        return Instrument("KR", f"{m.group(1)}.{m.group(2)}")
    if stem.startswith("_"):  # sanitised index symbols (^GSPC → _GSPC) are not stock caches
        return None
    return Instrument("US", stem.replace("_", "-"))  # BRK_B → BRK-B


def instrument_for_ticker(ticker: str) -> Instrument:
    ticker = ticker.strip().upper()
    suffix = ticker.rsplit(".", 1)[-1] if "." in ticker else ""
    if suffix in {"SH", "SZ", "BJ"}:
        return Instrument("CN", ticker)
    if suffix in {"KS", "KQ"}:
        return Instrument("KR", ticker)
    return Instrument("US", ticker)


def literal_assignments(path: Path, names: set[str]) -> dict:
    if not path.exists():
        return {}
    found = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    found[target.id] = ast.literal_eval(node.value)
    return found


def read_csv(path: Path, inst: Instrument) -> pd.DataFrame:
    raw = pd.read_csv(path)
    raw.columns = [str(c).lower() for c in raw.columns]
    rows = raw.rename(columns={"date": "trade_date"}).to_dict("records")
    for row in rows:
        row.setdefault("amount", None)
        # Yahoo never supplied turnover; legacy filled close × volume.
        row["amount_estimated"] = inst.market != "CN"
    return finalize_bars(rows)


def migrate(root: Path, session: Session, now: datetime | None = None) -> Report:
    now = now or datetime.now(timezone.utc)
    report = Report()
    cache = root / "data" / "cache"

    def add_instrument(inst: Instrument, name: str | None) -> None:
        existed = session.get(repo.InstrumentRow, inst.id) is not None
        row = repo.ensure_instrument(session, inst)
        if name and not row.name:
            row.name = name
        report.instruments += 0 if existed else 1

    # 股票池
    universe = literal_assignments(root / "a_share_universe.py", {"A_SHARE_UNIVERSE"}).get("A_SHARE_UNIVERSE", {})
    for group_order, (group_name, members) in enumerate(universe.items()):
        group = session.scalar(select(UniverseGroup).where(UniverseGroup.name == group_name))
        if group is None:
            group = UniverseGroup(name=group_name, sort_order=group_order)
            session.add(group)
            session.flush()
            report.groups += 1
        for order, (name, ticker) in enumerate(members):
            inst = instrument_for_ticker(ticker)
            add_instrument(inst, name)
            if session.get(UniverseMember, (group.id, inst.id)) is None:
                session.add(UniverseMember(group_id=group.id, instrument_id=inst.id, sort_order=order))
                report.members += 1

    # 美股、韩股常用清单 → 两个分组（侧栏按分组展示）
    options = literal_assignments(root / "app_config.py", {"US_TICKER_OPTIONS", "KR_TICKER_OPTIONS"})
    for offset, (market_key, market, group_name) in enumerate((("US_TICKER_OPTIONS", "US", "美股常用"),
                                                               ("KR_TICKER_OPTIONS", "KR", "韩股常用"))):
        labels = [(label, ticker) for label, ticker in options.get(market_key, {}).items() if ticker != "CUSTOM"]
        if not labels:
            continue
        group = session.scalar(select(UniverseGroup).where(UniverseGroup.name == group_name))
        if group is None:
            group = UniverseGroup(name=group_name, sort_order=1000 + offset)
            session.add(group)
            session.flush()
            report.groups += 1
        for order, (label, ticker) in enumerate(labels):
            match = LABEL.match(label)
            inst = Instrument(market, ticker)
            add_instrument(inst, match.group(1) if match else label)
            if session.get(UniverseMember, (group.id, inst.id)) is None:
                session.add(UniverseMember(group_id=group.id, instrument_id=inst.id, sort_order=order))
                report.members += 1

    # 自选
    watch_path = cache / "watchlist.json"
    if watch_path.exists():
        watchlist = session.get(Watchlist, 1)
        if watchlist is None:
            watchlist = Watchlist(id=1, name="默认", sort_order=0)
            session.add(watchlist)
            session.flush()
        items = json.loads(watch_path.read_text(encoding="utf-8")).get("items", [])
        for order, item in enumerate(items):
            inst = instrument_for_ticker(item["ticker"])
            add_instrument(inst, item.get("name") or None)
            if session.get(WatchlistItem, (1, inst.id)) is None:
                session.add(WatchlistItem(watchlist_id=1, instrument_id=inst.id, added_at=utcnow(), sort_order=order))
                report.watchlist_items += 1

    # 日线 CSV
    for path in sorted(cache.glob("*.csv")):
        inst = instrument_for_file(path.stem)
        if inst is None:
            continue
        meta = repo.get_meta(session, inst)
        if meta is not None and meta.source != LEGACY_SOURCE:
            report.skipped.append(f"{path.name}: 已有来自 {meta.source} 的数据，跳过")
            continue
        frame = read_csv(path, inst)
        csv_rows = len(pd.read_csv(path))
        frame = frame[frame.index < sessions.first_unsettled_day(inst.market, now)]
        if frame.empty:
            report.skipped.append(f"{path.name}: 没有可导入的行")
            continue
        add_instrument(inst, None)
        repo.upsert_bars(session, inst, frame, LEGACY_SOURCE, overwrite=False)
        if meta is None:
            repo.save_meta(session, inst, covered_start=frame.index.min(), covered_end=frame.index.max(),
                           last_checked_at=None, last_full_refresh_at=None, source=LEGACY_SOURCE)
        session.flush()
        report.files.append({"file": path.name, "instrument": inst.id, "csv_rows": csv_rows,
                             "imported_rows": len(frame), "db_rows": repo.count_bars(session, inst)})
    session.commit()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把旧版 data/cache 导入 SQLite（只读不删，可重复执行）")
    parser.add_argument("--db", type=Path, default=get_settings().db_path)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    engine = make_engine(args.db)
    upgrade(engine)
    with make_session_factory(engine)() as session:
        report = migrate(args.root, session)
    engine.dispose()

    print(f"数据库：{args.db}")
    print(f"新增标的 {report.instruments}，股票池分组 {report.groups}，成员 {report.members}，自选 {report.watchlist_items}")
    mismatched = 0
    for item in report.files:
        ok = item["db_rows"] == item["csv_rows"]
        mismatched += not ok
        print(f"  {'✓' if ok else '≠'} {item['file']:<22} {item['instrument']:<16} CSV {item['csv_rows']:>4} 行 → 库 {item['db_rows']:>4} 行")
    for line in report.skipped:
        print(f"  - {line}")
    return 1 if mismatched else 0


if __name__ == "__main__":
    sys.exit(main())
