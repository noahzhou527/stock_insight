"""
数据获取模块
使用 yfinance 从 Yahoo Finance 获取股票数据
"""

import yfinance as yf
import pandas as pd
import numpy as np
import os
import json
import re
from datetime import datetime, timedelta
from functools import lru_cache
from io import StringIO
from pathlib import Path
from curl_cffi import requests
from urllib.parse import urlparse
from yfinance.exceptions import YFRateLimitError, YFTickerMissingError

CACHE_DIR = Path(__file__).resolve().parent / "data" / "cache"
FINANCIAL_CACHE_DIR = CACHE_DIR / "financial_reports"
FINANCIAL_CACHE_TTL = timedelta(hours=12)
FINANCIAL_CACHE_RETENTION = timedelta(days=30)
REQUIRED_PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
DEMO_START_PRICES = {
    "AAPL": 190.0,
    "MSFT": 420.0,
    "TSLA": 180.0,
    "AMZN": 185.0,
    "GOOGL": 170.0,
    "META": 500.0,
    "NVDA": 120.0,
    "BRK-B": 410.0,
    "JPM": 200.0,
    "V": 275.0,
}


class DataFetchError(RuntimeError):
    """A classified failure returned by the external market-data provider."""

    def __init__(self, category: str, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.category = category
        self.cause = cause

    @property
    def diagnostics(self) -> str:
        if self.cause is None:
            return f"category={self.category}"
        return (
            f"category={self.category}\n"
            f"upstream_exception={type(self.cause).__name__}\n"
            f"upstream_message={self.cause}"
        )


def _classify_provider_error(error: Exception) -> DataFetchError:
    """Map yfinance/Yahoo failures to stable, user-actionable categories."""
    message = str(error).lower()

    if isinstance(error, YFRateLimitError) or any(
        phrase in message
        for phrase in ("too many requests", "rate limit", "rate limited", "http 429")
    ):
        return DataFetchError(
            "rate_limit",
            "Yahoo Finance rejected this request because the current IP is rate limited. "
            "Wait and try again, or use a different network.",
            error,
        )

    if isinstance(error, YFTickerMissingError):
        return DataFetchError(
            "ticker_or_data_unavailable",
            "Yahoo Finance has no price data for this ticker and date range.",
            error,
        )

    if any(phrase in message for phrase in ("timeout", "connection", "proxy", "dns", "ssl")):
        return DataFetchError(
            "network_error",
            "The request to Yahoo Finance could not reach the provider. Check the network or proxy and retry.",
            error,
        )

    return DataFetchError(
        "provider_error",
        "Yahoo Finance returned an unexpected error. Open Technical details for the upstream exception.",
        error,
    )


def _clear_broken_local_proxy() -> None:
    """Remove the known broken loopback proxy from this Python process only."""
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        value = os.environ.get(name)
        if not value:
            continue

        parsed = urlparse(value if "://" in value else f"http://{value}")
        if parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == 9:
            os.environ.pop(name, None)


def _create_yahoo_session() -> requests.Session:
    """Use a direct browser-like session after removing the broken local proxy."""
    _clear_broken_local_proxy()
    return requests.Session(impersonate="chrome", trust_env=False)


def _date_key(value) -> str:
    """Convert Streamlit/date/pandas inputs to YYYYMMDD for provider URLs."""
    return pd.Timestamp(value).strftime("%Y%m%d")


def _cache_path(ticker: str) -> Path:
    safe_ticker = "".join(char if char.isalnum() else "_" for char in ticker.upper())
    return CACHE_DIR / f"{safe_ticker}.csv"


def _financial_cache_path(ticker: str) -> Path:
    safe_ticker = "".join(char if char.isalnum() else "_" for char in ticker.upper())
    return FINANCIAL_CACHE_DIR / f"{safe_ticker}.json"


def _prune_financial_cache(now: datetime | None = None) -> None:
    """Remove financial-report cache files that no page has used for 30 days."""
    now = now or datetime.now()
    if not FINANCIAL_CACHE_DIR.exists():
        return
    for path in FINANCIAL_CACHE_DIR.glob("*.json"):
        if datetime.fromtimestamp(path.stat().st_mtime) < now - FINANCIAL_CACHE_RETENTION:
            path.unlink(missing_ok=True)


def _load_financial_cache(ticker: str) -> pd.DataFrame:
    _prune_financial_cache()
    path = _financial_cache_path(ticker)
    if not path.exists() or datetime.fromtimestamp(path.stat().st_mtime) < datetime.now() - FINANCIAL_CACHE_TTL:
        return pd.DataFrame()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = pd.DataFrame(payload["reports"])
        result.attrs.update({"source": "同花顺 F10 本地缓存", "ttm_net_profit": payload.get("ttm_net_profit")})
        return result
    except (OSError, ValueError, KeyError):
        return pd.DataFrame()


def _save_financial_cache(ticker: str, reports: pd.DataFrame) -> None:
    FINANCIAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _prune_financial_cache()
    payload = {"reports": reports.to_dict(orient="records"), "ttm_net_profit": reports.attrs.get("ttm_net_profit")}
    _financial_cache_path(ticker).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _standardize_price_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize provider output for downstream analysis helpers."""
    if df.empty:
        return df

    df = df.copy()
    df.columns = [str(col).capitalize() for col in df.columns]

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
    else:
        df.index = pd.to_datetime(df.index)

    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)

    missing = [col for col in REQUIRED_PRICE_COLUMNS if col not in df.columns]
    if missing:
        raise DataFetchError(
            "provider_schema_changed",
            f"The market-data provider response is missing columns: {', '.join(missing)}.",
        )

    retained_columns = [*REQUIRED_PRICE_COLUMNS]
    if "Amount" in df.columns:
        retained_columns.append("Amount")
    df = df[retained_columns].sort_index()
    for column in REQUIRED_PRICE_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    # Yahoo daily history for some exchanges (notably KRX) omits turnover.
    # Use close × volume as a consistent daily estimate, while preserving every
    # non-null amount supplied by the provider.
    estimated_amount = df["Close"] * df["Volume"]
    if "Amount" in df.columns:
        df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce").fillna(estimated_amount)
    else:
        df["Amount"] = estimated_amount
    return df.dropna(subset=["Open", "High", "Low", "Close"])


def _filter_suspicious_korean_daily_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Drop implausible KRX placeholder rows returned by the historical feed."""
    if df.empty or "Volume" not in df:
        return df
    volume = pd.to_numeric(df["Volume"], errors="coerce")
    nearby_volume = volume.rolling(window=5, center=True, min_periods=2).median()
    suspicious = (nearby_volume >= 1_000_000) & (volume > 0) & (volume < nearby_volume / 1_000)
    if not suspicious.any():
        return df
    result = df.loc[~suspicious].copy()
    result.attrs.update(df.attrs)
    result.attrs["filtered_suspicious_daily_bars"] = int(suspicious.sum())
    return result


def _filter_date_range(df: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    return df[(df.index >= start) & (df.index <= end)]


def _save_local_cache(ticker: str, df: pd.DataFrame) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(_cache_path(ticker), index_label="Date")


def _load_local_cache(ticker: str, start_date, end_date) -> pd.DataFrame:
    path = _cache_path(ticker)
    if not path.exists():
        return pd.DataFrame()

    cached = pd.read_csv(path)
    cached = _standardize_price_frame(cached)
    cached = _filter_date_range(cached, start_date, end_date)
    if not cached.empty:
        cached.attrs["source"] = "local cache"
    return cached


def _generate_demo_data(ticker: str, start_date, end_date) -> pd.DataFrame:
    """Create deterministic OHLCV demo data when every live source is blocked."""
    dates = pd.bdate_range(start=pd.Timestamp(start_date), end=pd.Timestamp(end_date))
    if dates.empty:
        return pd.DataFrame()

    seed = sum(ord(char) for char in ticker)
    rng = np.random.default_rng(seed)
    start_price = DEMO_START_PRICES.get(ticker, 100.0 + (seed % 80))

    returns = rng.normal(loc=0.0004, scale=0.018, size=len(dates))
    close = start_price * np.cumprod(1 + returns)
    open_ = np.r_[start_price, close[:-1]] * (1 + rng.normal(0, 0.004, len(dates)))
    high = np.maximum(open_, close) * (1 + rng.uniform(0.002, 0.018, len(dates)))
    low = np.minimum(open_, close) * (1 - rng.uniform(0.002, 0.018, len(dates)))
    volume = rng.integers(20_000_000, 120_000_000, len(dates))

    df = pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=dates,
    )
    df.attrs["source"] = "demo data"
    return df


def _fetch_from_yahoo(ticker: str, start_date, end_date) -> pd.DataFrame:
    session = _create_yahoo_session()
    df = yf.Ticker(ticker, session=session).history(start=start_date, end=end_date)
    df = _standardize_price_frame(df)
    if not df.empty:
        df.attrs["source"] = "Yahoo Finance"
    return df


def _stooq_symbol(ticker: str) -> str:
    return f"{ticker.replace('-', '.').lower()}.us"


def _fetch_from_stooq(ticker: str, start_date, end_date) -> pd.DataFrame:
    _clear_broken_local_proxy()
    symbol = _stooq_symbol(ticker)
    url = (
        "https://stooq.com/q/d/l/"
        f"?s={symbol}&d1={_date_key(start_date)}&d2={_date_key(end_date)}&i=d"
    )
    session = requests.Session(impersonate="chrome", trust_env=False)
    response = session.get(url, timeout=20)
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text))
    if df.empty or "Date" not in df.columns:
        raise DataFetchError(
            "fallback_data_unavailable",
            "The fallback provider returned no rows for this ticker and date range.",
        )

    df = _standardize_price_frame(df)
    df.attrs["source"] = "Stooq fallback"
    return df


