"""
数据获取模块
使用 yfinance 从 Yahoo Finance 获取股票数据
"""

import yfinance as yf
import pandas as pd
import numpy as np
import os
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

    df = df[REQUIRED_PRICE_COLUMNS].sort_index()
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


def fetch_stock_data(ticker: str, start_date, end_date) -> pd.DataFrame:
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


def get_sp500_tickers() -> list:
    """获取标普500成分股列表（用于扩展功能）"""
    # 这里可以扩展为从维基百科抓取真实数据
    return ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "BRK-B", "JPM", "V"]


def get_stock_info(ticker: str) -> dict:
    """获取股票基本信息"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return {
            'name': info.get('longName', 'N/A'),
            'sector': info.get('sector', 'N/A'),
            'market_cap': info.get('marketCap', 'N/A'),
            'pe_ratio': info.get('trailingPE', 'N/A'),
            'dividend_yield': info.get('dividendYield', 'N/A')
        }
    except:
        return {}
