"""Provider adapters and normalized data for the market-overview page."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from curl_cffi import requests
from yfinance.screener.query import EquityQuery

from config.app_config import CN_INDEX_CONFIG, KR_INDEX_CONFIG, US_INDEX_CONFIG
from data_fetcher import DataFetchError, _clear_broken_local_proxy, _create_yahoo_session, _parse_jsonp


EASTMONEY_CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EASTMONEY_TRENDS_URL = "https://push2.eastmoney.com/api/qt/stock/trends2/get"
CHINA_TZ = ZoneInfo("Asia/Shanghai")
US_TZ = ZoneInfo("America/New_York")


def is_us_trading_session() -> bool:
    now = datetime.now(US_TZ)
    return now.weekday() < 5 and now.replace(hour=9, minute=30, second=0, microsecond=0) <= now <= now.replace(hour=16, minute=0, second=0, microsecond=0)


def _ths_daily(symbol: str) -> pd.DataFrame:
    year = datetime.now(CHINA_TZ).year
    session = _create_yahoo_session()
    rows: list[dict] = []
    try:
        for requested_year in (year - 1, year):
            response = session.get(
                f"https://d.10jqka.com.cn/v6/line/hs_{symbol}/01/{requested_year}.js",
                headers={"User-Agent": "Mozilla/5.0", "Referer": f"https://stockpage.10jqka.com.cn/{symbol}/"},
                timeout=20,
            )
            response.raise_for_status()
            for raw in _parse_jsonp(response.text).get("data", "").split(";"):
                values = raw.split(",")
                if len(values) < 6:
                    continue
                rows.append({"Date": values[0], "Open": values[1], "High": values[2], "Low": values[3], "Close": values[4], "Volume": values[5], "Amount": values[6] if len(values) > 6 else None})
    except Exception as error:
        raise DataFetchError("ths_index_daily_failed", "同花顺指数日线数据暂时不可用。", error) from error
    if not rows:
        raise DataFetchError("ths_index_daily_empty", "同花顺未返回指数日线数据。")
    frame = pd.DataFrame(rows)
    frame["Date"] = pd.to_datetime(frame["Date"])
    frame = frame.drop_duplicates("Date").set_index("Date").sort_index()
    for column in ("Open", "High", "Low", "Close", "Volume", "Amount"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["Close"])


def _ths_intraday(symbol: str) -> pd.DataFrame:
    try:
        response = _create_yahoo_session().get(
            f"https://d.10jqka.com.cn/v6/time/hs_{symbol}/last.js",
            headers={"User-Agent": "Mozilla/5.0", "Referer": f"https://stockpage.10jqka.com.cn/{symbol}/"},
            timeout=20,
        )
        response.raise_for_status()
        payload = _parse_jsonp(response.text)
        quote = payload.get(f"hs_{symbol}", payload)
        trade_date, pre_close = str(quote["date"]), float(quote["pre"])
        rows = []
        for raw in quote.get("data", "").split(";"):
            values = raw.split(",")
            if len(values) < 5:
                continue
            rows.append({"DateTime": pd.to_datetime(f"{trade_date}{values[0]}", format="%Y%m%d%H%M"), "Price": float(values[1]), "Amount": float(values[2] or 0), "AvgPrice": float(values[3] or values[1]), "Volume": float(values[4] or 0)})
    except Exception as error:
        raise DataFetchError("ths_index_intraday_failed", "同花顺指数分时数据暂时不可用。", error) from error
    if not rows:
        raise DataFetchError("ths_index_intraday_empty", "同花顺未返回指数分时数据。")
    frame = pd.DataFrame(rows).set_index("DateTime").sort_index()
    frame.attrs.update({"pre_close": pre_close, "trade_date": trade_date, "source": "同花顺公开分时"})
    return frame


def _eastmoney_daily(secid: str) -> pd.DataFrame:
    _clear_broken_local_proxy()
    try:
        response = requests.Session(impersonate="chrome", trust_env=False).get(
            EASTMONEY_KLINE_URL,
            params={"secid": secid, "klt": "101", "fqt": "1", "lmt": "500", "end": "20500101", "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58"},
            timeout=20,
        )
        response.raise_for_status()
        rows = []
        for raw in (response.json().get("data") or {}).get("klines", []):
            values = raw.split(",")
            if len(values) >= 7:
                rows.append({"Date": values[0], "Open": values[1], "Close": values[2], "High": values[3], "Low": values[4], "Volume": values[5], "Amount": values[6]})
    except Exception as error:
        raise DataFetchError("eastmoney_index_daily_failed", "东方财富指数日线数据暂时不可用。", error) from error
    if not rows:
        raise DataFetchError("eastmoney_index_daily_empty", "东方财富未返回指数日线数据。")
    frame = pd.DataFrame(rows).set_index(pd.to_datetime(pd.DataFrame(rows)["Date"])).drop(columns="Date").sort_index()
    for column in frame.columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["Close"])


def _eastmoney_intraday(secid: str) -> pd.DataFrame:
    _clear_broken_local_proxy()
    try:
        response = requests.Session(impersonate="chrome", trust_env=False).get(
            EASTMONEY_TRENDS_URL,
            params={"secid": secid, "ndays": "1", "iscr": "0", "iscca": "0", "fields1": "f1,f2,f3,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f17", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json().get("data") or {}
        rows = []
        for raw in payload.get("trends", []):
            values = raw.split(",")
            if len(values) >= 8:
                rows.append({"DateTime": pd.to_datetime(values[0]), "Price": float(values[2]), "Amount": float(values[6] or 0), "AvgPrice": float(values[7] or values[2]), "Volume": float(values[5] or 0)})
    except Exception as error:
        raise DataFetchError("eastmoney_index_intraday_failed", "东方财富指数分时数据暂时不可用。", error) from error
    if not rows:
        raise DataFetchError("eastmoney_index_intraday_empty", "东方财富未返回指数分时数据。")
    frame = pd.DataFrame(rows).set_index("DateTime").sort_index()
    frame.attrs.update({"pre_close": float(payload.get("preClose") or payload.get("prePrice")), "trade_date": pd.Timestamp(frame.index[-1]).strftime("%Y%m%d"), "source": "东方财富公开分时"})
    return frame


def _amount(value) -> float | None:
    value = pd.to_numeric(value, errors="coerce")
    return float(value) if pd.notna(value) and value >= 0 else None


def fetch_cn_index(index_config: dict) -> dict:
    source = "同花顺公开行情"
    try:
        daily = _ths_daily(index_config["symbol"])
    except DataFetchError:
        if "eastmoney_secid" not in index_config:
            raise
        daily = _eastmoney_daily(index_config["eastmoney_secid"])
        source = "东方财富公开行情"
    intraday = None
    try:
        intraday = _ths_intraday(index_config["symbol"])
    except DataFetchError:
        if "eastmoney_secid" in index_config:
            try:
                intraday = _eastmoney_intraday(index_config["eastmoney_secid"])
                source = "东方财富公开行情"
            except DataFetchError:
                pass
    today = pd.Timestamp.now(tz=CHINA_TZ).tz_localize(None).normalize()
    intraday_is_today = intraday is not None and pd.Timestamp(intraday.attrs["trade_date"]).normalize() == today
    if intraday_is_today and len(intraday):
        completed = daily.loc[daily.index < today]
        previous = completed.iloc[-1] if not completed.empty else daily.iloc[-1]
        price = float(intraday["Price"].iloc[-1])
        previous_close = float(intraday.attrs["pre_close"])
        amount = _amount(intraday["Amount"].sum())
        trade_date = today
    else:
        current, previous = daily.iloc[-1], daily.iloc[-2] if len(daily) > 1 else daily.iloc[-1]
        price, previous_close = float(current["Close"]), float(previous["Close"])
        amount = _amount(current.get("Amount"))
        trade_date = daily.index[-1]
    previous_amount = _amount(previous.get("Amount"))
    amount_change = amount - previous_amount if amount is not None and previous_amount is not None else None
    return {**index_config, "price": price, "previous_close": previous_close, "change": price - previous_close, "change_pct": (price / previous_close - 1) * 100 if previous_close else None, "amount": amount, "previous_amount": previous_amount, "amount_change": amount_change, "amount_change_pct": amount_change / previous_amount * 100 if amount_change is not None and previous_amount else None, "trade_date": pd.Timestamp(trade_date).strftime("%Y-%m-%d"), "source": source, "intraday": intraday}


def _us_history(symbol: str, interval: str, period: str) -> pd.DataFrame:
    try:
        frame = yf.Ticker(symbol, session=_create_yahoo_session()).history(period=period, interval=interval, raise_errors=True)
    except Exception as error:
        raise DataFetchError("yahoo_index_failed", "Yahoo Finance 指数数据暂时不可用。", error) from error
    if frame.empty:
        raise DataFetchError("yahoo_index_empty", "Yahoo Finance 未返回指数数据。")
    frame.index = pd.to_datetime(frame.index)
    return frame


def fetch_us_index(index_config: dict) -> dict:
    daily = _us_history(index_config["symbol"], "1d", "10d")
    intraday = None
    try:
        intraday = _us_history(index_config["symbol"], "5m", "5d")
    except DataFetchError:
        pass
    today = pd.Timestamp.now(tz=US_TZ).date()
    if intraday is not None and not intraday.empty:
        target_session = pd.Timestamp(intraday.index[-1]).date()
        intraday = intraday[pd.Index(intraday.index.date) == target_session].copy()
    use_intraday = intraday is not None and not intraday.empty and pd.Timestamp(intraday.index[-1]).date() == today and is_us_trading_session()
    if use_intraday:
        price = float(intraday["Close"].iloc[-1])
        completed = daily.loc[daily.index.date < today]
        previous_close = float(completed["Close"].iloc[-1] if not completed.empty else daily["Close"].iloc[-1])
        trade_date = today
    else:
        price, previous_close = float(daily["Close"].iloc[-1]), float(daily["Close"].iloc[-2] if len(daily) > 1 else daily["Close"].iloc[-1])
        trade_date = pd.Timestamp(intraday.index[-1]).date() if intraday is not None and not intraday.empty else pd.Timestamp(daily.index[-1]).date()
    return {**index_config, "price": price, "previous_close": previous_close, "change": price - previous_close, "change_pct": (price / previous_close - 1) * 100 if previous_close else None, "amount": None, "previous_amount": None, "amount_change": None, "amount_change_pct": None, "trade_date": str(trade_date), "source": "Yahoo Finance", "intraday": intraday}


def fetch_market_indices(market: str) -> list[dict]:
    configs_by_market = {
        "CN": CN_INDEX_CONFIG,
        "US": US_INDEX_CONFIG,
        "KR": KR_INDEX_CONFIG,
    }
    configs = configs_by_market[market]
    fetcher = fetch_cn_index if market == "CN" else fetch_us_index
    results = []
    for config in configs:
        try:
            results.append(fetcher(config))
        except DataFetchError as error:
            results.append({**config, "error": str(error)})
    return results


def fetch_cn_market_breadth() -> dict:
    _clear_broken_local_proxy()
    session = requests.Session(impersonate="chrome", trust_env=False)
    changes: list[float] = []
    try:
        for fs in ("m:0+t:6,m:0+t:80", "m:1+t:2,m:1+t:23", "m:0+t:81+s:2048"):
            page = 1
            page_size = 100
            while True:
                response = session.get(EASTMONEY_CLIST_URL, params={"pn": page, "pz": page_size, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3", "fs": fs, "fields": "f12,f3"}, headers={"Referer": "https://quote.eastmoney.com/"}, timeout=20)
                response.raise_for_status()
                data = (response.json().get("data") or {})
                rows = data.get("diff") or []
                if isinstance(rows, dict):
                    rows = list(rows.values())
                changes.extend(float(value) for row in rows if (value := pd.to_numeric(row.get("f3"), errors="coerce")) == value)
                if page * page_size >= int(data.get("total", 0)) or not rows:
                    break
                page += 1
    except Exception as error:
        raise DataFetchError("eastmoney_breadth_failed", "东方财富全 A 股涨跌家数暂时不可用。", error) from error
    finally:
        session.close()
    return {"up": sum(value > 0 for value in changes), "down": sum(value < 0 for value in changes), "flat": sum(value == 0 for value in changes), "total": len(changes), "source": "东方财富全 A 股快照"}


def _screen_count(query: EquityQuery) -> int:
    response = yf.screen(query, size=1, session=_create_yahoo_session())
    return int(response.get("total", 0))


def fetch_us_market_breadth() -> dict:
    base = [EquityQuery("eq", ["region", "us"])]
    try:
        # EquityQuery itself makes yfinance submit quoteType=EQUITY.
        total = _screen_count(base[0])
        up = _screen_count(EquityQuery("and", [*base, EquityQuery("gt", ["percentchange", 0])]))
        down = _screen_count(EquityQuery("and", [*base, EquityQuery("lt", ["percentchange", 0])]))
    except Exception as error:
        raise DataFetchError("yahoo_breadth_failed", "Yahoo 美股涨跌家数暂时不可用。", error) from error
    return {"up": up, "down": down, "flat": max(total - up - down, 0), "total": total, "source": "Yahoo 可筛选的美国上市普通股"}


def fetch_market_breadth(market: str) -> dict:
    return fetch_cn_market_breadth() if market == "CN" else fetch_us_market_breadth()
