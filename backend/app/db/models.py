"""SQLAlchemy models — schema per docs/plan-b-draft.md §5.1.

Timestamps (``*_at``) are naive UTC. Dates (``trade_date`` etc.) are market-local.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Instrument(Base):
    __tablename__ = "instruments"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # "CN:300308.SZ"
    market: Mapped[str] = mapped_column(String(4))
    symbol: Mapped[str] = mapped_column(String)
    name: Mapped[str | None] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    name_updated_at: Mapped[datetime | None] = mapped_column(DateTime)


class UniverseGroup(Base):
    __tablename__ = "universe_groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class UniverseMember(Base):
    __tablename__ = "universe_members"
    group_id: Mapped[int] = mapped_column(ForeignKey("universe_groups.id", ondelete="CASCADE"), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class DailyBar(Base):
    __tablename__ = "daily_bars"
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)  # 股
    amount: Mapped[float | None] = mapped_column(Float)
    amount_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class BarsMeta(Base):
    __tablename__ = "bars_meta"
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    adj: Mapped[str] = mapped_column(String, default="qfq")
    covered_start: Mapped[date] = mapped_column(Date)
    covered_end: Mapped[date] = mapped_column(Date)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_full_refresh_at: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str | None] = mapped_column(String)


class FinancialReport(Base):
    __tablename__ = "financial_reports"
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    period_end: Mapped[date] = mapped_column(Date, primary_key=True)
    report_type: Mapped[str] = mapped_column(String, primary_key=True)  # annual / q1 / h1 / q3 / quarterly
    metric: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class PayloadCache(Base):
    __tablename__ = "payload_cache"
    resource: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)


class NewsItem(Base):
    __tablename__ = "news_items"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    url: Mapped[str | None] = mapped_column(String)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    observed_at: Mapped[datetime] = mapped_column(DateTime)


class Watchlist(Base):
    __tablename__ = "watchlists"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class UserPref(Base):
    __tablename__ = "user_prefs"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)


class FetchLog(Base):
    __tablename__ = "fetch_log"
    __table_args__ = (Index("ix_fetch_log_provider_started", "provider", "started_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String)
    resource: Mapped[str] = mapped_column(String)
    key: Mapped[str | None] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)  # ok / error
    error_category: Mapped[str | None] = mapped_column(String)
    error_message: Mapped[str | None] = mapped_column(Text)