def _parse_jsonp(payload: str) -> dict:
    """Extract the JSON object wrapped by a Tonghuashun JSONP callback."""
    start = payload.find("(")
    end = payload.rfind(")")
    if start < 0 or end <= start:
        raise DataFetchError(
            "ths_schema_changed",
            "同花顺返回了无法识别的行情格式。",
        )
    return json.loads(payload[start + 1:end])


def _fetch_a_share_year(ticker: str, year: int) -> pd.DataFrame:
    """Fetch one year of public daily A-share OHLCV data from Tonghuashun."""
    code = ticker.split(".")[0]
    url = f"https://d.10jqka.com.cn/v6/line/hs_{code}/01/{year}.js"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://stockpage.10jqka.com.cn/{code}/",
    }
    session = _create_yahoo_session()
    response = session.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    payload = _parse_jsonp(response.text)
    rows = []
    for raw_row in payload.get("data", "").split(";"):
        values = raw_row.split(",")
        if len(values) < 7:
            continue
        rows.append(
            {
                "Date": values[0],
                "Open": values[1],
                "High": values[2],
                "Low": values[3],
                "Close": values[4],
                "Volume": values[5],
                "Amount": values[6],
            }
        )
    if not rows:
        return pd.DataFrame()
    return _standardize_price_frame(pd.DataFrame(rows))


