from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from data_fetcher import (
    DataFetchError,
    fetch_a_share_financial_reports,
    fetch_a_share_intraday,
    fetch_yahoo_intraday,
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


def is_market_trading_session(market: str) -> bool:
    """Return whether the selected market is in its regular trading session."""
    market = market.upper()
    if market == "CN":
        return is_a_share_trading_session()
    timezone, start, end = {
        "US": ("America/New_York", "09:30", "16:00"),
        "KR": ("Asia/Seoul", "09:00", "15:30"),
    }.get(market, (None, None, None))
    if timezone is None:
        return False
    now = datetime.now(ZoneInfo(timezone))
    if now.weekday() >= 5:
        return False
    return datetime.strptime(start, "%H:%M").time() <= now.time() <= datetime.strptime(end, "%H:%M").time()


@st.cache_data(ttl=3600, show_spinner=False)
def load_historical_data(ticker, start, end, market, ths_access_token):
    """Load provider daily bars, which can lag the active trading session."""
    return fetch_stock_data(ticker, start, end, market=market, ths_access_token=ths_access_token)


def _intraday_daily_bar(intraday: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the latest intraday session into one provisional OHLCV bar."""
    if intraday is None or intraday.empty or "Price" not in intraday.columns:
        return pd.DataFrame()

    prices = pd.to_numeric(intraday["Price"], errors="coerce").dropna()
    if prices.empty:
        return pd.DataFrame()

    trade_date = intraday.attrs.get("trade_date") or intraday.index[-1]
    index = pd.DatetimeIndex([pd.Timestamp(trade_date).normalize()])
    raw_volume = intraday["Volume"] if "Volume" in intraday else pd.Series(0.0, index=intraday.index)
    volume = pd.to_numeric(raw_volume, errors="coerce").fillna(0)
    if "Amount" in intraday:
        amount = pd.to_numeric(intraday["Amount"], errors="coerce").fillna(0)
    else:
        amount = prices.reindex(intraday.index).fillna(0) * volume
    return pd.DataFrame(
        {
            "Open": [float(prices.iloc[0])],
            "High": [float(prices.max())],
            "Low": [float(prices.min())],
            "Close": [float(prices.iloc[-1])],
            "Volume": [float(volume.sum())],
            "Amount": [float(amount.sum())],
        },
        index=index,
    )


def merge_intraday_daily_bar(
    historical: pd.DataFrame,
    intraday: pd.DataFrame,
    end_date,
) -> pd.DataFrame:
    """Add or replace the selected range's newest day with an intraday bar."""
    bar = _intraday_daily_bar(intraday)
    if bar.empty or bar.index[-1] > pd.Timestamp(end_date).normalize():
        return historical

    result = pd.concat([historical, bar], sort=False)
    result.index = pd.to_datetime(result.index).normalize()
    result = result[~result.index.duplicated(keep="last")].sort_index()
    result.attrs.update(historical.attrs)
    result.attrs["includes_intraday_daily_bar"] = True
    return result


def load_data(ticker, start, end, market, ths_access_token):
    """Load daily history and overlay the latest available intraday session."""
    historical_error = None
    try:
        historical = load_historical_data(ticker, start, end, market, ths_access_token)
    except DataFetchError as error:
        historical_error = error
        historical = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "Amount"])

    try:
        intraday = load_intraday(ticker, market)
    except DataFetchError:
        if historical_error is not None:
            raise historical_error
        return historical

    result = merge_intraday_daily_bar(historical, intraday, end)
    if result.empty and historical_error is not None:
        raise historical_error
    return result


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
def load_valuation(ticker, cache_version=5):
    return fetch_a_share_valuation(ticker)


@st.cache_data(ttl=300, show_spinner=False)
def load_us_market_cap(ticker):
    return fetch_us_market_cap(ticker)


@st.cache_data(ttl=21600, show_spinner=False)
def load_financial_reports(ticker):
    return fetch_a_share_financial_reports(ticker)


@st.cache_data(ttl=25, show_spinner=False)
def load_intraday(ticker, market="CN"):
    """Load the latest intraday bars using the provider for the selected market."""
    if market.upper() == "CN":
        return fetch_a_share_intraday(ticker)
    return fetch_yahoo_intraday(ticker, market)
