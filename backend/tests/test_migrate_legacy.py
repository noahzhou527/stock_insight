from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from backend.app.db.models import UniverseMember, WatchlistItem
from backend.app.db.session import make_engine, make_session_factory, upgrade
from backend.app.providers.base import Instrument
from backend.app.repo import bars as repo
from backend.scripts.migrate_legacy_cache import instrument_for_file, migrate

NOW = datetime(2026, 11, 11, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.mark.parametrize("stem, expected", [
    ("300308_SZ", "CN:300308.SZ"), ("920190_BJ", "CN:920190.BJ"), ("005930_KS", "KR:005930.KS"),
    ("AAPL", "US:AAPL"), ("BRK_B", "US:BRK-B"), ("a_share_market_snapshot", None), ("_GSPC", None),
])
def test_file_mapping(stem, expected):
    inst = instrument_for_file(stem)
    assert (inst.id if inst else None) == expected


@pytest.fixture
def legacy_root(tmp_path):
    cache = tmp_path / "data" / "cache"
    cache.mkdir(parents=True)
    (cache / "300308_SZ.csv").write_text(
        "Date,Open,High,Low,Close,Volume,Amount\n2026-11-09,1,2,0.5,1.5,100,150\n2026-11-10,1,2,0.5,1.6,100,160\n"
        "2026-11-11,1,2,0.5,1.7,100,170\n", encoding="utf-8")
    (cache / "AAPL.csv").write_text("Date,Open,High,Low,Close,Volume,Amount\n2026-11-10,1,2,0.5,1.5,100,150\n", encoding="utf-8")
    (cache / "a_share_market_snapshot.csv").write_text("industry,name\nx,y\n", encoding="utf-8")
    (cache / "watchlist.json").write_text('{"items": [{"ticker": "300308.SZ", "name": "中际旭创"}]}', encoding="utf-8")
    (tmp_path / "a_share_universe.py").write_text(
        'A_SHARE_UNIVERSE = {"CPO": [("中际旭创", "300308.SZ"), ("新易盛", "300502.SZ")], "AI PC": [("雷神科技", "920190.BJ")]}\n',
        encoding="utf-8")
    (tmp_path / "app_config.py").write_text(
        'import streamlit as st\nUS_TICKER_OPTIONS = {"Apple (AAPL)": "AAPL", "Custom Input": "CUSTOM"}\n'
        'KR_TICKER_OPTIONS = {"三星电子 (005930.KS)": "005930.KS"}\n', encoding="utf-8")
    return tmp_path


def test_migrate_is_complete_and_idempotent(legacy_root, tmp_path):
    engine = make_engine(tmp_path / "db" / "m.db")
    upgrade(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        report = migrate(legacy_root, session, NOW)
    by_file = {f["file"]: f for f in report.files}
    assert by_file["300308_SZ.csv"]["db_rows"] == by_file["300308_SZ.csv"]["csv_rows"] == 3
    assert by_file["AAPL.csv"]["db_rows"] == 1
    assert report.groups == 2 and report.members == 3 and report.watchlist_items == 1
    with factory() as session:
        inst = Instrument("CN", "300308.SZ")
        meta = repo.get_meta(session, inst)
        assert (meta.covered_start, meta.covered_end, meta.source) == (date(2026, 11, 9), date(2026, 11, 11), "legacy-cache")
        assert session.get(repo.InstrumentRow, "US:AAPL").name == "Apple"
        assert session.get(repo.InstrumentRow, "KR:005930.KS").name == "三星电子"
        assert repo.load_bars(session, Instrument("US", "AAPL"))["amount_estimated"].all()
    with factory() as session:
        again = migrate(legacy_root, session, NOW)
        assert again.instruments == again.groups == again.members == again.watchlist_items == 0
        assert session.scalar(select(func.count()).select_from(UniverseMember)) == 3
        assert session.scalar(select(func.count()).select_from(WatchlistItem)) == 1
        assert repo.count_bars(session, Instrument("CN", "300308.SZ")) == 3
    assert (legacy_root / "data" / "cache" / "300308_SZ.csv").exists()  # read-only towards the cache
    engine.dispose()


def test_migrate_skips_today_before_settlement_and_live_refreshed_instruments(legacy_root, tmp_path):
    engine = make_engine(tmp_path / "db" / "m.db")
    upgrade(engine)
    factory = make_session_factory(engine)
    trading = datetime(2026, 11, 11, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    with factory() as session:
        report = migrate(legacy_root, session, trading)
        assert {f["file"]: f["db_rows"] for f in report.files}["300308_SZ.csv"] == 2  # 11-11 not settled yet
        repo.save_meta(session, Instrument("US", "AAPL"), source="Yahoo")
        session.commit()
        again = migrate(legacy_root, session, NOW)
        assert any("AAPL.csv" in line for line in again.skipped)
    engine.dispose()