def _fetch_a_share_ifind_data(
    ticker: str,
    start_date,
    end_date,
    access_token: str,
) -> pd.DataFrame:
    """Fetch A-share OHLCV through the official authenticated iFinD API."""
    payload = {
        "codes": ticker,
        "indicators": "open,high,low,close,volume",
        "startdate": pd.Timestamp(start_date).strftime("%Y-%m-%d"),
        "enddate": pd.Timestamp(end_date).strftime("%Y-%m-%d"),
        "functionpara": {"CPS": "2", "Fill": "Omit"},
    }
    headers = {
        "Content-Type": "application/json",
        "access_token": access_token,
        "ifindlang": "cn",
    }
    session = _create_yahoo_session()
    response = session.post(
        "https://quantapi.51ifind.com/api/v1/cmd_history_quotation",
        json=payload,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("errorcode", 0) not in (0, "0", None):
        raise DataFetchError(
            "ths_ifind_error",
            result.get("errmsg", "同花顺 iFinD 未返回历史行情。"),
        )

    tables = result.get("tables", {})
    if isinstance(tables, list):
        tables = tables[0] if tables else {}
    table = tables.get("table", tables) if isinstance(tables, dict) else {}
    times = tables.get("time", result.get("time", [])) if isinstance(tables, dict) else []
    if isinstance(times, str):
        times = [item for item in times.split(",") if item]

    normalized = {str(key).lower(): value for key, value in table.items()}
    rows = {"Date": times}
    for source, target in (
        ("open", "Open"),
        ("high", "High"),
        ("low", "Low"),
        ("close", "Close"),
        ("volume", "Volume"),
    ):
        rows[target] = normalized.get(source, [])
    if not times or any(len(rows[column]) != len(times) for column in REQUIRED_PRICE_COLUMNS):
        raise DataFetchError(
            "ths_schema_changed",
            "同花顺 iFinD 历史行情响应缺少必要字段。",
        )
    df = _standardize_price_frame(pd.DataFrame(rows))
    df.attrs["source"] = "同花顺 iFinD"
    return df


def _covers_requested_range(df: pd.DataFrame, start, end) -> bool:
    """Require daily history to reach both ends of the requested period."""
    if df.empty:
        return False
    first = pd.Timestamp(df.index.min()).normalize()
    last = pd.Timestamp(df.index.max()).normalize()
    return first <= pd.Timestamp(start).normalize() + pd.offsets.BDay(5) and last >= pd.Timestamp(end).normalize() - pd.offsets.BDay(5)


def _is_not_listed_error(error: Exception) -> bool:
    return "not listed" in str(error).lower() or "未上市" in str(error)


def fetch_a_share_data(
    ticker: str,
    start_date,
    end_date,
    access_token: str | None = None,
) -> pd.DataFrame:
    """Fetch A-share daily prices from Tonghuashun public market pages."""
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if end < start:
        raise DataFetchError("invalid_date_range", "结束日期不能早于开始日期。")

    if ticker.endswith(".BJ"):
        if not access_token:
            raise DataFetchError(
                "ths_token_required",
                "北交所行情需要配置同花顺 iFinD 的 THS_ACCESS_TOKEN。",
            )
        return _fetch_a_share_ifind_data(ticker, start, end, access_token)

    frames = []
    errors = []
    used_yahoo_fallback = False
    for year in range(start.year, end.year + 1):
        try:
            frame = _fetch_a_share_year(ticker, year)
            if not frame.empty:
                frames.append(frame)
        except Exception as error:
            errors.append(error)

    if not frames:
        cached = _load_local_cache(ticker, start, end)
        if not cached.empty:
            cached.attrs["source"] = "同花顺本地缓存"
            return cached
        if not errors:
            raise DataFetchError(
                "ths_empty_data",
                "同花顺未返回该股票在所选日期范围内的行情。",
            )
        raise DataFetchError(
            "ths_request_failed",
            "无法从同花顺获取该 A 股的历史行情，请稍后重试。",
            errors[0] if errors else None,
        ) from (errors[0] if errors else None)

    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = _filter_date_range(df, start, end)
    if not _covers_requested_range(df, start, end) and not any(_is_not_listed_error(error) for error in errors):
        try:
            yahoo_df = _fetch_from_yahoo(ticker, start, end + pd.Timedelta(days=1))
        except Exception as error:
            raise DataFetchError(
                "incomplete_history",
                "同花顺返回的日线未覆盖所选日期范围，且备用数据源不可用。",
                error,
            ) from error
        if _covers_requested_range(yahoo_df, start, end):
            df = _filter_date_range(yahoo_df, start, end)
            used_yahoo_fallback = True
        else:
            raise DataFetchError(
                "incomplete_history",
                "数据源未返回完整的所选日期范围，请调整日期后重试。",
            )
    if df.empty:
        raise DataFetchError(
            "ths_empty_data",
            "同花顺未返回该股票在所选日期范围内的行情。",
        )
    df.attrs["source"] = "Yahoo Finance" if used_yahoo_fallback else "同花顺"
    _save_local_cache(ticker, df)
    return df


def _last_numeric(value):
    if isinstance(value, dict):
        for nested in reversed(list(value.values())):
            result = _last_numeric(nested)
            if result is not None:
                return result
    elif isinstance(value, list):
        for item in reversed(value):
            result = _last_numeric(item)
            if result is not None:
                return result
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if np.isfinite(number):
            return number
    return None


def _find_latest_indicator_value(value, indicator: str):
    """Find the last numeric value for a named indicator in an iFinD response."""
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() == indicator.lower():
                return _last_numeric(nested)
        for nested in value.values():
            result = _find_latest_indicator_value(nested, indicator)
            if result is not None:
                return result
    elif isinstance(value, list):
        for item in value:
            result = _find_latest_indicator_value(item, indicator)
            if result is not None:
                return result
    return None


def fetch_a_share_pe_ttm(
    ticker: str,
    access_token: str | None,
    end_date=None,
) -> float | None:
    """Fetch latest PE (TTM) through the official Tonghuashun iFinD API."""
    if not access_token:
        return None

    end = pd.Timestamp(end_date or pd.Timestamp.now())
    start = end - pd.Timedelta(days=30)
    indicator = "ths_pe_ttm_stock"
    payload = {
        "codes": ticker,
        "startdate": start.strftime("%Y%m%d"),
        "enddate": end.strftime("%Y%m%d"),
        "functionpara": {"Days": "Tradedays", "Fill": "Previous"},
        "indipara": [{"indicator": indicator, "indiparams": ["100"]}],
    }
    headers = {
        "Content-Type": "application/json",
        "access_token": access_token,
        "ifindlang": "cn",
    }
    session = _create_yahoo_session()
    response = session.post(
        "https://quantapi.51ifind.com/api/v1/date_sequence",
        json=payload,
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("errorcode", 0) not in (0, "0", None):
        raise DataFetchError(
            "ths_ifind_error",
            result.get("errmsg", "同花顺 iFinD 未返回市盈率 TTM。"),
        )
    return _find_latest_indicator_value(result.get("tables", result), indicator)


def fetch_a_share_financial_reports(ticker: str) -> pd.DataFrame:
    """Load the latest available annual and quarterly reports from THS F10."""
    cached = _load_financial_cache(ticker)
    if not cached.empty:
        return cached
    code = ticker.split(".")[0]
    url = f"https://basic.10jqka.com.cn/{code}/finance.html"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://basic.10jqka.com.cn/{code}/",
    }
    session = _create_yahoo_session()
    try:
        response = session.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        html = response.content.decode("gb18030", errors="ignore")
        match = re.search(r'<p\s+id="main">\s*(.*?)\s*</p>', html, flags=re.S)
        if not match:
            raise ValueError("missing main financial payload")
        payload = json.loads(match.group(1))
    except Exception as error:
        raise DataFetchError(
            "ths_financials_failed",
            "无法从同花顺读取该公司的财务报告。",
            error,
        ) from error

    titles = [
        item[0] if isinstance(item, list) else item
        for item in payload.get("title", [])
    ]
    report = payload.get("report", [])
    if len(report) < 2 or not report[0]:
        raise DataFetchError(
            "ths_financials_empty",
            "同花顺暂未提供该公司的财务报告。",
        )

    periods = [str(value) for value in report[0]]
    fields = {}
    for index, title in enumerate(titles[1:], start=1):
        if index < len(report):
            fields[title] = report[index]

    # The F10 payload already orders its report periods from newest to oldest.
    # Keep the history here; the UI separately selects the latest four annual
    # reports and the latest four quarterly reports.
    selected_indices = list(range(len(periods)))

    def value(field, index):
        values = fields.get(field, [])
        if index >= len(values) or values[index] is False:
            return "—"
        return values[index]

    rows = []
    for index in selected_indices:
        period = periods[index]
        month_day = period[5:]
        report_type = {
            "03-31": "一季报",
            "06-30": "中报",
            "09-30": "三季报",
            "12-31": "年报",
        }.get(month_day, "定期报告")
        rows.append(
            {
                "报告期": period,
                "报告类型": report_type,
                "营业总收入": value("营业总收入", index),
                "营收同比": value("营业总收入同比增长率", index),
                "净利润": value("净利润", index),
                "净利润同比": value("净利润同比增长率", index),
                "扣非净利润": value("扣非净利润", index),
                "销售毛利率": value("销售毛利率", index),
                "基本每股收益": value("基本每股收益", index),
                "每股经营现金流": value("每股经营现金流", index),
                "净资产收益率": value("净资产收益率", index),
                "资产负债率": value("资产负债率", index),
            }
        )
    result = pd.DataFrame(rows)
    result.attrs["ttm_net_profit"] = _calculate_ttm_net_profit(
        periods, fields.get("净利润", [])
    )
    result.attrs["source"] = "同花顺 F10"
    _save_financial_cache(ticker, result)
    return result


def _parse_yahoo_financial_timeseries(payload: dict) -> pd.DataFrame:
    metric_labels = {
        "TotalRevenue": "营业总收入",
        "GrossProfit": "毛利润",
        "OperatingIncome": "营业利润",
        "NetIncome": "净利润",
        "BasicEPS": "基本每股收益",
    }
    reports: dict[tuple[str, str], dict] = {}
    for series in payload.get("timeseries", {}).get("result", []):
        types = series.get("meta", {}).get("type", [])
        if not types:
            continue
        series_type = str(types[0])
        report_type = "年报" if series_type.startswith("annual") else "季报"
        metric = metric_labels.get(
            series_type.removeprefix("annual").removeprefix("quarterly")
        )
        if metric is None:
            continue
        for item in series.get(series_type, []):
            period = item.get("asOfDate")
            raw = item.get("reportedValue", {}).get("raw")
            value = pd.to_numeric(raw, errors="coerce")
            if not period or pd.isna(value):
                continue
            report = reports.setdefault(
                (period, report_type), {"报告期": period, "报告类型": report_type}
            )
            report[metric] = float(value)

    result = pd.DataFrame(reports.values())
    if result.empty:
        return result
    columns = ["报告期", "报告类型", *metric_labels.values()]
    return result.reindex(columns=columns).sort_values("报告期", ascending=False).reset_index(drop=True)


def fetch_yahoo_financial_reports(ticker: str) -> pd.DataFrame:
    """Load annual and quarterly income statements for US and Korean equities."""
    metric_types = (
        "annualTotalRevenue,annualGrossProfit,annualOperatingIncome,annualNetIncome,annualBasicEPS,"
        "quarterlyTotalRevenue,quarterlyGrossProfit,quarterlyOperatingIncome,quarterlyNetIncome,quarterlyBasicEPS"
    )
    try:
        response = _create_yahoo_session().get(
            f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{ticker}",
            params={
                "symbol": ticker,
                "type": metric_types,
                "period1": "1577836800",
                "period2": "1924992000",
            },
            timeout=20,
        )
        response.raise_for_status()
        result = _parse_yahoo_financial_timeseries(response.json())
    except Exception as error:
        raise DataFetchError(
            "yahoo_financials_failed",
            "无法从 Yahoo Finance 获取财务报表，请稍后重试。",
            error,
        ) from error

    if result.empty:
        raise DataFetchError(
            "yahoo_financials_empty",
            "Yahoo Finance 暂未提供该股票的年度或季度财务报表。",
        )
    result.attrs["source"] = "Yahoo Finance"
    return result


def fetch_krw_usd_rate() -> float:
    """Return the latest USD value of one Korean won from Yahoo Finance."""
    try:
        response = _create_yahoo_session().get(
            "https://query1.finance.yahoo.com/v8/finance/chart/KRW=X",
            params={"range": "5d", "interval": "1d"},
            timeout=20,
        )
        response.raise_for_status()
        closes = response.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        krw_per_usd = next(
            (float(value) for value in reversed(closes) if value is not None and float(value) > 0),
            None,
        )
    except Exception as error:
        raise DataFetchError(
            "krw_usd_rate_failed",
            "无法获取韩元兑美元汇率，请切回韩元显示后重试。",
            error,
        ) from error

    if krw_per_usd is None:
        raise DataFetchError("krw_usd_rate_empty", "Yahoo Finance 未返回可用的韩元兑美元汇率。")
    return 1 / krw_per_usd


def _decode_ths_page(response) -> str:
    """Decode Tonghuashun pages that still mix GBK and UTF-8 encodings."""
    for encoding in ("gb18030", "utf-8"):
        try:
            text = response.content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "同花顺" in text or "市盈率" in text:
            return text
    return response.content.decode("gb18030", errors="ignore")


def _parse_pe_value(value: str | None) -> float | None:
    if not value:
        return None
    normalized = re.sub(r"<[^>]+>", " ", value)
    normalized = normalized.replace(",", "").strip()
    if any(word in normalized for word in ("亏损", "未公布", "--", "不适用")):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", normalized)
    if not match:
        return None
    number = float(match.group())
    return number if number > 0 and np.isfinite(number) else None


def _parse_market_cap(value: str | None) -> float | None:
    """Convert a Chinese market-cap label such as 13323亿 to yuan."""
    if not value:
        return None
    normalized = re.sub(r"<[^>]+>", " ", value)
    normalized = normalized.replace(",", "").replace(" ", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(万亿|亿|万|元)?", normalized)
    if not match:
        return None
    number = float(match.group(1))
    multiplier = {
        "万亿": 1e12,
        "亿": 1e8,
        "万": 1e4,
        "元": 1.0,
    }.get(match.group(2))
    if multiplier is None:
        return None
    result = number * multiplier
    return result if result > 0 and np.isfinite(result) else None


def _financial_amount_to_yuan(value) -> float | None:
    """Convert an F10 financial amount such as ``281.96亿`` to yuan."""
    if value is False or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if np.isfinite(value) else None

    normalized = re.sub(r"<[^>]+>", " ", str(value))
    normalized = normalized.replace(",", "").replace(" ", "").strip()
    if normalized in {"", "--", "—", "-"}:
        return None
    match = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(万亿|亿|万|元)?", normalized)
    if not match:
        return None
    multiplier = {"万亿": 1e12, "亿": 1e8, "万": 1e4, "元": 1.0, None: 1.0}[match.group(2)]
    amount = float(match.group(1)) * multiplier
    return amount if np.isfinite(amount) else None


def _latest_annual_cash_flow_value(payload: dict, metric: str) -> tuple[str | None, float | None]:
    """Read the newest annual value for one metric from an F10 cash-flow payload."""
    titles = payload.get("title", [])
    annual_rows = payload.get("year", [])
    if not annual_rows:
        return None, None

    periods = annual_rows[0]
    for index, title in enumerate(titles):
        label = title[0] if isinstance(title, list) else title
        if str(label).lstrip("*") != metric or index >= len(annual_rows):
            continue
        values = annual_rows[index]
        if not periods or not values:
            return None, None
        return f"{periods[0]}-12-31", _financial_amount_to_yuan(values[0])
    return None, None


@lru_cache(maxsize=128)
def fetch_a_share_annual_investment_spending(ticker: str) -> tuple[str | None, float | None]:
    """Fetch latest annual capital spending from the public F10 cash-flow table."""
    code = ticker.split(".")[0]
    session = _create_yahoo_session()
    try:
        response = session.get(
            f"https://basic.10jqka.com.cn/api/stock/finance/{code}_cash.json",
            headers={"User-Agent": "Mozilla/5.0", "Referer": f"https://basic.10jqka.com.cn/{code}/finance.html"},
            timeout=20,
        )
        response.raise_for_status()
        outer = response.json()
        payload = outer.get("flashData", {})
        if isinstance(payload, str):
            payload = json.loads(payload)
        return _latest_annual_cash_flow_value(
            payload,
            "购建固定资产、无形资产和其他长期资产支付的现金",
        )
    except Exception as error:
        raise DataFetchError(
            "ths_cash_flow_failed",
            "无法从同花顺读取该公司的现金流量表。",
            error,
        ) from error


def _calculate_ttm_net_profit(periods, net_profit_values) -> float | None:
    """Calculate TTM profit from cumulative F10 reports.

    F10 quarterly net profit is year-to-date.  Therefore TTM is the latest
    annual profit minus the comparable prior-year cumulative profit plus the
    newest cumulative profit.
    """
    if len(periods) != len(net_profit_values):
        return None

    dates = [str(period) for period in periods]
    annual_dates = [date for date in dates if date.endswith("-12-31")]
    if not annual_dates:
        return None
    latest_annual = max(annual_dates)
    latest_year = int(latest_annual[:4])

    current_periods = [
        date for date in dates
        if int(date[:4]) == latest_year + 1 and not date.endswith("-12-31")
    ]
    if not current_periods:
        return None
    current_period = max(current_periods)
    prior_comparable_period = f"{latest_year}-{current_period[5:]}"
    if prior_comparable_period not in dates:
        return None

    values_by_period = {
        date: _financial_amount_to_yuan(net_profit_values[index])
        for index, date in enumerate(dates)
    }
    annual_profit = values_by_period.get(latest_annual)
    current_profit = values_by_period.get(current_period)
    prior_comparable_profit = values_by_period.get(prior_comparable_period)
    if any(value is None for value in (annual_profit, current_profit, prior_comparable_profit)):
        return None
    ttm_profit = annual_profit - prior_comparable_profit + current_profit
    return ttm_profit if np.isfinite(ttm_profit) else None


def fetch_a_share_valuation(ticker: str) -> dict:
    """Fetch public TTM, static, and dynamic PE values from THS F10 pages."""
    code = ticker.split(".")[0]
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://basic.10jqka.com.cn/{code}/",
    }
    session = _create_yahoo_session()
    try:
        desktop_response = session.get(
            f"https://basic.10jqka.com.cn/{code}/",
            headers=headers,
            timeout=20,
        )
        desktop_response.raise_for_status()
        desktop = _decode_ths_page(desktop_response)

        mobile_response = session.get(
            f"https://basic.10jqka.com.cn/mobile/{code}/company.html",
            headers=headers,
            timeout=20,
        )
        mobile_response.raise_for_status()
        mobile = _decode_ths_page(mobile_response)
    except Exception as error:
        raise DataFetchError(
            "ths_valuation_failed",
            "无法从同花顺读取该公司的公开估值数据。",
            error,
        ) from error

    dynamic_match = re.search(
        r'id=["\']dtsyl["\'][^>]*>(.*?)</span>',
        desktop,
        flags=re.S | re.I,
    )
    static_match = re.search(
        r'id=["\']jtsyl["\'][^>]*>(.*?)</span>',
        desktop,
        flags=re.S | re.I,
    )
    market_cap_match = re.search(
        r'id=["\']stockzsz["\'][^>]*>(.*?)</span>',
        desktop,
        flags=re.S | re.I,
    )
    mobile_text = re.sub(r"<[^>]+>", " ", mobile)
    mobile_text = re.sub(r"\s+", " ", mobile_text)
    ttm_match = re.search(
        r"市盈率\s*\(TTM\)\s*[:：]?\s*"
        r"([-+]?\d+(?:\.\d+)?|亏损|未公布|不适用|--)",
        mobile_text,
        flags=re.I,
    )
    if not ttm_match:
        # The mobile F10 site serves two equivalent routes. Occasionally one
        # returns an incomplete shell, so retry the alternate route before
        # treating TTM PE as unavailable.
        try:
            fallback_response = session.get(
                f"https://basic.10jqka.com.cn/mobile/{code}/companyn.html",
                headers=headers,
                timeout=20,
            )
            fallback_response.raise_for_status()
            fallback_text = re.sub(
                r"<[^>]+>", " ", _decode_ths_page(fallback_response)
            )
            fallback_text = re.sub(r"\s+", " ", fallback_text)
            ttm_match = re.search(
                r"市盈率\s*\(TTM\)\s*[:：]?\s*"
                r"([-+]?\d+(?:\.\d+)?|亏损|未公布|不适用|--)",
                fallback_text,
                flags=re.I,
            )
        except Exception:
            pass

    market_cap = _parse_market_cap(
        market_cap_match.group(1) if market_cap_match else None
    )
    pe_ttm = _parse_pe_value(ttm_match.group(1) if ttm_match else None)
    ttm_net_profit = None
    source = "同花顺公开 F10"
    if market_cap:
        try:
            financial_reports = fetch_a_share_financial_reports(ticker)
            ttm_net_profit = financial_reports.attrs.get("ttm_net_profit")
            if ttm_net_profit is not None and ttm_net_profit > 0:
                pe_ttm = market_cap / ttm_net_profit
                source = "同花顺公开 F10（按财报推算 TTM）"
        except DataFetchError:
            pass

    return {
        "pe_ttm": pe_ttm,
        "pe_static": _parse_pe_value(
            static_match.group(1) if static_match else None
        ),
        "pe_dynamic": _parse_pe_value(
            dynamic_match.group(1) if dynamic_match else None
        ),
        "market_cap": market_cap,
        "ttm_net_profit": ttm_net_profit,
        "as_of": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "source": source,
    }


def fetch_us_market_cap(ticker: str) -> float | None:
    """Fetch the latest Yahoo Finance market capitalization for a non-A-share ticker."""
    try:
        response = _create_yahoo_session().get(
            f"https://finance.yahoo.com/quote/{ticker}/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        match = re.search(
            r'data-field=["\']marketCap["\'][^>]*>(.*?)</',
            response.text,
            flags=re.S | re.I,
        )
        if not match:
            return None
        label = re.sub(r"<[^>]+>", "", match.group(1))
        label = label.replace(",", "").strip().upper()
        value_match = re.search(r"(\d+(?:\.\d+)?)\s*([KMBTQ])?", label)
        if not value_match:
            return None
        multiplier = {
            "K": 1e3,
            "M": 1e6,
            "B": 1e9,
            "T": 1e12,
            "Q": 1e15,
        }.get(value_match.group(2), 1.0)
        number = float(value_match.group(1)) * multiplier
    except Exception:
        return None
    return number if number > 0 and np.isfinite(number) else None


def fetch_a_share_intraday(ticker: str) -> pd.DataFrame:
    """Fetch the latest A-share intraday time series from THS public pages."""
    code = ticker.split(".")[0]
    url = f"https://d.10jqka.com.cn/v6/time/hs_{code}/last.js"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://stockpage.10jqka.com.cn/{code}/",
    }
    session = _create_yahoo_session()
    try:
        response = session.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        payload = _parse_jsonp(response.text)
        quote = payload.get(f"hs_{code}", payload)
        trade_date = str(quote["date"])
        pre_close = float(quote["pre"])
        rows = []
        for raw_row in quote.get("data", "").split(";"):
            values = raw_row.split(",")
            if len(values) < 5:
                continue
            rows.append(
                {
                    "DateTime": pd.to_datetime(
                        f"{trade_date}{values[0]}",
                        format="%Y%m%d%H%M",
                    ),
                    "Price": float(values[1]),
                    "Amount": float(values[2] or 0),
                    "AvgPrice": float(values[3] or values[1]),
                    "Volume": float(values[4] or 0),
                }
            )
    except Exception as error:
        raise DataFetchError(
            "ths_intraday_failed",
            "同花顺当日分时数据暂时不可用。",
            error,
        ) from error

    if not rows:
        raise DataFetchError(
            "ths_intraday_empty",
            "同花顺暂未返回该股票的当日分时数据。",
        )
    df = pd.DataFrame(rows).set_index("DateTime").sort_index()
    df["Change"] = df["Price"] - pre_close
    df["ChangePct"] = df["Change"] / pre_close * 100
    df.attrs.update(
        {
            "pre_close": pre_close,
            "trade_date": trade_date,
            "symbol_name": str(quote.get("name", "")).strip(),
            "source": "同花顺公开分时",
        }
    )
    return df


