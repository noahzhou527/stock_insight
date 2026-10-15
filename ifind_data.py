"""Official iFinD HTTP data only; no public-site or demo-data fallback."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import tomllib

import numpy as np
import pandas as pd
from curl_cffi import requests

from data_fetcher import DataFetchError, _calculate_ttm_net_profit

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache" / "ifind"
SOURCE = "同花顺 iFinD"
CACHE_VERSION = 1
API_ROOT = "https://quantapi.51ifind.com/api/v1/"
_LOCK = threading.RLock()
_REQUEST_CACHE = {}
_LAST_REQUEST = 0.0
_TOKEN_CACHE = {}
_LOCAL = threading.local()

# Existing UI symbols are retained; only their provider representation changes.
US_CODES = {
    "AAPL": "AAPL.O", "MSFT": "MSFT.O", "TSLA": "TSLA.O",
    "AMZN": "AMZN.O", "GOOGL": "GOOGL.O", "META": "META.O",
    "NVDA": "NVDA.O", "AVGO": "AVGO.O", "SNDK": "SNDK.O",
    "MU": "MU.O", "BRK-B": "BRK.B.N", "JPM": "JPM.N", "V": "V.N",
    "^DJI": "DJI.GI", "^IXIC": "IXIC.GI", "^NDX": "NDX.GI",
    "^GSPC": "SPX.GI", "^KS11": "KS11.GI",
    "1A0001": "000001.SH", "1B0680": "000680.SH",
    "899050": "899050.BJ", "399001": "399001.SZ", "399006": "399006.SZ",
}


def _setting(name):
    value = os.getenv(name)
    if value:
        return value
    path = ROOT / ".streamlit" / "secrets.toml"
    if path.exists():
        try:
            return tomllib.loads(path.read_text(encoding="utf-8-sig")).get(name)
        except (OSError, tomllib.TOMLDecodeError):
            raise DataFetchError("ifind_config", "iFinD 本地凭证配置格式无效。") from None
    return None


def _session():
    if not hasattr(_LOCAL, "session"):
        _LOCAL.session = requests.Session(trust_env=False)
    return _LOCAL.session


def _post(endpoint, payload, headers):
    global _LAST_REQUEST
    # A single paced request gate also bounds the existing six financial workers.
    with _LOCK:
        time.sleep(max(0, 0.16 - (time.monotonic() - _LAST_REQUEST)))
        _LAST_REQUEST = time.monotonic()
        try:
            response = _session().post(
                API_ROOT + endpoint, json=payload,
                headers={"Content-Type": "application/json", "ifindlang": "cn", **headers},
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
        except Exception:
            # Never attach request headers, credential values or raw responses to errors.
            raise DataFetchError("ifind_network", f"iFinD {endpoint} 请求失败，请检查网络后重试。") from None
    if not isinstance(result, dict) or "errorcode" not in result:
        raise DataFetchError("ifind_schema", "iFinD 响应缺少错误状态。")
    code = result["errorcode"]
    if code not in (0, "0"):
        message = str(result.get("errmsg") or "未返回数据")
        for value in headers.values():
            if value:
                message = message.replace(str(value), "[hidden]")
        lower = message.lower()
        category = "ifind_permission" if "permission" in lower else "ifind_error"
        if "token" in lower and any(word in lower for word in ["invalid", "expire", "fail"]):
            category = "ifind_auth"
        raise DataFetchError(category, f"iFinD 返回 {code}：{message}")
    return result


def access_token():
    refresh = _setting("THS_REFRESH_TOKEN")
    if refresh:
        fingerprint = hashlib.sha256(refresh.encode()).hexdigest()
        with _LOCK:
            cached = _TOKEN_CACHE.get(fingerprint)
            if cached and time.monotonic() - cached[0] < 3600:
                return cached[1]
            result = _post("get_access_token", {}, {"refresh_token": refresh})
            token = (result.get("data") or {}).get("access_token")
            if not token:
                raise DataFetchError("ifind_auth", "iFinD 未返回有效的 Access Token。")
            _TOKEN_CACHE.clear()
            _TOKEN_CACHE[fingerprint] = (time.monotonic(), token)
            return token
    token = _setting("THS_ACCESS_TOKEN")
    if not token:
        raise DataFetchError("ifind_auth", "请在本地配置 THS_ACCESS_TOKEN 或 THS_REFRESH_TOKEN。")
    return token


def request(endpoint, payload, ttl=25):
    token = access_token()
    key = (endpoint, json.dumps(payload, sort_keys=True), hashlib.sha256(token.encode()).hexdigest())
    with _LOCK:
        cached = _REQUEST_CACHE.get(key)
        if cached and time.monotonic() - cached[0] < ttl:
            if isinstance(cached[1], DataFetchError):
                raise cached[1]
            return deepcopy(cached[1])
        try:
            result = _post(endpoint, payload, {"access_token": token})
        except DataFetchError as error:
            if error.category == "ifind_auth" and _setting("THS_REFRESH_TOKEN"):
                _TOKEN_CACHE.clear()
                result = _post(endpoint, payload, {"access_token": access_token()})
                _REQUEST_CACHE.clear()
                return result
            if error.category == "ifind_permission":
                _REQUEST_CACHE[key] = (time.monotonic(), error)
            raise
        if len(_REQUEST_CACHE) >= 512:
            _REQUEST_CACHE.clear()
        _REQUEST_CACHE[key] = (time.monotonic(), result)
        return deepcopy(result)


def code_for(ticker, market="CN"):
    overrides = _setting("IFIND_CODES") or {}
    if ticker in overrides:
        return str(overrides[ticker])
    if ticker in US_CODES:
        return US_CODES[ticker]
    if market == "US" and "." not in ticker:
        raise DataFetchError("ifind_symbol", "自定义美股请填写 iFinD 完整代码（例如 AAPL.O），或配置 IFIND_CODES。")
    if market == "KR" and ticker.endswith(".KS"):
        raise DataFetchError("ifind_symbol", "韩股 iFinD 证券代码尚未确认，请在 IFIND_CODES 中配置官方代码；不会使用 Yahoo 代码替代。")
    if not re.fullmatch(r"[A-Za-z0-9.^_-]+", ticker):
        raise DataFetchError("ifind_symbol", "证券代码格式无效。")
    return ticker


def _tables(result):
    tables = result.get("tables")
    if isinstance(tables, dict):
        return [tables]
    if not isinstance(tables, list):
        raise DataFetchError("ifind_schema", "iFinD 响应缺少 tables。")
    return tables


def _table_frame(table):
    times = table.get("time", [])
    if isinstance(times, str):
        times = times.split(",")
    if not times:
        return pd.DataFrame()
    rows = {}
    for key, values in (table.get("table") or {}).items():
        if values is None:
            values = [None] * len(times)
        elif not isinstance(values, list):
            values = [values]
        if len(values) != len(times):
            raise DataFetchError("ifind_schema", f"iFinD 字段 {key} 与时间序列长度不一致。")
        rows[key.lower()] = values
    frame = pd.DataFrame(rows, index=pd.to_datetime(times, errors="coerce"))
    if frame.index.isna().any():
        raise DataFetchError("ifind_schema", "iFinD 返回无效时间戳。")
    frame.index.name = "Date"
    return frame.sort_index()


def _last(table, field):
    value = (table.get("table") or {}).get(field)
    return value[-1] if isinstance(value, list) and value else value


def _number(value):
    value = pd.to_numeric(value, errors="coerce")
    return float(value) if pd.notna(value) and np.isfinite(value) else None


def _cache_path(kind, code):
    return CACHE_DIR / kind / (re.sub(r"[^A-Za-z0-9._-]", "_", code) + ".json")


def _read_frame(path):
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
        if content.get("source") != SOURCE or content.get("version") != CACHE_VERSION:
            return pd.DataFrame(), {}
        frame = pd.DataFrame(content["rows"])
        if "Date" in frame:
            frame = frame.set_index("Date")
            frame.index = pd.to_datetime(frame.index)
        else:
            frame = frame.drop(columns=["index"], errors="ignore")
        frame.attrs.update(content.get("attrs", {}))
        return frame, content
    except (OSError, ValueError, KeyError, TypeError):
        return pd.DataFrame(), {}


def _write_frame(path, frame, **metadata):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = json.loads(frame.reset_index().to_json(orient="records", date_format="iso"))
    content = {"source": SOURCE, "version": CACHE_VERSION, "saved_at": time.time(), "rows": rows, "attrs": frame.attrs, **metadata}
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        json.dump(content, file, ensure_ascii=False, allow_nan=False)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def historical(ticker, start, end, market="CN", ths_access_token=None):
    code = code_for(ticker, market)
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if end < start:
        raise DataFetchError("invalid_date_range", "结束日期不能早于开始日期。")
    path = _cache_path("daily", code)
    cached, meta = _read_frame(path)
    covers = bool(meta) and pd.Timestamp(meta["requested_start"]) <= start and pd.Timestamp(meta["requested_end"]) >= end
    if covers and time.time() - meta.get("saved_at", 0) < 300:
        return cached.loc[start:end].copy()
    fetch_start = start
    if not cached.empty and pd.Timestamp(meta["requested_start"]) <= start:
        fetch_start = min(end, max(start, cached.index.max() - pd.Timedelta(days=3)))
    chunks = []
    try:
        for year in range(fetch_start.year, end.year + 1):
            left, right = max(fetch_start, pd.Timestamp(year, 1, 1)), min(end, pd.Timestamp(year, 12, 31))
            result = request("cmd_history_quotation", {
                "codes": code, "indicators": "open,high,low,close,volume,amount",
                "startdate": str(left.date()), "enddate": str(right.date()),
                "functionpara": {"CPS": "1", "Fill": "Omit", "Currency": "YSHB"},
            }, ttl=300)
            for table in _tables(result):
                if table.get("thscode") == code:
                    frame = _table_frame(table)
                    if not frame.empty:
                        chunks.append(frame)
    except DataFetchError:
        if covers and not cached.empty:
            result = cached.loc[start:end].copy()
            result.attrs.update(source=SOURCE + " · 旧缓存", stale=True)
            return result
        raise
    if chunks:
        frame = pd.concat(chunks).rename(columns={k: k.title() for k in ["open", "high", "low", "close", "volume", "amount"]})
        for field in ["Open", "High", "Low", "Close", "Volume", "Amount"]:
            if field not in frame:
                raise DataFetchError("ifind_schema", f"iFinD 历史行情缺少 {field}。")
            frame[field] = pd.to_numeric(frame[field], errors="coerce")
        frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
        frame = pd.concat([cached, frame]) if not cached.empty else frame
        frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    else:
        frame = cached
    if frame.empty or frame.loc[start:end].empty:
        raise DataFetchError("ifind_empty", f"iFinD 未返回 {code} 在所选日期内的行情；请确认代码和账号权限。")
    frame.attrs.update(source=SOURCE, ifind_code=code, stale=False, price_adjustment="不复权")
    _write_frame(path, frame, requested_start=str(min(start, pd.Timestamp(meta.get("requested_start", start))).date()), requested_end=str(max(end, pd.Timestamp(meta.get("requested_end", end))).date()))
    return frame.loc[start:end].copy()


def quotes(codes, indicators="latest,preClose,changeRatio,amount,totalCapital,pe_ttm,tradeDate,tradeTime"):
    tables = {}
    codes = list(dict.fromkeys(codes))
    for offset in range(0, len(codes), 100):
        result = request("real_time_quotation", {"codes": ",".join(codes[offset:offset + 100]), "indicators": indicators})
        for table in _tables(result):
            tables[table.get("thscode")] = table
    return tables


def intraday(ticker, market="CN"):
    code = code_for(ticker, market)
    quote = quotes([code], "latest,preClose,tradeDate,tradeTime").get(code)
    if not quote:
        raise DataFetchError("ifind_empty", f"iFinD 未返回 {code} 实时行情。")
    quote_times = quote.get("time") or []
    trade_date = str(_last(quote, "tradeDate") or (quote_times[-1][:10] if quote_times else ""))
    try:
        day = pd.Timestamp(trade_date).normalize()
    except (ValueError, TypeError):
        raise DataFetchError("ifind_schema", "iFinD 未返回有效交易日期。") from None
    result = request("high_frequency", {
        "codes": code, "indicators": "close,volume,amount",
        "starttime": f"{day.date()} 00:00:00", "endtime": f"{day.date()} 23:59:59",
        "functionpara": {"Interval": "1", "CPS": "no", "Timeformat": "LocalTime", "Fill": "Original"},
    })
    tables = [t for t in _tables(result) if t.get("thscode") == code]
    frame = _table_frame(tables[0]) if tables else pd.DataFrame()
    if frame.empty or any(c not in frame for c in ["close", "volume", "amount"]):
        raise DataFetchError("ifind_empty", f"iFinD 未返回 {code} 的分钟行情。")
    frame = frame.rename(columns={"close": "Price", "volume": "Volume", "amount": "Amount"}).apply(pd.to_numeric, errors="coerce")
    frame = frame.loc[frame.index.normalize() == day].dropna(subset=["Price"])
    if market == "CN":
        clock = frame.index.strftime("%H:%M")
        frame = frame.loc[((clock >= "09:30") & (clock <= "11:30")) | ((clock >= "13:00") & (clock <= "15:00"))]
    if frame.empty:
        raise DataFetchError("ifind_empty", "iFinD 未返回交易时段内的分钟行情。")
    frame["AvgPrice"] = frame["Amount"].cumsum().div(frame["Volume"].cumsum().replace(0, np.nan))
    frame.attrs.update(source=SOURCE, trade_date=str(day.date()), pre_close=_number(_last(quote, "preClose")))
    if market == "CN":
        try:
            name_table = _basic(code, [("ths_stock_short_name_stock", [])])
            name = _last(name_table, "ths_stock_short_name_stock")
            if name:
                frame.attrs["symbol_name"] = name
        except DataFetchError:
            pass
    if frame.attrs["pre_close"] is None:
        raise DataFetchError("ifind_schema", "iFinD 分时行情缺少前收盘价。")
    return frame


def calendar(start, end, market="CN"):
    result = request("get_trade_dates", {
        "marketcode": {"CN": "212001", "US": "212010", "KR": "212027"}[market],
        "functionpara": {"mode": "1", "dateType": "0", "period": "D", "dateFormat": "0"},
        "startdate": str(pd.Timestamp(start).date()), "enddate": str(pd.Timestamp(end).date()),
    }, ttl=3600)
    dates = pd.DatetimeIndex(pd.to_datetime(_tables(result)[0].get("time", [])))
    if dates.empty:
        raise DataFetchError("ifind_calendar", "iFinD 未返回交易日历。")
    return dates


def _basic(code, indicators):
    result = request("basic_data_service", {"codes": code, "indipara": [
        {"indicator": indicator, "indiparams": params} for indicator, params in indicators
    ]}, ttl=300)
    tables = _tables(result)
    return tables[0] if tables else {}


def valuation(ticker):
    code = code_for(ticker)
    table = quotes([code]).get(code)
    if not table:
        raise DataFetchError("ifind_empty", "iFinD 未返回估值行情。")
    times = table.get("time") or []
    as_of = times[-1] if times else ""
    date = as_of[:10].replace("-", "")
    extra = _basic(code, [("ths_pe_lyr_stock", [date, "100"])])
    reports = financial_reports(ticker)
    latest = reports.iloc[0]
    profit = _number(latest["净利润"])
    capital = _number(_last(table, "totalCapital"))
    report_month = pd.Timestamp(latest["报告期"]).month
    annualized = profit * 12 / report_month if profit is not None else None
    return {"pe_ttm": _number(_last(table, "pe_ttm")), "pe_static": _number(_last(extra, "ths_pe_lyr_stock")),
            "pe_dynamic": capital / annualized if capital and annualized and annualized > 0 else None, "market_cap": capital,
            "ttm_net_profit": reports.attrs.get("ttm_net_profit"), "as_of": as_of,
            "source": SOURCE + "（动态 PE 按最新累计归母净利润年化计算）"}


def market_cap(ticker):
    code = code_for(ticker, "US")
    table = quotes([code], "totalCapital").get(code)
    return _number(_last(table or {}, "totalCapital"))


FINANCIAL_INDICATORS = [
    ("ths_revenue_stock", ["", "100"]), ("ths_np_atoopc_stock", ["", "100"]),
    ("ths_basic_eps_stock", [""]), ("ths_roe_stock", [""]),
    ("ths_total_assets_stock", ["", "100"]), ("ths_total_liab_stock", ["", "100"]),
    ("ths_ncf_from_oa_stock", ["", "100"]), ("ths_regular_report_actual_dd_stock", [""]),
    ("ths_operating_cost_stock", ["", "100"]), ("ths_total_shares_stock", [""]),
]


def financial_reports(ticker, market="CN"):
    code = code_for(ticker, market)
    if market != "CN":
        raise DataFetchError("ifind_financials", "海外财报的 iFinD 指标和报告币种尚未确认；本版本不使用网页数据替代。")
    path = _cache_path("financial", code)
    cached, meta = _read_frame(path)
    if not cached.empty and time.time() - meta.get("saved_at", 0) < 21600:
        return cached
    today = pd.Timestamp.now(tz="Asia/Shanghai").tz_localize(None).normalize()
    result = request("date_sequence", {
        "codes": code, "startdate": f"{today.year - 6}0101", "enddate": today.strftime("%Y%m%d"),
        "functionpara": {"Days": "Alldays", "Fill": "Blank", "Interval": "Q"},
        "indipara": [{"indicator": field, "indiparams": params} for field, params in FINANCIAL_INDICATORS],
    }, ttl=21600)
    tables = _tables(result)
    frame = _table_frame(tables[0]) if tables else pd.DataFrame()
    required = [field for field, _ in FINANCIAL_INDICATORS]
    if frame.empty or any(field not in frame for field in required):
        raise DataFetchError("ifind_financials", "iFinD 财务字段缺失，请确认基础数据权限。")
    disclosure = pd.to_datetime(frame["ths_regular_report_actual_dd_stock"].astype("string").str.replace(r"\.0$", "", regex=True), format="%Y%m%d", errors="coerce")
    frame = frame.loc[(frame.index <= today) & disclosure.notna() & (disclosure <= today)].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=["ths_revenue_stock", "ths_np_atoopc_stock"], how="all")
    if frame.empty:
        raise DataFetchError("ifind_financials", "iFinD 暂无已披露的财务报告。")
    rows = []
    for date, report in frame.iterrows():
        previous = frame.loc[frame.index == date - pd.DateOffset(years=1)]
        def growth(field):
            if previous.empty:
                return None
            base, value = _number(previous.iloc[0][field]), _number(report[field])
            return (value - base) / abs(base) * 100 if base and value is not None else None
        assets, liabilities = _number(report["ths_total_assets_stock"]), _number(report["ths_total_liab_stock"])
        rows.append({"报告期": str(date.date()), "报告类型": {3: "一季报", 6: "中报", 9: "三季报", 12: "年报"}[date.month],
                     "营业总收入": _number(report["ths_revenue_stock"]), "营收同比": growth("ths_revenue_stock"),
                     "净利润": _number(report["ths_np_atoopc_stock"]), "净利润同比": growth("ths_np_atoopc_stock"),
                     "基本每股收益": _number(report["ths_basic_eps_stock"]), "净资产收益率": _number(report["ths_roe_stock"]),
                     "资产负债率": liabilities / assets * 100 if assets and liabilities is not None else None,
                     "扣非净利润": None,
                     "销售毛利率": (report["ths_revenue_stock"] - report["ths_operating_cost_stock"]) / report["ths_revenue_stock"] * 100 if report["ths_revenue_stock"] else None,
                     "每股经营现金流": report["ths_ncf_from_oa_stock"] / report["ths_total_shares_stock"] if report["ths_total_shares_stock"] else None})
    reports = pd.DataFrame(rows).sort_values("报告期", ascending=False).reset_index(drop=True)
    reports.attrs.update(source=SOURCE, ttm_net_profit=_calculate_ttm_net_profit(reports["报告期"].tolist(), reports["净利润"].tolist()),
                         unavailable_fields=["扣非净利润"],
                         financial_basis="净利润为归母净利润；营业总收入栏使用营业收入；季报为累计口径；毛利率、资产负债率、每股经营现金流由接口字段计算")
    _write_frame(path, reports)
    return reports


def investment_spending(ticker):
    raise DataFetchError("ifind_indicator", "投资支出的 iFinD 指标尚未核实。")


def krw_usd_rate():
    raise DataFetchError("ifind_fx", "韩元兑美元的 iFinD 指标尚未核实，请使用韩元展示。")


def snapshot(rows):
    # Keep original snapshot close-normalized valuation semantics.
    codes = [row["ticker"] for row in rows]
    tables = quotes(codes)
    result = []
    now = pd.Timestamp.now(tz="Asia/Shanghai")
    names = {}
    for offset in range(0, len(codes), 100):
        try:
            names_result = request("basic_data_service", {"codes": ",".join(codes[offset:offset + 100]), "indipara": [{"indicator": "ths_stock_short_name_stock", "indiparams": []}]}, ttl=86400)
            names.update({t.get("thscode"): _last(t, "ths_stock_short_name_stock") for t in _tables(names_result)})
        except DataFetchError:
            # Missing name permission must not discard successful market quotes.
            pass
    for row in rows:
        table = tables.get(row["ticker"], {})
        times = table.get("time") or []
        stamp = times[-1] if times else None
        price, previous = _number(_last(table, "latest")), _number(_last(table, "preClose"))
        cap, pe = _number(_last(table, "totalCapital")), _number(_last(table, "pe_ttm"))
        trade_date = stamp[:10] if stamp else None
        before_close = trade_date == str(now.date()) and now.strftime("%H:%M") < "15:00"
        if before_close and price and previous:
            cap = cap * previous / price if cap is not None else None
            pe = pe * previous / price if pe is not None else None
        result.append({**row, "name": names.get(row["ticker"]) or row.get("name", ""), "price": price,
                       "previous_close": previous, "change_pct": _number(_last(table, "changeRatio")),
                       "amount": _number(_last(table, "amount")), "market_cap": cap, "pe_ttm": pe,
                       "quote_time": stamp, "trade_date": trade_date, "stale": price is None})
    frame = pd.DataFrame(result)
    frame.attrs.update(source=SOURCE, live_count=sum(not r["stale"] for r in result), stale_count=sum(r["stale"] for r in result))
    return frame


def market_breadth(market="CN"):
    if market != "CN":
        raise DataFetchError("ifind_breadth", "海外全市场涨跌家数接口尚未核实。")
    path = _cache_path("breadth", "CN")
    cached, meta = _read_frame(path)
    if not cached.empty and time.time() - meta.get("saved_at", 0) < 300:
        return cached.iloc[0].drop(labels=["index"], errors="ignore").to_dict()
    today = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y%m%d")
    universe_path = _cache_path("universe", "CN")
    universe_frame, universe_meta = _read_frame(universe_path)
    codes = universe_frame.get("code", pd.Series(dtype=str)).tolist() if universe_meta.get("date") == today else []
    if not codes or any(not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", str(code)) for code in codes):
        universe = request("data_pool", {"reportname": "p03425", "functionpara": {"date": today, "blockname": "001005010", "iv_type": "allcontract"},
                                          "outputpara": "p03291_f001,p03291_f002,p03291_f003,p03291_f004"}, ttl=86400)
        table = _tables(universe)[0].get("table", {})
        codes = table.get("p03291_f002", [])
    if not codes or any(not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", str(code)) for code in codes):
        raise DataFetchError("ifind_schema", "iFinD 全 A 股证券列表字段未匹配。")
    if universe_meta.get("date") != today or universe_frame.get("code", pd.Series(dtype=str)).tolist() != codes:
        _write_frame(universe_path, pd.DataFrame({"code": codes}), date=today)
    quote_tables = quotes(codes, "latest,preClose,tradeDate")
    changes = []
    for quote in quote_tables.values():
        latest, previous = _number(_last(quote, "latest")), _number(_last(quote, "preClose"))
        if latest is not None and previous and latest > 0:
            changes.append(latest - previous)
    if not changes:
        raise DataFetchError("ifind_breadth", "iFinD 未返回可统计的全 A 股行情。")
    result = {"up": sum(x > 0 for x in changes), "down": sum(x < 0 for x in changes), "flat": sum(x == 0 for x in changes),
              "total": len(changes), "source": f"{SOURCE} 全 A 股；有效报价 {len(changes)}/{len(codes)}，无有效报价或停牌零价未计入"}
    _write_frame(path, pd.DataFrame([result]))
    return result
