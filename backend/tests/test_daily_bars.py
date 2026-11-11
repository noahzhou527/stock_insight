"""§5.2 acceptance tests for the incremental daily-bar cache (fake provider, pinned clock)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from backend.app.db.session import make_engine, make_session_factory, upgrade
from backend.app.providers.base import Bars, DataFetchError, Instrument, Intraday, ProviderBase, finalize_bars
from backend.app.providers.composite import CompositeProvider, Routed
from backend.app.repo import bars as repo
from backend.app.services.daily_bars import DailyBarService

SH = ZoneInfo("Asia/Shanghai")
INST = Instrument("CN", "300308.SZ")


class FakeDaily(ProviderBase):
    """Weekday bars from ``listed`` onward; close = 100 + day_number, scaled by ``factor`` before ``ex_date``."""

    def __init__(self, name="同花顺", listed=date(2020, 1, 1)):
        self.name, self.listed = name, listed
        self.calls: list[tuple[date, date]] = []
        self.factor, self.ex_date = 1.0, None
        self.fail = False

    def close_for(self, day: date) -> float:
        base = 100 + (day - date(2020, 1, 1)).days * 0.01
        return base * (self.factor if self.ex_date and day < self.ex_date else 1.0)

    def daily_bars(self, inst, start, end):
        self.calls.append((start, end))
        if self.fail:
            raise DataFetchError("network_error", "无法连接")
        rows = []
        for day in pd.bdate_range(max(start, self.listed), end):
            c = self.close_for(day.date())
            rows.append({"trade_date": day.date(), "open": c, "high": c * 1.01, "low": c * 0.99, "close": c,
                         "volume": 1000, "amount": c * 1000})
        return Bars(finalize_bars(rows, start, end), self.name, "CNY", "中际旭创")


class Clock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, **kw):
        self.value += timedelta(**kw)


@pytest.fixture
def env(tmp_path):
    engine = make_engine(tmp_path / "t.db")
    upgrade(engine)
    factory = make_session_factory(engine)
    fake = FakeDaily()
    clock = Clock(datetime(2026, 11, 11, 16, 0, tzinfo=SH))  # Wednesday, settled (close 15:00 + 30 min)
    service = DailyBarService(factory, CompositeProvider({"ths": fake}), now=clock)
    yield service, fake, clock, factory
    engine.dispose()


def get(service, start, end, **kw):
    return service.get(INST, start, end, with_provisional=False, **kw)


def stored(factory) -> pd.DataFrame:
    with factory() as session:
        return repo.load_bars(session, INST)


def test_second_identical_request_makes_no_upstream_call(env):
    service, fake, clock, _ = env
    first = get(service, date(2026, 8, 11), date(2026, 11, 11))
    assert len(fake.calls) == 1 and first.frame.index.max() == date(2026, 11, 11)
    clock.advance(minutes=10)
    second = get(service, date(2026, 8, 11), date(2026, 11, 11))
    assert len(fake.calls) == 1
    assert second.frame.equals(first.frame)
    assert second.meta.freshness == "closed"


def test_extending_range_only_requests_the_earlier_part(env):
    service, fake, _, _ = env
    get(service, date(2026, 8, 11), date(2026, 11, 11))
    get(service, date(2025, 11, 11), date(2026, 11, 11))
    assert len(fake.calls) == 2
    start, end = fake.calls[1]
    assert start == date(2025, 11, 11)
    assert end <= date(2026, 8, 11) + timedelta(days=10)  # only the head gap (+ adjustment-check overlap)


def test_shorter_request_does_not_drop_longer_history(env):
    service, fake, _, factory = env
    get(service, date(2025, 11, 11), date(2026, 11, 11))
    year_rows = len(stored(factory))
    short = get(service, date(2026, 8, 11), date(2026, 11, 11))
    assert len(fake.calls) == 1
    assert len(stored(factory)) == year_rows
    assert short.frame.index.min() >= date(2026, 8, 11)


def test_adjustment_change_triggers_full_refetch_without_mixing(env):
    service, fake, clock, factory = env
    get(service, date(2026, 1, 1), date(2026, 11, 11))
    clock.advance(days=2)  # Friday 16:00
    fake.ex_date, fake.factor = date(2026, 11, 12), 0.95  # 除权: all history before 11-12 drops 5%
    result = get(service, date(2026, 1, 1), date(2026, 11, 13))
    starts = [c[0] for c in fake.calls]
    assert starts[-1] == date(2026, 1, 1)  # full refetch from covered_start
    rows = stored(factory)
    for day, row in rows.iterrows():
        assert row["close"] == pytest.approx(fake.close_for(day)), day
    assert result.frame.index.max() == date(2026, 11, 13)
    with factory() as session:
        assert repo.get_meta(session, INST).last_full_refresh_at is not None


def test_unlisted_range_is_not_requested_again(env):
    service, fake, clock, factory = env
    fake.listed = date(2026, 6, 1)
    get(service, date(2024, 1, 1), date(2026, 11, 11))
    assert stored(factory).index.min() == date(2026, 6, 1)
    clock.advance(minutes=10)
    get(service, date(2024, 1, 1), date(2026, 11, 11))
    get(service, date(2025, 1, 1), date(2026, 11, 11))
    assert len(fake.calls) == 1


def test_intraday_request_never_stores_today(env):
    service, fake, clock, factory = env
    clock.value = datetime(2026, 11, 11, 10, 0, tzinfo=SH)  # trading session
    points = pd.DataFrame({"price": [540.0, 545.0, 542.0], "avg_price": [540.0, 542.0, 542.0],
                           "volume": [100.0, 200.0, 300.0], "amount": [54000.0, 109000.0, 162600.0]},
                          index=pd.to_datetime(["2026-11-11 09:30", "2026-11-11 09:31", "2026-11-11 09:32"]))
    intraday = Intraday(points, date(2026, 11, 11), 471.0, "同花顺", "CNY", "中际旭创")
    result = service.get(INST, date(2026, 8, 11), date(2026, 11, 11),
                         intraday=lambda inst: Routed(intraday, "同花顺", False))
    rows = stored(factory)
    assert date(2026, 11, 11) not in rows.index
    assert rows.index.max() == date(2026, 11, 10)
    today = result.frame.loc[date(2026, 11, 11)]
    assert bool(today["provisional"]) and today["close"] == 542.0 and today["high"] == 545.0 and today["volume"] == 600
    assert result.meta.freshness == "provisional" and "分时合成" in result.meta.note


# ---------------------------------------------------------------- extra behaviour

def test_upstream_failure_serves_cached_rows(env):
    service, fake, clock, _ = env
    get(service, date(2026, 8, 11), date(2026, 11, 11))
    clock.advance(days=2)
    fake.fail = True
    result = get(service, date(2026, 8, 11), date(2026, 11, 13))
    assert result.meta.freshness == "cached" and result.frame.index.max() == date(2026, 11, 11)
    assert result.meta.errors[0]["category"] == "network_error"


def test_upstream_failure_without_cache_raises(env):
    service, fake, _, _ = env
    fake.fail = True
    with pytest.raises(DataFetchError):
        get(service, date(2026, 8, 11), date(2026, 11, 11))


def test_fallback_source_is_reported_and_stored(env, tmp_path):
    _, _, clock, factory = env
    primary, backup = FakeDaily("同花顺"), FakeDaily("东方财富")
    primary.fail = True
    service = DailyBarService(factory, CompositeProvider({"ths": primary, "eastmoney": backup}), now=clock)
    result = get(service, date(2026, 8, 11), date(2026, 11, 11))
    assert result.meta.freshness == "fallback" and result.meta.source == "东方财富"
    assert set(stored(factory)["source"]) == {"东方财富"}


def test_tail_refresh_throttled_to_five_minutes(env):
    service, fake, clock, _ = env
    fake.listed = date(2020, 1, 1)
    get(service, date(2026, 8, 11), date(2026, 11, 11))
    # Simulate a lagging feed: upstream stops at 11-10 for the next check.
    clock.advance(days=1)  # Thursday 16:00, 11-12 settled
    original = fake.daily_bars
    fake.daily_bars = lambda inst, s, e: original(inst, s, min(e, date(2026, 11, 11)))
    get(service, date(2026, 8, 11), date(2026, 11, 12))
    calls = len(fake.calls)
    clock.advance(minutes=2)
    get(service, date(2026, 8, 11), date(2026, 11, 12))
    assert len(fake.calls) == calls  # within 5 minutes: no re-check
    clock.advance(minutes=4)
    get(service, date(2026, 8, 11), date(2026, 11, 12))
    assert len(fake.calls) == calls + 1  # lagging day is re-checked later
