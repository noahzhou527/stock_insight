"""Optional watchlist fields, requested only when their columns are visible."""
import numpy as np
import pandas as pd
import streamlit as st

from data_fetcher import DataFetchError
from ifind_data import quotes, historical, _last, _number


@st.cache_data(ttl=60, show_spinner=False)
def load_watchlist_status(tickers: tuple) -> dict:
    try:
        tables = quotes(tickers, "tradeStatus")
        return {"statuses": {ticker: str(_last(tables.get(ticker, {}), "tradeStatus") or "") for ticker in tickers}}
    except DataFetchError as error:
        return {"statuses": {}, "error": f"个股交易状态暂不可用：{error}"}


@st.cache_data(ttl=60, show_spinner=False)
def load_watchlist_extras(tickers: tuple, day: str, fields: tuple) -> dict:
    result = {ticker: {} for ticker in tickers}
    realtime = set(fields) & {"open", "high", "low", "amplitude", "turnover"}
    if realtime:
        indicators = ["preClose", "open", "high", "low"]
        if "turnover" in fields:
            indicators.append("turnoverRatio")
        try:
            tables = quotes(tickers, ",".join(indicators))
            for ticker in tickers:
                table = tables.get(ticker, {})
                stamp = (table.get("time") or [""])[-1]
                if str(stamp)[:10] != day:
                    result[ticker]["note"] = "补充行情日期不一致"
                    continue
                values = {field: _number(_last(table, field)) for field in ("open", "high", "low", "preClose", "turnoverRatio")}
                result[ticker].update(open=values["open"], high=values["high"], low=values["low"], turnover=values["turnoverRatio"])
                previous = values["preClose"]
                result[ticker]["amplitude"] = ((values["high"] - values["low"]) / previous * 100
                    if previous and values["high"] is not None and values["low"] is not None else None)
        except DataFetchError as error:
            for ticker in tickers:
                result[ticker]["note"] = f"补充行情不可用：{error}"
    if set(fields) & {"return_5", "return_20"}:
        for ticker in tickers:
            try:
                frame = historical(ticker, pd.Timestamp(day) - pd.Timedelta(days=65), day, "CN")
                if frame.attrs.get("stale"):
                    result[ticker]["note"] = "历史行情来自旧缓存"
                    continue
                closes = pd.to_numeric(frame.loc[frame.index.normalize() < pd.Timestamp(day), "Close"], errors="coerce")
                for count in (5, 20):
                    if f"return_{count}" in fields and len(closes) >= count and closes.iloc[-count] > 0:
                        result[ticker][f"base_{count}"] = float(closes.iloc[-count])
            except DataFetchError as error:
                result[ticker]["note"] = f"历史行情不可用：{error}"
    return result


@st.cache_data(ttl=60, show_spinner=False)
def load_watchlist_benchmark(day: str) -> dict:
    try:
        table = quotes(["000300.SH"], "latest,preClose,changeRatio").get("000300.SH", {})
        stamp = (table.get("time") or [""])[-1]
        return {"date": str(stamp)[:10], "change_pct": _number(_last(table, "changeRatio")), "name": "沪深300"}
    except DataFetchError as error:
        return {"date": None, "change_pct": None, "name": "沪深300", "error": str(error)}
