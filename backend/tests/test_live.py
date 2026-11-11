"""Live-upstream checks for the P1 acceptance criteria. Opt-in:

    cd backend && ..\\.venv\\Scripts\\python -m pytest -m network
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.app.config import Settings
from backend.app.db.session import make_engine, make_session_factory, upgrade
from backend.app.providers.base import Instrument
from backend.app.providers.composite import build_default
from backend.app.providers.eastmoney import EastmoneyProvider
from backend.app.services.daily_bars import DailyBarService

pytestmark = pytest.mark.network


@pytest.fixture
def factory(tmp_path):
    engine = make_engine(tmp_path / "live.db")
    upgrade(engine)
    yield make_session_factory(engine)
    engine.dispose()


def test_beijing_exchange_daily_and_intraday(factory):
    inst = Instrument("CN", "920190.BJ")
    result = DailyBarService(factory, build_default()).get(inst, date.today() - timedelta(days=90), date.today())
    assert len(result.frame) > 40 and result.meta.source == "同花顺"
    assert len(build_default().intraday(inst).value.points) > 10


def test_cn_daily_without_ths_comes_from_eastmoney_in_shares(factory):
    inst = Instrument("CN", "300308.SZ")
    start, end = date.today() - timedelta(days=60), date.today()
    without_ths = DailyBarService(factory, build_default(Settings(disabled_providers=["ths"])))
    result = without_ths.get(inst, start, end, with_provisional=False)
    assert result.meta.source == "东方财富", result.meta
    ths_bars = build_default().daily_bars(inst, start, end).value.frame
    common = result.frame.index.intersection(ths_bars.index)[:-1]
    ratio = result.frame.loc[common, "volume"] / ths_bars.loc[common, "volume"]
    assert ratio.between(0.95, 1.05).all()


def test_eastmoney_intraday_reachable():
    intraday = EastmoneyProvider().intraday(Instrument("CN", "300308.SZ"))
    assert len(intraday.points) > 10
