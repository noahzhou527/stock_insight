"""Market overview backed exclusively by the official iFinD HTTP API."""
from __future__ import annotations
import pandas as pd
from app_config import CN_INDEX_CONFIG, US_INDEX_CONFIG, KR_INDEX_CONFIG
from data_fetcher import DataFetchError
from ifind_data import SOURCE, historical, intraday, market_breadth, quotes, code_for, _last, _number


def _index(config, market):
    today = pd.Timestamp.now().normalize()
    daily = historical(config["symbol"], today - pd.Timedelta(days=30), today, market)
    current = daily.iloc[-1]
    previous = daily.iloc[-2] if len(daily) > 1 else current
    price, previous_close = float(current["Close"]), float(previous["Close"])
    trade_date = daily.index[-1]
    amount, previous_amount = _number(current.get("Amount")), _number(previous.get("Amount"))
    minute = None
    source = daily.attrs.get("source", SOURCE)
    realtime_note = None
    try:
        code = code_for(config["symbol"], market)
        table = quotes([code], "latest,preClose,amount,riseCount,fallCount").get(code)
        if table and _number(_last(table, "latest")) is not None and _number(_last(table, "preClose")):
            price, previous_close = _number(_last(table, "latest")), _number(_last(table, "preClose"))
            timestamp = (table.get("time") or [None])[-1]
            if timestamp:
                trade_date = pd.Timestamp(timestamp).normalize()
                completed = daily.loc[daily.index < trade_date]
                previous_amount = _number(completed.iloc[-1].get("Amount")) if not completed.empty else None
            amount = _number(_last(table, "amount"))
        # Basket turnover/volume is a share price, not an index level or index VWAP.
        minute = intraday(config["symbol"], market).drop(columns=["AvgPrice"], errors="ignore")
    except DataFetchError as error:
        realtime_note = str(error)
        source += " · 日线（实时/分钟不可用）"
    if not previous_close:
        raise DataFetchError("ifind_schema", "iFinD 指数缺少有效前收盘价。")
    delta = amount - previous_amount if amount is not None and previous_amount is not None else None
    return {**config, "price": price, "previous_close": previous_close, "change": price - previous_close,
            "change_pct": (price / previous_close - 1) * 100, "amount": amount, "previous_amount": previous_amount,
            "amount_change": delta, "amount_change_pct": delta / previous_amount * 100 if delta is not None and previous_amount else None,
            "trade_date": str(pd.Timestamp(trade_date).date()), "source": source, "intraday": minute,
            "realtime_note": realtime_note}


def fetch_cn_index(index_config):
    return _index(index_config, "CN")


def fetch_us_index(index_config):
    return _index(index_config, "US")


def fetch_market_indices(market):
    results = []
    for config in {"CN": CN_INDEX_CONFIG, "US": US_INDEX_CONFIG, "KR": KR_INDEX_CONFIG}[market]:
        try:
            results.append(_index(config, market))
        except DataFetchError as error:
            results.append({**config, "error": str(error)})
    return results


def fetch_cn_market_breadth():
    return market_breadth("CN")


def fetch_us_market_breadth():
    return market_breadth("US")


def fetch_market_breadth(market):
    return market_breadth(market)
