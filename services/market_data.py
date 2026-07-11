from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from data_fetcher import (
    fetch_a_share_financial_reports,
    fetch_a_share_intraday,
    fetch_a_share_valuation,
    fetch_stock_data,
    fetch_us_market_cap,
)


def is_a_share_trading_session() -> bool:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.weekday() >= 5:
        return False
    current = now.time()
    return (
        datetime.strptime("09:30", "%H:%M").time()
        <= current
        <= datetime.strptime("11:30", "%H:%M").time()
    ) or (
        datetime.strptime("13:00", "%H:%M").time()
        <= current
        <= datetime.strptime("15:00", "%H:%M").time()
    )


@st.cache_data(ttl=3600, show_spinner=False)
def load_data(ticker, start, end, market, ths_access_token):
    return fetch_stock_data(ticker, start, end, market=market, ths_access_token=ths_access_token)


def indicator_warmup_start(display_start, ma_periods, rsi_period, show_bbi, show_boll):
    """Request enough earlier data to calculate indicators at the left edge."""
    required_sessions = [35, rsi_period + 1, *ma_periods]
    if show_bbi:
        required_sessions.append(24)
    if show_boll:
        required_sessions.append(20)
    return (pd.Timestamp(display_start).normalize() - pd.offsets.BDay(max(required_sessions) + 15)).date()


def trim_to_display_range(frame, display_start, display_end):
    """Trim data while retaining data-provider metadata."""
    attrs = frame.attrs.copy()
    start, end = pd.Timestamp(display_start), pd.Timestamp(display_end)
    trimmed = frame.loc[(frame.index >= start) & (frame.index <= end)].copy()
    trimmed.attrs.update(attrs)
    return trimmed


@st.cache_data(ttl=300, show_spinner=False)
def load_valuation(ticker, cache_version=4):
    return fetch_a_share_valuation(ticker)


@st.cache_data(ttl=300, show_spinner=False)
def load_us_market_cap(ticker):
    return fetch_us_market_cap(ticker)


@st.cache_data(ttl=21600, show_spinner=False)
def load_financial_reports(ticker):
    return fetch_a_share_financial_reports(ticker)


@st.cache_data(ttl=25, show_spinner=False)
def load_intraday(ticker):
    return fetch_a_share_intraday(ticker)