def fetch_yahoo_intraday(ticker: str, market: str = "US") -> pd.DataFrame:
    """Fetch the latest regular-session 5-minute bars for US/KR equities."""
    market = market.upper()
    timezone = {"US": "America/New_York", "KR": "Asia/Seoul"}.get(market)
    if timezone is None:
        raise DataFetchError("unsupported_intraday_market", f"Yahoo intraday is not supported for {market}.")

    session = _create_yahoo_session()
    try:
        instrument = yf.Ticker(ticker, session=session)
        bars = instrument.history(
            period="5d",
            interval="5m",
            prepost=False,
            auto_adjust=False,
        )
        daily = instrument.history(
            period="10d",
            interval="1d",
            prepost=False,
            auto_adjust=False,
        )
    except Exception as error:
        raise _classify_provider_error(error) from error

    if bars is None or bars.empty:
        raise DataFetchError(
            "yahoo_intraday_empty",
            "Yahoo Finance returned no recent intraday data for this ticker.",
        )

    # yfinance can return a MultiIndex even for a single symbol when its
    # session has previously been used for a group request.
    if isinstance(bars.columns, pd.MultiIndex):
        matching_level = next(
            (level for level in range(bars.columns.nlevels) if ticker in bars.columns.get_level_values(level)),
            None,
        )
        bars = bars.xs(ticker, axis=1, level=matching_level, drop_level=True) if matching_level is not None else bars.droplevel(-1, axis=1)
    bars = bars.copy()
    bars.index = pd.to_datetime(bars.index)
    if getattr(bars.index, "tz", None) is not None:
        bars.index = bars.index.tz_convert(timezone).tz_localize(None)
    bars = bars.sort_index().dropna(subset=["Close"])
    if bars.empty:
        raise DataFetchError("yahoo_intraday_empty", "Yahoo Finance returned no usable intraday bars.")

    # A single chart should represent the latest available regular session,
    # including the latest completed day when the market is closed.
    trade_date = bars.index[-1].date()
    bars = bars.loc[bars.index.date == trade_date].copy()
    prices = pd.to_numeric(bars["Close"], errors="coerce")
    raw_volume = bars["Volume"] if "Volume" in bars.columns else pd.Series(0, index=bars.index)
    volumes = pd.to_numeric(raw_volume, errors="coerce").fillna(0)
    amounts = prices * volumes
    cumulative_volume = volumes.cumsum()
    avg_price = amounts.cumsum().div(cumulative_volume.replace(0, np.nan)).fillna(prices)

    previous_close = None
    if daily is not None and not daily.empty and "Close" in daily.columns:
        daily_index = pd.to_datetime(daily.index)
        if getattr(daily_index, "tz", None) is not None:
            daily_index = daily_index.tz_convert(timezone).tz_localize(None)
        daily_close = pd.Series(pd.to_numeric(daily["Close"], errors="coerce").to_numpy(), index=daily_index.date)
        prior = daily_close.loc[daily_close.index < trade_date].dropna()
        if not prior.empty:
            previous_close = float(prior.iloc[-1])
    if previous_close is None or not np.isfinite(previous_close):
        previous_close = float(prices.iloc[0])

    result = pd.DataFrame(
        {
            "Price": prices,
            "Amount": amounts,
            "AvgPrice": avg_price,
            "Volume": volumes,
        },
        index=bars.index,
    )
    result["Change"] = result["Price"] - previous_close
    result["ChangePct"] = result["Change"] / previous_close * 100 if previous_close else 0.0
    result.attrs.update(
        {
            "pre_close": previous_close,
            "trade_date": trade_date.isoformat(),
            "source": "Yahoo Finance 5-minute intraday",
            "market": market,
        }
    )
    return result


