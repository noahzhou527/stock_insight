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
from io import StringIO
from pathlib import Path
from curl_cffi import requests
from urllib.parse import urlparse
from yfinance.exceptions import YFRateLimitError, YFTickerMissingError

CACHE_DIR = Path(__file__).resolve().parent / "data" / "cache"
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
    if "Amount" in df.columns:
        df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    return df.dropna(subset=["Open", "High", "Low", "Close"])


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
    try:
        for year in range(start.year, end.year + 1):
            frame = _fetch_a_share_year(ticker, year)
            if not frame.empty:
                frames.append(frame)
    except Exception as error:
        cached = _load_local_cache(ticker, start, end)
        if not cached.empty:
            cached.attrs["source"] = "同花顺本地缓存"
            return cached
        raise DataFetchError(
            "ths_request_failed",
            "无法从同花顺获取该 A 股的历史行情，请稍后重试。",
            error,
        ) from error

    if not frames:
        raise DataFetchError(
            "ths_empty_data",
            "同花顺未返回该股票在所选日期范围内的行情。",
        )

    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = _filter_date_range(df, start, end)
    if df.empty:
        raise DataFetchError(
            "ths_empty_data",
            "同花顺未返回该股票在所选日期范围内的行情。",
        )
    df.attrs["source"] = "同花顺"
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
    """Load the latest annual report and current fiscal-year quarters from THS F10."""
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

    annual_indices = [
        index for index, period in enumerate(periods)
        if period.endswith("-12-31")
    ]
    latest_annual_index = annual_indices[0] if annual_indices else None
    latest_year = max(int(period[:4]) for period in periods)
    quarter_indices = [
        index for index, period in enumerate(periods)
        if int(period[:4]) == latest_year and not period.endswith("-12-31")
    ]
    selected_indices = (
        ([latest_annual_index] if latest_annual_index is not None else [])
        + list(reversed(quarter_indices))
    )

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
    result.attrs["source"] = "同花顺 F10"
    return result


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

    return {
        "pe_ttm": _parse_pe_value(ttm_match.group(1) if ttm_match else None),
        "pe_static": _parse_pe_value(
            static_match.group(1) if static_match else None
        ),
        "pe_dynamic": _parse_pe_value(
            dynamic_match.group(1) if dynamic_match else None
        ),
        "market_cap": _parse_market_cap(
            market_cap_match.group(1) if market_cap_match else None
        ),
        "as_of": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "source": "同花顺公开 F10",
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
            "source": "同花顺公开分时",
        }
    )
    return df


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
        _save_local_cache(ticker, df)
        return df

    try:
        df = _fetch_from_stooq(ticker, start_date, end_date)
    except Exception as fallback_error:
        cached = _load_local_cache(ticker, start_date, end_date)
        if not cached.empty:
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
