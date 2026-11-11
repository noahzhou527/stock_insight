"""Market trading-session rules (weekdays + fixed hours, no holiday calendar).

Ported from services/market_data.py (is_market_trading_session). Pure functions:
every helper takes an aware ``now`` so tests can pin the clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MarketHours:
    tz: ZoneInfo
    sessions: tuple[tuple[time, time], ...]
    currency: str

    @property
    def close(self) -> time:
        return self.sessions[-1][1]


MARKETS: dict[str, MarketHours] = {
    "CN": MarketHours(ZoneInfo("Asia/Shanghai"), ((time(9, 30), time(11, 30)), (time(13, 0), time(15, 0))), "CNY"),
    "US": MarketHours(ZoneInfo("America/New_York"), ((time(9, 30), time(16, 0)),), "USD"),
    "KR": MarketHours(ZoneInfo("Asia/Seoul"), ((time(9, 0), time(15, 30)),), "KRW"),
}

# Daily rows dated "today" are not persisted until this long after the close (§5.2 step 5).
SETTLE_DELAY = timedelta(minutes=30)


def hours(market: str) -> MarketHours:
    try:
        return MARKETS[market.upper()]
    except KeyError:
        raise ValueError(f"unknown market: {market}") from None


def local_now(market: str, now: datetime) -> datetime:
    return now.astimezone(hours(market).tz)


def market_today(market: str, now: datetime) -> date:
    return local_now(market, now).date()


def is_trading_session(market: str, now: datetime) -> bool:
    local = local_now(market, now)
    if local.weekday() >= 5:
        return False
    return any(start <= local.time() <= end for start, end in hours(market).sessions)


def _previous_weekday(day: date) -> date:
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def is_settled(market: str, now: datetime) -> bool:
    """True once today's daily bar may be stored (weekday, close + 30 min passed)."""
    local = local_now(market, now)
    settle_at = datetime.combine(local.date(), hours(market).close, tzinfo=local.tzinfo) + SETTLE_DELAY
    return local.weekday() < 5 and local >= settle_at


def last_settled_trading_day(market: str, now: datetime) -> date:
    """Most recent weekday whose daily bar is final (today only after close + 30 min)."""
    today = market_today(market, now)
    if is_settled(market, now):
        return today
    return _previous_weekday(today)


def first_unsettled_day(market: str, now: datetime) -> date:
    """Rows dated on/after this day must not be persisted yet."""
    return last_settled_trading_day(market, now) + timedelta(days=1)