def fetch_stock_data(
    ticker: str,
    start_date,
    end_date,
    market: str = "US",
    ths_access_token: str | None = None,
) -> pd.DataFrame:
    """
    从 Yahoo Finance 获取股票历史数据

    Parameters:
        ticker: 股票代码 (如 'AAPL', 'MSFT')
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        DataFrame 包含 OHLCV 数据
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise DataFetchError("invalid_ticker", "Enter a stock ticker before fetching data.")

    if market.upper() == "CN":
        return fetch_a_share_data(
            ticker,
            start_date,
            end_date,
            access_token=ths_access_token,
        )

    try:
        df = _fetch_from_yahoo(ticker, start_date, end_date)
    except Exception as error:
        yahoo_error = _classify_provider_error(error)
    else:
        if df.empty:
            raise DataFetchError(
                "empty_data",
                "Yahoo Finance returned no rows for this ticker and date range.",
            )
        if market.upper() == "KR":
            df = _filter_suspicious_korean_daily_bars(df)
        _save_local_cache(ticker, df)
        return df

    try:
        df = _fetch_from_stooq(ticker, start_date, end_date)
    except Exception as fallback_error:
        cached = _load_local_cache(ticker, start_date, end_date)
        if not cached.empty:
            if market.upper() == "KR":
                cached = _filter_suspicious_korean_daily_bars(cached)
            cached.attrs["fallback_reason"] = yahoo_error.category
            return cached

        demo = _generate_demo_data(ticker, start_date, end_date)
        if not demo.empty:
            demo.attrs["fallback_reason"] = yahoo_error.category
            demo.attrs["fallback_error"] = str(fallback_error)
            return demo

        message = f"{yahoo_error} The fallback provider, local cache, and demo data were also unavailable."
        raise DataFetchError(yahoo_error.category, message, fallback_error) from fallback_error

    if df.empty:
        raise DataFetchError(
            "empty_data",
            "The market-data providers returned no rows for this ticker and date range.",
        )

    _save_local_cache(ticker, df)
    return df
