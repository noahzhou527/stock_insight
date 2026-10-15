from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from data_fetcher import DataFetchError
from ifind_data import (
    calendar,
    financial_reports as fetch_a_share_financial_reports,
    intraday as fetch_a_share_intraday,
    intraday as fetch_yahoo_intraday,
    valuation as fetch_a_share_valuation,
    historical as fetch_stock_data,
    market_cap as fetch_us_market_cap,
    financial_reports as fetch_yahoo_financial_reports,
    krw_usd_rate as fetch_krw_usd_rate,
)
from ifind_data import _cache_path, _read_frame, _write_frame


@st.cache_data(ttl=86400, show_spinner=False)
def load_a_share_trade_dates(year: int) -> pd.DatetimeIndex:
    """Use the official exchange calendar, retaining a verified disk copy."""
    path = _cache_path("calendar", str(year))
    cached, meta = _read_frame(path)
    today = str(pd.Timestamp.now(tz="Asia/Shanghai").date())
    if not cached.empty and meta.get("checked_date") == today:
        return pd.DatetimeIndex(cached.index).normalize()
    try:
        dates = calendar(f"{year}-01-01", f"{year}-12-31", "CN").normalize()
        _write_frame(path, pd.DataFrame({"trading": True}, index=dates.rename("Date")), checked_date=today)
        return dates
    except DataFetchError:
        if not cached.empty:
            return pd.DatetimeIndex(cached.index).normalize()
        return pd.DatetimeIndex([])


def a_share_session_state(now=None) -> dict:
    now = pd.Timestamp(now if now is not None else datetime.now(ZoneInfo("Asia/Shanghai")))
    now = now.tz_localize("Asia/Shanghai") if now.tzinfo is None else now.tz_convert("Asia/Shanghai")
    day = now.tz_localize(None).normalize()
    try:
        dates = load_a_share_trade_dates(now.year)
        if dates.empty:
            return {"trading": False, "label": "交易日历暂不可用 · 自动刷新暂停", "calendar_ok": False}
        if day not in dates:
            return {"trading": False, "label": "休市 · 非交易日", "calendar_ok": True}
    except DataFetchError:
        return {"trading": False, "label": "交易日历暂不可用 · 自动刷新暂停", "calendar_ok": False}
    clock = now.strftime("%H:%M:%S")
    trading = "09:30:00" <= clock < "11:30:00" or "13:00:00" <= clock < "15:00:00"
    label = "交易中" if trading else "09:30 开盘" if clock < "09:30:00" else "13:00 开盘" if clock < "13:00:00" else "已收盘"
    return {"trading": trading, "label": label, "calendar_ok": True}


def is_a_share_trading_session() -> bool:
    return a_share_session_state()["trading"]


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


@st.cache_data(ttl=300, show_spinner=False)
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
        # This is a provisional sum of minute-level turnover. Provider update
        # timing and precision can make it differ slightly from the finalized
        # daily value; after-hours turnover is already provider-supplied and
        # must not be added again.
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
    if intraday.attrs.get("symbol_name"):
        result.attrs["symbol_name"] = intraday.attrs["symbol_name"]
    return result


def historical_data_lags_intraday(historical: pd.DataFrame, intraday: pd.DataFrame) -> bool:
    """Return whether daily history is missing at least one completed session."""
    if historical.empty or intraday is None or intraday.empty:
        return False
    trade_date = intraday.attrs.get("trade_date")
    if not trade_date:
        return False
    latest_daily_date = pd.Timestamp(historical.index[-1]).normalize()
    latest_completed_date = pd.Timestamp(trade_date).normalize() - pd.offsets.BDay(1)
    return latest_daily_date < latest_completed_date


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

    if market.upper() == "CN" and historical_data_lags_intraday(historical, intraday):
        try:
            load_historical_data.clear()
            historical = load_historical_data(ticker, start, end, market, ths_access_token)
        except DataFetchError:
            pass

    result = merge_intraday_daily_bar(historical, intraday, end)
    trade_date = pd.Timestamp(intraday.attrs.get("trade_date", intraday.index[-1])).normalize()
    if not historical.empty and historical.index[-1].normalize() >= trade_date and not is_market_trading_session(market):
        if intraday.attrs.get("symbol_name"):
            historical.attrs["symbol_name"] = intraday.attrs["symbol_name"]
        return historical
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


@st.cache_data(ttl=3600, show_spinner=False)
def load_chart_sessions(start, end, market):
    """Use benchmark trading dates to size the chart, without padding stock data."""
    return calendar(start, end, market)


@st.cache_data(ttl=300, show_spinner=False)
def load_valuation(ticker, cache_version=5):
    return fetch_a_share_valuation(ticker)


@st.cache_data(ttl=300, show_spinner=False)
def load_us_market_cap(ticker):
    return fetch_us_market_cap(ticker)


@st.cache_data(ttl=21600, show_spinner=False)
def load_financial_reports(ticker, market="CN", cache_version=2):
    """Load financial reports, with a versioned cache for parser upgrades."""
    if market.upper() == "CN":
        return fetch_a_share_financial_reports(ticker)
    return fetch_yahoo_financial_reports(ticker, market)


@st.cache_data(ttl=3600, show_spinner=False)
def load_krw_usd_rate():
    return fetch_krw_usd_rate()


@st.cache_data(ttl=25, show_spinner=False)
def load_intraday(ticker, market="CN"):
    """Load the latest intraday bars using the provider for the selected market."""
    if market.upper() == "CN":
        return fetch_a_share_intraday(ticker)
    return fetch_yahoo_intraday(ticker, market)
